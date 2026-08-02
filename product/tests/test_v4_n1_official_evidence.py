from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.contracts import digest  # noqa: E402
from data_core.v4_n1_official_evidence import (  # noqa: E402
    OfficialEvidenceError,
    build_packet,
    materialize_financial_receipt,
    merge_financial_receipts,
    rebind_narrative_receipt,
)


def financial_receipt(*, ticker: str = "000001.SZ", source_url: str = "https://static.cninfo.com.cn/finalpage/example.PDF") -> dict:
    document = {
        "document_id": "official-filing:cninfo_official_filing_document_v1:1234567890",
        "published_at": "2026-04-30T16:00:00Z",
        "raw_hash": "a" * 64,
        "source_url": source_url,
        "title": "2026年一季度报告",
    }
    fact = {
        "ticker": ticker,
        "metric": "revenue",
        "value": 123.0,
        "document_id": document["document_id"],
        "raw_hash": document["raw_hash"],
        "page_number": 8,
        "quoted_label": "营业收入",
        "quoted_anchor": "营业收入 123.0 100.0",
        "report_period": "2026Q1",
        "statement_scope": "consolidated",
        "unit": "元",
        "currency": "CNY",
        "source_url": source_url,
        "column_identity": "current_period",
        "column_header_excerpt": "本期发生额 上期发生额",
        "unit_source_excerpt": "单位：元",
        "validation_status": "pending_magnitude_validation",
        "as_of_date": None,
        "audit_status": "unaudited",
    }
    receipt = {
        "schema_version": "e4-financial-sequence-batch-v1",
        "data_kind": "real",
        "cohort": [ticker],
        "periods_attempted": ["2026Q1"],
        "sequential": True,
        "configured_max_concurrency": 1,
        "inter_ticker_delay_seconds": 0.0,
        "tickers": [{
            "ticker": ticker,
            "reports": [
                {"period": "2026Q1", "status": "available", "document": document, "facts": [fact]},
                {"period": "2025FY", "status": "missing", "reason": "ticker_collection_timeout", "raw_text_excerpt": "official collector exceeded the bounded issuer window", "request_diagnostics": [{"method": "POST", "source_url": "http://www.cninfo.com.cn/new/hisAnnouncement/query", "http_status": None, "response_body_sha256": None}]},
            ],
        }],
        "counts": {"tickers": 1, "facts": 1, "available_reports": 1, "missing_reports": 1},
        "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True, "does_not_promote_tier_or_action": True},
    }
    receipt["receipt_hash"] = digest(receipt)
    return receipt


def json_bytes_without_receipt_ids(value: dict) -> bytes:
    payload = {key: item for key, item in value.items() if key not in {"receipt_hash", "receipt_id"}}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()


