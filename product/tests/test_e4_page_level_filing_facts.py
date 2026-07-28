from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_page_level_filing_facts import FilingNumericFact  # noqa: E402


class FilingNumericFactTest(unittest.TestCase):
    def test_requires_page_identity_and_accounting_context(self) -> None:
        fact = FilingNumericFact("300750.SZ", "revenue", 1.0, "official:1", "a" * 64, 1,
                                 "营业收入", "营业收入 1", "2024年度", "consolidated", "元", "CNY", "https://example.com/a.pdf")
        fact.validate()
        with self.assertRaisesRegex(ValueError, "missing"):
            FilingNumericFact("300750.SZ", "revenue", 1.0, "official:1", "a" * 64, 1,
                              "", "anchor", "2024年度", "consolidated", "元", "CNY", "https://example.com/a.pdf").validate()


if __name__ == "__main__":
    unittest.main()
