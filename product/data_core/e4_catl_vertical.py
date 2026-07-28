"""Evidence-bound CATL vertical adapter; inputs remain runtime-only."""
from __future__ import annotations

from dataclasses import asdict, replace
from statistics import pstdev
from typing import Any, Mapping

from report_contract import HistoricalFinancialPeriod, ValuationEngineInput, ValuationScenarioAssumptions, run_deterministic_valuation
from .decision_policy import DecisionInput, decide

_REQUIRED = ("revenue", "operating_profit", "income_tax_expense", "total_profit", "capital_expenditure", "operating_cash_flow", "net_profit_parent", "cash", "total_assets", "total_liabilities", "total_equity", "shares_outstanding", "depreciation_fixed_assets", "amortization_intangible", "inventory_cashflow_change", "receivables_cashflow_change", "payables_cashflow_change", "short_term_borrowings", "long_term_borrowings")
_UNIT_SCALE = {"元": 1, "千元": 1_000, "万元": 10_000}


def _money(fact: Mapping[str, Any]) -> float:
    unit = str(fact.get("unit"));
    if unit not in _UNIT_SCALE:
        raise ValueError(f"unsupported financial unit: {unit}")
    return float(fact["value"]) * _UNIT_SCALE[unit] / 100_000_000


def _historical(history: Mapping[str, Any]) -> tuple[tuple[HistoricalFinancialPeriod, ...], list[dict[str, Any]]]:
    periods = []; missing = []
    for report in history.get("reports") or ():
        if not str(report.get("period", "")).endswith("FY"):
            continue
        facts = {item["metric"]: item for item in report.get("facts") or ()}
        gaps = [key for key in _REQUIRED if key not in facts]
        if gaps:
            missing.append({"period": report.get("period"), "missing_inputs": gaps, "raw_missing": report.get("missing_metrics") or []}); continue
        revenue = _money(facts["revenue"]); operating_profit = _money(facts["operating_profit"])
        total_profit = _money(facts["total_profit"]); tax_rate = _money(facts["income_tax_expense"]) / total_profit if total_profit else 0
        periods.append(HistoricalFinancialPeriod(
            period=str(report["period"]).replace("FY", "-12-31"), currency="CNY", revenue=revenue,
            ebit=operating_profit, tax_rate=max(0, min(1, tax_rate)),
            depreciation_amortization=_money(facts["depreciation_fixed_assets"]) + _money(facts["amortization_intangible"]),
            capital_expenditure=_money(facts["capital_expenditure"]),
            # Cash-flow supplementary rows are effects on cash; invert their sum
            # to retain C2's 'investment in working capital' sign convention.
            change_in_nwc=-sum(_money(facts[key]) for key in ("inventory_cashflow_change", "receivables_cashflow_change", "payables_cashflow_change")),
            operating_cash_flow=_money(facts["operating_cash_flow"]), net_income=_money(facts["net_profit_parent"]),
            cash=_money(facts["cash"]), debt=_money(facts["short_term_borrowings"]) + _money(facts["long_term_borrowings"]),
            assets=_money(facts["total_assets"]), liabilities=_money(facts["total_liabilities"]), equity=_money(facts["total_equity"]),
            shares_outstanding=float(facts["shares_outstanding"]["value"]),
        ))
    adjusted = []
    previous = None
    for period in periods:
        event = previous is not None and abs(period.shares_outstanding / previous - 1) > .5
        adjusted.append(replace(period, share_event=event))
        previous = period.shares_outstanding
    return tuple(adjusted), missing


def _scenarios(periods: tuple[HistoricalFinancialPeriod, ...]) -> tuple[tuple[ValuationScenarioAssumptions, ...], dict[str, Any]]:
    growth = (periods[-1].revenue / periods[0].revenue) ** (1 / (len(periods) - 1)) - 1
    margin = periods[-1].ebit / periods[-1].revenue
    conversion = periods[-1].operating_cash_flow / periods[-1].net_income
    assumptions = {"assumption_status": "provisional_unreviewed", "mechanical": {"historical_revenue_cagr": growth, "latest_ebit_margin": margin, "latest_cash_conversion": conversion}, "provisional": {"wacc": 0.09, "terminal_growth": 0.03, "forecast_years": 5, "reason": "industry-default ranges require analyst review"}}
    configs = (("bear", .25, growth - .08, margin - .04), ("base", .5, growth - .03, margin), ("bull", .25, growth + .03, margin + .03))
    return tuple(ValuationScenarioAssumptions(name, probability, (rate,) * 5, (operating_margin,) * 5, periods[-1].tax_rate, periods[-1].depreciation_amortization / periods[-1].revenue, periods[-1].capital_expenditure / periods[-1].revenue, periods[-1].change_in_nwc / periods[-1].revenue, .09, .03) for name, probability, rate, operating_margin in configs), assumptions


