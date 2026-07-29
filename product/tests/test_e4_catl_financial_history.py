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

    def test_bank_date_columns_and_issuer_specific_labels_are_page_bound(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        page = DocumentPage(
            "doc", 126, digest, "v",
            "合并资产负债表\n（货币单位均以人民币百万元列示）\n2025年12月31日 2024年12月31日\n"
            "资产合计 13,070,523 12,152,036\n负债合计 11,789,624 10,918,561\n归属于本行股东权益合计 1,272,875 1,226,014",
            "bank", "native", "table",
        )
        parsed = DocumentParseResult("doc", digest, "v", "p", (page,), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw)
        self.assertEqual({item.metric for item in facts}, {"total_assets", "total_liabilities", "parent_equity"})
        self.assertTrue(all(item.column_identity in {"current_period", "previous_period"} for item in facts))

    def test_english_statement_context_and_balance_columns_carry_to_next_page(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        header = DocumentPage(
            "doc", 10, digest, "v",
            "1. Consolidated balance sheet\nUnit: RMB\nClosing balance Opening balance",
            "a", "native", "table",
        )
        values = DocumentPage(
            "doc", 11, digest, "v",
            "Total assets 39,038,036,320.92 37,879,046,367.15",
            "b", "native", "table",
        )
        parsed = DocumentParseResult("doc", digest, "v", "p", (header, values), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw)
        self.assertEqual([(item.report_period, item.column_identity, item.value) for item in facts], [
            ("2025FY", "period_end", 39_038_036_320.92),
            ("2024FY", "period_begin", 37_879_046_367.15),
        ])

    def test_chinese_note_reference_is_not_admitted_as_cash_value(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        page = DocumentPage(
            "doc", 84, digest, "v",
            "合并资产负债表\n单位：元\n期末余额 期初余额\n货币资金 六、1 2,924,099,340.75 3,115,628,975.55",
            "a", "native", "table",
        )
        parsed = DocumentParseResult("doc", digest, "v", "p", (page,), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw)
        self.assertEqual([(item.value, item.column_identity) for item in facts], [
            (2_924_099_340.75, "period_end"),
            (3_115_628_975.55, "period_begin"),
        ])

    def test_asset_subtotal_cannot_impersonate_total_assets(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult

        raw = b"%PDF-test"; digest = hashlib.sha256(raw).hexdigest()
        page = DocumentPage(
            "doc", 9, digest, "v",
            "合并资产负债表\n单位：元\n期末余额 期初余额\n流动资产合计 15,830 13,898\n资产合计 35,829 33,347",
            "a", "native", "table",
        )
        parsed = DocumentParseResult("doc", digest, "v", "p", (page,), (), ())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document", return_value=parsed):
            facts = extract_report_facts(OfficialReport("2025FY", "doc", "https://official.example/doc.pdf"), raw)
        total_assets = [(item.metric, item.value) for item in facts if item.metric == "total_assets"]
        self.assertEqual(total_assets, [
            ("total_assets", 35_829), ("total_assets", 33_347),
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

    def test_quarter_end_columns_are_not_opening_columns(self) -> None:
        from unittest.mock import patch
        from data_core.document_intelligence import DocumentPage, DocumentParseResult
        raw=b"%PDF-test"; digest=hashlib.sha256(raw).hexdigest()
        page=DocumentPage("1225107946",5,digest,"v","合并资产负债表\n单位：千元\n项目 期末余额 期初余额\n货币资金 351,997,422 333,512,927\n流动资产合计 692,498,192 638,481,543\n流动负债合计 434,010,194 399,625,988","x","native","table")
        parsed=DocumentParseResult("1225107946",digest,"v","p",(page,),(),())
        with patch("data_core.e4_catl_financial_history.parse_pdf_document",return_value=parsed): facts=extract_report_facts(OfficialReport("2026Q1","1225107946","https://static.cninfo.com.cn/finalpage/2026-04-16/1225107946.PDF"),raw)
        values={item.metric:item.value for item in facts if item.column_identity=="period_end"}
        self.assertEqual(values["cash"],351_997_422);self.assertEqual(values["current_assets"],692_498_192);self.assertEqual(values["current_liabilities"],434_010_194)

    def test_same_statement_mixed_column_identity_fails(self) -> None:
        from data_core.e4_catl_financial_history import OfficialFinancialFact, validate_statement_column_consistency
        common=dict(ticker="300750.SZ",document_id="doc",raw_hash="a"*64,page_number=5,quoted_label="x",quoted_anchor="raw",report_period="2026Q1",statement_scope="consolidated",unit="千元",currency="CNY",source_url="https://official.example/doc.pdf")
        facts=[OfficialFinancialFact(metric="cash",value=1,column_identity="period_begin",**common),OfficialFinancialFact(metric="current_assets",value=2,column_identity="period_end",**common),OfficialFinancialFact(metric="current_liabilities",value=1,column_identity="period_end",**common)]
        self.assertEqual(validate_statement_column_consistency(facts)["status"],"failed")

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
