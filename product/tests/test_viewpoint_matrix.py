from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    DocumentChunk,
    DocumentPage,
    DocumentParseResult,
    PageCitation,
    SellSideViewpoint,
    ViewpointClaim,
    build_sell_side_viewpoint_matrix,
    normalize_broker_estimate,
)


def document(document_id: str, raw_hash: str, text: str) -> DocumentParseResult:
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    page = DocumentPage(
        document_id=document_id,
        page_number=1,
        raw_hash=raw_hash,
        parser_version="test-parser-v1",
        text=text,
        text_hash=text_hash,
        extraction_method="native_text",
        table_status="none_detected",
    )
    chunk = DocumentChunk(
        chunk_id=f"chunk-{document_id}",
        document_id=document_id,
        page_number=1,
        raw_hash=raw_hash,
        parser_version="test-parser-v1",
        char_start=0,
        char_end=len(text),
        text=text,
        extraction_method="native_text",
    )
    return DocumentParseResult(
        document_id=document_id,
        raw_hash=raw_hash,
        parser_version="test-parser-v1",
        parse_id=f"parse-{document_id}",
        pages=(page,),
        chunks=(chunk,),
        warnings=(),
    )


def viewpoint(
    report_id: str,
    broker: str,
    report_date: str,
    *,
    raw_character: str,
    eps: float = 10.0,
    rating: str = "增持",
    target: float = 400.0,
    stance: str = "bullish",
    topic: str = "demand",
    strength: str = "explicit",
    quote: str | None = None,
) -> tuple[SellSideViewpoint, DocumentParseResult]:
    raw_hash = raw_character * 64
    document_id = f"doc-{report_id}"
    text = f"{broker} states demand and margin evidence for {report_id}."
    parsed = document(document_id, raw_hash, text)
    cited_quote = quote if quote is not None else f"demand and margin evidence for {report_id}"
    claim = ViewpointClaim(
        claim_id=f"claim-{report_id}",
        topic=topic,
        stance=stance,
        text=f"{broker} view on {topic}",
        strength=strength,
        citations=(
            PageCitation(
                document_id=document_id,
                page_number=1,
                raw_hash=raw_hash,
                quote=cited_quote,
                chunk_id=f"chunk-{document_id}",
            ),
        ),
    )
    estimate = normalize_broker_estimate(
        ticker="300750.SZ",
        broker=broker,
        analyst=f"{broker} analyst",
        report_id=report_id,
        report_date=report_date,
        raw_hash=raw_hash,
        fiscal_year=2027,
        eps=eps,
        target_price=target,
        rating=rating,
    )
    return (
        SellSideViewpoint(
            ticker="300750.SZ",
            report_id=report_id,
            report_title=f"{broker} CATL update",
            document_id=document_id,
            raw_hash=raw_hash,
            broker=broker,
            analyst=f"{broker} analyst",
            report_date=report_date,
            rating=rating,
            target_price=target,
            currency="CNY",
            estimates=(estimate,),
            claims=(claim,),
        ),
        parsed,
    )


