from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "product") not in sys.path:
    sys.path.insert(0, str(ROOT / "product"))

from data_core.industry_catalysts import CatalystSection, build_catalyst_profiles, catalyst_coverage  # noqa: E402
from data_core.industry_graph import EvidenceCapture, audited_candidates  # noqa: E402


class IndustryCatalystTest(unittest.TestCase):
    def test_all_segments_have_ordered_explicit_sections_and_replay(self) -> None:
        first = build_catalyst_profiles((), as_of="2026-07-24")
        self.assertEqual(first, build_catalyst_profiles((), as_of="2026-07-24"))
        self.assertEqual(catalyst_coverage(first), {"total": 108, "available": 0, "missing_evidence": 108, "fact_sections": 0})
        self.assertTrue(all(len(item.sections) == 6 and item.status == "missing_evidence" for item in first))

    def test_captured_first_party_sources_only_promote_connected_segments(self) -> None:
        urls = sorted({item.evidence_url for item in audited_candidates()})
        captures = tuple(EvidenceCapture(url, character * 64, "2026-07-24T00:00:00Z") for url, character in zip(urls, "abc", strict=True))
        profiles = build_catalyst_profiles(captures, as_of="2026-07-24")
        coverage = catalyst_coverage(profiles)
        self.assertGreaterEqual(coverage["available"], 20)
        self.assertEqual(coverage["fact_sections"], coverage["available"])
        for profile in profiles:
            profile.validate()

    def test_sections_fail_closed_when_fact_or_judgment_identity_is_spoofed(self) -> None:
        with self.assertRaisesRegex(ValueError, "fact section"):
            CatalystSection("current_state", "fact", "x").validate()
        with self.assertRaisesRegex(ValueError, "research judgment"):
            CatalystSection("driver", "research_judgment", "x", model_version=None).validate()

    def test_stale_or_future_source_capture_fails_closed(self) -> None:
        url = audited_candidates()[0].evidence_url
        with self.assertRaisesRegex(ValueError, "stale"):
            build_catalyst_profiles((EvidenceCapture(url, "a" * 64, "2026-07-01T00:00:00Z"),), as_of="2026-07-24")
        with self.assertRaisesRegex(ValueError, "future"):
            build_catalyst_profiles((EvidenceCapture(url, "a" * 64, "2026-07-25T00:00:00Z"),), as_of="2026-07-24")


if __name__ == "__main__":
    unittest.main()
