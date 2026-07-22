from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest


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
from report_contract import (  # noqa: E402
    A_SHARE_GENERAL_PROFILE_V1,
    RESEARCH_SECTION_SPECS_V2,
    SECTION_CONTRACT_SCHEMA_VERSION,
    SECTION_CONTRACT_VERSION,
    ReportContractError,
    ResearchReportProfile,
    SectionCompletion,
    build_research_section_contract_v2,
)


def value_for(value_type: str):
    return {
        "object": {"verified": True},
        "array": [{"verified": True}],
        "string": "verified",
        "number": 1.0,
        "boolean": True,
    }[value_type]


def all_inputs(*, include_optional: bool = True) -> dict[str, dict[str, object]]:
    return {
        spec.section_id: {
            item.key: value_for(item.value_type)
            for item in spec.required_inputs + (spec.optional_inputs if include_optional else ())
        }
        for spec in RESEARCH_SECTION_SPECS_V2
    }


def candidate() -> EvidenceCandidate:
    digest = "a" * 64
    return EvidenceCandidate(
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
        manifest_hash=digest,
        raw_hash="b" * 64,
        record_hash="c" * 64,
    )


def passed_evidence_set():
    return build_evidence_set(
        ticker="300750.SZ",
        candidates=(candidate(),),
        policy=EvidenceGatePolicy(
            as_of="2026-07-22T10:00:00Z",
            requirements=(EvidenceRequirement("market", min_primary=1, min_total=1),),
        ),
    )


def test_canonical_contract_has_18_typed_sections_and_30_to_50_page_budget() -> None:
    assert len(RESEARCH_SECTION_SPECS_V2) == 18
    assert [item.order for item in RESEARCH_SECTION_SPECS_V2] == list(range(1, 19))
    assert len({item.section_id for item in RESEARCH_SECTION_SPECS_V2}) == 18
    assert all(item.required_inputs and item.optional_inputs for item in RESEARCH_SECTION_SPECS_V2)
    assert all(item.origins for item in RESEARCH_SECTION_SPECS_V2)
    assert {
        input_spec.value_type
        for section in RESEARCH_SECTION_SPECS_V2
        for input_spec in section.required_inputs + section.optional_inputs
    }.issubset({"object", "array", "string", "number", "boolean"})

    contract = build_research_section_contract_v2({}, structure_only=True)
    assert contract.total_page_budget == (32, 50)
    assert contract.schema_version == SECTION_CONTRACT_SCHEMA_VERSION
    assert contract.contract_version == SECTION_CONTRACT_VERSION


def test_required_and_optional_inputs_have_fixed_full_partial_missing_semantics() -> None:
    first = RESEARCH_SECTION_SPECS_V2[0]
    values = all_inputs(include_optional=False)
    partial_values = {first.required_inputs[0].key: value_for(first.required_inputs[0].value_type)}
    values[first.section_id] = partial_values
    contract = build_research_section_contract_v2(values, structure_only=True)
    by_id = {item.section_id: item for item in contract.sections}

    assert by_id[first.section_id].status is SectionCompletion.PARTIAL
    assert by_id[first.section_id].missing_required == (first.required_inputs[1].key,)
    assert by_id[RESEARCH_SECTION_SPECS_V2[1].section_id].status is SectionCompletion.FULL

    empty = build_research_section_contract_v2({}, structure_only=True)
    assert {item.status for item in empty.sections} == {SectionCompletion.MISSING}
    assert {item.value for item in SectionCompletion} == {"full", "partial", "missing"}


def test_section_profile_and_version_hashes_are_bound_to_contract_identity() -> None:
    first = build_research_section_contract_v2(all_inputs(), structure_only=True)
    second = build_research_section_contract_v2(all_inputs(), structure_only=True)

    assert first == second
    assert len(first.contract_hash) == len(first.profile_hash) == len(first.version_hash) == 64
    assert all(item.profile_hash == first.profile_hash for item in first.sections)
    assert all(item.version_hash == first.version_hash for item in first.sections)
    assert [item.section_hash for item in first.sections] == [
        item.section_hash for item in RESEARCH_SECTION_SPECS_V2
    ]

    alternate = replace(
        A_SHARE_GENERAL_PROFILE_V1,
        profile_version="1.0.1",
        optional_modules=A_SHARE_GENERAL_PROFILE_V1.optional_modules + ("bank_kpi_appendix",),
    )
    changed = build_research_section_contract_v2(all_inputs(), profile=alternate, structure_only=True)
    assert changed.profile_hash != first.profile_hash
    assert changed.contract_hash != first.contract_hash
    assert changed.version_hash == first.version_hash


def test_input_hash_changes_with_content_without_changing_schema_identity() -> None:
    values = all_inputs()
    first = build_research_section_contract_v2(values, structure_only=True)
    values["executive_summary"]["market_snapshot"] = {"price": 300}
    second = build_research_section_contract_v2(values, structure_only=True)

    assert first.contract_hash == second.contract_hash
    assert first.sections[0].section_hash == second.sections[0].section_hash
    assert first.sections[0].input_hash != second.sections[0].input_hash


def test_structure_design_does_not_require_b6_but_live_acceptance_does() -> None:
    structure = build_research_section_contract_v2({}, structure_only=True)
    assert structure.live_eligible is False
    assert structure.evidence_set_id is None

    with pytest.raises(ReportContractError, match="B6-passed evidence set"):
        build_research_section_contract_v2(all_inputs(), structure_only=False)

    evidence_set = passed_evidence_set()
    live = build_research_section_contract_v2(
        all_inputs(), structure_only=False, evidence_set=evidence_set
    )
    assert live.live_eligible is True
    assert live.evidence_set_id == evidence_set.evidence_set_id
    assert live.evidence_manifest_hash == evidence_set.manifest_hash


def test_failed_b6_evidence_gate_cannot_be_attached_to_live_contract() -> None:
    failed = build_evidence_set(
        ticker="300750.SZ",
        candidates=(),
        policy=EvidenceGatePolicy(
            as_of="2026-07-22T10:00:00Z",
            requirements=(EvidenceRequirement("market", min_primary=1, min_total=1),),
        ),
    )
    assert failed.publishable is False
    with pytest.raises(ReportContractError, match="B6-passed evidence set"):
        build_research_section_contract_v2(
            all_inputs(), structure_only=False, evidence_set=failed
        )


def test_unknown_sections_inputs_and_wrong_types_fail_closed() -> None:
    with pytest.raises(ReportContractError, match="unknown research sections"):
        build_research_section_contract_v2({"invented": {}}, structure_only=True)
    with pytest.raises(ReportContractError, match="received unknown inputs"):
        build_research_section_contract_v2(
            {"executive_summary": {"invented": {}}}, structure_only=True
        )
    with pytest.raises(ReportContractError, match="must be object"):
        build_research_section_contract_v2(
            {"executive_summary": {"market_snapshot": "not-an-object"}},
            structure_only=True,
        )

    broken_profile = ResearchReportProfile(
        profile_id="broken",
        profile_version="1",
        market="CN",
        section_ids=("executive_summary",),
    )
    with pytest.raises(ValueError, match="every canonical section"):
        build_research_section_contract_v2({}, profile=broken_profile, structure_only=True)
