"""Explicit analyst-authored valuation-assumption receipts; never defaults."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Mapping
from report_contract import ValuationScenarioAssumptions
from .contracts import digest

SCHEMA_VERSION = "e4-s4-valuation-assumption-receipt-v1"

def compile_assumption_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    required = ("ticker", "research_cutoff", "author_id", "rationale", "source_identities", "scenarios")
    if any(not value.get(key) for key in required): raise ValueError("valuation assumption receipt is incomplete")
    try:
        cutoff = datetime.fromisoformat(str(value["research_cutoff"]).replace("Z", "+00:00"))
    except ValueError as exc: raise ValueError("research cutoff is invalid") from exc
    if cutoff.tzinfo is None or len(str(value["rationale"]).strip()) < 20: raise ValueError("valuation assumption provenance is incomplete")
    sources = value["source_identities"]
    if not isinstance(sources, Mapping) or not sources: raise ValueError("valuation assumptions require source identities")
    for identity in sources.values():
        if not isinstance(identity, Mapping) or not isinstance(identity.get("raw_hash"), str) or len(identity["raw_hash"]) != 64: raise ValueError("valuation assumption source identity is invalid")
    scenarios = value["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) != 3: raise ValueError("exactly three explicit scenarios are required")
    try: checked = [ValuationScenarioAssumptions(**{**dict(row), "revenue_growth": tuple(row["revenue_growth"]), "ebit_margin": tuple(row["ebit_margin"])}) for row in scenarios]
    except (KeyError, TypeError, ValueError) as exc: raise ValueError("valuation scenario is malformed") from exc
    for row in checked: row.validate()
    if {row.name for row in checked} != {"bear", "base", "bull"} or abs(sum(row.probability for row in checked) - 1) > 1e-9: raise ValueError("valuation scenarios are invalid")
    result = {"schema_version": SCHEMA_VERSION, "data_kind": "analyst_judgment", "ticker": str(value["ticker"]).upper(), "research_cutoff": value["research_cutoff"], "author_id": str(value["author_id"]), "rationale": str(value["rationale"]).strip(), "source_identities": dict(sources), "scenarios": [dict(row) for row in scenarios], "truth_boundary": {"explicit_human_authorship_required": True, "no_default_assumptions": True, "counts_as_tier_a_or_b": False, "no_target_position_or_action": True}}
    result["receipt_hash"] = digest(result); return result
