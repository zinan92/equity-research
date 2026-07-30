from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_r2_industry_wiring import wire_r2_industry_receipts  # noqa: E402
from report_contract import build_research_section_contract_v3  # noqa: E402


def receipts():
    audit = {"schema_version": "r2-ai-compute-world-model-acceptance-v1", "status": "passed", "gates": {"ontology": True, "company_positions": True, "relationship_graph": True, "dossiers": True, "five_questions": True, "archive_isolation": True}, "receipt_hash": "a" * 64}
    batch = {"schema_version": "n3-dossier-batch-v1", "receipt_hash": "b" * 64, "counts": {"requested": 20, "compiled": 20, "failed": 0, "no_action": 20}, "rows": [{"ticker": "300750.SZ", "status": "compiled", "dossier_id": "dossier_catl"}]}
    return audit, batch


class R2IndustryWiringTest(unittest.TestCase):
    def test_only_a_page_cited_issuer_gets_profile_inputs(self) -> None:
        inputs, receipts_ = wire_r2_industry_receipts(*receipts(), ticker="300750.SZ")
        self.assertEqual(set(inputs), {"industry_coordinates", "technology_products_and_business_model"})
        self.assertIn("r2_acceptance_receipt_id", receipts_)
        self.assertEqual(inputs["industry_coordinates"]["company_position"]["citation"]["page"], 2)
        contract = build_research_section_contract_v3(inputs)
        sections = {item.section_id: item for item in contract.sections}
        self.assertEqual(sections["industry_coordinates"].status.value, "partial")
        self.assertEqual(sections["technology_products_and_business_model"].status.value, "partial")
        self.assertEqual(sections["development_timeline"].status.value, "missing")

    def test_missing_issuer_position_is_not_forced_into_c1(self) -> None:
        inputs, reason = wire_r2_industry_receipts(*receipts(), ticker="600519.SH")
        self.assertEqual(inputs, {})
        self.assertIn("shape_mismatch", reason)

    def test_partial_audit_is_rejected(self) -> None:
        audit, batch = receipts(); audit["status"] = "partial"
        with self.assertRaisesRegex(ValueError, "not passed"):
            wire_r2_industry_receipts(audit, batch, ticker="300750.SZ")
