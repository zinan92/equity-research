"""Sequential, official-PDF financial-history batch for the E4 audit cohort.

This module deliberately treats collection and extraction as separate facts.
CNINFO is used only to discover and download issuer filings; every numeric
output is then extracted from the captured PDF with page identity.  A missing
document, a parse gap, or an uncertain table row is retained in the runtime
receipt instead of being filled by a vendor field.
"""
from __future__ import annotations

import hashlib
import json
import signal
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .ashare import MemoryAuthoritySink
from .contracts import digest
from .e4_catl_financial_history import OfficialReport, _missing_metric_records, extract_report_facts
from .official_filings import OfficialFilingBatch, OfficialHttpTransport, sync_exchange_filings


# The original 20-ticker receipt is runtime-only by design.  This is its
# replayable replacement cohort: it retains the three independently published
# #479 samples, SH/SZ/BJ coverage, and the same broad industry mix.  It is an
# issuer-selection input, never a source of financial facts.
E4_AUDIT_COHORT_V2 = (
    "000001.SZ", "000002.SZ", "000012.SZ", "000963.SZ", "002709.SZ", "300750.SZ",
    "600000.SH", "600009.SH", "600011.SH", "600019.SH", "600036.SH", "600276.SH",
    "600519.SH", "600941.SH", "601000.SH", "601857.SH",
    "920027.BJ", "920118.BJ", "920185.BJ", "920751.BJ",
)
ANNUAL_YEARS = tuple(range(2021, 2026))


class _ParseTimeout(TimeoutError):
    pass


def _extract_bounded(report: OfficialReport, body: bytes, *, seconds: int = 45):
    """Do not let one pathological PDF stall a single-concurrency cohort."""
    def expired(_signum, _frame):
        raise _ParseTimeout(f"page parser exceeded {seconds}s")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return extract_report_facts(report, body)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _document_from_batch(batch: OfficialFilingBatch, *, wanted_type: str) -> tuple[dict[str, Any], bytes] | None:
    """Return one official raw PDF of the wanted type, without guessing a URL."""
    for document_id, outcome in batch.documents.items():
        record = outcome.records[0] if outcome.records else None
        attempt = next((item for item in reversed(outcome.attempts) if item.raw and item.fetched), None)
        if record is None or attempt is None:
            continue
        payload = record.payload
        if payload.get("document_type") != wanted_type:
            continue
        body = attempt.fetched.body
        if not body.startswith(b"%PDF"):
            continue
        return ({
            "document_id": str(payload.get("document_id") or document_id),
            "source_url": attempt.raw.source_url,
            "raw_hash": attempt.raw.raw_hash,
            "published_at": str(payload.get("published_at") or ""),
            "title": str(payload.get("title") or ""),
        }, body)
    return None


def _failure_excerpt(batch: OfficialFilingBatch) -> str:
    """A bounded primary-source diagnostic for a negative discovery result."""
    outcome = batch.discovery
    attempt = outcome.attempts[-1] if outcome.attempts else None
    if attempt and attempt.fetched:
        text = attempt.fetched.body.decode("utf-8", errors="replace")
        return " ".join(text.split())[:520]
    return (str(getattr(attempt, "error", "official discovery returned no raw response"))[:520])


def _capture_one(
    ticker: str,
    period: str,
    *,
    transport: OfficialHttpTransport,
    sync: Callable[..., OfficialFilingBatch] = sync_exchange_filings,
) -> dict[str, Any]:
    year = int(period[:4])
    # A FY is normally published in the following calendar year.  An interim
    # request uses the present year and takes the newest qualifying interim.
    if period.endswith("FY"):
        start, end, wanted, category = f"{year + 1}-01-01", f"{year + 1}-12-31", "annual_report", "category_ndbg_szsh"
    else:
        start, end, wanted, category = f"{year}-01-01", str(date.today()), "quarterly_report", "category_yjdbg_szsh"
    try:
        batch = sync(
            ticker, authority_sink=MemoryAuthoritySink(), transport=transport,
            start_date=start, end_date=end, limit=30, financial_reports_only=True,
            # The period/category window is intentionally narrow.  One
            # document is enough and prevents downloading every historical
            # amendment merely to select the first qualifying filing.
            max_documents=1, max_discovery_pages=1, category=category,
        )
    except Exception as exc:
        return {"period": period, "status": "missing", "reason": "official_collection_exception",
                "raw_text_excerpt": f"{type(exc).__name__}: {exc}"[:520]}
    selected = _document_from_batch(batch, wanted_type=wanted)
    if selected is None:
        return {"period": period, "status": "missing", "reason": f"official_{wanted}_not_captured",
                "raw_text_excerpt": _failure_excerpt(batch),
                "discovery_summary": batch.to_summary()}
    identity, body = selected
    report = OfficialReport(period, identity["document_id"], identity["source_url"], ticker=ticker)
    try:
        facts = _extract_bounded(report, body)
    except _ParseTimeout as exc:
        return {"period": period, "status": "missing", "reason": "page_parse_timeout",
                "raw_text_excerpt": str(exc), "document": identity}
    present = {fact.metric for fact in facts}
    return {
        "period": period, "status": "available", "document": identity,
        "facts": [asdict(fact) for fact in facts],
        "missing_metrics": _missing_metric_records(report, body, present),
    }


