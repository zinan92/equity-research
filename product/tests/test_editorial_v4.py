from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from editorial_v4_contract import canonical_hash, validate_dossier, validate_evidence_packet  # noqa: E402
from editorial_v4_qa import _filter_false_positive_blockers  # noqa: E402
from editorial_v4_renderer import render_dossier  # noqa: E402


def _packet() -> dict:
    source = {
        "source_id": "src-1",
        "document_id": "official-doc-1",
        "title": "2025年年度报告",
        "source_url": "https://static.cninfo.com.cn/example.pdf",
        "raw_sha256": "a" * 64,
        "page_count": 20,
        "report_period": "2025FY",
    }
    evidence = [
        {
            "evidence_id": "e-narr",
            "source_id": "src-1",
            "document_id": "official-doc-1",
            "source_url": source["source_url"],
            "raw_sha256": source["raw_sha256"],
            "report_period": "2025FY",
            "page_number": 3,
            "quoted_anchor": "公司披露具备独特的制造能力",
            "metric": None,
        },
        {
            "evidence_id": "e-current",
            "source_id": "src-1",
            "document_id": "official-doc-1",
            "source_url": source["source_url"],
            "raw_sha256": source["raw_sha256"],
            "report_period": "2025FY",
            "page_number": 10,
            "quoted_anchor": "营业总收入 100000 80000",
            "metric": "revenue",
            "value": 100000.0,
            "unit": "千元",
        },
        {
            "evidence_id": "e-previous",
            "source_id": "src-1",
            "document_id": "official-doc-1",
            "source_url": source["source_url"],
            "raw_sha256": source["raw_sha256"],
            "report_period": "2024FY",
            "page_number": 10,
            "quoted_anchor": "营业总收入 100000 80000",
            "metric": "revenue",
            "value": 80000.0,
            "unit": "千元",
        },
    ]
    payload = {
        "schema_version": "editorial-v4-evidence-packet-v1",
        "ticker": "600000.SH",
        "issuer_name": "测试公司",
        "data_kind": "real",
        "evidence_cutoff": "2026-08-03",
        "truth_boundary": {"official_pdf_only": True},
        "sources": [source],
        "evidence": evidence,
        "financial_facts": evidence[1:],
        "derived_metrics": [
            {
                "derived_id": "d-revenue",
                "metric": "revenue",
                "current_evidence_id": "e-current",
                "previous_evidence_id": "e-previous",
                "current_period": "2025FY",
                "previous_period": "2024FY",
                "current_value": 100000.0,
                "previous_value": 80000.0,
                "absolute_change": 20000.0,
                "percent_change": 25.0,
                "direction": "增长",
                "formula": "deterministic",
                "computed_by": "test",
            }
        ],
        "gaps": [],
    }
    payload["packet_hash"] = canonical_hash(payload)
    return payload


def _dossier(packet: dict) -> dict:
    body = "本章基于官方页级材料，若材料不足则明确列出缺口并说明下一步验证。" * 14
    return {
        "schema_version": "editorial-v4-dossier-v1",
        "ticker": packet["ticker"],
        "issuer_name": packet["issuer_name"],
        "input_packet_hash": packet["packet_hash"],
        "sources": packet["sources"],
        "generation_receipt": {"request_hash": "b" * 64, "response_hash": "c" * 64},
        "production_record": {
            "run_id": "editorial-v4-run:test",
            "model_provider": "DeepSeek",
            "model": "deepseek-v4-pro",
            "prompt_version": "test",
            "input_packet_sha256": packet["packet_hash"],
            "review_status": "pending",
            "action_state": "blocked",
        },
        "boundary": {"review_only": True, "no_tier_credit": True, "no_publication_credit": True},
        "latest_card": "最新数据：输入未提供可靠估值数据与行动建议",
        "sections": [
            {"id": section_id, "title": title, "body": body, "claim_ids": []}
            for section_id, title in (
                ("one_line_position", "一句话定位"),
                ("founder_team", "创始人与团队"),
                ("timeline", "发展时间线"),
                ("technology_products", "技术与产品"),
                ("financial_valuation", "财务与估值"),
                ("risks_commentary", "风险与点评"),
                ("plain_language", "大白话结论"),
            )
        ],
        "claims": [],
        "missing_inputs": [],
        "overall_conclusion": "",
    }


