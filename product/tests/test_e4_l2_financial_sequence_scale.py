from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_financial_sequence_batch import _page_parse_exception, _retryable_parse_worker_row, _ticker_exception_reports, _timeout_reports, run_financial_sequence_batch  # noqa: E402


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

    def test_ticker_deadline_keeps_all_periods_as_typed_missing(self) -> None:
        reports = _timeout_reports(("2021FY", "2026Q1"), seconds=300)
        self.assertEqual([row["reason"] for row in reports], ["ticker_collection_timeout", "ticker_collection_timeout"])
        self.assertTrue(all("300s" in row["raw_text_excerpt"] for row in reports))

    def test_ticker_worker_exception_keeps_all_periods_as_typed_missing(self) -> None:
        reports = _ticker_exception_reports(("2021FY", "2026Q1"), EOFError("worker pipe closed"))
        self.assertEqual([row["reason"] for row in reports], ["ticker_collection_exception", "ticker_collection_exception"])
        self.assertTrue(all("EOFError" in row["raw_text_excerpt"] for row in reports))

    def test_malformed_pdf_text_is_one_report_gap_and_widened_rows_retry(self) -> None:
        record = _page_parse_exception("2024FY", UnicodeEncodeError("utf-8", "\ud835", 0, 1, "surrogate"), document={"document_id": "official:1"})
        self.assertEqual(record["reason"], "page_parse_exception")
        self.assertEqual(record["document"]["document_id"], "official:1")
        legacy = {"reports": [{"status": "missing", "reason": "ticker_collection_exception", "raw_text_excerpt": "ValueError: isolated page parser failed: UnicodeEncodeError"}] * 6}
        self.assertTrue(_retryable_parse_worker_row(legacy))
