from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from report_contract import (  # noqa: E402
    HistoricalFinancialPeriod,
    ReportContractError,
    ValuationEngineInput,
    ValuationScenarioAssumptions,
    build_financial_bridge,
    run_deterministic_valuation,
)


def period(
    year: int,
    *,
    revenue: float,
    shares: float = 2_400_000_000,
    share_event: bool = False,
) -> HistoricalFinancialPeriod:
    return HistoricalFinancialPeriod(
        period=f"{year}-12-31",
        currency="CNY",
        revenue=revenue,
        ebit=revenue * 0.2,
        tax_rate=0.2,
        depreciation_amortization=revenue * 0.04,
        capital_expenditure=revenue * 0.08,
        change_in_nwc=revenue * 0.01,
        operating_cash_flow=revenue * 0.18,
        net_income=revenue * 0.15,
        cash=1500 + (year - 2024) * 250,
        debt=1000,
        assets=7000 + (year - 2024) * 1000,
        liabilities=3000,
        equity=4000 + (year - 2024) * 1000,
        shares_outstanding=shares,
        share_event=share_event,
    )


def scenario(
    name: str,
    probability: float,
    growth: float,
    margin: float,
) -> ValuationScenarioAssumptions:
    return ValuationScenarioAssumptions(
        name=name,
        probability=probability,
        revenue_growth=(growth,) * 5,
        ebit_margin=(margin,) * 5,
        tax_rate=0.2,
        depreciation_pct_revenue=0.04,
        capex_pct_revenue=0.08,
        nwc_investment_pct_revenue=0.01,
        wacc=0.09,
        terminal_growth=0.03,
    )


def engine_input() -> ValuationEngineInput:
    shares = 2_400_000_000
    price = 250.0
    return ValuationEngineInput(
        ticker="300750.SZ",
        currency="CNY",
        unit_scale=100_000_000,
        current_price=price,
        market_cap=price * shares,
        shares_outstanding=shares,
        historical=(period(2024, revenue=3000), period(2025, revenue=4000)),
        scenarios=(
            scenario("bear", 0.25, 0.03, 0.16),
            scenario("base", 0.50, 0.12, 0.20),
            scenario("bull", 0.25, 0.22, 0.24),
        ),
        peer_ev_ebitda=(14.0, 16.0, 18.0),
        historical_pe=(20.0, 24.0, 28.0),
    )


def test_historical_financial_bridge_balances_and_reconciles_cash_flow() -> None:
    rows = build_financial_bridge(engine_input())

    assert len(rows) == 2
    assert all(item.balance_check == 0 for item in rows)
    latest = rows[-1]
    assert latest.nopat == 640
    assert latest.unlevered_fcf == 440
    assert latest.reported_fcf == 400
    assert latest.cash_conversion == pytest.approx(1.2)
    assert latest.net_debt == -750


def test_bull_base_bear_assumptions_and_outputs_are_auditable() -> None:
    value = engine_input()
    result = run_deterministic_valuation(value)

    assert [item.name for item in result.scenario_results] == ["bear", "base", "bull"]
    assert sum(item.probability for item in result.scenario_results) == 1
    assert [item.per_share_value for item in result.scenario_results] == sorted(
        item.per_share_value for item in result.scenario_results
    )
    assert all(len(item.assumption_hash) == 64 for item in result.scenario_results)
    assert all(len(item.revenues) == len(item.unlevered_fcf) == 5 for item in result.scenario_results)


def test_dcf_reverse_dcf_comps_and_history_share_one_currency_unit_and_identity() -> None:
    result = run_deterministic_valuation(engine_input())

    assert {item.method for item in result.methods} == {
        "probability_weighted_dcf", "peer_ev_ebitda", "historical_pe"
    }
    assert {item.currency for item in result.methods} == {"CNY"}
    assert {item.unit for item in result.methods} == {"CNY/share"}
    assert {item.inputs_hash for item in result.methods} == {result.input_hash}
    assert all(item.per_share_value > 0 for item in result.methods)
    assert -0.5 < result.reverse_dcf_implied_growth < 1.0
    assert result.weighted_dcf_per_share == next(
        item.per_share_value for item in result.methods if item.method == "probability_weighted_dcf"
    )


def test_currency_unit_market_cap_and_share_count_anomalies_fail_closed() -> None:
    value = engine_input()
    wrong_currency = replace(
        value,
        historical=(value.historical[0], replace(value.historical[1], currency="USD")),
    )
    with pytest.raises(ReportContractError, match="currency mismatch"):
        run_deterministic_valuation(wrong_currency)
    with pytest.raises(ReportContractError, match="unit scale"):
        run_deterministic_valuation(replace(value, unit_scale=100_000_000_000))
    with pytest.raises(ReportContractError, match="market cap and share count"):
        run_deterministic_valuation(replace(value, market_cap=value.market_cap * 0.5))

    jumped = replace(value.historical[1], shares_outstanding=value.shares_outstanding * 2)
    with pytest.raises(ReportContractError, match="share-count jump"):
        run_deterministic_valuation(replace(value, historical=(value.historical[0], jumped)))


def test_unbalanced_statement_and_unmarked_share_event_are_rejected() -> None:
    value = engine_input()
    broken = replace(value.historical[1], assets=value.historical[1].assets + 500)
    with pytest.raises(ReportContractError, match="does not balance"):
        run_deterministic_valuation(replace(value, historical=(value.historical[0], broken)))

    split_old = replace(value.historical[0], shares_outstanding=1_200_000_000)
    split_new = replace(value.historical[1], share_event=True)
    allowed = replace(value, historical=(split_old, split_new))
    assert run_deterministic_valuation(allowed).scenario_results


def test_sensitivity_table_is_stable_and_directionally_monotonic() -> None:
    first = run_deterministic_valuation(engine_input())
    second = run_deterministic_valuation(engine_input())

    assert first.sensitivity == second.sensitivity
    assert len(first.sensitivity.wacc_values) == 5
    assert len(first.sensitivity.terminal_growth_values) == 5
    assert all(len(row) == 5 for row in first.sensitivity.per_share_values)
    assert all(list(row) == sorted(row) for row in first.sensitivity.per_share_values)
    for column in range(5):
        values = [row[column] for row in first.sensitivity.per_share_values]
        assert values == sorted(values, reverse=True)


def test_engine_replays_identically_and_hashes_assumption_changes() -> None:
    value = engine_input()
    first = run_deterministic_valuation(value)
    replay = run_deterministic_valuation(value)
    assert first == replay
    assert len(first.input_hash) == len(first.output_hash) == 64

    scenarios = list(value.scenarios)
    scenarios[1] = replace(scenarios[1], revenue_growth=(0.13,) * 5)
    changed = run_deterministic_valuation(replace(value, scenarios=tuple(scenarios)))
    assert changed.input_hash != first.input_hash
    assert changed.output_hash != first.output_hash
    assert changed.weighted_dcf_per_share != first.weighted_dcf_per_share
