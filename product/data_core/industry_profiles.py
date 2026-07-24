"""Declarative industry profiles on the single canonical report contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from report_contract import MODULE_SPECS


@dataclass(frozen=True)
class IndustryProfile:
    profile_id: str
    name: str
    required_inputs: tuple[str, ...]
    kpis: tuple[str, ...]
    valuation_focus: tuple[str, ...]
    missing_policy: str


PROFILES = {
    "battery": IndustryProfile("battery", "电池", ("capacity", "utilization", "shipment", "pricing", "cash_flow"), ("capacity_utilization", "unit_margin", "shipment_growth", "inventory_days", "operating_cash_conversion"), ("earnings_multiple", "capacity_cycle", "free_cash_flow"), "Missing capacity, shipment or pricing evidence keeps valuation and decision modules partial."),
    "consumer": IndustryProfile("consumer", "消费", ("same_store_sales", "channel_mix", "brand_investment", "inventory", "cash_flow"), ("same_store_sales_growth", "gross_margin", "inventory_turnover", "channel_mix", "cash_conversion"), ("earnings_multiple", "brand_premium", "free_cash_flow"), "Missing demand, channel or inventory evidence keeps thesis and valuation modules partial."),
    "bank": IndustryProfile("bank", "银行", ("net_interest_margin", "asset_quality", "capital", "loan_growth", "liquidity"), ("net_interest_margin", "nonperforming_loan_ratio", "coverage_ratio", "capital_adequacy", "loan_growth"), ("price_to_book", "return_on_equity", "dividend_yield"), "Missing asset-quality, capital or liquidity evidence blocks valuation and any position conclusion."),
}


def profile_contract(profile_id: str, inputs: Mapping[str, object]) -> dict[str, object]:
    profile = PROFILES.get(profile_id)
    if profile is None:
        raise ValueError("unknown industry profile")
    missing = tuple(key for key in profile.required_inputs if inputs.get(key) in (None, ""))
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "canonical_modules": tuple(spec.id for spec in MODULE_SPECS),
        "kpis": profile.kpis,
        "valuation_focus": profile.valuation_focus,
        "missing_inputs": missing,
        "status": "available" if not missing else "partial",
        "missing_policy": profile.missing_policy,
    }
