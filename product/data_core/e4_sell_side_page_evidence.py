"""Parse E4 runtime sell-side PDFs into hash-bound page/chunk evidence receipts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import digest
from .document_intelligence import DocumentParseResult, parse_pdf_document


E4_SELL_SIDE_PAGE_EVIDENCE_SCHEMA_VERSION = "e4-s4-sell-side-page-evidence-v1"


def _inside(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("runtime raw path escapes supplied runtime root") from exc
    return candidate


def _result_summary(result: DocumentParseResult, report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "parsed", "document_id": result.document_id, "ticker": report["ticker"],
        "report_id": report["report_id"], "source_url": report["source_url"],
        "raw_hash": result.raw_hash, "parser_version": result.parser_version, "parse_id": result.parse_id,
        "pages": [{"page_number": page.page_number, "text_hash": page.text_hash, "extraction_method": page.extraction_method, "table_status": page.table_status, "extraction_error": page.extraction_error} for page in result.pages],
        "chunks": [{"chunk_id": chunk.chunk_id, "page_number": chunk.page_number, "char_start": chunk.char_start, "char_end": chunk.char_end, "extraction_method": chunk.extraction_method} for chunk in result.chunks],
        "warnings": list(result.warnings),
    }


def compile_sell_side_page_evidence(batch_receipt_path: Path, runtime_root: Path) -> dict[str, Any]:
    """Parse only verified runtime PDF rows; all failures remain local and typed."""
    batch_bytes = batch_receipt_path.read_bytes()
    batch = json.loads(batch_bytes)
    boundary = batch.get("truth_boundary") or {}
    if batch.get("schema_version") != "e4-s4-sell-side-evidence-batch-v1" or batch.get("data_kind") != "real" or boundary.get("counts_as_tier_a_or_b") is not False:
        raise ValueError("page evidence compiler requires a real input-only sell-side receipt")
    rows: list[dict[str, Any]] = []
    for ticker_row in batch.get("tickers") or []:
        ticker = str(ticker_row.get("ticker") or "").upper()
        for report in ticker_row.get("reports") or []:
            base = {"ticker": ticker, "report_id": str(report.get("report_id") or "")}
            if report.get("archive_status") != "archived_pdf":
                rows.append({**base, "status": "blocked", "blockers": ["sell_side_pdf_not_archived"]})
                continue
            raw_hash, path_text = str(report.get("pdf_raw_hash") or ""), str(report.get("runtime_raw_path") or "")
            try:
                path = _inside(runtime_root, path_text)
                raw = path.read_bytes()
                if not raw_hash or hashlib.sha256(raw).hexdigest() != raw_hash:
                    raise ValueError("runtime PDF bytes do not match receipt raw hash")
                parsed = parse_pdf_document(f"sell-side-report:{report['report_id']}", raw, expected_raw_hash=raw_hash)
                rows.append(_result_summary(parsed, {**report, "ticker": ticker}))
            except Exception as exc:
                rows.append({**base, "status": "blocked", "blockers": ["sell_side_page_parse_failed"], "error": type(exc).__name__})
    receipt = {
        "schema_version": E4_SELL_SIDE_PAGE_EVIDENCE_SCHEMA_VERSION, "data_kind": "real",
        "sell_side_batch_receipt_sha256": hashlib.sha256(batch_bytes).hexdigest(), "documents": rows,
        "counts": {"requested": len(rows), "parsed": sum(row["status"] == "parsed" for row in rows), "blocked": sum(row["status"] == "blocked" for row in rows)},
        "truth_boundary": {"page_evidence_is_not_viewpoint_matrix": True, "counts_as_tier_a_or_b": False, "counts_as_numeric_page_audit": False, "counts_as_position_or_target": False},
    }
    receipt["receipt_hash"] = digest(receipt)
    return receipt


def write_sell_side_page_evidence(batch_receipt_path: Path, runtime_root: Path) -> dict[str, Any]:
    receipt = compile_sell_side_page_evidence(batch_receipt_path, runtime_root)
    path = runtime_root / f"sell-side-page-evidence-{receipt['receipt_hash'][:16]}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path), "receipt": receipt}