class EditorialV4ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = _packet()
        self.dossier = _dossier(self.packet)

    def _with_claim(self, claim: dict, rendered: str, overall: str = "") -> dict:
        dossier = copy.deepcopy(self.dossier)
        dossier["sections"][0]["body"] = rendered + dossier["sections"][0]["body"]
        dossier["claims"] = [claim]
        dossier["overall_conclusion"] = overall
        return dossier

    def test_packet_requires_official_host_and_hash(self) -> None:
        self.assertEqual(validate_evidence_packet(self.packet)["status"], "passed")
        forged = copy.deepcopy(self.packet)
        forged["sources"][0]["source_url"] = "https://example.com/not-official.pdf"
        forged["packet_hash"] = canonical_hash({k: v for k, v in forged.items() if k != "packet_hash"})
        self.assertEqual(validate_evidence_packet(forged)["status"], "failed")

    def test_aggressive_positioning_is_allowed_when_judgment_bound(self) -> None:
        claim = {"claim_id": "J-01", "kind": "judgment", "text": "公司是绝对龙头", "evidence_ids": ["e-narr"], "derived_ids": [], "falsifier": "若同行份额持续反超则证伪"}
        dossier = self._with_claim(claim, "公司是绝对龙头[J-01]。", "公司是绝对龙头[J-01]")
        self.assertEqual(validate_dossier(dossier, self.packet)["status"], "passed")

    def test_unmarked_aggressive_positioning_fails(self) -> None:
        dossier = copy.deepcopy(self.dossier)
        dossier["sections"][0]["body"] = "公司是绝对龙头。" + dossier["sections"][0]["body"]
        result = validate_dossier(dossier, self.packet)
        self.assertIn("judgment_marker_missing", {row["code"] for row in result["errors"]})

    def test_self_report_requires_paragraph_attribution(self) -> None:
        claim = {"claim_id": "C-01", "kind": "issuer_self_report", "text": "公司披露具备独特的制造能力", "evidence_ids": ["e-narr"], "derived_ids": [], "falsifier": "若后续披露修正则重审"}
        good = self._with_claim(claim, "公司披露具备独特的制造能力[C-01]。")
        self.assertEqual(validate_dossier(good, self.packet)["status"], "passed")
        bad = self._with_claim(claim, "具备独特的制造能力[C-01]。")
        self.assertIn("self_report_body_unmarked", {row["code"] for row in validate_dossier(bad, self.packet)["errors"]})

    def test_numeric_unit_conversion_is_deterministic(self) -> None:
        claim = {"claim_id": "F-01", "kind": "fact", "text": "2025年营业总收入为1亿元", "evidence_ids": ["e-current"], "derived_ids": [], "falsifier": ""}
        dossier = self._with_claim(claim, "2025年营业总收入为1亿元[F-01]。")
        self.assertNotIn("numeric_quote_mismatch", {row["code"] for row in validate_dossier(dossier, self.packet)["errors"]})
        bad = copy.deepcopy(dossier)
        bad["claims"][0]["text"] = "2025年营业总收入为999亿元"
        self.assertIn("numeric_quote_mismatch", {row["code"] for row in validate_dossier(bad, self.packet)["errors"]})

    def test_comparison_must_state_deterministic_direction(self) -> None:
        claim = {"claim_id": "F-01", "kind": "fact", "text": "2025年营业总收入的当期数值", "evidence_ids": ["e-current", "e-previous"], "derived_ids": ["d-revenue"], "falsifier": ""}
        dossier = self._with_claim(claim, "2025年营业总收入的当期数值[F-01]。")
        self.assertIn("comparison_direction_missing", {row["code"] for row in validate_dossier(dossier, self.packet)["errors"]})

    def test_historical_actual_cannot_be_conditional(self) -> None:
        claim = {"claim_id": "J-01", "kind": "judgment", "text": "如果公司保持优势，那么2025年营业总收入将达到1亿元", "evidence_ids": ["e-current"], "derived_ids": [], "falsifier": "若后续数据不符则证伪"}
        dossier = self._with_claim(claim, "如果公司保持优势，那么2025年营业总收入将达到1亿元[J-01]。")
        self.assertIn("historical_condition", {row["code"] for row in validate_dossier(dossier, self.packet)["errors"]})

    def test_absence_of_target_price_is_not_an_action(self) -> None:
        dossier = copy.deepcopy(self.dossier)
        dossier["sections"][0]["body"] = "估值证据缺失，未提供目标价。" + dossier["sections"][0]["body"]
        self.assertNotIn("action_language", {row["code"] for row in validate_dossier(dossier, self.packet)["errors"]})
        dossier["sections"][0]["body"] = "目标价为100元。" + dossier["sections"][0]["body"]
        self.assertIn("action_language", {row["code"] for row in validate_dossier(dossier, self.packet)["errors"]})

    def test_qa_filter_keeps_judgment_and_gap_semantics(self) -> None:
        judgment = {"claim_id": "J-01", "kind": "judgment", "text": "公司是绝对龙头", "evidence_ids": ["e-narr"], "falsifier": "若同行反超则证伪"}
        dossier = self._with_claim(judgment, "公司是绝对龙头[J-01]。", "公司是绝对龙头[J-01]")
        raw = {"blockers": [{"code": "judgment_missing_marker", "message": "旧快照未看到标记", "claim_id": "J-01"}]}
        self.assertEqual(_filter_false_positive_blockers(raw, dossier, self.packet), [])
        gap = {"claim_id": "G-01", "kind": "gap", "text": "缺乏估值数据，无法独立判断", "evidence_ids": [], "derived_ids": [], "falsifier": ""}
        gap_dossier = self._with_claim(gap, "")
        raw_gap = {"blockers": [{"code": "gap_as_fact", "message": "gap as fact", "claim_id": "G-01"}]}
        self.assertEqual(_filter_false_positive_blockers(raw_gap, gap_dossier, self.packet), [])

    def test_renderer_is_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = render_dossier(self.dossier, self.packet, Path(temp))
            html = Path(paths["html_path"]).read_text(encoding="utf-8")
            self.assertIn("未通过真人审阅", html)
            self.assertNotIn("买入", html)


if __name__ == "__main__":
    unittest.main()
