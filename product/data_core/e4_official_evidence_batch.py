"""Polite runtime-only official-filing bootstrap for the strict E4-S4 corpus.

This bridge deliberately stops before a Report Model.  A captured official PDF
is a traceable primary input, not a completed research report or a coverage
credit.  Raw bytes and manifests belong to the ignored runtime directory.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .ashare import MemoryAuthoritySink
from .contracts import digest
from .official_filings import OfficialFilingBatch, sync_exchange_filings


E4_OFFICIAL_EVIDENCE_BATCH_SCHEMA_VERSION = "e4-s4-official-evidence-batch-v1"
QUALIFYING_DOCUMENT_TYPES = frozenset({"annual_report", "semiannual_report", "quarterly_report"})
MAX_OFFICIAL_FILING_AGE_DAYS = 365
SyncFn = Callable[..., OfficialFilingBatch]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_real_identity_tickers(receipt_path: Path, *, required: int = 100) -> tuple[str, ...]:
    """Load only the bounded, runtime-captured real security-master input."""
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    boundary = payload.get("truth_boundary") or {}
    if (
        payload.get("schema_version") != "ashare-security-master-v1"
        or payload.get("data_kind") != "real"
        or boundary.get("identity_only") is not True
    ):
        raise ValueError("official evidence batch requires a real bounded security-master receipt")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("security-master records are invalid")
    tickers = tuple(sorted({str(row.get("ticker") or "").upper() for row in records}))
    if len(tickers) < required or not all(tickers):
        raise ValueError(f"security-master receipt must contain at least {required} unique tickers")
    return tickers[:required]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _raw_receipt(document_outcome: Any, raw_root: Path) -> dict[str, Any]:
    attempt = next(
        (item for item in reversed(document_outcome.attempts) if item.raw and item.fetched), None
    )
    record = document_outcome.records[0] if document_outcome.records else None
    if attempt is None or record is None:
        raise ValueError("official document outcome has no raw capture")
    body = attempt.fetched.body
    raw_hash = hashlib.sha256(body).hexdigest()
    if raw_hash != attempt.raw.raw_hash:
        raise ValueError("official document raw hash does not match fetched body")
    if record.payload.get("document_type") not in QUALIFYING_DOCUMENT_TYPES:
        raise ValueError("official document is not a qualifying financial report")
    published_at = str(record.payload["published_at"])
    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    if published.tzinfo is None:
        raise ValueError("official document published_at must include timezone")
    if (datetime.now(timezone.utc) - published.astimezone(timezone.utc)).days > MAX_OFFICIAL_FILING_AGE_DAYS:
        raise ValueError("official document is older than the E4 batch recency limit")
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_path = raw_root / f"{raw_hash}.pdf"
    if raw_path.exists() and raw_path.read_bytes() != body:
        raise ValueError("official document raw hash collision")
    if not raw_path.exists():
        raw_path.write_bytes(body)
    return {
        "status": "captured",
        "data_kind": "real",
        "document_id": record.payload["document_id"],
        "document_type": record.payload["document_type"],
        "published_at": published_at,
        "source_key": document_outcome.selected_source,
        "source_url": attempt.raw.source_url,
        "raw_hash": raw_hash,
        "storage_uri": attempt.raw.storage_uri,
        "runtime_raw_path": str(raw_path),
        "report_model_hash": None,
        "tier": None,
        "numeric_spot_audit": False,
        "page_citation_spot_audit": False,
        "blockers": ["official_primary_captured_but_report_model_not_compiled"],
    }


def _result_for_batch(ticker: str, batch: OfficialFilingBatch, raw_root: Path) -> dict[str, Any]:
    if not batch.discovery.publishable:
        return {
            "status": "failed", "data_kind": "real", "ticker": ticker,
            "blockers": ["official_filing_discovery_failed"],
        }
    if len(batch.documents) > 1:
        raise ValueError("official evidence batch may capture at most one document per ticker")
    if not batch.documents:
        return {
            "status": "failed", "data_kind": "real", "ticker": ticker,
            "blockers": ["no_qualifying_recent_financial_report"],
        }
    document_id, outcome = next(iter(batch.documents.items()))
    if not outcome.publishable:
        return {
            "status": "failed", "data_kind": "real", "ticker": ticker,
            "document_id": document_id, "blockers": ["official_filing_document_capture_failed"],
        }
    try:
        return {"ticker": ticker, **_raw_receipt(outcome, raw_root)}
    except ValueError as exc:
        return {
            "status": "failed", "data_kind": "real", "ticker": ticker,
            "document_id": document_id,
            "blockers": ["official_filing_stale_or_unqualified"],
            "error": type(exc).__name__,
        }


def run_official_evidence_batch(
    identity_receipt_path: Path,
    runtime_root: Path,
    *,
    max_tickers: int = 100,
    inter_ticker_delay_seconds: float = 1.0,
    sync: SyncFn = sync_exchange_filings,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Capture one qualifying official filing per ticker, sequentially and resumably."""
    if not isinstance(max_tickers, int) or not 1 <= max_tickers <= 100:
        raise ValueError("max_tickers must be 1-100")
    if inter_ticker_delay_seconds < 0:
        raise ValueError("inter_ticker_delay_seconds must be nonnegative")
    tickers = load_real_identity_tickers(identity_receipt_path)[:max_tickers]
    runtime_root.mkdir(parents=True, exist_ok=True)
    latest_path = runtime_root / "official-evidence-batch-latest.json"
    previous: dict[str, Mapping[str, Any]] = {}
    if latest_path.exists():
        pointer = json.loads(latest_path.read_text(encoding="utf-8"))
        previous_path = runtime_root / str(pointer.get("receipt") or "")
        if previous_path.is_file():
            previous_payload = json.loads(previous_path.read_text(encoding="utf-8"))
            previous = {str(item.get("ticker") or "").upper(): item for item in previous_payload.get("tickers") or []}

    rows: list[dict[str, Any]] = []
    raw_root = runtime_root / "raw"
    for index, ticker in enumerate(tickers):
        prior = previous.get(ticker)
        if prior and prior.get("status") == "captured":
            rows.append({"ticker": ticker, "status": "skipped", "data_kind": "real", "resumed_from_raw_hash": prior.get("raw_hash"), "blockers": ["already_captured"]})
            continue
        try:
            sink = MemoryAuthoritySink()
            batch = sync(
                ticker, authority_sink=sink, limit=30, financial_reports_only=True, max_documents=1,
            )
            rows.append(_result_for_batch(ticker, batch, raw_root))
        except Exception as exc:  # a single issuer must never abort the corpus
            rows.append({"ticker": ticker, "status": "failed", "data_kind": "real", "blockers": ["collector_exception"], "error": type(exc).__name__})
        if index < len(tickers) - 1 and inter_ticker_delay_seconds:
            sleep(inter_ticker_delay_seconds)

    captured = [row for row in rows if row.get("status") == "captured"]
    receipt = {
        "schema_version": E4_OFFICIAL_EVIDENCE_BATCH_SCHEMA_VERSION,
        "identity_receipt_path": str(identity_receipt_path),
        "identity_receipt_sha256": hashlib.sha256(identity_receipt_path.read_bytes()).hexdigest(),
        "data_kind": "real",
        "sequential": True,
        "configured_max_concurrency": 1,
        "inter_ticker_delay_seconds": inter_ticker_delay_seconds,
        "tickers": rows,
        "counts": {"requested": len(tickers), "captured_official_primary": len(captured), "failed": sum(row.get("status") == "failed" for row in rows), "resumed": sum(row.get("status") == "skipped" for row in rows)},
        "truth_boundary": {
            "official_primary_is_input_not_report_model": True,
            "counts_as_report_model_coverage": False,
            "counts_as_tier_a_or_b": False,
            "counts_as_numeric_page_audit": False,
        },
    }
    receipt["receipt_hash"] = digest(receipt)
    receipt_path = runtime_root / f"official-evidence-batch-{receipt['receipt_hash'][:16]}.json"
    _write_json(receipt_path, receipt)
    _write_json(latest_path, {"receipt": receipt_path.name, "receipt_hash": receipt["receipt_hash"]})
    return {"path": str(receipt_path), "receipt": receipt}
