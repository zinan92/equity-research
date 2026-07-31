from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_judgment_review_queue import build_judgment_review_queue  # noqa: E402
from tests.test_e4_judgment_wiring import receipt  # noqa: E402


class JudgmentReviewQueueTest(unittest.TestCase):
    def test_queue_has_full_text_page_citations_and_impact_order(self) -> None:
        queue = build_judgment_review_queue(receipt(), ticker="300750.SZ")
        self.assertEqual(queue["counts"]["pending_human_review"], 10)
        self.assertEqual(queue["items"][0]["judgment_id"], "investment_thesis")
        thesis = next(item for item in queue["items"] if item["judgment_id"] == "investment_thesis")
        self.assertEqual(thesis["current_section_reason"], "pending_judgment_review")
        self.assertFalse(thesis["would_promote_section_to_full"])
        self.assertIn("chapter_draft", thesis["remaining_required_inputs_after_approval"])
        self.assertIn("variant_view", thesis["remaining_required_inputs_after_approval"])
        self.assertEqual(thesis["section_status_after_all_pending_judgments_approved"], "partial")
        self.assertEqual(thesis["citations"][0]["document_id"], "official:1")
        self.assertEqual(thesis["citations"][0]["pdf_page_url"], "https://static.cninfo.com.cn/a.pdf#page=8")
        moat = next(item for item in queue["items"] if item["judgment_id"] == "moat_assessment")
        self.assertFalse(moat["would_promote_section_to_full"])
        self.assertIn("moat_evidence", moat["remaining_required_inputs_after_approval"])
        risks = [item for item in queue["items"] if item["section_id"] == "risks_counter_thesis_and_triggers"]
        self.assertEqual(len(risks), 4)
        self.assertTrue(all(not item["would_promote_section_to_full"] for item in risks))
        self.assertTrue(
            all("chapter_draft" in item["remaining_required_inputs_after_approval"] for item in risks)
        )
