"""Fail-closed quality aggregate for controlled research expansion."""
from __future__ import annotations
from typing import Any, Mapping
from .contracts import digest

QUALITY_DASHBOARD_SCHEMA_VERSION = "research-quality-dashboard-v1"

def build_expansion_gate(*, coverage: Mapping[str, Any], cadence: Mapping[str, Any], citations: Mapping[str, Any], outcomes: Mapping[str, Any], correction_issue: str | None = None) -> dict[str, Any]:
    components = {"coverage": coverage.get("status"), "cadence": cadence.get("status"), "citations": citations.get("status"), "outcomes": outcomes.get("status")}
    missing = [name for name, status in components.items() if status != "passed"]
    if correction_issue:
        missing.append("manual_correction")
    receipt = {"schema_version": QUALITY_DASHBOARD_SCHEMA_VERSION, "components": components, "correction_issue": correction_issue, "decision": "no_go" if missing else "go", "blocked_by": missing, "boundary": "receipt only; no source collection, action, target, position, recommendation, or order"}
    receipt["receipt_hash"] = digest(receipt)
    return receipt
