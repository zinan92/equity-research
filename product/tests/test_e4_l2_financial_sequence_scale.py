from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_financial_sequence_batch import run_financial_sequence_batch  # noqa: E402


class FinancialSequenceScaleTest(unittest.TestCase):
    def test_accepts_100_distinct_tickers_with_single_concurrency(self) -> None:
        tickers = tuple(f"{index:06d}.SZ" for index in range(100))
        with tempfile.TemporaryDirectory() as directory:
            result = run_financial_sequence_batch(Path(directory), tickers=tickers, delay_seconds=0, transport=object(), sync=lambda ticker, **_kwargs: (_ for _ in ()).throw(RuntimeError(ticker)))
        self.assertEqual(result["receipt"]["counts"]["tickers"], 100)
        self.assertEqual(result["receipt"]["configured_max_concurrency"], 1)
        self.assertEqual(result["receipt"]["counts"]["missing_reports"], 600)

    def test_rejects_more_than_100_tickers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "1-100"):
                run_financial_sequence_batch(Path(directory), tickers=tuple(f"{index:06d}.SZ" for index in range(101)), delay_seconds=0)