class V4N1OfficialEvidenceTests(unittest.TestCase):
    def test_materializes_page_facts_and_keeps_typed_missing(self) -> None:
        materialized = materialize_financial_receipt(financial_receipt(), ticker="000001.SZ")
        self.assertEqual(materialized["financial_status"], "available")
        self.assertEqual(materialized["available_reports"], 1)
        self.assertEqual(materialized["missing_reports"][0]["reason"], "ticker_collection_timeout")
        self.assertEqual(len(materialized["round7_financial"]["page_facts"]), 1)
        self.assertEqual(materialized["round7_financial"]["page_facts"][0]["page_number"], 8)
        self.assertEqual(len(materialized["request_diagnostics"]), 1)

    def test_nonofficial_url_fails_closed(self) -> None:
        forged = financial_receipt(source_url="https://example.com/annual.pdf")
        with self.assertRaisesRegex(OfficialEvidenceError, "CNINFO official"):
            materialize_financial_receipt(forged, ticker="000001.SZ")

    def test_packet_hash_is_deterministic_and_narrative_is_identity_bound(self) -> None:
        financial = financial_receipt()
        narrative = {
            "schema_version": "e4-official-narrative-evidence-v1",
            "data_kind": "real",
            "ticker": "000001.SZ",
            "generated_at": "2026-08-02T00:00:00+00:00",
            "reports": [{
                "period": "2026Q1",
                "document_id": "official-filing:cninfo_official_filing_document_v1:1234567890",
                "status": "available",
                "raw_hash": "a" * 64,
                "source_url": "https://static.cninfo.com.cn/finalpage/example.PDF",
            }],
            "blocks": [{
                "ticker": "000001.SZ",
                "report_period": "2026Q1",
                "document_id": "official-filing:cninfo_official_filing_document_v1:1234567890",
                "raw_hash": "a" * 64,
                "page_number": 3,
                "section_path": "第三节 管理层讨论与分析 > 主要业务",
                "text": "公司围绕客户需求推进经营活动。",
                "source_url": "https://static.cninfo.com.cn/finalpage/example.PDF",
                "extraction_method": "native_text",
                "status": "resolved",
                "reason": None,
            }],
            "coverage": {},
            "source_financial_receipt_sha256": financial["receipt_hash"],
            "truth_boundary": {"official_cninfo_pdf_only": True},
        }
        narrative["receipt_hash"] = hashlib.sha256(json_bytes_without_receipt_ids(narrative)).hexdigest()
        narrative["receipt_id"] = "e4-official-narrative-evidence-v1:" + narrative["receipt_hash"]
        first = build_packet({"000001.SZ": financial}, narrative_inputs={"000001.SZ": narrative})
        second = build_packet({"000001.SZ": copy.deepcopy(financial)}, narrative_inputs={"000001.SZ": copy.deepcopy(narrative)})
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])
        self.assertEqual(first["companies"][0]["narrative"]["status"], "available")
        self.assertEqual(first["companies"][0]["narrative"]["receipt_id"], narrative["receipt_id"])

    def test_narrative_ticker_mismatch_is_rejected(self) -> None:
        narrative = {"schema_version": "e4-official-narrative-evidence-v1", "data_kind": "real", "ticker": "000002.SZ", "reports": [{"document_id": "doc"}], "blocks": [{"document_id": "doc", "raw_hash": "a" * 64, "source_url": "https://static.cninfo.com.cn/a.pdf", "page_number": 1}]}
        narrative["receipt_hash"] = digest(narrative)
        with self.assertRaisesRegex(OfficialEvidenceError, "ticker mismatch"):
            build_packet({"000001.SZ": financial_receipt()}, narrative_inputs={"000001.SZ": narrative})

    def test_period_receipts_merge_without_duplicate_periods(self) -> None:
        first = financial_receipt()
        first["tickers"][0]["reports"] = first["tickers"][0]["reports"][:1]
        first["periods_attempted"] = ["2026Q1"]
        first["counts"] = {"tickers": 1, "facts": 1, "available_reports": 1, "missing_reports": 0}
        first["receipt_hash"] = digest({key: value for key, value in first.items() if key != "receipt_hash"})
        second = copy.deepcopy(first)
        second["tickers"][0]["reports"][0]["period"] = "2025FY"
        second["tickers"][0]["reports"][0]["facts"][0]["report_period"] = "2025FY"
        second["periods_attempted"] = ["2025FY"]
        second["receipt_hash"] = digest({key: value for key, value in second.items() if key != "receipt_hash"})
        merged = merge_financial_receipts([first, second])
        self.assertEqual(merged["periods_attempted"], ["2025FY", "2026Q1"])
        with self.assertRaisesRegex(OfficialEvidenceError, "duplicate financial period"):
            merge_financial_receipts([first, first])

    def test_narrative_rebinding_records_prior_identity(self) -> None:
        financial = financial_receipt()
        narrative = {
            "schema_version": "e4-official-narrative-evidence-v1",
            "data_kind": "real",
            "ticker": "000001.SZ",
            "generated_at": "2026-08-02T00:00:00+00:00",
            "reports": [],
            "blocks": [],
            "coverage": {},
            "source_financial_receipt_sha256": "b" * 64,
            "truth_boundary": {"official_cninfo_pdf_only": True},
        }
        narrative["receipt_hash"] = hashlib.sha256(json_bytes_without_receipt_ids(narrative)).hexdigest()
        narrative["receipt_id"] = "e4-official-narrative-evidence-v1:" + narrative["receipt_hash"]
        rebound = rebind_narrative_receipt(narrative, financial_receipt_hash=financial["receipt_hash"])
        self.assertEqual(rebound["source_rebound_from_receipt_id"], narrative["receipt_id"])
        self.assertEqual(rebound["source_financial_receipt_sha256"], financial["receipt_hash"])

    def test_tracked_packet_replay_verifier_passes(self) -> None:
        from scripts.verify_v4_n1_evidence import verify

        result = verify(ROOT / "docs/evidence/v4-n1-official/receipt.json")
        self.assertEqual(result["status"], "passed")
        self.assertEqual([row["ticker"] for row in result["companies"]], ["000001.SZ", "000002.SZ", "600000.SH"])


if __name__ == "__main__":
    unittest.main()
