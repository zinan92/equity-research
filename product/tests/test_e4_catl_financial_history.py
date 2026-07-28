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
        capex = [item for item in facts if item.metric == "capital_expenditure" and item.column_identity != "previous_period"]
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
        capex = [item for item in facts if item.metric == "capital_expenditure" and item.column_identity != "previous_period"]
        self.assertEqual(len(capex), 1)
        self.assertEqual(capex[0].value, 4_821_526.81)
        self.assertEqual(capex[0].page_number, 109)
        self.assertEqual(capex[0].statement_scope, "consolidated")
        self.assertEqual(capex[0].unit, "万元")

    def test_bank_consolidated_statement_uses_its_declared_million_unit(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        page = DocumentPage(
            "doc", 120, digest, "v",
            "合并及银行利润表\\n货币单位：人民币百万元\\n本期发生额 上期发生额\\n营业收入 131,442 146,695",
            "bank", "native", "table",
        )
        parsed = DocumentParseResult("doc", digest, "v", "p", (page,), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw)
        revenue = [item for item in facts if item.metric == "revenue"]
        self.assertEqual([(item.statement_scope, item.unit, item.value) for item in revenue], [
            ("consolidated", "人民币百万元", 131_442),
            ("consolidated", "人民币百万元", 146_695),
        ])

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

    def test_balance_identity_detects_a_wrong_column_candidate(self) -> None:
        from data_core.e4_catl_financial_history import OfficialFinancialFact, validate_balance_sheet
        common = dict(ticker="300750.SZ", document_id="doc", raw_hash="a" * 64, page_number=1,
                      quoted_label="x", quoted_anchor="raw", report_period="2025FY", statement_scope="consolidated",
                      unit="千元", currency="CNY", source_url="https://official.example/doc.pdf", column_identity="period_end")
        facts = [OfficialFinancialFact(metric="total_assets", value=100, **common), OfficialFinancialFact(metric="total_liabilities", value=60, **common), OfficialFinancialFact(metric="total_equity", value=40, **common)]
        self.assertEqual(validate_balance_sheet(facts)["status"], "passed")
        facts[-1] = OfficialFinancialFact(metric="total_equity", value=4, **common)
        self.assertEqual(validate_balance_sheet(facts)["status"], "failed")

    def test_headered_two_column_row_keeps_both_period_instances(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult
        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        page = DocumentPage("doc", 7, digest, "v", "合并利润表\n单位：千元\n本期发生额 上期发生额\n一、营业总收入 423,701,834 362,012,554", "t", "native", "table")
        parsed = DocumentParseResult("doc", digest, "v", "p", (page,), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            rows = [item for item in extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw) if item.metric == "revenue"]
        self.assertEqual([(item.report_period, item.column_identity, item.value) for item in rows], [("2025FY", "current_period", 423_701_834), ("2024FY", "previous_period", 362_012_554)])

    def test_cross_year_comparison_keeps_both_source_instances(self) -> None:
        from data_core.e4_catl_financial_history import OfficialFinancialFact, compare_cross_year
        common = dict(ticker="300750.SZ", raw_hash="a" * 64, quoted_label="营收", quoted_anchor="raw", statement_scope="consolidated", unit="千元", currency="CNY", source_url="https://official.example/doc.pdf")
        prior = OfficialFinancialFact(metric="revenue", value=362, document_id="old", page_number=119, report_period="2024FY", column_identity="current_period", **common)
        later = OfficialFinancialFact(metric="revenue", value=362, document_id="new", page_number=116, report_period="2024FY", column_identity="previous_period", **common)
        row = compare_cross_year([later], [prior])[0]
        self.assertEqual(row["status"], "consistent")
        self.assertEqual((row["current_document_id"], row["previous_document_id"]), ("new", "old"))


if __name__ == "__main__":
    unittest.main()
