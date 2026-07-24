from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.company_positions import REVIEW_TARGETS, position_coverage  # noqa: E402
from data_core.industry_ontology import build_ontology  # noqa: E402


class CompanyPositionTest(unittest.TestCase):
    def test_candidate_pool_is_a_share_primary_and_explicitly_unverified(self) -> None:
        self.assertGreaterEqual(len(REVIEW_TARGETS), 50)
        self.assertTrue(all(item.market == "A" for item in REVIEW_TARGETS))
        self.assertTrue(all(item.status in {"accepted", "needs_evidence"} for item in REVIEW_TARGETS))
        self.assertEqual(sum(item.status == "accepted" for item in REVIEW_TARGETS), 30)
        self.assertEqual(sum(item.citation is not None for item in REVIEW_TARGETS), 30)
        self.assertEqual(len({item.ticker for item in REVIEW_TARGETS}), len(REVIEW_TARGETS))

    def test_accepted_positions_have_official_page_citations_and_valid_ontology_segments(self) -> None:
        _, segments = build_ontology()
        segment_ids = {item.segment_id for item in segments}
        for position in REVIEW_TARGETS:
            self.assertIn(position.segment_id, segment_ids)
            if position.status == "accepted":
                assert position.citation is not None
                url, page, raw_hash = position.citation
                self.assertTrue(url.startswith("https://static.cninfo.com.cn/"))
                self.assertGreaterEqual(page, 1)
                self.assertEqual(len(raw_hash), 64)

    def test_coverage_only_counts_page_bound_citations(self) -> None:
        accepted = replace(REVIEW_TARGETS[0], status="accepted", citation=("https://official.example/report.pdf", 2, "a" * 64))
        coverage = position_coverage((accepted, REVIEW_TARGETS[1]))
        self.assertEqual(coverage, {"total": 2, "accepted": 1, "needs_evidence": 1, "page_cited": 1, "source_gaps": 0})


if __name__ == "__main__":
    unittest.main()
