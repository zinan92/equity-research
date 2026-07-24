from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_market_snapshot import _compare_change, _compare_price, _compare_valuations, combine_reports


class ValidateMarketSnapshotTest(unittest.TestCase):
    def test_out_of_window_exact_value_is_explained_residual(self):
        result = _compare_price(
            100.0,
            {"2026-06-22": 100.0, "2026-07-01": 94.0},
            "2026-06-30",
            "2026-07-02",
        )
        self.assertEqual(result["status"], "explained_residual")
        self.assertEqual(result["reason"], "benchmark_as_of_outside_declared_window")
        self.assertEqual(result["matched_trade_date"], "2026-06-22")
        self.assertEqual(result["declared_window_closest"]["trade_date"], "2026-07-01")

    def test_unseen_value_remains_outlier(self):
        result = _compare_price(
            100.0,
            {"2026-06-22": 90.0, "2026-07-01": 94.0},
            "2026-06-30",
            "2026-07-02",
        )
        self.assertEqual(result["status"], "outlier")

    def test_peg_with_undisclosed_benchmark_growth_basis_is_not_claimed_equal(self):
        result = _compare_valuations(
            {"peg": 1.0},
            {
                "values": {"peg": 1.0},
                "definitions": {"peg": "SEC_TTM_growth"},
            },
        )
        self.assertEqual(result["peg"]["status"], "definition_mismatch")

    def test_change_uses_previous_source_trading_day(self):
        result = _compare_change(
            10.0,
            {"2026-06-19": 100.0, "2026-06-22": 110.0},
            "2026-06-22",
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["previous_trade_date"], "2026-06-19")

    def test_change_reference_difference_is_not_hidden_by_wider_tolerance(self):
        result = _compare_change(
            2.0,
            {"2026-06-19": 100.0, "2026-06-22": 110.0},
            "2026-06-22",
        )
        self.assertEqual(result["status"], "reference_mismatch")
        self.assertEqual(
            result["reason"],
            "benchmark_previous_close_basis_differs_from_source_daily_close",
        )

    def test_combine_preserves_residual_and_valuation_counts(self):
        base = {
            "schema_version": "market-snapshot-validation-v2",
            "window_start": "2026-06-30",
            "window_end": "2026-07-02",
            "price_tolerance": 0.005,
            "sec_enabled": True,
            "sec_ticker_index_raw_hash": "a" * 64,
            "frozen_fx_count": 1,
            "historical_valuation_policy": "no bars",
        }
        first = {
            **base,
            "companies": [
                {
                    "ticker": "AAA",
                    "price": {"status": "pass"},
                    "change": {"status": "pass"},
                    "valuation": {
                        "mcap": {"status": "pass"},
                        "pe": {"status": "outlier"},
                    },
                }
            ],
        }
        second = {
            **base,
            "companies": [
                {
                    "ticker": "BBB",
                    "price": {"status": "explained_residual"},
                    "change": {"status": "outlier"},
                    "valuation": {
                        "mcap": {"status": "missing_historical_source"},
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, payload in enumerate((first, second)):
                path = Path(directory) / f"{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths.append(path)
            combined = combine_reports(paths)
        self.assertEqual(combined["companies_checked"], 2)
        self.assertEqual(combined["price_pass_count"], 1)
        self.assertEqual(combined["price_explained_residual_count"], 1)
        self.assertEqual(combined["change_pass_count"], 1)
        self.assertEqual(combined["change_outlier_count"], 1)
        self.assertEqual(combined["valuation_pass_count"], 1)
        self.assertEqual(combined["valuation_outlier_count"], 1)
        self.assertEqual(combined["valuation_missing_count"], 1)


if __name__ == "__main__":
    unittest.main()
