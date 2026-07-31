from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    EvidenceCandidate,
    EvidenceGatePolicy,
    EvidenceRequirement,
    EvidenceRole,
    build_evidence_set,
)
from data_core.round7_north_star import ROUND7_READER_UNITS  # noqa: E402
from report_contract import (  # noqa: E402
    A_SHARE_ROUND7_PROFILE_V1,
    RESEARCH_SECTION_SPECS_V3,
    SECTION_CONTRACT_SCHEMA_VERSION,
    SECTION_CONTRACT_VERSION,
    ReportContractError,
    ResearchReportProfile,
    SectionCompletion,
    build_research_section_contract_v3,
)


def value_for(value_type: str):
    return {
        "object": {"verified": True},
        "array": [{"verified": True}],
        "string": "verified",
        "number": 1.0,
        "boolean": True,
    }[value_type]


def chapter_draft(*, status: str = "human_reviewed_judgment") -> dict:
    value = {
        "status": status,
        "text": "complete evidence-bound chapter",
        "evidence_bindings": [
            {
                "document_id": "official:filing",
                "page_number": 8,
                "quoted_anchor": "原文证据",
            }
        ],
    }
    if status == "human_reviewed_judgment":
        value["review_status"] = "approved"
    return value


def all_inputs(*, include_optional: bool = True) -> dict[str, dict[str, object]]:
    return {
        spec.section_id: {
            item.key: (
                chapter_draft()
                if item.key == "chapter_draft"
                else value_for(item.value_type)
            )
            for item in spec.required_inputs
            + (spec.optional_inputs if include_optional else ())
        }
        for spec in RESEARCH_SECTION_SPECS_V3
    }


def passed_evidence_set():
    candidate = EvidenceCandidate(
        evidence_id="market-evidence",
        ticker="300750.SZ",
        component="market",
        role=EvidenceRole.PRIMARY,
        source_key="canonical_market",
        source_family="canonical_market",
        authority_tier="canonical",
        independent_of_subject=False,
        status="accepted",
        known_at="2026-07-21T10:00:00Z",
        effective_at="2026-07-21T07:00:00Z",
        manifest_hash="a" * 64,
        raw_hash="b" * 64,
        record_hash="c" * 64,
    )
    return build_evidence_set(
        ticker="300750.SZ",
        candidates=(candidate,),
        policy=EvidenceGatePolicy(
            as_of="2026-07-22T10:00:00Z",
            requirements=(
                EvidenceRequirement("market", min_primary=1, min_total=1),
            ),
        ),
    )


