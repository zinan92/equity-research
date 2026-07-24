from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    PageCitation,
    ParserConfig,
    ReportClaim,
    assess_corpus_quality,
    parse_pdf_document,
    resolve_citation_return_path,
    validate_publication_citations,
)


def mixed_pdf(*, table: bool = False) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=(612, 792), pageCompression=0)
    document.setFont("Helvetica", 12)
    document.drawString(72, 730, "NATIVE PAGE ONE revenue evidence and business overview")
    if table:
        document.drawString(72, 700, "2025 Revenue 100 2026 Revenue 120")
        document.drawString(72, 680, "2025 Profit 20 2026 Profit 24")
    document.showPage()

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((100, 200), "SCANNED PAGE TWO searchable OCR evidence", fill="black")
    document.drawImage(ImageReader(image), 0, 0, width=612, height=792)
    document.showPage()
    document.save()
    return output.getvalue()


def fake_ocr(_pdf_bytes: bytes, page_number: int) -> str:
    if page_number == 2:
        return "SCANNED PAGE TWO searchable OCR evidence"
    return ""


class DocumentIntelligenceTest(unittest.TestCase):
    def test_native_text_and_ocr_fallback_keep_page_bound_chunks(self) -> None:
        raw = mixed_pdf()
        result = parse_pdf_document("catl-annual", raw, ocr_backend=fake_ocr)

        self.assertEqual([page.extraction_method for page in result.pages], ["native_text", "ocr"])
        self.assertIn("NATIVE PAGE ONE", result.pages[0].text)
        self.assertIn("SCANNED PAGE TWO", result.pages[1].text)
        self.assertTrue(result.chunks)
        for chunk in result.chunks:
            page = result.page(chunk.page_number)
            self.assertEqual(chunk.document_id, page.document_id)
            self.assertEqual(chunk.raw_hash, page.raw_hash)
            self.assertEqual(chunk.text, page.text[chunk.char_start : chunk.char_end])
            if chunk.page_number == 1:
                self.assertNotIn("SCANNED PAGE TWO", chunk.text)

    def test_parser_version_is_deterministic_and_rerunnable(self) -> None:
        raw = mixed_pdf()
        first = parse_pdf_document("catl-annual", raw, ocr_backend=fake_ocr)
        replay = parse_pdf_document("catl-annual", raw, ocr_backend=fake_ocr)
        upgraded = parse_pdf_document(
            "catl-annual",
            raw,
            ocr_backend=fake_ocr,
            config=ParserConfig(parser_version="park-document-parser-v2"),
        )

        self.assertEqual(first, replay)
        self.assertNotEqual(first.parse_id, upgraded.parse_id)
        self.assertNotEqual(first.parser_version, upgraded.parser_version)
        with self.assertRaisesRegex(ValueError, "raw hash"):
            parse_pdf_document(
                "catl-annual", raw, expected_raw_hash="0" * 64, ocr_backend=fake_ocr
            )

    def test_quality_receipt_meets_default_page_and_ocr_thresholds(self) -> None:
        result = parse_pdf_document("catl-annual", mixed_pdf(), ocr_backend=fake_ocr)
        quality = assess_corpus_quality(
            result,
            expected_page_markers={1: "NATIVE PAGE ONE", 2: "SCANNED PAGE TWO"},
            scanned_page_numbers=(2,),
        )

        self.assertTrue(quality.passed)
        self.assertEqual(quality.page_mapping_accuracy, 1.0)
        self.assertEqual(quality.scanned_text_coverage, 1.0)

        failed = assess_corpus_quality(
            result,
            expected_page_markers={1: "wrong marker", 2: "SCANNED PAGE TWO"},
            scanned_page_numbers=(2,),
        )
        self.assertFalse(failed.passed)
        self.assertEqual(failed.page_mapping_accuracy, 0.5)

    def test_publication_gate_requires_exact_document_page_and_raw_hash(self) -> None:
        result = parse_pdf_document("catl-annual", mixed_pdf(), ocr_backend=fake_ocr)
        valid = ReportClaim(
            "claim-valid",
            "Revenue evidence exists.",
            (
                PageCitation(
                    result.document_id,
                    1,
                    result.raw_hash,
                    quote="NATIVE PAGE ONE revenue evidence",
                    chunk_id=result.chunks[0].chunk_id,
                ),
            ),
        )
        bad_hash = ReportClaim(
            "claim-bad-hash",
            "This must not publish.",
            (PageCitation(result.document_id, 1, "f" * 64),),
        )
        bad_page = ReportClaim(
            "claim-bad-page",
            "This must not publish either.",
            (PageCitation(result.document_id, 99, result.raw_hash),),
        )
        uncited = ReportClaim("claim-uncited", "No evidence.", ())

        gate = validate_publication_citations(
            [valid, bad_hash, bad_page, uncited], {result.document_id: result}
        )

        self.assertEqual([claim.claim_id for claim in gate.published_claims], ["claim-valid"])
        self.assertEqual(
            {claim.claim_id for claim in gate.blocked_claims},
            {"claim-bad-hash", "claim-bad-page", "claim-uncited"},
        )
        self.assertFalse(gate.publishable)
        self.assertEqual(sum(check.valid for check in gate.checks), 1)

    def test_citation_return_path_requires_official_raw_bound_receipt(self) -> None:
        result = parse_pdf_document("official-filing:cninfo:annual", mixed_pdf(), ocr_backend=fake_ocr)
        citation = PageCitation(result.document_id, 2, result.raw_hash)
        payload = {
            "document_id": result.document_id,
            "content_hash": result.raw_hash,
            "storage_uri": f"raw/{result.raw_hash}.pdf",
            "http_metadata": {"source_url": "https://static.cninfo.com.cn/finalpage/annual.pdf"},
        }
        path = resolve_citation_return_path(citation, payload)
        self.assertEqual(path.page_number, 2)
        self.assertEqual(path.raw_hash, result.raw_hash)
        self.assertEqual(path.source_url, payload["http_metadata"]["source_url"])

        with self.assertRaisesRegex(ValueError, "raw_hash"):
            resolve_citation_return_path(PageCitation(result.document_id, 2, "0" * 64), payload)
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            resolve_citation_return_path(
                citation,
                {**payload, "http_metadata": {"source_url": "fixture://annual.pdf"}},
            )

    def test_possible_table_without_coordinates_is_never_silent(self) -> None:
        result = parse_pdf_document("catl-annual", mixed_pdf(table=True), ocr_backend=fake_ocr)

        self.assertEqual(result.pages[0].table_status, "possible_unlocated")
        self.assertTrue(any("possible table" in warning for warning in result.warnings))

    def test_ocr_failure_marks_page_unreadable_instead_of_inventing_text(self) -> None:
        def failed_ocr(_pdf_bytes: bytes, _page_number: int) -> str:
            raise RuntimeError("engine unavailable")

        result = parse_pdf_document("catl-annual", mixed_pdf(), ocr_backend=failed_ocr)

        self.assertEqual(result.pages[1].extraction_method, "unreadable")
        self.assertEqual(result.pages[1].text, "")
        self.assertIn("engine unavailable", result.pages[1].extraction_error)
        self.assertFalse(any(chunk.page_number == 2 for chunk in result.chunks))


if __name__ == "__main__":
    unittest.main()
