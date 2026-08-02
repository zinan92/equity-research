from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.round7_evidence import build_evidence_registry, load_source_receipts, select_section_evidence  # noqa: E402
from data_core.round7_chapter_generator import build_chapter_request  # noqa: E402
from data_core.round7_profiles import load_profile, profile_hash  # noqa: E402
from v4_dossier_generator import generate_v4_dossier  # noqa: E402
from scripts.run_round7_dossier import _validate_cutoff  # noqa: E402


class V4N2ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile_path = ROOT / "docs/evidence/v4-n2/000001.SZ-profile.json"
        self.profile = load_profile(self.profile_path, ticker="000001.SZ")

    def test_profile_is_hashed_and_receipt_bound(self) -> None:
        self.assertEqual(self.profile["profile_hash"], profile_hash(self.profile))
        self.assertEqual(
            self.profile["source_receipts"]["narrative_receipt_hash"],
            "5d605a0c080ea5e65e7ad8cf2931b151bb9654c955fe269d0f307787f037e6e0",
        )

    def test_bank_selector_uses_profile_not_catl_rules(self) -> None:
        narratives, financials = load_source_receipts(
            narrative_path=ROOT / "docs/evidence/v4-n1-official/000001.SZ-official-narrative-evidence.json",
            financial_path=ROOT / "docs/evidence/v4-n1-official/000001.SZ-financial-page-evidence.json",
            ticker="000001.SZ",
        )
        registry = build_evidence_registry(narratives, financials)
        rows = select_section_evidence(
            registry,
            section_id="business_model_and_business_lines",
            profile=self.profile,
        )
        self.assertTrue(rows)
        self.assertTrue(any("零售" in str(row.get("text")) for row in rows))
        self.assertFalse(any("动力电池" in str(row.get("text")) for row in rows))
        self.assertFalse(any("第二章 会计数据和财务指标" in str(row.get("text")) for row in rows))

    def test_bank_profile_replaces_catl_writing_instruction_and_binds_receipts(self) -> None:
        from report_contract import RESEARCH_SECTION_SPECS_V3

        spec = next(
            item
            for item in RESEARCH_SECTION_SPECS_V3
            if item.section_id == "business_model_and_business_lines"
        )
        request = build_chapter_request(
            spec=spec,
            issuer=self.profile["issuer"],
            evidence=[
                {
                    "evidence_id": "N-test",
                    "kind": "narrative",
                    "text": "零售金融覆盖个人客户。",
                    "section_path": "主要业务",
                    "self_report": False,
                    "allowed_numeric_displays": [],
                }
            ],
            profile=self.profile,
        )
        self.assertNotIn("动力电池", request["section_writing_instruction"])
        self.assertIn("零售金融", request["section_writing_instruction"])
        self.assertEqual(
            request["issuer_profile"]["source_receipts"]["narrative_receipt_hash"],
            self.profile["source_receipts"]["narrative_receipt_hash"],
        )

    def test_profile_json_is_not_a_fixture_or_model_output(self) -> None:
        raw = self.profile_path.read_text(encoding="utf-8")
        self.assertNotIn("fixture", raw.lower())
        self.assertNotIn("东财", raw)
        self.assertEqual(json.loads(raw)["schema_version"], "round7-issuer-profile-v1")

    def test_generated_round7_maps_through_v4_and_keeps_upstream_identity(self) -> None:
        source = ROOT / "artifacts/round7-dossiers"
        with __import__("tempfile").TemporaryDirectory() as tmp:
            receipt = generate_v4_dossier(
                ticker="000001.SZ",
                output_dir=Path(tmp),
                round7_dossier_path=source / "000001.SZ.receipt.json",
                round7_markdown_path=source / "000001.SZ.md",
                round7_profile_path=self.profile_path,
            )
        self.assertEqual(receipt["generation_mode"], "round7_generated_whole_dossier_adaptation")
        self.assertEqual(receipt["upstream"]["profile_hash"], self.profile["profile_hash"])
        self.assertEqual(receipt["fresh_model_calls"], 8)
        self.assertEqual(receipt["tier_credit"], "none")
        self.assertEqual(len(receipt["upstream"]["accepted_model_request_ids"]), 8)
        self.assertEqual(receipt["upstream"]["accepted_semantic_audit_count"], 8)
        self.assertTrue(receipt["upstream"]["typed_gaps"])

    def test_as_of_before_source_generation_is_rejected(self) -> None:
        narratives = {"generated_at": "2026-08-02T11:15:03+00:00", "reports": []}
        with self.assertRaisesRegex(ValueError, "precedes"):
            _validate_cutoff(
                narratives=narratives,
                financials={"page_facts": []},
                as_of="2026-08-02T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
