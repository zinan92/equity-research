from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.contracts import digest  # noqa: E402
from partial_model_store import PartialModelStoreError, load_partial_model  # noqa: E402


def receipt(*, row: dict | None = None) -> dict:
    model = {
        "schema_version": "e4-s4-partial-report-model-v1", "ticker": "300750.SZ", "data_kind": "real",
        "as_of": "2026-07-25T00:00:00Z", "evidence_set_id": "set", "evidence_manifest_hash": "a" * 64,
        "raw_hash": "b" * 64, "document_id": "official:1", "report_model_hash": "c" * 64,
        "sections": {"filings": "available", "market": "available"},
        "input_facts": {"market": {"quote": {"last_price": 123.0}}},
        "blockers": ["partial_model_missing_valuation"], "numeric_spot_audit": False, "page_citation_spot_audit": False,
        "decision_boundary": {"tier": "C", "action": "no_action", "target_price": None, "position_range": None},
    }
    payload = {
        "schema_version": "e4-s4-partial-report-model-v1", "data_kind": "real",
        "truth_boundary": {"tier_is_c_only": True, "counts_as_tier_a_or_b": False},
        "models": [row or {"ticker": "300750.SZ", "status": "compiled", "model": model}],
    }
    payload["receipt_hash"] = digest(payload)
    return payload


class PartialModelStoreTest(unittest.TestCase):
    def write(self, root: Path, value: dict) -> None:
        name = "partial-report-models-test.json"
        (root / name).write_text(json.dumps(value), encoding="utf-8")
        (root / "partial-report-models-latest.json").write_text(json.dumps({"receipt": name, "receipt_hash": value["receipt_hash"]}), encoding="utf-8")

    def test_reads_safe_tier_c_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.write(root, receipt())
            actual = load_partial_model("300750", root)
        self.assertEqual((actual["ticker"], actual["status"], actual["decision_boundary"]["tier"]), ("300750.SZ", "available", "C"))
        self.assertEqual(actual["input_facts"]["market"]["quote"]["last_price"], 123.0)
        self.assertNotIn("runtime_raw_path", actual)
        self.assertIsNone(actual["decision_boundary"]["target_price"])

    def test_reports_a_valid_blocked_row_as_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.write(root, receipt(row={"ticker": "300750.SZ", "status": "blocked", "blockers": ["official_input_missing"]}))
            actual = load_partial_model("300750.SZ", root)
        self.assertEqual(actual, {"ticker": "300750.SZ", "status": "unavailable", "data_kind": "real", "blockers": ["official_input_missing"]})

    def test_refuses_tampered_receipt_and_pointer_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = receipt(); self.write(root, value)
            value["models"][0]["model"]["input_facts"] = {"market": {"quote": {"last_price": 0}}}
            (root / "partial-report-models-test.json").write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(PartialModelStoreError, "identity"):
                load_partial_model("300750.SZ", root)
            (root / "partial-report-models-latest.json").write_text(json.dumps({"receipt": "../outside.json", "receipt_hash": "x"}), encoding="utf-8")
            with self.assertRaisesRegex(PartialModelStoreError, "unsafe"):
                load_partial_model("300750.SZ", root)


if __name__ == "__main__":
    unittest.main()