class SellSideViewpointMatrixTest(unittest.TestCase):
    def build(self, rows):
        viewpoints = [item[0] for item in rows]
        corpus = {item[1].document_id: item[1] for item in rows}
        return build_sell_side_viewpoint_matrix(
            "300750.SZ", viewpoints, corpus, as_of="2026-04-30"
        )

    def test_page_bound_views_are_deterministic_and_feed_report_contract(self) -> None:
        first = viewpoint("r1", "甲证券", "2026-04-01", raw_character="a")
        second = viewpoint(
            "r2", "乙证券", "2026-04-02", raw_character="b", stance="bearish"
        )
        matrix = self.build([second, first])
        replay = self.build([first, second])

        self.assertEqual(matrix.matrix_id, replay.matrix_id)
        self.assertEqual(matrix.input_hash, replay.input_hash)
        self.assertEqual(matrix.coverage.coverage_level, "multi_broker")
        self.assertEqual(matrix.coverage.published_claim_count, 2)
        self.assertEqual(matrix.topics[0].allowed_summary_language, "documented_disagreement")
        report_inputs = matrix.to_report_inputs()
        self.assertEqual(set(report_inputs), {"broker_estimates", "consensus_history"})
        self.assertEqual(report_inputs["consensus_history"][0]["matrix_id"], matrix.matrix_id)

    def test_invalid_page_quote_remains_visible_but_cannot_enter_summary(self) -> None:
        row = viewpoint(
            "bad-citation",
            "甲证券",
            "2026-04-01",
            raw_character="c",
            quote="words not present on the cited page",
        )
        matrix = self.build([row])

        self.assertEqual(matrix.coverage.published_claim_count, 0)
        self.assertEqual(matrix.coverage.blocked_claim_count, 1)
        self.assertEqual(matrix.coverage.coverage_level, "insufficient")
        self.assertEqual(matrix.topics, ())
        self.assertTrue(
            any("quote not found" in error for error in matrix.blocked_claims[0].errors)
        )
        self.assertEqual(matrix.rows[0].blocked_claim_ids, ("claim-bad-citation",))

    def test_consensus_excludes_outlier_without_deleting_the_report(self) -> None:
        rows = [
            viewpoint("r1", "甲证券", "2026-04-01", raw_character="a", eps=9.5),
            viewpoint("r2", "乙证券", "2026-04-02", raw_character="b", eps=10.0),
            viewpoint("r3", "丙证券", "2026-04-03", raw_character="c", eps=10.5),
            viewpoint("r4", "丁证券", "2026-04-04", raw_character="d", eps=11.0),
            viewpoint("r5", "戊证券", "2026-04-05", raw_character="e", eps=100.0),
        ]
        matrix = self.build(rows)
        point = matrix.consensus.point("eps", 2027)

        self.assertEqual(point.mean, 10.25)
        self.assertEqual(point.contributor_count, 4)
        self.assertEqual(point.excluded_count, 1)
        self.assertEqual(len(matrix.consensus.quarantine), 1)
        self.assertEqual(len(matrix.rows), 5)

    def test_revision_timeline_preserves_rating_target_and_forecast_changes(self) -> None:
        old = viewpoint(
            "old", "同一券商", "2026-03-01", raw_character="f",
            eps=10.0, rating="持有", target=350.0,
        )
        new = viewpoint(
            "new", "同一券商", "2026-04-01", raw_character="1",
            eps=12.0, rating="买入", target=420.0,
        )
        matrix = self.build([new, old])
        revisions = {(item.dimension, item.fiscal_year): item for item in matrix.revisions}

        self.assertEqual(revisions[("rating", None)].direction, "upgraded")
        self.assertEqual(revisions[("rating", None)].previous_value, "持有")
        self.assertEqual(revisions[("target_price", None)].direction, "increased")
        self.assertEqual(revisions[("eps", 2027)].previous_value, 10.0)
        self.assertEqual(revisions[("eps", 2027)].current_value, 12.0)
        self.assertFalse(matrix.rows[0].latest_for_broker)
        self.assertTrue(matrix.rows[1].latest_for_broker)

    def test_summary_language_never_upgrades_tentative_or_mixed_evidence(self) -> None:
        tentative = viewpoint(
            "tentative", "甲证券", "2026-04-01", raw_character="2", strength="tentative"
        )
        tentative_matrix = self.build([tentative])
        self.assertEqual(
            tentative_matrix.topics[0].allowed_summary_language,
            "tentative_report_language_only",
        )

        mixed = [
            viewpoint("m1", "甲证券", "2026-04-01", raw_character="3", stance="bullish"),
            viewpoint("m2", "乙证券", "2026-04-02", raw_character="4", stance="bullish"),
            viewpoint("m3", "丙证券", "2026-04-03", raw_character="5", stance="bearish"),
        ]
        mixed_matrix = self.build(mixed)
        topic = mixed_matrix.topics[0]
        self.assertEqual(topic.evidence_level, "multi_broker")
        self.assertEqual(topic.allowed_summary_language, "documented_disagreement")
        self.assertEqual(len(topic.bullish_claim_ids), 2)
        self.assertEqual(len(topic.bearish_claim_ids), 1)

    def test_report_estimate_identity_mismatch_fails_closed(self) -> None:
        item, parsed = viewpoint("r1", "甲证券", "2026-04-01", raw_character="6")
        wrong = normalize_broker_estimate(
            ticker="300750.SZ",
            broker="另一券商",
            analyst="analyst",
            report_id="r1",
            report_date="2026-04-01",
            raw_hash="6" * 64,
            fiscal_year=2027,
            eps=10.0,
        )
        broken = SellSideViewpoint(**{**item.__dict__, "estimates": (wrong,)})

        with self.assertRaisesRegex(ValueError, "estimate identity"):
            build_sell_side_viewpoint_matrix(
                "300750.SZ", [broken], {parsed.document_id: parsed}, as_of="2026-04-30"
            )


if __name__ == "__main__":
    unittest.main()
