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
            replay_sample(ticker="002594.SZ", industry="汽车制造", path=ROOT / "docs/dossier-production/samples/002594.SZ-v1.md"),
            replay_sample(ticker="300308.SZ", industry="光模块", path=ROOT / "docs/dossier-production/samples/300308.SZ-v1.md"),
            replay_sample(ticker="NVDA", industry="AI芯片", path=ROOT / "docs/dossier-production/samples/nvda-v1.md"),
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
        row = replay_sample(ticker="NVDA", industry="AI芯片", path=ROOT / "docs/dossier-production/samples/nvda-v1.md")
        with self.assertRaisesRegex(ValueError, "unique"):
            build_replay_receipt([row, row])


if __name__ == "__main__":
    unittest.main()
