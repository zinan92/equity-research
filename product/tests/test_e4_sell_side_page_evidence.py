from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_sell_side_page_evidence import compile_sell_side_page_evidence  # noqa: E402


def pdf_bytes() -> bytes:
    output = io.BytesIO(); page = canvas.Canvas(output, pageCompression=0)
    page.drawString(72, 720, "Sell-side report page evidence with revenue outlook")
    page.showPage(); page.save()
    return output.getvalue()


class SellSidePageEvidenceTest(unittest.TestCase):
    def _receipt(self, report: dict) -> dict:
        return {"schema_version": "e4-s4-sell-side-evidence-batch-v1", "data_kind": "real", "truth_boundary": {"counts_as_tier_a_or_b": False}, "tickers": [{"ticker": "300750.SZ", "reports": [report]}]}

    def _write(self, root: Path, payload: dict) -> Path:
        path = root / "batch.json"; path.write_text(json.dumps(payload), encoding="utf-8"); return path

    def test_parses_hash_bound_pdf_into_page_and_chunk_identities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw_root = root / "runtime"; raw_root.mkdir(); raw = pdf_bytes(); raw_hash = hashlib.sha256(raw).hexdigest(); path = raw_root / "raw.pdf"; path.write_bytes(raw)
            report = {"report_id": "r1", "archive_status": "archived_pdf", "pdf_raw_hash": raw_hash, "runtime_raw_path": str(path), "source_url": "https://pdf.dfcfw.com/pdf/H3_r1_1.pdf"}
            output = compile_sell_side_page_evidence(self._write(root, self._receipt(report)), raw_root)
            document = output["documents"][0]
            self.assertEqual((document["status"], document["raw_hash"]), ("parsed", raw_hash))
            self.assertTrue(document["pages"]); self.assertTrue(document["chunks"])
            self.assertFalse(output["truth_boundary"]["counts_as_tier_a_or_b"])

    def test_missing_mismatched_and_metadata_rows_stay_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw_root = root / "runtime"; raw_root.mkdir(); raw = pdf_bytes(); path = raw_root / "bad.pdf"; path.write_bytes(raw)
            reports = [
                {"report_id": "mismatch", "archive_status": "archived_pdf", "pdf_raw_hash": "0" * 64, "runtime_raw_path": str(path), "source_url": "https://pdf.dfcfw.com/pdf/H3_x_1.pdf"},
                {"report_id": "metadata", "archive_status": "metadata_only", "source_url": "https://pdf.dfcfw.com/pdf/H3_y_1.pdf"},
            ]
            output = compile_sell_side_page_evidence(self._write(root, self._receipt(reports[0])), raw_root)
            self.assertEqual(output["documents"][0]["blockers"], ["sell_side_page_parse_failed"])
            output = compile_sell_side_page_evidence(self._write(root, self._receipt(reports[1])), raw_root)
            self.assertEqual(output["documents"][0]["blockers"], ["sell_side_pdf_not_archived"])
