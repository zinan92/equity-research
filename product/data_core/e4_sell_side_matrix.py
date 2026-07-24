"""Compile page-verified E4 sell-side reports through the existing C3 matrix."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .contracts import digest
from .document_intelligence import DocumentParseResult, parse_pdf_document
from .e4_sell_side_page_evidence import _inside
from .viewpoint_matrix import SellSideViewpoint, build_sell_side_viewpoint_matrix


E4_SELL_SIDE_MATRIX_SCHEMA_VERSION = "e4-s4-sell-side-matrix-v1"


def _load(path: Path, schema: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes(); value = json.loads(raw)
    if value.get("schema_version") != schema or value.get("data_kind") != "real":
        raise ValueError("matrix compiler requires a real schema-bound receipt")
    return raw, value


def _research_cutoff(value: str) -> str:
    """Require an explicit timestamp without changing C3's report-date cutoff."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("research_cutoff must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("research_cutoff must include timezone")
    return str(value)


def _parse_report(report: Mapping[str, Any], evidence: Mapping[str, Any], runtime_root: Path) -> DocumentParseResult:
    path = _inside(runtime_root, str(report.get("runtime_raw_path") or ""))
    raw = path.read_bytes(); raw_hash = str(report.get("pdf_raw_hash") or "")
    if hashlib.sha256(raw).hexdigest() != raw_hash:
        raise ValueError("runtime PDF bytes do not match report raw hash")
    result = parse_pdf_document(f"sell-side-report:{report['report_id']}", raw, expected_raw_hash=raw_hash)
    if evidence.get("raw_hash") != raw_hash or evidence.get("parse_id") != result.parse_id or evidence.get("parser_version") != result.parser_version:
        raise ValueError("page evidence does not match reparsed report identity")
    return result


def compile_sell_side_matrices(
    batch_path: Path, page_evidence_path: Path, runtime_root: Path, *, as_of: str, research_cutoff: str,
) -> dict[str, Any]:
    """Build rating-only C3 matrices from reports whose exact PDFs were page parsed.

    No claim is inferred from report text.  Ratings stay catalog-attributed and
    the C3 matrix exposes missing target/estimate/claim fields.
    """
    research_cutoff = _research_cutoff(research_cutoff)
    batch_bytes, batch = _load(batch_path, "e4-s4-sell-side-evidence-batch-v1")
    evidence_bytes, evidence = _load(page_evidence_path, "e4-s4-sell-side-page-evidence-v1")
    if evidence.get("sell_side_batch_receipt_sha256") != hashlib.sha256(batch_bytes).hexdigest():
        raise ValueError("page evidence does not match sell-side batch lineage")
    by_report = {str(row.get("report_id") or ""): row for row in evidence.get("documents") or [] if row.get("status") == "parsed"}
    output: list[dict[str, Any]] = []
    for ticker_row in batch.get("tickers") or []:
        ticker = str(ticker_row.get("ticker") or "").upper(); viewpoints = []; corpus: dict[str, DocumentParseResult] = {}; blockers: list[dict[str, Any]] = []
        for report in ticker_row.get("reports") or []:
            report_id = str(report.get("report_id") or ""); evidence_row = by_report.get(report_id)
            if report.get("archive_status") != "archived_pdf" or evidence_row is None:
                blockers.append({"report_id": report_id, "reason": "page_verified_pdf_unavailable"}); continue
            if not report.get("broker") or not report.get("rating"):
                blockers.append({"report_id": report_id, "reason": "catalog_broker_or_rating_missing"}); continue
            try:
                document = _parse_report(report, evidence_row, runtime_root)
                viewpoint = SellSideViewpoint(
                    ticker=ticker, report_id=report_id, report_title=str(report.get("title") or ""), document_id=document.document_id,
                    raw_hash=document.raw_hash, broker=str(report["broker"]), analyst=report.get("analyst"), report_date=str(report["published_at"])[:10],
                    rating=str(report["rating"]), target_price=None, currency="CNY", estimates=(), claims=(),
                )
                viewpoints.append(viewpoint); corpus[document.document_id] = document
            except Exception as exc:
                blockers.append({"report_id": report_id, "reason": "matrix_input_invalid", "error": type(exc).__name__})
        if viewpoints:
            matrix = build_sell_side_viewpoint_matrix(ticker, viewpoints, corpus, as_of=as_of)
            output.append({"ticker": ticker, "status": "compiled", "matrix": {"matrix_id": matrix.matrix_id, "input_hash": matrix.input_hash, "as_of": matrix.as_of, "research_cutoff": research_cutoff, "rows": [row.__dict__ for row in matrix.rows], "coverage": matrix.coverage.__dict__}, "blockers": blockers})
        else:
            output.append({"ticker": ticker, "status": "blocked", "blockers": blockers or [{"reason": "no_page_verified_sell_side_viewpoint"}]})
    receipt = {"schema_version": E4_SELL_SIDE_MATRIX_SCHEMA_VERSION, "data_kind": "real", "as_of": as_of, "research_cutoff": research_cutoff, "batch_receipt_sha256": hashlib.sha256(batch_bytes).hexdigest(), "page_evidence_receipt_sha256": hashlib.sha256(evidence_bytes).hexdigest(), "matrices": output, "counts": {"compiled": sum(row["status"] == "compiled" for row in output), "blocked": sum(row["status"] == "blocked" for row in output)}, "truth_boundary": {"matrix_is_not_tier": True, "counts_as_tier_a_or_b": False, "counts_as_numeric_page_audit": False, "counts_as_position_or_target": False}}
    receipt["receipt_hash"] = digest(receipt)
    return receipt
