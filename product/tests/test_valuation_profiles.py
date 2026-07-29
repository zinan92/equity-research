from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.valuation_profiles import (  # noqa: E402
    PROFILE_BANK,
    PROFILE_CONSUMER,
    PROFILE_MANUFACTURING,
    compile_valuation_profile,
)
from report_contract import HistoricalFinancialPeriod, ValuationEngineInput, ValuationScenarioAssumptions  # noqa: E402


def _engine() -> ValuationEngineInput:
    period = lambda year, revenue: HistoricalFinancialPeriod(
        period=f"{year}-12-31", currency="CNY", revenue=revenue, ebit=revenue * 0.2,
        tax_rate=0.2, depreciation_amortization=revenue * 0.04,
        capital_expenditure=revenue * 0.08, change_in_nwc=revenue * 0.01,
        operating_cash_flow=revenue * 0.18, net_income=revenue * 0.15,
        cash=1500, debt=1000, assets=7000, liabilities=3000, equity=4000,
        shares_outstanding=2_400_000_000,
    )
    scenario = lambda name, probability, growth, margin: ValuationScenarioAssumptions(
        name, probability, (growth,) * 5, (margin,) * 5, 0.2, 0.04, 0.08, 0.01, 0.09, 0.03
    )
    return ValuationEngineInput(
        ticker="300750.SZ", currency="CNY", unit_scale=100_000_000, current_price=250,
        market_cap=600_000_000_000, shares_outstanding=2_400_000_000,
        historical=(period(2024, 3000), period(2025, 4000)),
        scenarios=(scenario("bear", 0.25, 0.03, 0.16), scenario("base", 0.5, 0.12, 0.2), scenario("bull", 0.25, 0.22, 0.24)),
        peer_ev_ebitda=(14, 16, 18), historical_pe=(20, 24, 28),
    )


class ValuationProfilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = {
            "official_financials": {"receipt_id": "official:financial:v1"},
            "canonical_market": {"receipt_id": "canonical:market:v1"},
            "assumptions": {"receipt_id": "analyst:assumptions:v1"},
        }

    def test_manufacturing_requires_review_before_available(self) -> None:
        result = compile_valuation_profile(
            PROFILE_MANUFACTURING,
            {"engine_input": _engine(), "source_receipts": self.sources, "assumption_review_status": "unreviewed"},
        )
        self.assertEqual(result["status"], "partial")
        self.assertIn("pending_assumption_review", result["reasons"])
        self.assertEqual(result["model_family"], "manufacturing_fcff_dcf")
        self.assertTrue(result["truth_boundary"]["does_not_surface_target_price"])

    def test_consumer_adds_historical_and_peer_pe_cross_checks(self) -> None:
        result = compile_valuation_profile(
            PROFILE_CONSUMER,
            {
                "engine_input": _engine(), "source_receipts": self.sources, "assumption_review_status": "human_reviewed",
                "peer_pe": (22, 26), "volume_price_mix": "receipt:driver", "channel_inventory": "receipt:channel",
                "cash_conversion": "receipt:cash", "payout_policy": "receipt:payout",
            },
        )
        self.assertEqual(result["status"], "available")
        self.assertTrue({"consumer_historical_pe", "consumer_peer_pe"}.issubset({row["method"] for row in result["methods"]}))

    def test_bank_never_calls_manufacturing_dcf(self) -> None:
        result = compile_valuation_profile(
            PROFILE_BANK,
            {
                "source_receipts": self.sources, "assumption_review_status": "human_reviewed", "currency": "CNY",
                "book_value": 4_000_000_000, "shares_outstanding": 1_000_000_000, "roe": 0.12,
                "cost_of_equity": 0.10, "payout_ratio": 0.3, "terminal_growth": 0.03, "peer_pb": 0.8,
                "peer_bank_set": ("600000.SH", "600036.SH"),
                "cet1_ratio": 0.11, "total_capital_ratio": 0.14, "rwa": 8_000_000_000,
                "nim": 0.02, "credit_cost": 0.006, "npl_ratio": 0.012,
            },
        )
        self.assertEqual(result["model_family"], "bank_residual_income_and_dividend_discount")
        self.assertNotIn("dcf", " ".join(row["method"] for row in result["methods"]))

    def test_missing_inputs_remain_blocked(self) -> None:
        result = compile_valuation_profile(PROFILE_BANK, {"source_receipts": self.sources})
        self.assertEqual(result["status"], "blocked")
        self.assertIn("missing_book_value", result["reasons"])
