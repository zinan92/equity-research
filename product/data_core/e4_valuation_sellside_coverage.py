"""Fail-closed valuation/sell-side coverage overlay for E4 partial models."""
from __future__ import annotations
from typing import Any, Mapping
from .contracts import digest

def bind_coverage(model: Mapping[str, Any], *, valuation_status: str, sell_side_status: str) -> dict[str, Any]:
    if valuation_status not in {"accepted", "missing", "blocked"} or sell_side_status not in {"accepted", "missing", "blocked"}:
        raise ValueError("coverage status is invalid")
    result = dict(model)
    result["sections"] = {**dict(model.get("sections") or {}), "valuation": valuation_status, "sell_side": sell_side_status}
    result["decision_boundary"] = {"tier": "C", "action": "no_action", "target_price": None, "position_range": None}
    result["coverage_binding_hash"] = digest({"model": model.get("report_model_hash"), "valuation": valuation_status, "sell_side": sell_side_status})
    return result
