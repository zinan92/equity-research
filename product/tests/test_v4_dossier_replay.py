from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_replay import build_reader_index, build_replay_receipt, replay_sample  # noqa: E402


class V4ReplayTests(unittest.TestCase):
    def test_three_industries_share_one_replay_contract(self) -> None:
        rows = [
            replay_sample(ticker="000001.SZ", industry="银行", path=ROOT / "artifacts/round7-dossiers/000001.SZ.md"),
            replay_sample(ticker="300750.SZ", industry="电池", path=ROOT / "artifacts/round7-dossiers/300750.SZ.md"),
            replay_sample(ticker="600519.SH", industry="白酒", path=ROOT / "artifacts/round7-dossiers/600519.SH.md"),
        ]
        receipt = build_replay_receipt(rows)
        self.assertEqual(receipt["sample_count"], 3)
        self.assertEqual(receipt["fresh_model_calls"], 0)
        self.assertFalse(receipt["is_live_research"])
        self.assertEqual({row["validation"] for row in receipt["samples"]}, {"passed"})
        html = build_reader_index(receipt)
        self.assertEqual(html.count('<button class="tab'), 3)
        self.assertIn("replay only", html)

    def test_duplicate_ticker_is_rejected(self) -> None:
        row = replay_sample(ticker="600519.SH", industry="白酒", path=ROOT / "artifacts/round7-dossiers/600519.SH.md")
        with self.assertRaisesRegex(ValueError, "unique"):
            build_replay_receipt([row, row])


if __name__ == "__main__":
    unittest.main()
