from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.industry_graph import (  # noqa: E402
    EvidenceCapture,
    IndustryEdge,
    IndustryGraph,
    audited_candidates,
    build_audited_graph,
    empty_industry_graph,
)
from data_core.industry_ontology import build_ontology  # noqa: E402


class IndustryGraphTest(unittest.TestCase):
    def test_graph_only_traverses_accepted_evidence_bound_edges(self) -> None:
        _, segments = build_ontology()
        edge = IndustryEdge("edge-1", segments[0].segment_id, segments[1].segment_id, "enables", "forward", "high", "2026-07-24", "evidence:official:1")
        pending = IndustryEdge("edge-2", segments[0].segment_id, segments[2].segment_id, "enables", "forward", "unknown", "2026-07-24", None, "needs_evidence")
        graph = IndustryGraph(segments, (edge, pending))
        self.assertEqual(graph.neighbors(segments[0].segment_id, direction="downstream"), (edge,))
        self.assertEqual(graph.audit()["needs_evidence"], 1)

    def test_invalid_or_unsupported_edges_fail_closed(self) -> None:
        _, segments = build_ontology()
        base = dict(edge_id="edge", source_id=segments[0].segment_id, target_id=segments[1].segment_id, relation_type="enables", direction="forward", strength="high", as_of="2026-07-24", evidence_id="evidence:1")
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            IndustryGraph(segments, (IndustryEdge(**{**base, "evidence_id": None}),))
        with self.assertRaisesRegex(ValueError, "unknown"):
            IndustryGraph(segments, (IndustryEdge(**{**base, "target_id": "missing"}),))
        self.assertEqual(empty_industry_graph().audit()["edge_count"], 0)

    def test_audited_graph_requires_all_immutable_source_captures(self) -> None:
        candidates = audited_candidates()
        urls = {item.evidence_url for item in candidates}
        self.assertEqual(len(candidates), 30)
        self.assertEqual(len(urls), 3)
        captures = tuple(
            EvidenceCapture(url, character * 64, "2026-07-24T00:00:00Z")
            for url, character in zip(sorted(urls), "abc", strict=True)
        )
        graph = build_audited_graph(captures, as_of="2026-07-24")
        self.assertEqual(graph.audit()["accepted"], 30)
        with self.assertRaisesRegex(ValueError, "require immutable captures"):
            build_audited_graph(captures[:-1], as_of="2026-07-24")


if __name__ == "__main__":
    unittest.main()
