from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))
from data_core.canonical_read_api import canonical_read_projection  # noqa: E402


class CanonicalReadApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {"ticker": "300750.SZ", "name": "宁德时代", "industry": "动力电池", "data_mode": "REAL", "research_status": "partial", "report_contract": {"id": "c1"}}

    def test_all_surfaces_are_canonical_only_and_live_is_explicit(self) -> None:
        for kind in ("company", "sector", "dossier", "score", "roadmap", "report"):
            value = canonical_read_projection(kind, self.report)
            self.assertEqual(value["source_state"], "live")
            self.assertEqual(value["fallback"], "none")
            self.assertFalse(value["truth_boundary"]["cached_fallback"])
            self.assertFalse(value["truth_boundary"]["fixture_fallback"])

    def test_fixture_is_labelled_never_recast_as_live(self) -> None:
        value = canonical_read_projection("company", {**self.report, "data_mode": "FIXTURE"})
        self.assertEqual(value["source_state"], "fixture")

    def test_unknown_surface_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported"):
            canonical_read_projection("unknown", self.report)
