from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))
from data_core.e4_catl_vertical import compile_vertical  # noqa: E402


class M1DecisionInputsTest(unittest.TestCase):
    def test_real_market_inputs_survive_blocked_valuation(self):
        history = {"reports": [{"period": "2025FY", "facts": []}]}
        market = {"quote": {"last_price": 100, "market_cap": 6000}, "daily_bars": [{"close": 100, "volume": 2_000_000}]}
        row = compile_vertical(history, market, ticker="300750.SZ", context_manifest_hash="a" * 64, dossier_id="dossier")
        self.assertEqual(row["decision"]["reasons"], ("insufficient_evidence_coverage", "missing_quality_risk_or_liquidity"))
        self.assertEqual(row["market_snapshot"]["last_price"], 100)
        self.assertIn("score_receipt", row)
