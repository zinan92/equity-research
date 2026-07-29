from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("l2_m1_verify", ROOT / "scripts" / "verify_e4_l2_m1_financial_batch.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = MODULE; SPEC.loader.exec_module(MODULE)


class FinancialBatchVerificationTest(unittest.TestCase):
    def test_retains_failure_taxonomy_and_official_boundary(self) -> None:
        cohort = [f"{index:06d}.SZ" for index in range(100)]
        sequence = {"schema_version": "e4-financial-sequence-batch-v1", "data_kind": "real", "receipt_hash": "sequence", "cohort": cohort, "periods_attempted": ["2021FY"] * 6, "configured_max_concurrency": 1, "sequential": True, "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True}, "counts": {"available_reports": 1, "missing_reports": 599, "facts": 2}, "tickers": [{"ticker": ticker, "reports": [{"status": "missing", "reason": "official_annual_report_not_captured"}]} for ticker in cohort]}
        identity = {"schema_version": "ashare-security-master-v1", "data_kind": "real", "receipt_hash": "identity", "records": [{"ticker": ticker, "exchange": "SZSE"} for ticker in cohort]}
        result = MODULE.build_summary(sequence, identity)
        self.assertEqual(result["coverage"]["requested_tickers"], 100)
        self.assertEqual(result["missing_reason_counts"], {"official_annual_report_not_captured": 100})
        self.assertTrue(result["truth_boundary"]["missing_is_retained_not_filled"])
