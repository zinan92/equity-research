from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.round7_chapter_generator import (
    ROUND7_LAYOUTS,
    build_chapter_request,
    compile_dossier,
    generate_chapter,
    render_markdown,
    validate_chapter,
)
from data_core.round7_evidence import (
    build_evidence_registry,
    load_source_receipts,
    select_section_evidence,
)
from data_core.round7_north_star import (
    ROUND7_STRUCTURE_SIGNATURE,
    structure_signature,
)
from report_contract import RESEARCH_SECTION_SPECS_V3


def narrative(evidence_id: str = "N-test", *, self_report: bool = False) -> dict:
    text = "公司专注于动力电池和储能电池的研发、生产及销售，并向客户提供产品方案。"
    return {
        "evidence_id": evidence_id,
        "kind": "narrative",
        "text": text,
        "section_path": "管理层讨论与分析 > 主要业务",
        "report_period": "2025FY",
        "self_report": self_report,
        "allowed_numeric_displays": [],
        "citation": {
            "document_id": "official-filing:cninfo:test",
            "raw_hash": "a" * 64,
            "page_number": 8,
            "quoted_anchor": text,
            "source_url": "https://static.cninfo.com.cn/test.pdf",
            "section_path": "管理层讨论与分析 > 主要业务",
        },
    }


def financial() -> dict:
    return {
        "evidence_id": "P-test",
        "kind": "financial",
        "metric": "revenue",
        "period": "2025FY",
        "display": "120",
        "unit": "元",
        "currency": "CNY",
        "comparison": {
            "prior_display": "100",
            "direction": "增长",
            "magnitude": "20.0%",
            "required_phrase": "同比增长20.0%",
        },
        "allowed_numeric_displays": ["2025", "120", "100", "20.0%"],
        "citation": {
            "document_id": "official-filing:cninfo:test",
            "raw_hash": "a" * 64,
            "page_number": 61,
            "quoted_anchor": "营业总收入 120 100",
            "quoted_label": "营业总收入",
            "source_url": "https://static.cninfo.com.cn/test.pdf",
            "statement_scope": "consolidated",
        },
    }


def valid_response() -> dict:
    quote = narrative()["text"]
    return {
        "section_id": "one_line_positioning",
        "rows": [
            {
                "cells": [
                    {
                        "column_id": "positioning",
                        "kind": "fact",
                        "text": quote,
                        "evidence_ids": ["N-test"],
                        "supporting_quotes": [
                            {"evidence_id": "N-test", "quote": quote[:24]}
                        ],
                    },
                    {
                        "column_id": "research_judgment",
                        "kind": "judgment",
                        "text": "这一业务边界意味着公司的研究重点应放在两类电池产品的兑现、客户需求变化与产品方案转化上，仍需后续正式披露分别验证各业务线的收入质量、盈利贡献、现金转化和持续性。",
                        "evidence_ids": ["N-test"],
                        "supporting_quotes": [
                            {"evidence_id": "N-test", "quote": quote[6:34]}
                        ],
                    },
                ],
            }
        ],
    }


def fixture_rows(section_id: str) -> list[dict]:
    cells = []
    for column in ROUND7_LAYOUTS[section_id]["columns"]:
        kind = column["kinds"][0]
        cells.append(
            {
                "column_id": column["id"],
                "kind": kind,
                "text": (
                    "主题"
                    if kind == "label"
                    else "仍需下一份正式披露核验。"
                    if kind == "gap"
                    else "这一证据意味着后续仍需验证。"
                    if kind == "judgment"
                    else "公司披露了动力电池业务。"
                ),
                "evidence_ids": [] if kind in {"label", "gap"} else ["N-test"],
                "supporting_quotes": [],
                "source_character": "page_bound_official_evidence",
            }
        )
    return [{"cells": cells}]


