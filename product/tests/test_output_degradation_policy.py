from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))
from data_core.output_degradation_policy import output_allowance, output_policy_receipt  # noqa: E402


class OutputDegradationPolicyTest(unittest.TestCase):
    def test_tier_a_complete_only_permits_decision_surfaces(self) -> None:
        allowance = output_allowance("A", "complete", decision_receipt_present=True)
        self.assertTrue(allowance.show_target_price)
        self.assertTrue(allowance.show_position_range)
        self.assertTrue(allowance.show_action)

    def test_tier_a_without_a_decision_receipt_still_suppresses_action(self) -> None:
        allowance = output_allowance("A", "complete")
        self.assertFalse(allowance.show_target_price)
        self.assertIn("decision_receipt_not_present", allowance.suppression_reasons)

    def test_low_coverage_never_permits_high_confidence_position(self) -> None:
        for tier in ("A", "B", "C", "missing"):
            allowance = output_allowance(tier, "partial")
            self.assertFalse(allowance.show_target_price)
            self.assertFalse(allowance.show_position_range)
            self.assertFalse(allowance.show_action)
            self.assertIn("coverage_not_complete_no_high_confidence_position", allowance.suppression_reasons)

    def test_b_c_and_missing_are_honestly_degraded(self) -> None:
        tier_b = output_allowance("B", "complete")
        tier_c = output_allowance("C", "complete")
        missing = output_allowance("missing", "missing")
        self.assertTrue(tier_b.show_research_report)
        self.assertFalse(tier_b.show_action)
        self.assertFalse(tier_c.show_research_report)
        self.assertTrue(tier_c.show_evidence_browser)
        self.assertFalse(missing.show_evidence_browser)
        self.assertIn("display_diagnostics_only", missing.suppression_reasons)

    def test_receipt_does_not_change_existing_policies(self) -> None:
        receipt = output_policy_receipt("C", "partial")
        self.assertTrue(receipt["truth_boundary"]["does_not_modify_decision_policy"])
        self.assertTrue(receipt["truth_boundary"]["does_not_create_target_position_or_action"])
