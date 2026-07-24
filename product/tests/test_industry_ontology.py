from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import build_ontology, ontology_receipt, validate_ontology  # noqa: E402


class IndustryOntologyTest(unittest.TestCase):
    def test_self_owned_ontology_has_required_stable_coverage(self) -> None:
        nodes, segments = build_ontology()
        receipt = ontology_receipt()
        self.assertEqual(len(nodes), 12)
        self.assertEqual(len(segments), 108)
        self.assertEqual(receipt["node_count"], 12)
        self.assertEqual(receipt["segment_count"], 108)
        self.assertRegex(str(receipt["identity_hash"]), r"^[0-9a-f]{64}$")
        self.assertTrue(all(item.segment_id.startswith("ai-compute/") for item in segments))
        self.assertTrue(all(item.source_strategy for item in segments))

    def test_duplicate_or_orphan_or_boundary_break_fails_closed(self) -> None:
        nodes, segments = build_ontology()
        with self.assertRaisesRegex(ValueError, "identities"):
            validate_ontology(nodes, (*segments, segments[0]))
        with self.assertRaisesRegex(ValueError, "orphan"):
            validate_ontology(nodes, (replace(segments[0], node_id="missing"), *segments[1:]))
        with self.assertRaisesRegex(ValueError, "definition"):
            validate_ontology(nodes, (replace(segments[0], definition=""), *segments[1:]))


if __name__ == "__main__":
    unittest.main()
