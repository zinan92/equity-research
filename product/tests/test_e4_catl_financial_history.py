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

    def test_wrapped_capex_row_stays_in_its_explicit_statement_scope(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        consolidated = DocumentPage("doc", 8, digest, "v", "合并现金流量表\n单位：千元\n购建固定资产、无形资产和其他长 42,344,558 31,179,943\n期资产支付的现金", "c", "native", "table")
        parent = DocumentPage("doc", 9, digest, "v", "母公司现金流量表\n单位：千元\n购建固定资产、无形资产和其他长\n2,056,300 3,130,258\n期资产支付的现金", "p", "native", "table")
        parsed = DocumentParseResult("doc", digest, "v", "p", (consolidated, parent), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw)
        capex = [item for item in facts if item.metric == "capital_expenditure"]
        self.assertEqual(len(capex), 1)
        self.assertEqual(capex[0].value, 42_344_558)
        self.assertEqual(capex[0].statement_scope, "consolidated")

    def test_statement_context_and_unit_carry_across_pages_until_next_title(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        title = DocumentPage("doc", 108, digest, "v", "5、合并现金流量表\n单位：万元", "a", "native", "table")
        mixed = DocumentPage("doc", 109, digest, "v", "购建固定资产、无形资产和其他长 4,821,526.81 4,376,777.08\n期资产支付的现金\n6、母公司现金流量表\n单位：万元", "b", "native", "table")
        parent = DocumentPage("doc", 110, digest, "v", "购建固定资产、无形资产和其他长 539,342.45 729,809.66\n期资产支付的现金", "c", "native", "table")
        parsed = DocumentParseResult("doc", digest, "v", "p", (title, mixed, parent), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2022FY", "doc", "https://official.example/doc.pdf"), raw)
        capex = [item for item in facts if item.metric == "capital_expenditure"]
        self.assertEqual(len(capex), 1)
        self.assertEqual(capex[0].value, 4_821_526.81)
        self.assertEqual(capex[0].page_number, 109)
        self.assertEqual(capex[0].statement_scope, "consolidated")
        self.assertEqual(capex[0].unit, "万元")

    def test_missing_extraction_records_keep_a_raw_excerpt(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult
        from data_core.e4_catl_financial_history import _missing_metric_records

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        page = DocumentPage("doc", 1, digest, "v", "合并利润表\n单位：千元\n一、营业总收入 100", "p", "native", "table")
        parsed = DocumentParseResult("doc", digest, "v", "p", (page,), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            missing = _missing_metric_records(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw, {"revenue"})
        operating_cost = next(item for item in missing if item["metric"] == "operating_cost")
        self.assertEqual(operating_cost["reason"], "no_page_bound_consolidated_row")
        self.assertIn("营业总收入", operating_cost["raw_text_excerpt"])


if __name__ == "__main__":
    unittest.main()