class ResearchSectionContractV3Test(unittest.TestCase):
    def test_canonical_contract_matches_round7_order_and_length(self) -> None:
        self.assertEqual(
            tuple(item.section_id for item in RESEARCH_SECTION_SPECS_V3),
            ROUND7_READER_UNITS,
        )
        self.assertEqual(
            [item.order for item in RESEARCH_SECTION_SPECS_V3],
            list(range(1, 10)),
        )
        self.assertEqual(
            tuple(item.title for item in RESEARCH_SECTION_SPECS_V3),
            (
                "一句话定位",
                "身份、创始人与治理",
                "技术来源与发展史",
                "商业模式与业务线",
                "财务与经营时间序列",
                "护城河的证据链",
                "风险、反题材与观察触发器",
                "研究结论与待补问题",
                "生产记录",
            ),
        )
        self.assertTrue(
            all(
                item.required_inputs and item.optional_inputs
                for item in RESEARCH_SECTION_SPECS_V3
            )
        )
        self.assertTrue(
            all(
                any(item.key == "chapter_draft" for item in section.required_inputs)
                for section in RESEARCH_SECTION_SPECS_V3
                if section.section_id != "production_record"
            )
        )
        production = RESEARCH_SECTION_SPECS_V3[-1]
        self.assertEqual(production.section_id, "production_record")
        self.assertNotIn(
            "chapter_draft",
            {item.key for item in production.required_inputs},
        )
        contract = build_research_section_contract_v3({})
        self.assertEqual(contract.target_body_characters, (3_080, 4_620))
        self.assertEqual(contract.schema_version, SECTION_CONTRACT_SCHEMA_VERSION)
        self.assertEqual(contract.contract_version, SECTION_CONTRACT_VERSION)

    def test_required_and_optional_inputs_have_fixed_semantics(self) -> None:
        first = RESEARCH_SECTION_SPECS_V3[0]
        values = all_inputs(include_optional=False)
        values[first.section_id] = {
            first.required_inputs[0].key: value_for(
                first.required_inputs[0].value_type
            )
        }
        contract = build_research_section_contract_v3(values)
        by_id = {item.section_id: item for item in contract.sections}
        self.assertIs(by_id[first.section_id].status, SectionCompletion.PARTIAL)
        self.assertEqual(
            by_id[first.section_id].missing_required,
            tuple(item.key for item in first.required_inputs[1:]),
        )
        self.assertIs(
            by_id[RESEARCH_SECTION_SPECS_V3[1].section_id].status,
            SectionCompletion.FULL,
        )
        empty = build_research_section_contract_v3({})
        self.assertEqual(
            {item.status for item in empty.sections},
            {SectionCompletion.MISSING},
        )

    def test_unreviewed_chapter_or_legacy_material_cannot_be_full(self) -> None:
        values = all_inputs(include_optional=False)
        values["one_line_positioning"]["chapter_draft"] = chapter_draft(
            status="ai_generated_judgment_unreviewed"
        )
        values["moat_evidence_chain"]["legacy_judgment_materials"] = [
            {"status": "ai_generated_judgment_unreviewed"}
        ]
        contract = build_research_section_contract_v3(values)
        by_id = {item.section_id: item for item in contract.sections}
        for section_id in ("one_line_positioning", "moat_evidence_chain"):
            self.assertIs(by_id[section_id].status, SectionCompletion.PARTIAL)
            self.assertEqual(
                by_id[section_id].status_reason,
                "pending_judgment_review",
            )

    def test_contract_identity_and_input_hashes_are_deterministic(self) -> None:
        first = build_research_section_contract_v3(all_inputs())
        second = build_research_section_contract_v3(all_inputs())
        self.assertEqual(first, second)
        self.assertEqual(
            {len(first.contract_hash), len(first.profile_hash), len(first.version_hash)},
            {64},
        )
        alternate = replace(
            A_SHARE_ROUND7_PROFILE_V1,
            profile_version="1.0.1",
            optional_modules=A_SHARE_ROUND7_PROFILE_V1.optional_modules
            + ("bank_kpi_appendix",),
        )
        changed_profile = build_research_section_contract_v3(
            all_inputs(),
            profile=alternate,
        )
        self.assertNotEqual(changed_profile.profile_hash, first.profile_hash)
        self.assertNotEqual(changed_profile.contract_hash, first.contract_hash)
        values = all_inputs()
        values["one_line_positioning"]["market_snapshot"] = {"price": 300}
        changed_input = build_research_section_contract_v3(values)
        self.assertEqual(changed_input.contract_hash, first.contract_hash)
        self.assertNotEqual(
            changed_input.sections[0].input_hash,
            first.sections[0].input_hash,
        )

    def test_chapter_without_explicit_human_approval_fails_closed(self) -> None:
        values = all_inputs(include_optional=False)
        values["one_line_positioning"]["chapter_draft"] = {
            "text": "AI output without status",
            "evidence_bindings": [
                {
                    "document_id": "official:filing",
                    "page_number": 8,
                    "quoted_anchor": "原文证据",
                }
            ],
        }
        with self.assertRaisesRegex(ReportContractError, "explicit review status"):
            build_research_section_contract_v3(values)
        values["one_line_positioning"]["chapter_draft"] = chapter_draft()
        values["one_line_positioning"]["chapter_draft"]["review_status"] = "pending"
        with self.assertRaisesRegex(ReportContractError, "not approved"):
            build_research_section_contract_v3(values)

    def test_b6_boundary_is_unchanged_for_live_acceptance(self) -> None:
        structure = build_research_section_contract_v3({})
        self.assertFalse(structure.live_eligible)
        with self.assertRaisesRegex(
            ReportContractError,
            "B6-passed evidence set",
        ):
            build_research_section_contract_v3(
                all_inputs(),
                structure_only=False,
            )
        evidence_set = passed_evidence_set()
        live = build_research_section_contract_v3(
            all_inputs(),
            structure_only=False,
            evidence_set=evidence_set,
        )
        self.assertTrue(live.live_eligible)
        self.assertEqual(live.evidence_set_id, evidence_set.evidence_set_id)
        self.assertEqual(
            live.evidence_manifest_hash,
            evidence_set.manifest_hash,
        )

    def test_unknown_old_sections_inputs_and_wrong_types_fail_closed(self) -> None:
        for retired_id in (
            "investment_thesis",
            "industry_coordinates",
            "founder_and_team",
            "development_timeline",
            "technology_products_and_business_model",
            "financials_and_valuation",
            "why_it_can_win",
            "core_risks",
            "plain_language_verdict",
        ):
            with self.subTest(retired_id=retired_id):
                with self.assertRaisesRegex(
                    ReportContractError,
                    "unknown research sections",
                ):
                    build_research_section_contract_v3({retired_id: {}})
        with self.assertRaisesRegex(ReportContractError, "received unknown inputs"):
            build_research_section_contract_v3(
                {"one_line_positioning": {"investment_thesis": {}}}
            )
        with self.assertRaisesRegex(ReportContractError, "must be object"):
            build_research_section_contract_v3(
                {"one_line_positioning": {"market_snapshot": "not-an-object"}}
            )
        broken_profile = ResearchReportProfile(
            profile_id="broken",
            profile_version="1",
            market="CN",
            section_ids=("one_line_positioning",),
        )
        with self.assertRaisesRegex(ValueError, "every canonical section"):
            build_research_section_contract_v3({}, profile=broken_profile)


if __name__ == "__main__":
    unittest.main()
