"""Industry-specific valuation model selection with review and provenance gates.

The profiles select a calculation family; they do not grant a report section,
Tier, target price, position or action.  Facts and market data must arrive
through the existing receipt-bound adapters before a caller can use a result.
"""
from __future__ import annotations

from dataclasses import asdict
from statistics import median
from typing import Any, Mapping

from report_contract import ValuationEngineInput, ValuationMethodResult, run_deterministic_valuation

from .contracts import digest

PROFILE_MANUFACTURING = "manufacturing"
PROFILE_CONSUMER = "consumer"
PROFILE_BANK = "bank"
_REVIEW_STATES = {"unreviewed", "human_reviewed"}


def profile_requirements(profile_id: str) -> tuple[str, ...]:
    requirements = {
        PROFILE_MANUFACTURING: ("engine_input", "source_receipts", "assumption_review_status"),
        PROFILE_CONSUMER: (
            "engine_input",
            "source_receipts",
            "assumption_review_status",
            "peer_pe",
            "volume_price_mix",
            "channel_inventory",
            "cash_conversion",
            "payout_policy",
        ),
        PROFILE_BANK: (
            "source_receipts",
            "assumption_review_status",
            "book_value",
            "shares_outstanding",
            "roe",
            "cost_of_equity",
            "payout_ratio",
            "terminal_growth",
            "peer_pb",
            "peer_bank_set",
            "cet1_ratio",
            "total_capital_ratio",
            "rwa",
            "nim",
            "credit_cost",
            "npl_ratio",
        ),
    }
    if profile_id not in requirements:
        raise ValueError(f"unknown valuation profile: {profile_id}")
    return requirements[profile_id]


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != () and value != [] and value != {}


def _source_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("valuation profile requires receipt-bound source identities")
    identifiers = []
    for name, item in sorted(value.items()):
        if not isinstance(item, Mapping) or not str(item.get("receipt_id") or "").strip():
            raise ValueError(f"valuation source receipt is missing for {name}")
        identifiers.append(str(item["receipt_id"]))
    return tuple(identifiers)


def _review_state(value: Any) -> str:
    if value not in _REVIEW_STATES:
        raise ValueError("valuation assumption review status must be unreviewed or human_reviewed")
    return str(value)


def _method(method: str, value: float, currency: str, input_hash: str) -> dict[str, Any]:
    if value <= 0:
        raise ValueError(f"{method} produced a nonpositive per-share value")
    return asdict(ValuationMethodResult(method, round(value, 6), currency, f"{currency}/share", input_hash))


def _result(
    profile_id: str,
    *,
    status: str,
    reasons: list[str],
    methods: list[dict[str, Any]],
    source_ids: tuple[str, ...],
    model_family: str,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "profile_id": profile_id,
        "status": status,
        "reasons": reasons,
        "model_family": model_family,
        "methods": methods,
        "source_receipt_ids": list(source_ids),
        "input_hash": digest({key: value for key, value in inputs.items() if key != "engine_input"}),
        "truth_boundary": {
            "does_not_change_section_contract": True,
            "does_not_change_tier": True,
            "does_not_surface_target_price": True,
            "does_not_surface_position_or_action": True,
        },
    }
    payload["output_hash"] = digest(payload)
    return payload


def _blocked(profile_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in profile_requirements(profile_id) if not _present(inputs.get(key))]
    return _result(
        profile_id,
        status="blocked",
        reasons=[f"missing_{key}" for key in missing],
        methods=[],
        source_ids=(),
        model_family="not_selected",
        inputs=inputs,
    )


def _manufacturing(inputs: Mapping[str, Any], source_ids: tuple[str, ...], review: str) -> dict[str, Any]:
    engine = inputs["engine_input"]
    if not isinstance(engine, ValuationEngineInput):
        raise ValueError("manufacturing profile requires ValuationEngineInput")
    valuation = run_deterministic_valuation(engine)
    methods = [asdict(item) for item in valuation.methods]
    status = "available" if review == "human_reviewed" else "partial"
    reasons = [] if status == "available" else ["pending_assumption_review"]
    return _result(
        PROFILE_MANUFACTURING,
        status=status,
        reasons=reasons,
        methods=methods,
        source_ids=source_ids,
        model_family="manufacturing_fcff_dcf",
        inputs=inputs,
    )


