"""One honest Any-Ticker output policy over B6 evidence and C1 sections."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable

from report_contract import ResearchSectionContract, SectionCompletion

from .evidence_gate import ImmutableEvidenceSet


DEGRADATION_POLICY_VERSION = "park-any-ticker-degradation-v1"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class ResearchTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    MISSING = "missing"


_BLOCKED_FIELDS = ("action", "target_price", "position_range")
_TIER_ALLOWED = {
    ResearchTier.A: ("status", "summary", "report", "evidence", "action", "target_price", "position_range", "next_steps"),
    ResearchTier.B: ("status", "summary", "partial_report", "evidence", "next_steps"),
    ResearchTier.C: ("status", "coverage", "evidence", "next_steps"),
    ResearchTier.MISSING: ("status", "next_steps"),
}


@dataclass(frozen=True)
class SourceGapAction:
    component: str
    reason: str
    next_step: str


SOURCE_GAP_ACTIONS = {
    "filings": "collect an accepted official filing with raw identity and page citations",
    "market": "refresh a point-in-time market snapshot before calculating valuation or action",
    "valuation": "run the C2 valuation bridge from accepted historical inputs",
    "sell_side": "collect page-cited sell-side reports or retain the sell-side section as missing",
    "events": "collect an entity-resolved event source before presenting catalysts",
    "default": "keep the section visible as missing evidence and request a canonical refresh",
}


@dataclass(frozen=True)
class DegradationReceipt:
    ticker: str
    tier: ResearchTier
    evidence_set_id: str | None
    evidence_manifest_hash: str | None
    section_statuses: tuple[tuple[str, str], ...]
    allowed_fields: tuple[str, ...]
    blocked_fields: tuple[str, ...]
    source_gap_actions: tuple[SourceGapAction, ...]
    reasons: tuple[str, ...]
    policy_version: str
    receipt_hash: str


def _source_actions(evidence_set: ImmutableEvidenceSet | None) -> tuple[SourceGapAction, ...]:
    if evidence_set is None:
        return (SourceGapAction("identity", "no canonical evidence set", SOURCE_GAP_ACTIONS["default"]),)
    actions = []
    for gap in evidence_set.receipt.coverage.source_gaps:
        actions.append(SourceGapAction(gap.component, gap.reason, SOURCE_GAP_ACTIONS.get(gap.component, SOURCE_GAP_ACTIONS["default"])))
    for requirement in evidence_set.receipt.coverage.requirements:
        if requirement.missing:
            actions.append(SourceGapAction(requirement.component, ",".join(requirement.missing), SOURCE_GAP_ACTIONS.get(requirement.component, SOURCE_GAP_ACTIONS["default"])))
    return tuple(sorted(actions, key=lambda item: (item.component, item.reason, item.next_step)))


def assess_any_ticker(
    ticker: str, *, evidence_set: ImmutableEvidenceSet | None, section_contract: ResearchSectionContract | None,
    data_kind: str = "real",
) -> DegradationReceipt:
    """Return the maximum honest output tier; no caller can elevate fixture data."""
    normalized = ticker.upper().strip()
    if not normalized:
        raise ValueError("ticker is required")
    reasons: list[str] = []
    sections: tuple[tuple[str, str], ...] = ()
    if data_kind != "real":
        tier = ResearchTier.MISSING
        reasons.append(f"non_real_data_kind:{data_kind}")
    elif evidence_set is None:
        tier = ResearchTier.MISSING
        reasons.append("missing_canonical_evidence_set")
    elif evidence_set.ticker.upper() != normalized:
        raise ValueError("evidence set ticker mismatch")
    elif not evidence_set.publishable:
        tier = ResearchTier.C
        reasons.append("evidence_gate_not_passed")
    elif section_contract is None:
        tier = ResearchTier.C
        reasons.append("missing_section_contract")
    else:
        if section_contract.evidence_manifest_hash != evidence_set.manifest_hash:
            raise ValueError("section contract evidence manifest mismatch")
        sections = tuple((section.section_id, section.status.value) for section in section_contract.sections)
        if not section_contract.live_eligible:
            tier = ResearchTier.C
            reasons.append("section_contract_not_live_eligible")
        elif all(section.status is SectionCompletion.FULL for section in section_contract.sections):
            tier = ResearchTier.A
        else:
            tier = ResearchTier.B
            reasons.append("partial_or_missing_sections")
    actions = _source_actions(evidence_set)
    if tier is not ResearchTier.A:
        reasons.append("investment_action_fields_blocked")
    allowed = _TIER_ALLOWED[tier]
    blocked = () if tier is ResearchTier.A else _BLOCKED_FIELDS
    payload = {
        "ticker": normalized, "tier": tier.value,
        "evidence_set_id": evidence_set.evidence_set_id if evidence_set else None,
        "evidence_manifest_hash": evidence_set.manifest_hash if evidence_set else None,
        "section_statuses": sections, "allowed_fields": allowed, "blocked_fields": blocked,
        "source_gap_actions": [asdict(item) for item in actions], "reasons": tuple(reasons),
        "policy_version": DEGRADATION_POLICY_VERSION,
    }
    return DegradationReceipt(
        normalized, tier, payload["evidence_set_id"], payload["evidence_manifest_hash"], sections,
        allowed, blocked, actions, tuple(reasons), DEGRADATION_POLICY_VERSION, _hash(payload),
    )
