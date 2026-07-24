from __future__ import annotations

import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.decision_policy import DecisionInput, decide  # noqa: E402
from data_core.vertical_slices import (  # noqa: E402
    compile_three_company_vertical_slices,
    official_evidence_anchors,
    vertical_slice_audit,
)


class VerticalSliceTest(unittest.TestCase):
    def test_real_official_anchors_have_page_and_raw_identity(self) -> None:
        anchors = official_evidence_anchors()
        self.assertEqual([item.ticker for item in anchors], ["300750.SZ", "600519.SH", "600036.SH"])
        self.assertEqual({item.segment_id for item in anchors}, {
            "cross-sector/battery", "cross-sector/consumer", "cross-sector/bank",
        })
        for anchor in anchors:
            self.assertTrue(anchor.document_url.startswith("https://"))
            self.assertGreaterEqual(anchor.page, 1)
            self.assertEqual(len(anchor.raw_hash), 64)

    def test_same_pipeline_keeps_all_missing_inputs_and_blocks_decision(self) -> None:
        rows = compile_three_company_vertical_slices()
        self.assertEqual(len({item.dossier.schema_version for item in rows}), 1)
        self.assertEqual(len({item.report.report_contract["contract_version"] for item in rows}), 1)
        for row in rows:
            self.assertEqual(row.decision.action, "no_action")
            self.assertIn("missing_market_price", row.decision.reasons)
            self.assertIn("insufficient_evidence_coverage", row.decision.reasons)
            self.assertEqual(row.gaps, ("market_price", "valuation", "quality_risk_liquidity", "sell_side", "catalyst_profile"))
            self.assertEqual(row, next(item for item in compile_three_company_vertical_slices() if item.ticker == row.ticker))

    def test_policy_never_requires_a_fabricated_price_for_a_blocked_receipt(self) -> None:
        receipt = decide(DecisionInput(
            ticker="300750.SZ", context_manifest_hash="a" * 64, dossier_id="dossier_test",
            current_price=None, target_price=None, quality_score=None, risk_score=None, liquidity_score=None,
            coverage_passed=False, sector_exposure=0, current_position=0, cash_weight=1,
        ))
        self.assertEqual(receipt.action, "no_action")
        self.assertIn("missing_market_price", receipt.reasons)

    def test_audit_names_evidence_and_never_promotes_fixture_facts(self) -> None:
        audit = vertical_slice_audit()
        self.assertEqual(audit["status"], "partial_evidence_bound")
        self.assertFalse(audit["fixture_facts_used"])
        self.assertTrue(audit["shared_schema"])
        self.assertEqual(len(audit["companies"]), 3)


if __name__ == "__main__":
    unittest.main()