class Round7ChapterGeneratorTest(unittest.TestCase):
    def test_one_transport_call_returns_a_complete_chapter(self) -> None:
        spec = RESEARCH_SECTION_SPECS_V3[0]
        evidence = [narrative()]
        registry = {"N-test": evidence[0]}
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key"
            key.write_text("test-key")
            tasks = []

            def transport(payload, secret):
                self.assertEqual(secret, "test-key")
                request = json.loads(payload["messages"][1]["content"])
                tasks.append(request["task"])
                if request["task"] == "audit_one_complete_round7_chapter":
                    return {"verdict": "pass", "findings": []}
                self.assertEqual(
                    request["task"],
                    "write_one_complete_round7_chapter",
                )
                return valid_response()

            chapter, receipts = generate_chapter(
                spec=spec,
                issuer={"ticker": "FAKE.X", "name": "换名公司"},
                evidence=evidence,
                registry=registry,
                key_file=key,
                max_attempts=1,
                transport=transport,
            )
        self.assertEqual(chapter["section_id"], "one_line_positioning")
        self.assertEqual(len(receipts), 1)
        self.assertTrue(receipts[0]["accepted"])
        self.assertEqual(chapter["review_status"], "pending_human_review")
        self.assertEqual(
            tasks,
            [
                "write_one_complete_round7_chapter",
                "audit_one_complete_round7_chapter",
            ],
        )
        self.assertEqual(
            receipts[0]["semantic_audit"]["verdict"],
            "pass",
        )

    def test_request_has_no_catl_specific_fallback(self) -> None:
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[narrative()],
        )
        serialized = json.dumps(request, ensure_ascii=False)
        self.assertIn("换名公司", serialized)
        self.assertNotIn("宁德时代", serialized)
        self.assertNotIn("贵州茅台", serialized)

    def test_comparison_direction_is_machine_enforced(self) -> None:
        evidence = financial()
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[evidence],
        )
        response = {
            "section_id": "one_line_positioning",
            "rows": [
                {
                    "cells": [
                        {
                            "column_id": "positioning",
                            "kind": "fact",
                            "text": "公司2025年营业总收入为120元。",
                            "evidence_ids": ["P-test"],
                            "supporting_quotes": [
                                {
                                    "evidence_id": "P-test",
                                    "quote": "营业总收入 120 100",
                                }
                            ],
                        },
                        {
                            "column_id": "research_judgment",
                            "kind": "judgment",
                            "text": "这一收入基线意味着后续仍需验证盈利质量。",
                            "evidence_ids": ["P-test"],
                            "supporting_quotes": [
                                {
                                    "evidence_id": "P-test",
                                    "quote": "营业总收入 120 100",
                                }
                            ],
                        },
                    ],
                },
            ],
        }
        problems = validate_chapter(
            response,
            request=request,
            registry={"P-test": evidence},
        )
        self.assertTrue(any("omits comparison direction" in item for item in problems))

    def test_disclosed_actual_cannot_be_conditional_consequent(self) -> None:
        evidence = financial()
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[evidence],
        )
        response = valid_response()
        response["rows"][0]["cells"][0] = {
            "column_id": "positioning",
            "kind": "fact",
            "text": "如果需求保持稳定，那么公司可能实现120元营业总收入。",
            "evidence_ids": ["P-test"],
            "supporting_quotes": [
                {"evidence_id": "P-test", "quote": "营业总收入 120 100"}
            ],
        }
        problems = validate_chapter(
            response,
            request=request,
            registry={"P-test": evidence},
        )
        self.assertTrue(
            any("conditional consequent" in item for item in problems)
        )

    def test_self_report_requires_explicit_label(self) -> None:
        evidence = narrative(self_report=True)
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[evidence],
        )
        problems = validate_chapter(
            valid_response(),
            request=request,
            registry={"N-test": evidence},
        )
        self.assertTrue(any("self-report" in item for item in problems))

    def test_unrelated_fact_cannot_borrow_a_page_citation(self) -> None:
        evidence = narrative()
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[evidence],
        )
        response = valid_response()
        response["rows"][0]["cells"][0]["text"] = (
            "公司已经建成火星基地并完成星际电池量产，"
            "相关产品已向外星客户稳定交付。"
        )
        problems = validate_chapter(
            response,
            request=request,
            registry={"N-test": evidence},
        )
        self.assertTrue(
            any("deterministic page-bound text" in item for item in problems)
        )

    def test_tier_b_blocks_configuration_advice_synonyms(self) -> None:
        evidence = narrative()
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[evidence],
        )
        for text in (
            "这一证据意味着当前建议提高配置比例，仍需后续验证。",
            "当前推荐增配该公司，仍需后续验证经营兑现。",
            "当前可考虑做多该公司，仍需后续验证经营兑现。",
            "投资者宜扩大敞口，仍需后续验证经营兑现。",
            "目前适宜重点配置该公司，仍需后续验证经营兑现。",
        ):
            response = valid_response()
            response["rows"][0]["cells"][1]["text"] = text
            problems = validate_chapter(
                response,
                request=request,
                registry={"N-test": evidence},
            )
            self.assertTrue(
                any(
                    marker in item
                    for item in problems
                    for marker in (
                        "investment-action intent",
                        "closed Tier-B grammar",
                        "investment-execution term",
                        "allowed research outcome",
                    )
                ),
                (text, problems),
            )

    def test_operating_capital_configuration_is_not_user_action(self) -> None:
        evidence = narrative()
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[evidence],
        )
        response = valid_response()
        response["rows"][0]["cells"][1]["text"] = (
            "这一业务意味着资本配置效率可能影响现金回报，仍需验证。"
        )
        problems = validate_chapter(
            response,
            request=request,
            registry={"N-test": evidence},
        )
        self.assertFalse(
            any("investment-execution" in item for item in problems), problems
        )

    def test_comparison_cannot_be_negated_or_put_in_future_consequent(self) -> None:
        evidence = financial()
        request = build_chapter_request(
            spec=RESEARCH_SECTION_SPECS_V3[0],
            issuer={"ticker": "FAKE.X", "name": "换名公司"},
            evidence=[evidence],
        )
        for text, expected in (
            (
                "这一结果表明公司并非同比增长20.0%，仍需验证。",
                "negates the disclosed comparison",
            ),
            (
                "如果需求改善，那么公司可能同比增长20.0%。",
                "conditional consequent",
            ),
        ):
            response = valid_response()
            response["rows"][0]["cells"][1] = {
                "column_id": "research_judgment",
                "kind": "judgment",
                "text": text,
                "evidence_ids": ["P-test"],
                "supporting_quotes": [
                    {
                        "evidence_id": "P-test",
                        "quote": "营业总收入 120 100",
                    }
                ],
            }
            problems = validate_chapter(
                response,
                request=request,
                registry={"P-test": evidence},
            )
            self.assertTrue(any(expected in item for item in problems), problems)

    def test_real_source_receipts_build_page_bound_inputs(self) -> None:
        narratives, financials = load_source_receipts(
            narrative_path=ROOT
            / "artifacts/evidence/300750.SZ-official-narrative-evidence.json",
            financial_path=ROOT
            / "artifacts/evidence/300750.SZ-financial-page-evidence.json",
            ticker="300750.SZ",
        )
        registry = build_evidence_registry(narratives, financials)
        self.assertGreater(len(registry), 100)
        for spec in RESEARCH_SECTION_SPECS_V3[:-1]:
            selected = select_section_evidence(
                registry,
                section_id=spec.section_id,
            )
            self.assertTrue(selected)
            self.assertTrue(
                all(item["citation"]["page_number"] >= 1 for item in selected)
            )

    def test_unreviewed_whole_chapters_keep_tier_b(self) -> None:
        evidence = narrative()
        registry = {"N-test": evidence}
        chapters = []
        evidence_by_section = {}
        for spec in RESEARCH_SECTION_SPECS_V3[:-1]:
            chapters.append(
                {
                    "section_id": spec.section_id,
                    "title": spec.title,
                    "status": "ai_generated_judgment_unreviewed",
                    "review_status": "pending_human_review",
                    "input_hash": "b" * 64,
                    "model_request_id": f"request-{spec.order}",
                    "character_count": spec.target_characters[0],
                    "rows": fixture_rows(spec.section_id),
                    "blocks": [
                        {
                            "kind": "fact",
                            "text": "公司披露了动力电池业务。",
                            "evidence_ids": ["N-test"],
                            "supporting_quotes": [],
                        },
                        {
                            "kind": "judgment",
                            "text": "这一业务仍需后续验证。",
                            "evidence_ids": ["N-test"],
                            "supporting_quotes": [],
                        },
                    ],
                    "evidence_ids": ["N-test"],
                }
            )
            evidence_by_section[spec.section_id] = [evidence]
        page_fact = {
            "ticker": "300750.SZ",
            "metric": "revenue",
            "value": 120.0,
            "document_id": "official-filing:cninfo:test",
            "raw_hash": "a" * 64,
            "page_number": 61,
            "quoted_label": "营业总收入",
            "quoted_anchor": "营业总收入 120 100",
            "report_period": "2025FY",
            "statement_scope": "consolidated",
            "unit": "元",
            "currency": "CNY",
            "source_url": "https://static.cninfo.com.cn/test.pdf",
        }
        dossier = compile_dossier(
            ticker="300750.SZ",
            issuer={
                "ticker": "300750.SZ",
                "name": "宁德时代新能源科技股份有限公司",
                "short_name": "宁德时代",
            },
            chapters=chapters,
            evidence_by_section=evidence_by_section,
            registry=registry,
            page_facts=[page_fact],
            provider_receipts=[
                {
                    "request_id": f"request-{spec.order}",
                    "section_id": spec.section_id,
                    "accepted": True,
                }
                for spec in RESEARCH_SECTION_SPECS_V3[:-1]
            ],
            source_receipts={"source": "receipt"},
        )
        self.assertEqual(dossier["degradation"]["tier"], "B")
        self.assertEqual(
            dossier["degradation"]["blocked_fields"],
            ["action", "target_price", "position_range"],
        )
        statuses = {
            item["section_id"]: str(item["status"])
            for item in dossier["section_contract"]["sections"]
        }
        self.assertEqual(statuses["production_record"], "full")
        self.assertTrue(
            all(
                status == "partial"
                for section_id, status in statuses.items()
                if section_id != "production_record"
            )
        )
        markdown = render_markdown(dossier)
        self.assertEqual(
            structure_signature(markdown),
            ROUND7_STRUCTURE_SIGNATURE,
        )
        for spec in RESEARCH_SECTION_SPECS_V3:
            self.assertIn(f"## {spec.order}. {spec.title}", markdown)
        self.assertIn("## Sources", markdown)


if __name__ == "__main__":
    unittest.main()
