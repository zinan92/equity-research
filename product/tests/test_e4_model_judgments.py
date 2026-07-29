from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_core.e4_model_judgments import (  # noqa: E402
    JUDGMENT_STATUS,
    _source_display_token,
    freeze_judgment_input,
    generate_model_judgments,
)


BASE = {
    "document_id": "official-doc",
    "raw_hash": "a" * 64,
    "page_number": 25,
    "source_url": "https://static.cninfo.com.cn/annual.pdf",
    "report_period": "2025FY",
}


def financial(metric: str, value: int, anchor: str) -> dict:
    return {
        **BASE,
        "metric": metric,
        "value": value,
        "quoted_anchor": anchor,
        "unit": "万元",
        "statement_scope": "consolidated",
    }


def narrative() -> dict:
    return {
        **BASE,
        "status": "resolved",
        "section_path": "第三节 管理层讨论与分析 > 产品与技术",
        "text": "公司动力电池系统产品已经交付客户项目，并继续推进电化学技术研发与量产验证。",
    }


def identity(ticker: str = "111111.SZ", name: str = "样本公司") -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "exchange": "深圳证券交易所",
        "industry": "制造业",
    }


def missing_row(judgment_id: str, evidence_ids: list[str] | None = None) -> dict:
    return {
        "judgment_id": judgment_id,
        "status": "missing",
        "missing_reason": {
            "gap_code": "unsupported_by_frozen_input",
            "detail": "supplied page evidence does not support the requested research task",
            "searched_evidence_ids": evidence_ids or [],
        },
    }


class ModelJudgmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.key_file = Path(self.temporary.name) / "key"
        self.key_file.write_text("test-secret", encoding="utf-8")
        self.facts = [
            financial("revenue", 100, "营业收入 100 万元"),
            financial("operating_cost", 70, "营业成本 70 万元"),
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _transport(self, available_id: str, available_value: dict):
        def send(payload, _secret):
            request = json.loads(payload["messages"][1]["content"])
            original = request.get("original_request") or request
            rows = []
            for task in original["tasks"]:
                judgment_id = task["judgment_id"]
                rows.append(
                    available_value
                    if judgment_id == available_id
                    else missing_row(
                        judgment_id,
                        list(original["evidence_registry"])[:2],
                    )
                )
            return {"judgments": rows}

        return send

    def test_model_body_is_preserved_and_bound_sentence_by_sentence(self) -> None:
        body = "动力电池系统产品已经交付客户项目与营业收入100万元可作为当前经营验证线索。"
        value = {
            "judgment_id": "investment_thesis",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "inference",
                    "evidence_ids": ["N0001", "F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "N0001",
                            "quote": "动力电池系统产品已经交付客户项目",
                        },
                        {
                            "evidence_id": "F0001",
                            "quote": "营业收入 100 万元",
                        },
                    ],
                }
            ],
        }
        result = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            transport=self._transport("investment_thesis", value),
        )
        thesis = result["content"]["investment_thesis"]
        self.assertEqual(thesis["status"], JUDGMENT_STATUS)
        self.assertEqual(thesis["text"], body)
        self.assertEqual(thesis["claims"][0]["text"], body)
        self.assertEqual(thesis["name_swap_test"]["total_sentences"], 1)
        self.assertEqual(thesis["name_swap_test"]["passed_sentences"], 1)
        self.assertEqual(
            thesis["claims"][0]["citations"][0]["document_id"],
            "official-doc",
        )

    def test_resume_revalidates_and_skips_an_accepted_judgment(self) -> None:
        body = "如果动力电池系统产品持续交付客户项目，那么营业收入100万元可作为经营验证线索。"
        value = {
            "judgment_id": "investment_thesis",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "inference",
                    "evidence_ids": ["N0001", "F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "N0001",
                            "quote": "动力电池系统产品已经交付客户项目",
                        },
                        {
                            "evidence_id": "F0001",
                            "quote": "营业收入 100 万元",
                        },
                    ],
                }
            ],
        }
        first = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            judgment_ids=["investment_thesis"],
            transport=self._transport("investment_thesis", value),
        )
        first["schema_version"] = "e4-model-judgments-v1"
        first["receipt_hash"] = "test-resume-receipt"
        first["model_receipts"][0]["request_id"] = "test-request-id"
        first["model_receipts"][0]["finish_reason"] = "stop"

        def unexpected_transport(_payload, _secret):
            raise AssertionError("accepted resumed judgment must not call model")

        resumed = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            judgment_ids=["investment_thesis"],
            transport=unexpected_transport,
            resume_receipt=first,
        )
        self.assertEqual(
            resumed["content"]["investment_thesis"]["text"],
            body,
        )
        tampered = json.loads(json.dumps(first))
        tampered["content"]["investment_thesis"]["text"] = "tampered"
        with self.assertRaisesRegex(ValueError, "content hash mismatch"):
            generate_model_judgments(
                ticker="111111.SZ",
                issuer_identity=identity(),
                page_facts=self.facts,
                narrative_blocks=[narrative()],
                source_receipts={"financial": "f", "narrative": "n"},
                dossier_id="dossier",
                key_file=self.key_file,
                judgment_ids=["investment_thesis"],
                transport=unexpected_transport,
                resume_receipt=tampered,
            )
    def test_untraceable_model_number_fails_closed_without_prose_fallback(self) -> None:
        body = "动力电池系统产品已经交付客户项目可作为营业收入101万元的验证线索。"
        value = {
            "judgment_id": "investment_thesis",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "inference",
                    "evidence_ids": ["N0001", "F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "N0001",
                            "quote": "动力电池系统产品已经交付客户项目",
                        }
                    ],
                }
            ],
        }
        result = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            transport=self._transport("investment_thesis", value),
        )
        thesis = result["content"]["investment_thesis"]
        self.assertEqual(thesis["status"], "missing")
        self.assertEqual(thesis["reason"], "generation_validation_failure")
        self.assertNotIn("text", thesis)
        self.assertTrue(
            any("101" in item for item in thesis["validation_errors"])
        )

    def test_shared_product_words_do_not_admit_unsupported_comparative(self) -> None:
        body = "动力电池系统产品已经交付客户项目可能打败所有同行并获得全球第一。"
        value = {
            "judgment_id": "investment_thesis",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "inference",
                    "evidence_ids": ["N0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "N0001",
                            "quote": "动力电池系统产品已经交付客户项目",
                        }
                    ],
                }
            ],
        }
        result = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            transport=self._transport("investment_thesis", value),
        )
        thesis = result["content"]["investment_thesis"]
        self.assertEqual(thesis["status"], "missing")
        self.assertTrue(
            any(
                "unsupported comparative" in item
                for item in thesis["validation_errors"]
            )
        )

    def test_fact_claim_cannot_append_an_unsupported_second_clause(self) -> None:
        body = "动力电池系统产品已经交付客户项目，且火星客户已签署长期采购合同。"
        value = {
            "judgment_id": "investment_thesis",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "fact",
                    "evidence_ids": ["N0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "N0001",
                            "quote": "动力电池系统产品已经交付客户项目",
                        }
                    ],
                }
            ],
        }
        result = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            transport=self._transport("investment_thesis", value),
        )
        thesis = result["content"]["investment_thesis"]
        self.assertEqual(thesis["status"], "missing")
        self.assertTrue(
            any(
                "claim_type must be inference" in item
                for item in thesis["validation_errors"]
            )
        )

    def test_falsification_requires_direction_threshold_window_and_baseline(self) -> None:
        body = "如果营业收入100万元在下一年度披露中低于100万元，那么当前经营规模可能无法维持并触发研究重审。"
        value = {
            "judgment_id": "falsification_tests",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "inference",
                    "evidence_ids": ["F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "F0001",
                            "quote": "营业收入 100 万元",
                        },
                    ],
                }
            ],
            "tests": [
                {
                    "direction": "below",
                    "threshold_evidence_id": "F0001",
                    "threshold": "100",
                    "unit": "万元",
                    "time_window": "下一份年度正式披露",
                    "evidence_ids": ["F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "F0001",
                            "quote": "营业收入 100 万元",
                        }
                    ],
                    "latest_actual_baseline": {
                        "evidence_id": "F0001",
                        "display_value": "100",
                        "unit": "万元",
                        "period": "2025FY",
                    },
                    "reason": "营业收入跌破当前披露基线意味着现有经营规模可能无法维持",
                }
            ],
        }
        result = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            transport=self._transport("falsification_tests", value),
        )
        test = result["content"]["falsification_tests"]["tests"][0]
        self.assertEqual(test["direction"], "below")
        self.assertEqual(test["latest_actual_baseline"]["period"], "2025FY")
        self.assertNotRegex(json.dumps(test), r"\d[eE][+-]\d")

        invalid_window = json.loads(json.dumps(value))
        invalid_window["tests"][0]["time_window"] = "2025FY"
        rejected = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            transport=self._transport(
                "falsification_tests",
                invalid_window,
            ),
        )
        self.assertEqual(
            rejected["content"]["falsification_tests"]["status"],
            "missing",
        )
        self.assertTrue(
            any(
                "future or next formal disclosure" in item
                for item in rejected["content"]["falsification_tests"][
                    "validation_errors"
                ]
            )
        )

    def test_single_period_fact_cannot_support_a_growth_claim(self) -> None:
        body = "如果营业收入100万元表明业务增长，那么经营趋势可能继续改善。"
        value = {
            "judgment_id": "investment_thesis",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "inference",
                    "evidence_ids": ["F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "F0001",
                            "quote": "营业收入 100 万元",
                        }
                    ],
                }
            ],
        }
        result = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            judgment_ids=["investment_thesis"],
            transport=self._transport("investment_thesis", value),
        )
        thesis = result["content"]["investment_thesis"]
        self.assertEqual(thesis["status"], "missing")
        self.assertTrue(
            any(
                "unsupported temporal comparison" in item
                for item in thesis["validation_errors"]
            )
        )

    def test_falsification_structured_fields_cannot_bypass_numeric_gate(self) -> None:
        body = "营业收入100万元若低于当前基线，则需要重审产品交付假设。"
        value = {
            "judgment_id": "falsification_tests",
            "status": "available",
            "text": body,
            "claims": [
                {
                    "text": body,
                    "claim_type": "inference",
                    "evidence_ids": ["N0001", "F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "N0001",
                            "quote": "动力电池系统产品已经交付客户项目",
                        },
                        {
                            "evidence_id": "F0001",
                            "quote": "营业收入 100 万元",
                        },
                    ],
                }
            ],
            "tests": [
                {
                    "direction": "below",
                    "threshold_evidence_id": "F0001",
                    "threshold": "100",
                    "unit": "万元",
                    "time_window": "未来999年",
                    "evidence_ids": ["N0001", "F0001"],
                    "supporting_quotes": [
                        {
                            "evidence_id": "N0001",
                            "quote": "动力电池系统产品已经交付客户项目",
                        }
                    ],
                    "latest_actual_baseline": {
                        "evidence_id": "F0001",
                        "display_value": "100",
                        "unit": "万元",
                        "period": "2025FY",
                    },
                    "reason": "收入跌破当前披露基线意味着动力电池系统产品交付未能支撑现有经营规模",
                }
            ],
        }
        result = generate_model_judgments(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
            dossier_id="dossier",
            key_file=self.key_file,
            transport=self._transport("falsification_tests", value),
        )
        item = result["content"]["falsification_tests"]
        self.assertEqual(item["status"], "missing")
        self.assertTrue(
            any("999" in error for error in item["validation_errors"])
        )

    def test_model_failure_propagates_and_writes_no_fallback(self) -> None:
        def unavailable(_payload, _secret):
            raise RuntimeError("model unavailable")

        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            generate_model_judgments(
                ticker="111111.SZ",
                issuer_identity=identity(),
                page_facts=self.facts,
                narrative_blocks=[narrative()],
                source_receipts={"financial": "f", "narrative": "n"},
                dossier_id="dossier",
                key_file=self.key_file,
                transport=unavailable,
            )

    def test_same_path_accepts_second_identity_without_ticker_branch(self) -> None:
        first = freeze_judgment_input(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=self.facts,
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
        )
        second = freeze_judgment_input(
            ticker="222222.SH",
            issuer_identity=identity("222222.SH", "另一家公司"),
            page_facts=self.facts,
            narrative_blocks=[{**narrative(), "ticker": "222222.SH"}],
            source_receipts={"financial": "f2", "narrative": "n2"},
        )
        self.assertEqual(
            [item["judgment_id"] for item in first.request["tasks"]],
            [item["judgment_id"] for item in second.request["tasks"]],
        )
        self.assertEqual(first.request["prompt_version"], second.request["prompt_version"])

    def test_suspicious_note_number_is_not_admitted_as_fact_value(self) -> None:
        bad = financial(
            "operating_cost",
            44,
            "二、营业总成本其中：营业成本 44 14,892,277,570.91",
        )
        self.assertIsNone(_source_display_token(bad))

    def test_derived_margin_components_keep_one_statement_scope(self) -> None:
        consolidated = self.facts
        parent = [
            {
                **financial("revenue", 90, "营业收入 90 万元"),
                "statement_scope": "parent",
            },
            {
                **financial("operating_cost", 60, "营业成本 60 万元"),
                "statement_scope": "parent",
            },
        ]
        frozen = freeze_judgment_input(
            ticker="111111.SZ",
            issuer_identity=identity(),
            page_facts=[*consolidated, *parent],
            narrative_blocks=[narrative()],
            source_receipts={"financial": "f", "narrative": "n"},
        )
        for evidence in frozen.registry.values():
            if evidence.get("kind") != "deterministic_derived_metric":
                continue
            component_scopes = {
                frozen.registry[item]["scope"]
                for item in evidence["component_evidence_ids"]
            }
            self.assertEqual(component_scopes, {evidence["scope"]})

    def test_generator_has_no_fstring_or_issuer_hardcoding(self) -> None:
        source_path = (
            Path(__file__).resolve().parents[1]
            / "data_core"
            / "e4_model_judgments.py"
        )
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertFalse(any(isinstance(node, ast.JoinedStr) for node in ast.walk(tree)))
        for forbidden in ("CATL", "宁德时代", "贵州茅台", "300750", "600519"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
