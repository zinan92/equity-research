from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.e4_partial_report_models import compile_partial_report_models  # noqa: E402


class PartialReportModelsTest(unittest.TestCase):
    def batch_receipt(self, root: Path) -> Path:
        raw_root = root / "raw"
        raw_root.mkdir()
        body = b"%PDF-1.7\nreal filing\n%%EOF"
        raw_hash = hashlib.sha256(body).hexdigest()
        raw_path = raw_root / f"{raw_hash}.pdf"
        raw_path.write_bytes(body)
        payload = {
            "schema_version": "e4-s4-official-evidence-batch-v1", "data_kind": "real",
            "truth_boundary": {"counts_as_report_model_coverage": False},
            "tickers": [{
                "ticker": "000001.SZ", "status": "captured", "data_kind": "real",
                "document_id": "official-filing:cninfo:1", "document_type": "annual_report",
                "published_at": "2026-03-31T00:00:00Z", "source_key": "cninfo_official_filing_document_v1",
                "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-31/real.PDF",
                "raw_hash": raw_hash, "storage_uri": f"canonical-raw/raw/sha256/{raw_hash[:2]}/{raw_hash}",
                "runtime_raw_path": str(raw_path), "fetched_at": "2026-07-24T00:00:00Z", "known_at": "2026-07-24T00:00:00Z",
            }],
        }
        path = root / "batch.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_compiles_deterministic_partial_model_without_tier_inflation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.batch_receipt(root)
            first = compile_partial_report_models(path, root)
            second = compile_partial_report_models(path, root)
            model = first["models"][0]["model"]
            self.assertEqual(first, second)
            self.assertEqual(model["decision_boundary"], {"tier": "C", "action": "no_action", "target_price": None, "position_range": None})
            self.assertEqual(first["coverage"]["000001.SZ"]["tier"], "C")
            self.assertFalse(first["coverage"]["000001.SZ"]["numeric_spot_audit"])

    def test_rejects_tampered_raw_and_nonreal_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.batch_receipt(root)
            payload = json.loads(path.read_text(encoding="utf-8"))
            Path(payload["tickers"][0]["runtime_raw_path"]).write_bytes(b"tampered")
            blocked = compile_partial_report_models(path, root)
            self.assertEqual(blocked["models"][0]["status"], "blocked")
            payload["data_kind"] = "fixture"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "real E4-S4c"):
                compile_partial_report_models(path, root)

    def test_rejects_companion_with_other_official_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.batch_receipt(root)
            companion = root / "companion.json"
            companion.write_text(json.dumps({
                "schema_version": "e4-s4-market-fundamentals-batch-v1", "data_kind": "real",
                "official_receipt_sha256": "0" * 64,
                "truth_boundary": {"counts_as_tier_a_or_b": False}, "tickers": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                compile_partial_report_models(path, root, companion)
