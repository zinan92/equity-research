from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.evidence_gate import EvidenceCandidate, EvidenceGatePolicy, EvidenceRequirement, EvidenceRole, SourceCoverageGap, build_evidence_set  # noqa: E402
from data_core.research_degradation import ResearchTier, assess_any_ticker  # noqa: E402
from report_contract import RESEARCH_SECTION_SPECS_V2, build_research_section_contract_v2  # noqa: E402


def evidence(*, passed: bool = True, gaps=()):
    candidate = EvidenceCandidate(
        "official-filing", "300750.SZ", "filings", EvidenceRole.PRIMARY, "cninfo", "issuer", "official", False,
        "accepted", "2026-07-21T10:00:00Z", "2026-07-21T09:00:00Z", "a" * 64, "b" * 64, "c" * 64,
    )
    requirement = EvidenceRequirement("filings", min_primary=1 if passed else 2, min_total=1 if passed else 2)
    return build_evidence_set(ticker="300750.SZ", candidates=(candidate,), policy=EvidenceGatePolicy(as_of="2026-07-22T10:00:00Z", requirements=(requirement,)), source_gaps=gaps)


def full_inputs():
    value = {"object": {"accepted": True}, "array": [{"accepted": True}], "string": "accepted", "number": 1.0, "boolean": True}
    return {spec.section_id: {item.key: value[item.value_type] for item in spec.required_inputs} for spec in RESEARCH_SECTION_SPECS_V2}


class ResearchDegradationTest(unittest.TestCase):
    def test_a_tier_requires_real_passed_evidence_and_all_sections_full(self) -> None:
        set_ = evidence()
        contract = build_research_section_contract_v2(full_inputs(), structure_only=False, evidence_set=set_)
        receipt = assess_any_ticker("300750.SZ", evidence_set=set_, section_contract=contract)
        self.assertEqual(receipt.tier, ResearchTier.A)
        self.assertEqual(receipt.blocked_fields, ())
        self.assertIn("position_range", receipt.allowed_fields)

    def test_b_tier_is_partial_and_cannot_emit_action_fields(self) -> None:
        set_ = evidence()
        inputs = full_inputs()
        inputs["valuation"] = {}
        contract = build_research_section_contract_v2(inputs, structure_only=False, evidence_set=set_)
        receipt = assess_any_ticker("300750.SZ", evidence_set=set_, section_contract=contract)
        self.assertEqual(receipt.tier, ResearchTier.B)
        self.assertEqual(receipt.blocked_fields, ("action", "target_price", "position_range"))
        self.assertIn("partial_or_missing_sections", receipt.reasons)

    def test_c_and_missing_preserve_source_actions_and_reject_fixture_upgrade(self) -> None:
        insufficient = evidence(passed=False, gaps=(SourceCoverageGap("valuation", "valuation", "not captured", required=True),))
        c = assess_any_ticker("300750.SZ", evidence_set=insufficient, section_contract=None)
        self.assertEqual(c.tier, ResearchTier.C)
        self.assertTrue(any("run the C2 valuation bridge" in item.next_step for item in c.source_gap_actions))
        fixture = assess_any_ticker("300750.SZ", evidence_set=evidence(), section_contract=None, data_kind="fixture")
        self.assertEqual(fixture.tier, ResearchTier.MISSING)
        self.assertIn("non_real_data_kind:fixture", fixture.reasons)

    def test_manifest_and_ticker_mismatch_fail_closed(self) -> None:
        set_ = evidence()
        contract = build_research_section_contract_v2(full_inputs(), structure_only=False, evidence_set=set_)
        with self.assertRaisesRegex(ValueError, "ticker mismatch"):
            assess_any_ticker("600519.SH", evidence_set=set_, section_contract=contract)


if __name__ == "__main__":
    unittest.main()
