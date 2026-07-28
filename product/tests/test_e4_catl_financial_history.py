from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_catl_financial_history import OfficialReport, extract_report_facts  # noqa: E402


class CatlHistoryTest(unittest.TestCase):
    def test_only_consolidated_page_rows_are_admitted(self) -> None:
        # A compact fake PDF cannot exercise the parser; this integration test
        # intentionally protects the selection rules with a patched parse path.
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"
        digest = hashlib.sha256(raw).hexdigest()
        page = DocumentPage("doc", 7, digest, "v", "合并利润表\n单位：千元\n一、营业总收入 100 90\n其中：营业成本 60 55", "t", "native", "table")
        parsed = DocumentParseResult("doc", digest, "v", "p", (page,), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw)
        self.assertEqual({item.metric for item in facts}, {"revenue", "operating_cost"})
        self.assertTrue(all(item.statement_scope == "consolidated" and item.unit == "千元" for item in facts))


if __name__ == "__main__":
    unittest.main()