def _scores(history: Mapping[str, Any], periods: tuple[HistoricalFinancialPeriod, ...], market: Mapping[str, Any]) -> tuple[dict[str, float | None], dict[str, Any]]:
    annual_reports = [item for item in history["reports"] if str(item.get("period", "")).endswith("FY")]
    latest_facts = {item["metric"]: item for item in annual_reports[-1].get("facts") or ()}
    gross_margin = 1 - _money(latest_facts["operating_cost"]) / periods[-1].revenue if "operating_cost" in latest_facts else None
    net_margin = periods[-1].net_income / periods[-1].revenue
    roe = periods[-1].net_income / periods[-1].equity
    conversion = periods[-1].operating_cash_flow / periods[-1].net_income
    quality_inputs = [gross_margin, net_margin, roe, conversion]
    quality = None if any(value is None for value in quality_inputs) else sum((min(max(gross_margin / .4, 0), 1), min(max(net_margin / .15, 0), 1), min(max(roe / .2, 0), 1), min(max(conversion, 0), 1))) / 4
    leverage = periods[-1].debt / periods[-1].assets
    margins = [item.net_income / item.revenue for item in periods]
    volatility = pstdev(margins)
    risk = (min(max(leverage / .6, 0), 1) + min(max(volatility / .2, 0), 1)) / 2
    quote = market.get("quote") or {}; bars = market.get("daily_bars") or []
    daily_values = [float(row.get("close", 0)) * float(row.get("volume", 0)) for row in bars if row.get("close") and row.get("volume")]
    liquidity = None if not quote.get("market_cap") or not daily_values else (min(float(quote["market_cap"]) / 5000, 1) + min((sum(daily_values) / len(daily_values)) / 100_000_000, 1)) / 2
    return {"quality": quality, "risk": risk, "liquidity": liquidity}, {"assumption_status": "provisional_unreviewed", "formula": {"quality": "mean(clamp(gross_margin/40%), clamp(net_margin/15%), clamp(ROE/20%), clamp(CFO/net_income))", "risk": "mean(clamp(debt/assets/60%), clamp(pstdev(net_margins)/20%))", "liquidity": "mean(clamp(market_cap/5000亿元), clamp(avg_30d_close_times_volume/1亿元))"}, "inputs": {"gross_margin": gross_margin, "net_margin": net_margin, "roe": roe, "cash_conversion": conversion, "leverage": leverage, "earnings_margin_volatility": volatility, "market_cap": quote.get("market_cap"), "daily_value_count": len(daily_values)}}


def compile_vertical(history: Mapping[str, Any], market: Mapping[str, Any], *, ticker: str, context_manifest_hash: str, dossier_id: str) -> dict[str, Any]:
    periods, missing = _historical(history); quote = market.get("quote") or {}
    if len(periods) < 5 or missing or not quote.get("last_price") or not quote.get("market_cap"):
        decision = decide(DecisionInput(ticker, context_manifest_hash, dossier_id, float(quote["last_price"]) if quote.get("last_price") else None, None, None, None, None, False, 0, 0, 1))
        return {"ticker": ticker, "financial_history_status": "partial", "valuation": {"status": "blocked", "valuation_completeness": "missing", "methods_run": [], "methods_missing": ["probability_weighted_dcf: page-bound C2 inputs incomplete", "peer_ev_ebitda: not collected", "historical_pe: canonical market-history receipt not supplied"], "missing_history": missing}, "market_snapshot": dict(quote), "current_market": dict(quote), "decision": {**asdict(decision), "valuation_completeness": "missing"}}
    scenarios, assumptions = _scenarios(periods)
    result = run_deterministic_valuation(ValuationEngineInput(ticker, "CNY", 100_000_000, float(quote["last_price"]), float(quote["market_cap"]) * 100_000_000, periods[-1].shares_outstanding, periods, scenarios, (), ()))
    target = result.weighted_dcf_per_share
    # Provisional assumptions intentionally hold policy coverage false.
    scores, score_receipt = _scores(history, periods, market)
    decision = decide(DecisionInput(ticker, context_manifest_hash, dossier_id, float(quote["last_price"]), target, scores["quality"], scores["risk"], scores["liquidity"], False, 0, 0, 1))
    return {"ticker": ticker, "financial_history_status": "available", "valuation": {"status": "compiled", "valuation_completeness": result.valuation_completeness, "methods_run": [item.method for item in result.methods], "methods_missing": list(result.methods_missing), "target_price": target, "assumptions": assumptions, "receipt": asdict(result)}, "scores": scores, "score_receipt": score_receipt, "market_snapshot": dict(quote), "current_market": dict(quote), "decision": {**asdict(decision), "valuation_completeness": result.valuation_completeness}}


def compile_catl_vertical(history: Mapping[str, Any], market: Mapping[str, Any], *, context_manifest_hash: str, dossier_id: str) -> dict[str, Any]:
    return compile_vertical(history, market, ticker="300750.SZ", context_manifest_hash=context_manifest_hash, dossier_id=dossier_id)
