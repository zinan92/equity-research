from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_page_level_filing_facts import FilingNumericFact  # noqa: E402
from data_core.e4_vertical_degradation import compile_vertical_degradation  # noqa: E402


class VerticalDegradationTest(unittest.TestCase):
    def test_real_page_fact_reaches_b_through_existing_policy(self) -> None:
        fact = FilingNumericFact("300750.SZ", "revenue", 1.0, "official:one", "a" * 64, 9,
                                 "营业总收入", "营业总收入 1", "2026年第一季度", "consolidated", "元", "CNY", "https://static.cninfo.com.cn/a.pdf")
        result = compile_vertical_degradation("300750.SZ", (fact,), known_at="2026-07-28T00:00:00Z")
        self.assertEqual(result["evidence_set"]["status"], "passed")
        self.assertTrue(result["section_contract"]["live_eligible"])
        self.assertEqual(result["section_contract"]["evidence_manifest_hash"], result["evidence_set"]["manifest_hash"])
        self.assertEqual(result["degradation"]["tier"], "B")
        self.assertEqual(result["degradation"]["reasons"], ("partial_or_missing_sections", "investment_action_fields_blocked"))


if __name__ == "__main__":
    unittest.main()