def _consumer(inputs: Mapping[str, Any], source_ids: tuple[str, ...], review: str) -> dict[str, Any]:
    engine = inputs["engine_input"]
    if not isinstance(engine, ValuationEngineInput):
        raise ValueError("consumer profile requires ValuationEngineInput")
    valuation = run_deterministic_valuation(engine)
    latest = engine.historical[-1]
    eps = latest.net_income * engine.unit_scale / engine.shares_outstanding
    peer_pe = tuple(float(value) for value in inputs["peer_pe"])
    if not peer_pe or any(value <= 0 for value in peer_pe):
        raise ValueError("consumer peer PE inputs must be positive")
    methods = [asdict(item) for item in valuation.methods]
    methods.extend(
        [
            _method("consumer_historical_pe", median(engine.historical_pe) * eps, engine.currency, valuation.input_hash),
            _method("consumer_peer_pe", median(peer_pe) * eps, engine.currency, valuation.input_hash),
        ]
    )
    status = "available" if review == "human_reviewed" else "partial"
    reasons = [] if status == "available" else ["pending_assumption_review"]
    return _result(
        PROFILE_CONSUMER,
        status=status,
        reasons=reasons,
        methods=methods,
        source_ids=source_ids,
        model_family="consumer_dcf_historical_pe_peer_pe",
        inputs=inputs,
    )


def _bank(inputs: Mapping[str, Any], source_ids: tuple[str, ...], review: str) -> dict[str, Any]:
    values = {
        key: float(inputs[key])
        for key in profile_requirements(PROFILE_BANK)
        if key not in {"source_receipts", "assumption_review_status", "peer_bank_set"}
    }
    if any(value <= 0 for value in values.values()):
        raise ValueError("bank valuation inputs must be positive")
    if not 0 < values["payout_ratio"] <= 1 or values["terminal_growth"] >= values["cost_of_equity"]:
        raise ValueError("bank payout, cost of equity or terminal growth is invalid")
    if values["npl_ratio"] >= 1 or values["cet1_ratio"] >= 1 or values["total_capital_ratio"] >= 1:
        raise ValueError("bank regulatory ratios must be expressed as decimals below one")
    book_per_share = values["book_value"] / values["shares_outstanding"]
    residual_income = book_per_share + (
        (values["roe"] - values["cost_of_equity"]) * book_per_share
        / (values["cost_of_equity"] - values["terminal_growth"])
    )
    dividend_discount = (
        book_per_share
        * values["roe"]
        * values["payout_ratio"]
        * (1 + values["terminal_growth"])
        / (values["cost_of_equity"] - values["terminal_growth"])
    )
    input_hash = digest(inputs)
    methods = [
        _method("bank_residual_income", residual_income, str(inputs.get("currency") or "CNY"), input_hash),
        _method("bank_dividend_discount", dividend_discount, str(inputs.get("currency") or "CNY"), input_hash),
        _method("bank_peer_price_to_book", book_per_share * values["peer_pb"], str(inputs.get("currency") or "CNY"), input_hash),
    ]
    status = "available" if review == "human_reviewed" else "partial"
    reasons = [] if status == "available" else ["pending_assumption_review"]
    return _result(
        PROFILE_BANK,
        status=status,
        reasons=reasons,
        methods=methods,
        source_ids=source_ids,
        model_family="bank_residual_income_and_dividend_discount",
        inputs=inputs,
    )


def compile_valuation_profile(profile_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one profile without falling back across sector model families."""
    profile_requirements(profile_id)
    if any(not _present(inputs.get(key)) for key in profile_requirements(profile_id)):
        return _blocked(profile_id, inputs)
    source_ids = _source_ids(inputs["source_receipts"])
    review = _review_state(inputs["assumption_review_status"])
    if profile_id == PROFILE_MANUFACTURING:
        return _manufacturing(inputs, source_ids, review)
    if profile_id == PROFILE_CONSUMER:
        return _consumer(inputs, source_ids, review)
    return _bank(inputs, source_ids, review)
