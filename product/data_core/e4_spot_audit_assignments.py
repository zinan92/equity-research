"""Prepare, but never grant, E4 numeric/page human-audit assignments."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import digest
from .e4_partial_report_models import E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION


E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION = "e4-s4-spot-audit-assignments-v1"
ASSIGNMENT_COUNT = 20


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _candidate(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    model = entry.get("model")
    if entry.get("status") != "compiled" or not isinstance(model, Mapping):
        return None
    boundary = model.get("decision_boundary")
    facts = model.get("input_facts")
    market = facts.get("market") if isinstance(facts, Mapping) else None
    fundamentals = facts.get("fundamentals") if isinstance(facts, Mapping) else None
    quote = market.get("quote") if isinstance(market, Mapping) else None
    latest_period = fundamentals.get("latest_period") if isinstance(fundamentals, Mapping) else None
    numeric_value = quote.get("last_price") if isinstance(quote, Mapping) else None
    if not (
        model.get("schema_version") == E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION
        and model.get("data_kind") == "real"
        and isinstance(model.get("ticker"), str)
        and isinstance(model.get("document_id"), str)
        and isinstance(model.get("raw_hash"), str) and len(model["raw_hash"]) == 64 and all(char in "0123456789abcdef" for char in model["raw_hash"].lower())
        and isinstance(model.get("report_model_hash"), str) and len(model["report_model_hash"]) == 64 and all(char in "0123456789abcdef" for char in model["report_model_hash"].lower())
        and boundary == {"tier": "C", "action": "no_action", "target_price": None, "position_range": None}
        and isinstance(numeric_value, (int, float))
        and isinstance(latest_period, Mapping)
        and latest_period.get("report_period")
        and set(market.get("source_components") or ()) == {"quote", "daily_bars"}
        and set(fundamentals.get("source_components") or ()) == {"fundamentals", "balance_sheet", "income_statement", "cash_flow"}
    ):
        return None
    return {
        "ticker": model["ticker"], "report_model_hash": model["report_model_hash"],
        "document_identity": {"document_id": model["document_id"], "raw_hash": model["raw_hash"]},
        "numeric_check": {
            "fact_path": "input_facts.market.quote.last_price", "expected_value": numeric_value,
            "observed_at": quote.get("observed_at"), "source_components": list(market.get("source_components") or ()),
        },
        "page_citation_check": {
            "document_id": model["document_id"], "raw_hash": model["raw_hash"],
            "required_reviewer_record": ["page_number", "quoted_label", "citation_note"],
        },
        "financial_context": {"report_period": latest_period["report_period"], "announced_at": latest_period.get("announced_at")},
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
        receipt.get("schema_version") != E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION
        or receipt.get("data_kind") != "real"
        or boundary.get("tier_is_c_only") is not True
        or receipt.get("receipt_hash") != digest({key: value for key, value in receipt.items() if key != "receipt_hash"})
    ):
        raise ValueError("audit assignments require a real, identity-valid Tier-C partial receipt")
    entries = receipt.get("models")
    if not isinstance(entries, list):
        raise ValueError("partial model rows are invalid")
    candidates = [candidate for candidate in (_candidate(entry) for entry in entries if isinstance(entry, Mapping)) if candidate]
    candidates.sort(key=lambda row: row["ticker"])
    if len({row["ticker"] for row in candidates}) != len(candidates):
        raise ValueError("partial model candidates contain duplicate tickers")
    if len(candidates) < ASSIGNMENT_COUNT:
        raise ValueError("insufficient fact-bearing real partial models for twenty audit assignments")
    selected = candidates[:ASSIGNMENT_COUNT]
    output = {
        "schema_version": E4_SPOT_AUDIT_ASSIGNMENTS_SCHEMA_VERSION,
        "data_kind": "runtime_only_audit",
        "partial_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "partial_receipt_hash": receipt["receipt_hash"],
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
            f"- Numeric check: verify `{assignment['numeric_check']['fact_path']}` equals `{assignment['numeric_check']['expected_value']}` against its declared source identity.",
            f"- Page check: locate `{assignment['page_citation_check']['document_id']}` with raw SHA-256 `{assignment['page_citation_check']['raw_hash']}`, then record page number, quoted label and citation note.",
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
