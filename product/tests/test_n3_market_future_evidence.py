from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.document_intelligence import DocumentPage  # noqa: E402
from data_core.n3_dossier_batch import selected_positions  # noqa: E402
from data_core.n3_market_future_evidence import _from_pages  # noqa: E402


class N3MarketFutureEvidenceTest(unittest.TestCase):
    def test_source_bound_forward_market_driver_yields_one_page_citation(self) -> None:
        position = selected_positions()[0]
        page = DocumentPage(document_id="fixture", page_number=18, raw_hash=position.citation[2], parser_version="fixture", text="随着下游市场需求持续增长，公司将扩大相关产品布局。", text_hash="a" * 64, extraction_method="native_text", table_status="none_detected")
        evidence = _from_pages(position, (page,), known_at="2026-07-25T00:00:00Z")
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.page_number, 18)
        self.assertEqual(evidence.observation_type, "issuer_disclosed_market_outlook")

    def test_generic_future_aspiration_without_market_context_stays_gap(self) -> None:
        position = selected_positions()[0]
        page = DocumentPage(document_id="fixture", page_number=18, raw_hash=position.citation[2], parser_version="fixture", text="公司未来将持续努力提升管理水平。", text_hash="a" * 64, extraction_method="native_text", table_status="none_detected")
        self.assertIsNone(_from_pages(position, (page,), known_at="2026-07-25T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
