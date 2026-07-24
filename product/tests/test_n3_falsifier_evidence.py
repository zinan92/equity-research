from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.document_intelligence import DocumentPage  # noqa: E402
from data_core.n3_dossier_batch import selected_positions  # noqa: E402
from data_core.n3_falsifier_evidence import _falsifier_from_pages  # noqa: E402


class N3FalsifierEvidenceTest(unittest.TestCase):
    def test_source_bound_observable_risk_yields_one_page_citation(self) -> None:
        position = selected_positions()[0]
        page = DocumentPage(
            document_id="fixture", page_number=17, raw_hash=position.citation[2],
            parser_version="fixture", text="风险因素：若核心客户需求下降，公司收入和利润可能受到不利影响。",
            text_hash="a" * 64, extraction_method="native_text", table_status="none_detected",
        )
        evidence = _falsifier_from_pages(position, (page,), known_at="2026-07-25T00:00:00Z")
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.page_number, 17)
        self.assertEqual(evidence.raw_hash, position.citation[2])
        self.assertIn("需求下降", evidence.observed_condition)

    def test_generic_risk_heading_without_observable_condition_stays_gap(self) -> None:
        position = selected_positions()[0]
        page = DocumentPage(
            document_id="fixture", page_number=17, raw_hash=position.citation[2],
            parser_version="fixture", text="风险因素：请投资者注意相关风险。",
            text_hash="a" * 64, extraction_method="native_text", table_status="none_detected",
        )
        self.assertIsNone(_falsifier_from_pages(position, (page,), known_at="2026-07-25T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
