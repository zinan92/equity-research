from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_judgment_wiring import wire_unreviewed_judgment_receipt  # noqa: E402
from report_contract import build_research_section_contract_v2  # noqa: E402


def receipt() -> dict:
    citation = {"document_id": "official:1", "raw_hash": "a" * 64, "page_number": 8, "quoted_anchor": "收入", "source_url": "https://static.cninfo.com.cn/a.pdf"}
    judgment = {"status": "ai_generated_judgment_unreviewed", "facts": [{"metric": "revenue", "citation": citation}], "text": "draft"}
    value = {"schema_version": "e4-m3-catl-judgments-v1", "data_kind": "real", "ticker": "300750.SZ", "source_dossier_receipt": "r2", "content": {key: dict(judgment) for key in ("investment_thesis", "variant_view", "moat_assessment", "risk_register", "falsification_tests", "monitoring_kpis", "action_triggers", "accounting_checks", "operating_kpis", "margin_bridge")}}
    value["receipt_hash"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value


def model_receipt() -> dict:
    citation = {
        "document_id": "official:1",
        "raw_hash": "a" * 64,
        "page_number": 8,
        "quoted_anchor": "收入",
        "source_url": "https://static.cninfo.com.cn/a.pdf",
    }
    content = {
        "investment_thesis": {
            "status": "ai_generated_judgment_unreviewed",
            "facts": [{"metric": "revenue", "citation": citation}],
            "text": "model draft",
        }
    }
    canonical = lambda value: hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    value = {
        "schema_version": "e4-model-judgments-v1",
        "data_kind": "real",
        "ticker": "300750.SZ",
        "generator_version": "e4-model-judgments-v1",
        "prompt_version": "e4-model-judgments-prompt-v1",
        "validator_version": "e4-model-judgments-validator-v1",
        "input_hash": "b" * 64,
        "prompt_hash": "c" * 64,
        "response_hashes": ["d" * 64],
        "model_receipts": [
            {
                "request_id": "request-1",
                "model": "model",
                "finish_reason": "stop",
            }
        ],
        "content_hash": canonical(content),
        "content": content,
        "validation": {"status": "passed", "errors": {}},
    }
    value["receipt_hash"] = hashlib.sha256(
        json.dumps(value, sort_keys=True).encode()
    ).hexdigest()
    return value


class JudgmentWiringTest(unittest.TestCase):
    def test_receipt_identified_drafts_are_present_but_not_full(self) -> None:
        inputs = wire_unreviewed_judgment_receipt(receipt(), ticker="300750.SZ")
        contract = build_research_section_contract_v2(inputs)
        by_section = {item.section_id: item for item in contract.sections}
        self.assertEqual(by_section["investment_thesis"].status.value, "partial")
        self.assertEqual(by_section["investment_thesis"].status_reason, "pending_judgment_review")
        self.assertEqual(by_section["investment_thesis"].pending_judgment_inputs, ("investment_thesis", "variant_view"))
        self.assertIn("receipt_id", inputs["investment_thesis"]["investment_thesis"]["source_receipt"])

    def test_unreviewed_input_cannot_upgrade_an_otherwise_complete_section(self) -> None:
        inputs = wire_unreviewed_judgment_receipt(receipt(), ticker="300750.SZ")
        inputs["competition_and_moat"]["peer_comparison"] = [{"peer": "official"}]
        contract = build_research_section_contract_v2(inputs)
        section = next(item for item in contract.sections if item.section_id == "competition_and_moat")
        self.assertEqual(section.status.value, "partial")
        self.assertEqual(section.status_reason, "pending_judgment_review")

    def test_tampered_or_non_real_receipt_is_rejected(self) -> None:
        forged = receipt(); forged["data_kind"] = "fixture"
        with self.assertRaisesRegex(ValueError, "not a real"):
            wire_unreviewed_judgment_receipt(forged, ticker="300750.SZ")
        forged = receipt(); forged["receipt_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            wire_unreviewed_judgment_receipt(forged, ticker="300750.SZ")

    def test_generic_receipt_requires_real_model_and_content_identity(self) -> None:
        inputs = wire_unreviewed_judgment_receipt(
            model_receipt(),
            ticker="300750.SZ",
        )
        self.assertIn("investment_thesis", inputs)
        forged = model_receipt()
        forged["model_receipts"][0]["request_id"] = None
        forged["receipt_hash"] = hashlib.sha256(
            json.dumps(
                {key: value for key, value in forged.items() if key != "receipt_hash"},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "model-call"):
            wire_unreviewed_judgment_receipt(forged, ticker="300750.SZ")
        forged = model_receipt()
        forged["content"]["investment_thesis"]["text"] = "tampered"
        forged["receipt_hash"] = hashlib.sha256(
            json.dumps(
                {key: value for key, value in forged.items() if key != "receipt_hash"},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "content hash"):
            wire_unreviewed_judgment_receipt(forged, ticker="300750.SZ")