def run_financial_sequence_batch(
    runtime_root: Path,
    *,
    tickers: Iterable[str] = E4_AUDIT_COHORT_V2,
    delay_seconds: float = 1.0,
    transport: OfficialHttpTransport | None = None,
    sync: Callable[..., OfficialFilingBatch] = sync_exchange_filings,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Collect 5 FY + latest currently available interim, one issuer at a time."""
    requested = tuple(dict.fromkeys(str(value).upper() for value in tickers))
    if len(requested) != 20:
        raise ValueError("M2 requires exactly 20 distinct tickers")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")
    runtime_root.mkdir(parents=True, exist_ok=True)
    active_transport = transport or OfficialHttpTransport(
        # Keep each retry bounded.  The transport still retries four times
        # with exponential jitter, but a temporarily slow issuer cannot hold
        # the whole single-concurrency cohort indefinitely.
        timeout_seconds=5.0, min_request_interval_seconds=delay_seconds,
    )
    rows: list[dict[str, Any]] = []
    checkpoint_path = runtime_root / "financial-sequence-batch-checkpoint.json"
    if checkpoint_path.exists():
        prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if prior.get("data_kind") == "real" and prior.get("configured_max_concurrency") == 1:
            rows = list(prior.get("tickers") or [])
    completed = {str(item.get("ticker") or "").upper() for item in rows}
    # 2026H1 filings are not universally available by the collection date;
    # use Q1 as the common latest interim floor and retain absence explicitly.
    periods = tuple(f"{year}FY" for year in ANNUAL_YEARS) + ("2026Q1",)
    for index, ticker in enumerate(requested):
        if ticker in completed:
            continue
        reports = [_capture_one(ticker, period, transport=active_transport, sync=sync) for period in periods]
        rows.append({"ticker": ticker, "reports": reports})
        checkpoint = {
            "schema_version": "e4-financial-sequence-batch-checkpoint-v1", "state": "in_progress",
            "data_kind": "real", "configured_max_concurrency": 1,
            "inter_ticker_delay_seconds": delay_seconds, "tickers": rows,
        }
        _write_json(checkpoint_path, checkpoint)
        if index < len(requested) - 1 and delay_seconds:
            sleep(delay_seconds)
    facts = [fact for row in rows for report in row["reports"] for fact in report.get("facts", ())]
    output: dict[str, Any] = {
        "schema_version": "e4-financial-sequence-batch-v1", "data_kind": "real",
        "cohort": list(requested), "periods_attempted": list(periods), "sequential": True,
        "configured_max_concurrency": 1, "inter_ticker_delay_seconds": delay_seconds,
        "tickers": rows,
        "counts": {"tickers": len(rows), "facts": len(facts), "available_reports": sum(report["status"] == "available" for row in rows for report in row["reports"]), "missing_reports": sum(report["status"] == "missing" for row in rows for report in row["reports"])},
        "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True, "does_not_promote_tier_or_action": True},
    }
    output["receipt_hash"] = digest(output)
    path = runtime_root / f"financial-sequence-batch-{output['receipt_hash'][:16]}.json"
    _write_json(path, output)
    _write_json(runtime_root / "financial-sequence-batch-latest.json", {"state": "completed", "receipt": path.name, "receipt_hash": output["receipt_hash"]})
    checkpoint = runtime_root / "financial-sequence-batch-checkpoint.json"
    if checkpoint.exists():
        checkpoint.unlink()
    return {"path": str(path), "receipt": output}
