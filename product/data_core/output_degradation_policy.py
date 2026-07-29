"""Read-only display permissions for existing research degradation tiers.

This module deliberately does not calculate a tier, alter C1/B6/decision
policy, or create a recommendation.  It tells product readers which already
compiled artifacts may be displayed without turning low coverage into a
high-confidence position recommendation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .contracts import digest

Tier = Literal["A", "B", "C", "missing"]
Coverage = Literal["complete", "partial", "missing"]


@dataclass(frozen=True)
class OutputAllowance:
    tier: Tier
    coverage: Coverage
    decision_receipt_present: bool
    show_evidence_browser: bool
    show_research_report: bool
    show_decision_summary: bool
    show_valuation_methods: bool
    show_unreviewed_judgment: bool
    show_target_price: bool
    show_position_range: bool
    show_action: bool
    suppression_reasons: tuple[str, ...]
    policy_hash: str


def output_allowance(
    tier: Tier,
    coverage: Coverage,
    *,
    decision_receipt_present: bool = False,
) -> OutputAllowance:
    """Return presentation-only permissions from already established state."""
    if tier not in {"A", "B", "C", "missing"}:
        raise ValueError("unsupported degradation tier")
    if coverage not in {"complete", "partial", "missing"}:
        raise ValueError("unsupported coverage status")

    base = {
        "tier": tier,
        "coverage": coverage,
        "decision_receipt_present": decision_receipt_present,
        "show_evidence_browser": tier != "missing",
        "show_research_report": tier in {"A", "B"},
        "show_decision_summary": tier in {"A", "B"},
        "show_valuation_methods": tier in {"A", "B"},
        "show_unreviewed_judgment": tier in {"A", "B"},
        "show_target_price": tier == "A" and coverage == "complete" and decision_receipt_present,
        "show_position_range": tier == "A" and coverage == "complete" and decision_receipt_present,
        "show_action": tier == "A" and coverage == "complete" and decision_receipt_present,
        "suppression_reasons": [],
    }
    reasons: list[str] = base["suppression_reasons"]
    if tier == "missing":
        reasons.extend(("missing_report_model", "display_diagnostics_only"))
    elif tier == "C":
        reasons.extend(("partial_report_model", "no_research_conclusion_or_recommendation"))
    elif tier == "B":
        reasons.append("tier_b_never_surfaces_target_position_or_action")
    if coverage != "complete":
        reasons.append("coverage_not_complete_no_high_confidence_position")
    if not decision_receipt_present:
        reasons.append("decision_receipt_not_present")
    if not base["show_target_price"]:
        reasons.append("target_price_suppressed")
    if not base["show_position_range"]:
        reasons.append("position_range_suppressed")
    if not base["show_action"]:
        reasons.append("action_suppressed")
    payload = {**base, "suppression_reasons": tuple(sorted(set(reasons)))}
    policy_hash = digest(payload)
    return OutputAllowance(**payload, policy_hash=policy_hash)


def output_policy_receipt(
    tier: Tier,
    coverage: Coverage,
    *,
    decision_receipt_present: bool = False,
) -> dict[str, object]:
    """Serialize an allowance without converting it into a decision receipt."""
    allowance = output_allowance(tier, coverage, decision_receipt_present=decision_receipt_present)
    return {
        "schema_version": "research-output-degradation-policy-v1",
        "allowance": asdict(allowance),
        "truth_boundary": {
            "does_not_modify_tier_strategy": True,
            "does_not_modify_b6_policy": True,
            "does_not_modify_decision_policy": True,
            "does_not_create_target_position_or_action": True,
        },
    }
