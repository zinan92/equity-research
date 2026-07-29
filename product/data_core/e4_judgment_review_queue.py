"""Human-review queue for receipt-bound AI judgment drafts."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from report_contract import build_research_section_contract_v2

from .e4_judgment_wiring import JUDGMENT_INPUTS, wire_unreviewed_judgment_receipt


_IMPACT = {
    "investment_thesis": (1, "核心结论"), "variant_view": (1, "核心结论"),
    "risk_register": (2, "反方与失效条件"), "falsification_tests": (2, "反方与失效条件"),
    "moat_assessment": (3, "竞争优势"), "margin_bridge": (4, "盈利质量"),
    "operating_kpis": (5, "经营兑现"), "accounting_checks": (6, "会计质量"),
    "monitoring_kpis": (7, "持续跟踪"), "action_triggers": (7, "持续跟踪"),
}


def _approved(value: Any) -> Any:
    if isinstance(value, dict):
        copied = {key: _approved(item) for key, item in value.items()}
        if copied.get("status") == "ai_generated_judgment_unreviewed":
            copied["status"] = "human_reviewed_judgment"
            copied["review_status"] = "approved"
        return copied
    if isinstance(value, list):
        return [_approved(item) for item in value]
    return value


def build_judgment_review_queue(
    receipt: Mapping[str, Any], *, ticker: str, section_assessments: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    inputs = wire_unreviewed_judgment_receipt(receipt, ticker=ticker)
    current = build_research_section_contract_v2(inputs)
    approved = build_research_section_contract_v2(_approved(deepcopy(inputs)))
    current_by_id = {item.section_id: item for item in current.sections}
    approved_by_id = {item.section_id: item for item in approved.sections}
    rows: list[dict[str, Any]] = []
    content = receipt["content"]
    for section_id, mappings in JUDGMENT_INPUTS.items():
        pending_keys = [source_key for source_key, _input_key, _input_type in mappings if source_key in content and content[source_key].get("status") == "ai_generated_judgment_unreviewed"]
        for source_key in pending_keys:
            value = content[source_key]
            priority, impact = _IMPACT[source_key]
            citations = []
            for fact in value["facts"]:
                citation = dict(fact["citation"])
                citation["pdf_page_url"] = str(citation["source_url"]) + "#page=" + str(citation["page_number"])
                citations.append(citation)
            body = {key: deepcopy(value[key]) for key in ("text", "claims", "tests", "items") if key in value}
            section_current = current_by_id[section_id]
            section_approved = approved_by_id[section_id]
            # The queue may be built against the fully wired report receipt;
            # that preserves existing official inputs (such as revenue history)
            # while evaluating the one remaining human-review condition.
            recorded = (section_assessments or {}).get(section_id)
            current_status = str(recorded.get("status")) if recorded else section_current.status.value
            current_reason = recorded.get("status_reason") if recorded else section_current.status_reason
            independently_missing = list(recorded.get("missing_required") or ()) if recorded else list(section_approved.missing_required)
            other_pending_inputs = [
                input_key
                for other_key, input_key, _input_type in mappings
                if other_key != source_key
                and other_key in content
                and content[other_key].get("status") == "ai_generated_judgment_unreviewed"
            ]
            missing_after_one_approval = sorted(set(independently_missing + other_pending_inputs))
            promotes = current_status == "partial" and not missing_after_one_approval
            all_pending_status = (
                "full"
                if current_status == "partial" and not independently_missing
                else section_approved.status.value
            )
            rows.append({
                "judgment_id": source_key,
                "ticker": ticker.upper(),
                "section_id": section_id,
                "impact_rank": priority,
                "impact": impact,
                "body": body,
                "citations": citations,
                "source_receipt_id": f"{receipt['schema_version']}:{receipt['receipt_hash']}",
                "review_status": "pending_human_review",
                "approval_writeback": {"status": "human_reviewed_judgment", "review_status": "approved"},
                "current_section_status": current_status,
                "current_section_reason": current_reason,
                "section_status_after_all_pending_judgments_approved": all_pending_status,
                "would_promote_section_to_full": promotes,
                "remaining_required_inputs_after_approval": missing_after_one_approval,
            })
    rows.sort(key=lambda row: (row["impact_rank"], row["section_id"], row["judgment_id"]))
    return {
        "schema_version": "e4-judgment-review-queue-v1", "data_kind": "real", "ticker": ticker.upper(),
        "source_receipt_id": f"{receipt['schema_version']}:{receipt['receipt_hash']}",
        "sort": "impact_rank ascending; equal ranks by section and judgment identifier",
        "counts": {"pending_human_review": len(rows), "would_promote_section_to_full": sum(item["would_promote_section_to_full"] for item in rows)},
        "items": rows,
    }
