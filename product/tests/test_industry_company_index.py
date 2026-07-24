from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.company_positions import REVIEW_TARGETS  # noqa: E402
from data_core.industry_company_index import IndustryCompanyIndex, build_industry_company_index  # noqa: E402
from data_core.industry_ontology import build_ontology  # noqa: E402


class IndustryCompanyIndexTest(unittest.TestCase):
    def test_bidirectional_lookup_keeps_unaccepted_records_out_of_facts(self) -> None:
        index = build_industry_company_index()
        accepted = index.company("300750.SZ")
        self.assertIsNotNone(accepted)
        assert accepted is not None
        self.assertEqual(accepted.segment_id, "ai-compute/energy-supply-chain/battery")
        self.assertIsNone(index.company("688041.SH"))
        self.assertEqual(index.company("688041.SH", include_unaccepted=True).status, "needs_evidence")

        battery_facts = index.companies_for_segment("ai-compute/energy-supply-chain/battery")
        self.assertEqual([item.ticker for item in battery_facts], ["002460.SZ", "300750.SZ"])
        self.assertEqual(
            [item.ticker for item in index.companies_for_segment("ai-compute/chip-design/cpu", include_unaccepted=True)],
            ["688041.SH", "688047.SH"],
        )

    def test_index_receipt_reconciles_existing_position_coverage_and_is_deterministic(self) -> None:
        first = build_industry_company_index().receipt()
        second = build_industry_company_index(tuple(reversed(REVIEW_TARGETS))).receipt()
        self.assertEqual(first["coverage"], {"total": 50, "accepted": 30, "needs_evidence": 20, "page_cited": 30, "source_gaps": 0})
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])
        self.assertTrue(first["truth_boundary"]["accepted_only_in_public_lookup"])

    def test_unknown_and_invalid_records_fail_closed(self) -> None:
        index = build_industry_company_index()
        self.assertIsNone(index.company("000000.SZ"))
        with self.assertRaisesRegex(ValueError, "unknown industry segment"):
            index.companies_for_segment("unknown/segment")

        _, segments = build_ontology()
        with self.assertRaisesRegex(ValueError, "unknown ontology segment"):
            IndustryCompanyIndex((replace(REVIEW_TARGETS[0], segment_id="unknown/segment"),), segments)
        with self.assertRaisesRegex(ValueError, "requires page citation"):
            IndustryCompanyIndex((replace(REVIEW_TARGETS[0], status="accepted"),), segments)


if __name__ == "__main__":
    unittest.main()
