"""Prepare, but never grant, E4 numeric/page human-audit assignments."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import digest
from .e4_page_level_filing_facts import E4_PAGE_FACTS_SCHEMA_VERSION


E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION = "e4-s4-spot-audit-assignments-v1"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _candidate(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    fact = entry.get("fact")
    if entry.get("status") != "available" or not isinstance(fact, Mapping):
        return None
    required = ("ticker", "document_id", "raw_hash", "metric", "value", "page_number", "quoted_label", "quoted_anchor", "report_period", "statement_scope", "unit", "currency", "source_url")
    if not (
        all(fact.get(key) not in (None, "") for key in required)
        and isinstance(fact.get("value"), (int, float)) and isinstance(fact.get("page_number"), int)
        and len(str(fact.get("raw_hash"))) == 64
        and all(char in "0123456789abcdef" for char in str(fact.get("raw_hash")).lower())
    ):
        return None
    return {
        "ticker": fact["ticker"], "document_identity": {"document_id": fact["document_id"], "raw_hash": fact["raw_hash"]},
        "numeric_check": {
            "metric": fact["metric"], "expected_value": fact["value"], "unit": fact["unit"], "currency": fact["currency"],
            "report_period": fact["report_period"], "statement_scope": fact["statement_scope"],
        },
        "page_citation_check": {
            "document_id": fact["document_id"], "raw_hash": fact["raw_hash"], "page_number": fact["page_number"],
            "quoted_label": fact["quoted_label"], "quoted_anchor": fact["quoted_anchor"], "source_url": fact["source_url"],
        },
        "review_status": "pending_human_review",
    }


def compile_spot_audit_assignments(partial_receipt_path: Path) -> dict[str, Any]:
    raw = partial_receipt_path.read_bytes()
    try:
        receipt = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("partial model receipt is invalid") from exc
    boundary = receipt.get("truth_boundary") or {}
    if (
        receipt.get("schema_version") != E4_PAGE_FACTS_SCHEMA_VERSION
        or receipt.get("data_kind") != "real"
        or boundary.get("page_bound_primary_facts_only") is not True
        or receipt.get("receipt_hash") != digest({key: value for key, value in receipt.items() if key != "receipt_hash"})
    ):
        raise ValueError("audit assignments require a real, page-bound filing-facts receipt")
    entries = receipt.get("facts")
    if not isinstance(entries, list):
        raise ValueError("page-level filing fact rows are invalid")
    candidates = [candidate for candidate in (_candidate(entry) for entry in entries if isinstance(entry, Mapping)) if candidate]
    candidates.sort(key=lambda row: row["ticker"])
    if not candidates:
        raise ValueError("no page-bound filing facts are available for audit assignment")
    selected = candidates
    output = {
        "schema_version": E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION,
        "data_kind": "runtime_only_audit",
        "page_facts_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "page_facts_receipt_hash": receipt["receipt_hash"],
        "assignments": selected,
        "counts": {"assigned": len(selected), "pending_human_review": len(selected), "completed": 0},
        "truth_boundary": {
            "assignments_are_not_completed_audits": True,
            "counts_as_numeric_page_audit": False,
            "counts_as_tier_a_or_b": False,
            "no_target_position_or_action": True,
        },
    }
    output["receipt_hash"] = digest(output)
    return output


def render_spot_audit_guide(assignments: Mapping[str, Any]) -> str:
    if assignments.get("schema_version") != E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION:
        raise ValueError("audit assignment receipt schema is invalid")
    lines = ["# E4 spot-audit review guide", "", "This is an assignment list, not an audit result. Complete each row with an independent reviewer record; do not alter the source receipt.", ""]
    for assignment in assignments.get("assignments") or []:
        lines.extend([
            f"## {assignment['ticker']}",
            f"- Numeric check: verify `{assignment['numeric_check']['metric']}` equals `{assignment['numeric_check']['expected_value']}` {assignment['numeric_check']['unit']} for {assignment['numeric_check']['report_period']}.",
            f"- Page check: open `{assignment['page_citation_check']['source_url']}`, verify raw SHA-256 `{assignment['page_citation_check']['raw_hash']}`, then compare page {assignment['page_citation_check']['page_number']} and label `{assignment['page_citation_check']['quoted_label']}`.",
            "- Required result: a named reviewer, timestamp, pass/fail for both checks, and an explanation for any failure.",
            "",
        ])
    return "\n".join(lines) + "\n"


def write_spot_audit_assignments(partial_receipt_path: Path, runtime_root: Path) -> dict[str, Any]:
    receipt = compile_spot_audit_assignments(partial_receipt_path)
    path = runtime_root / f"spot-audit-assignments-{receipt['receipt_hash'][:16]}.json"
    _write_json(path, receipt)
    _write_json(runtime_root / "spot-audit-assignments-latest.json", {"receipt": path.name, "receipt_hash": receipt["receipt_hash"]})
    guide = runtime_root / f"spot-audit-guide-{receipt['receipt_hash'][:16]}.md"
    guide.write_text(render_spot_audit_guide(receipt), encoding="utf-8")
    return {"path": str(path), "guide_path": str(guide), "receipt": receipt}
