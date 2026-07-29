from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_core.document_intelligence import DocumentPage
from data_core.e4_catl_financial_history import OfficialReport
from data_core.e4_narrative_evidence import (
    _heading,
    capture_issuer_narrative,
    extract_narrative_blocks,
    merge_narrative_receipts,
)


def page(number: int, text: str) -> DocumentPage:
    raw = b"%PDF-1.7 test"
    return DocumentPage("doc", number, hashlib.sha256(raw).hexdigest(), "test", text, hashlib.sha256(text.encode()).hexdigest(), "native_text", "none_detected")


class NarrativeEvidenceTest(unittest.TestCase):
    def test_retains_page_hash_path_and_cross_page_heading_context(self) -> None:
        report = OfficialReport("2025FY", "doc", "https://static.cninfo.com.cn/doc.pdf")
        raw = b"%PDF-1.7 test"
        rows = extract_narrative_blocks(report, raw, pages=(
            page(12, "第三节 管理层讨论与分析\n一、报告期内公司所处行业情况\n动力电池行业在报告期内经历了供需调整，公司持续跟踪客户需求变化并安排产能。\n12"),
            page(13, "公司围绕海外客户与技术迭代推进产品研发，并按披露节奏评估项目进展和经营风险。\n13"),
        ))
        resolved = [row for row in rows if row.status == "resolved"]
        self.assertEqual([row.page_number for row in resolved], [12, 13])
        self.assertTrue(all(row.raw_hash == hashlib.sha256(raw).hexdigest() for row in resolved))
        self.assertTrue(all("第三节 管理层讨论与分析" in str(row.section_path) for row in resolved))
        self.assertTrue(all("报告期内公司所处行业情况" in str(row.section_path) for row in resolved))

    def test_removes_toc_and_repeated_margins_and_keeps_unassigned_excerpt(self) -> None:
        report = OfficialReport("2025FY", "doc", "https://static.cninfo.com.cn/doc.pdf")
        raw = b"%PDF-1.7 test"
        rows = extract_narrative_blocks(report, raw, pages=(
            page(1, "宁德时代新能源科技股份有限公司\n目录 …… 1 …… 12 …… 30 …… 50 …… 80 …… 100\n1"),
            page(20, "宁德时代新能源科技股份有限公司\n这是一段没有已经识别章节上下文但仍需要人工回看的叙述性文字，不能被硬塞进任何研究章节。\n20"),
            page(21, "宁德时代新能源科技股份有限公司\n第三节 管理层讨论与分析\n经营情况讨论与分析\n公司围绕客户需求、技术能力和经营效率开展日常运营，相关结论应回到本页原文核验。\n21"),
        ))
        self.assertFalse(any("目录" in row.text or "宁德时代新能源科技" == row.text for row in rows))
        self.assertTrue(any(row.status == "unresolved" and "没有已经识别" in row.text for row in rows))
        self.assertTrue(any(row.status == "resolved" and row.page_number == 21 for row in rows))

    def test_rejects_dated_resolution_as_a_heading(self) -> None:
        self.assertIsNone(_heading("1、2021年6月22日，公司董事会审议通过了项目议案"))

    def test_merge_preserves_real_source_run_ids(self) -> None:
        base = {"schema_version": "e4-official-narrative-evidence-v1", "data_kind": "real", "ticker": "600519.SH", "generated_at": "2026-07-29T00:00:00+00:00", "reports": [], "blocks": [], "coverage": {}, "truth_boundary": {}}
        base["receipt_hash"] = hashlib.sha256(__import__("json").dumps(base, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        base["receipt_id"] = "e4-official-narrative-evidence-v1:" + base["receipt_hash"]
        merged = merge_narrative_receipts([base])
        self.assertEqual(merged["source_run_receipts"], [base["receipt_id"]])
        self.assertEqual(merged["ticker"], "600519.SH")

        forged = json.loads(json.dumps(base))
        forged["receipt_id"] = "e4-official-narrative-evidence-v1:forged"
        with self.assertRaisesRegex(ValueError, "receipt id mismatch"):
            merge_narrative_receipts([forged])

    def test_generic_capture_requires_frozen_official_identity(self) -> None:
        official = OfficialReport(
            "2025FY",
            "official-doc",
            "https://static.cninfo.com.cn/annual.pdf",
            ticker="600519.SH",
        )
        with self.assertRaisesRegex(ValueError, "frozen raw SHA-256"):
            capture_issuer_narrative(
                "600519.SH",
                [official],
                expected_raw_hashes={},
                source_financial_receipt_sha256="a" * 64,
            )
        nonofficial = OfficialReport(
            "2025FY",
            "document",
            "https://example.com/annual.pdf",
            ticker="600519.SH",
        )
        with self.assertRaisesRegex(ValueError, "official CNINFO"):
            capture_issuer_narrative(
                "600519.SH",
                [nonofficial],
                expected_raw_hashes={"document": "a" * 64},
                source_financial_receipt_sha256="b" * 64,
            )

    def test_generic_capture_marks_raw_hash_mismatch_missing(self) -> None:
        report = OfficialReport(
            "2025FY",
            "official-doc",
            "https://static.cninfo.com.cn/annual.pdf",
            ticker="600519.SH",
        )
        response = SimpleNamespace(status_code=200, body=b"%PDF-mismatch")
        with patch(
            "data_core.e4_narrative_evidence.default_http_transport",
            return_value=response,
        ):
            receipt = capture_issuer_narrative(
                "600519.SH",
                [report],
                expected_raw_hashes={"official-doc": "a" * 64},
                source_financial_receipt_sha256="b" * 64,
            )
        self.assertEqual(
            receipt["reports"][0]["reason"],
            "official_pdf_raw_hash_mismatch",
        )
        self.assertEqual(receipt["blocks"], [])


if __name__ == "__main__":
    unittest.main()
