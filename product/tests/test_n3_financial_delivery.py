from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
import unittest

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.n3_financial_delivery import run_financial_delivery_batch  # noqa: E402


REQUIRED = ("quote", "daily_bars", "fundamentals", "balance_sheet", "income_statement", "cash_flow")


def good_worker(ticker, queue):
    queue.put({"status": "ok", "summary": {
        "instrument": {"ticker": ticker},
        "fundamentals": [{"report_period": "2025-12-31", "announced_at": "2026-03-30"}],
        "data_gaps": [],
        "sources": {key: {"data_kind": "real", "publishable": True, "selected_source": key, "raw_hash": "a" * 64, "manifest_hash": "b" * 64, "known_at": "2026-07-24T00:00:00Z"} for key in REQUIRED},
    }})


def period_missing_worker(ticker, queue):
    queue.put({"status": "ok", "summary": {
        "instrument": {"ticker": ticker}, "fundamentals": [], "data_gaps": [],
        "sources": {key: {"data_kind": "real", "publishable": True, "selected_source": key, "raw_hash": "a" * 64, "manifest_hash": "b" * 64, "known_at": "2026-07-24T00:00:00Z"} for key in REQUIRED},
    }})


class N3FinancialDeliveryTest(unittest.TestCase):
    def test_real_input_receipt_has_20_period_bound_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = run_financial_delivery_batch(Path(temp), collector_timeout_seconds=3, worker=good_worker)
            receipt = result["receipt"]
            self.assertEqual(receipt["counts"], {"requested": 20, "resolved": 20, "available": 20, "gaps": 0})
            self.assertTrue(all(row["report_period"] == "2025-12-31" for row in receipt["tickers"]))
            self.assertFalse(receipt["truth_boundary"]["counts_as_valuation"])

    def test_missing_financial_period_is_an_explicit_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = run_financial_delivery_batch(Path(temp), collector_timeout_seconds=3, worker=period_missing_worker)
            self.assertEqual(result["receipt"]["counts"]["available"], 0)
            self.assertTrue(all("missing_latest_financial_period" in row["blockers"] for row in result["receipt"]["tickers"]))


if __name__ == "__main__":
    unittest.main()
