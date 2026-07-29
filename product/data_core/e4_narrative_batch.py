"""Sequential 100-ticker official-PDF narrative extraction with receipt lineage."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping

from .e4_catl_financial_history import OfficialReport
from .e4_narrative_evidence import NarrativeBlock, _report_coverage, extract_narrative_blocks
from .official_filings import default_http_transport


class _NarrativeParseTimeout(TimeoutError):
    """The PDF prose parser exceeded its per-document isolation deadline."""


def _extract_child(report: OfficialReport, body: bytes, connection: Any) -> None:
    try:
        connection.send(("ok", [asdict(block) for block in extract_narrative_blocks(report, body)]))
    except BaseException as exc:
        connection.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


def _extract_bounded(
    report: OfficialReport,
    body: bytes,
    *,
    seconds: int = 45,
) -> list[dict[str, Any]]:
    """Parse in a killable child so one malformed PDF cannot stall the cohort."""
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    worker = context.Process(target=_extract_child, args=(report, body, child), daemon=True)
    worker.start()
    child.close()
    try:
        if not parent.poll(seconds):
            worker.terminate()
            worker.join(5)
            raise _NarrativeParseTimeout(
                f"narrative parser exceeded {seconds}s in isolated worker"
            )
        status, payload = parent.recv()
        worker.join(5)
        if status != "ok":
            raise ValueError(f"isolated narrative parser failed: {payload}")
        return list(payload)
    finally:
        parent.close()
        if worker.is_alive():
            worker.terminate()
            worker.join(5)


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _selection(row: Mapping[str, Any]) -> tuple[Mapping[str, Any], str] | None:
    available = [
        item
        for item in row.get("reports") or []
        if item.get("status") == "available" and isinstance(item.get("document"), Mapping)
    ]
    annual = [item for item in available if str(item.get("period") or "").endswith("FY")]
    candidates = annual or available
    if not candidates:
        return None
    basis = "latest_available_annual" if annual else "latest_available_interim_fallback"
    return max(candidates, key=lambda item: str(item.get("period") or "")), basis


def _capture(
    ticker: str,
    report: Mapping[str, Any],
    fetch: Callable[..., Any] = default_http_transport,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = report["document"]
    base = {"ticker": ticker, "period": report["period"], "document": document}
    try:
        response = fetch(str(document["source_url"]), {"Accept": "application/pdf"})
    except Exception as exc:
        return ({**base, "status": "missing", "reason": f"official_pdf_fetch_failed:{type(exc).__name__}"}, [])
    body = response.body
    if response.status_code != 200 or not body.startswith(b"%PDF"):
        return ({**base, "status": "missing", "reason": "official_pdf_unavailable"}, [])
    observed_hash = hashlib.sha256(body).hexdigest()
    if observed_hash != document["raw_hash"]:
        return ({**base, "status": "missing", "reason": "official_pdf_raw_hash_mismatch", "observed_raw_hash": observed_hash}, [])
    report_identity = OfficialReport(
        str(report["period"]), str(document["document_id"]), str(document["source_url"]), ticker=ticker
    )
    try:
        serialized = _extract_bounded(report_identity, body)
    except _NarrativeParseTimeout as exc:
        return ({**base, "status": "missing", "reason": "narrative_parse_timeout", "raw_text_excerpt": str(exc)}, [])
    except Exception as exc:
        return ({**base, "status": "missing", "reason": "narrative_parse_exception", "raw_text_excerpt": f"{type(exc).__name__}: {exc}"[:520]}, [])
    blocks = [NarrativeBlock(**block) for block in serialized]
    return ({**base, "status": "available", "coverage": _report_coverage(blocks)}, serialized)


def run_narrative_batch(
    financial_path: Path,
    runtime_root: Path,
    *,
    delay_seconds: float = 1.0,
    fetch: Callable[..., Any] = default_http_transport,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Re-fetch one official filing per frozen identity, sequentially and resumably."""
    source_bytes = financial_path.read_bytes()
    financial = json.loads(source_bytes)
    boundary = financial.get("truth_boundary", {})
    if (
        financial.get("schema_version") != "e4-financial-sequence-batch-v1"
        or financial.get("data_kind") != "real"
        or boundary.get("official_cninfo_pdf_only") is not True
    ):
        raise ValueError("narrative batch requires a real official financial-sequence receipt")
    cohort = tuple(financial.get("cohort") or ())
    if len(cohort) != 100 or len(set(cohort)) != 100:
        raise ValueError("L2-M2 requires the completed 100-ticker cohort")
    rows_by_ticker = {
        str(row.get("ticker") or "").upper(): row for row in financial.get("tickers") or []
    }
    if set(rows_by_ticker) != set(cohort):
        raise ValueError("financial sequence rows do not match cohort")

    financial_sha256 = hashlib.sha256(source_bytes).hexdigest()
    runtime_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = runtime_root / "narrative-batch-checkpoint.json"
    rows: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    if checkpoint_path.exists():
        previous = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if (
            previous.get("financial_sequence_sha256") == financial_sha256
            and previous.get("data_kind") == "real"
        ):
            rows = list(previous.get("rows") or [])
            blocks = list(previous.get("blocks") or [])
    completed = {row["ticker"] for row in rows}
    for ticker in cohort:
        if ticker in completed:
            continue
        selected = _selection(rows_by_ticker[ticker])
        if selected is None:
            row, extracted = ({"ticker": ticker, "status": "missing", "reason": "no_available_official_report"}, [])
        else:
            chosen, selection_basis = selected
            row, extracted = _capture(ticker, chosen, fetch=fetch)
            row["selection_basis"] = selection_basis
        rows.append(row)
        blocks.extend(extracted)
        _write(
            checkpoint_path,
            {
                "schema_version": "e4-narrative-batch-checkpoint-v1",
                "data_kind": "real",
                "financial_sequence_sha256": financial_sha256,
                "configured_max_concurrency": 1,
                "rows": rows,
                "blocks": blocks,
            },
        )
        if delay_seconds:
            sleep(delay_seconds)

    counts = {
        "tickers": len(rows),
        "available": sum(row["status"] == "available" for row in rows),
        "missing": sum(row["status"] == "missing" for row in rows),
        "blocks": len(blocks),
        "resolved_blocks": sum(block.get("status") == "resolved" for block in blocks),
        "unresolved_blocks": sum(block.get("status") != "resolved" for block in blocks),
        "annual_selection": sum(row.get("selection_basis") == "latest_available_annual" for row in rows),
        "interim_fallback_selection": sum(row.get("selection_basis") == "latest_available_interim_fallback" for row in rows),
        "missing_reasons": dict(sorted(Counter(row.get("reason") for row in rows if row["status"] == "missing").items())),
    }
    output: dict[str, Any] = {
        "schema_version": "e4-l2-narrative-batch-v1",
        "data_kind": "real",
        "financial_sequence_sha256": financial_sha256,
        "cohort": list(cohort),
        "sequential": True,
        "configured_max_concurrency": 1,
        "inter_ticker_delay_seconds": delay_seconds,
        "rows": rows,
        "blocks": blocks,
        "counts": counts,
        "truth_boundary": {
            "official_cninfo_pdf_only": True,
            "page_bound_only": True,
            "financial_receipt_is_selection_lineage_only": True,
            "does_not_promote_tier_or_action": True,
            "missing_is_retained_not_filled": True,
        },
    }
    output["receipt_hash"] = hashlib.sha256(
        json.dumps(output, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    path = runtime_root / f"narrative-batch-{output['receipt_hash'][:16]}.json"
    _write(path, output)
    _write(
        runtime_root / "narrative-batch-latest.json",
        {"state": "completed", "receipt": path.name, "receipt_hash": output["receipt_hash"]},
    )
    checkpoint_path.unlink(missing_ok=True)
    return {"path": str(path), "receipt": output}
