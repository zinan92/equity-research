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

from data_core.contracts import digest  # noqa: E402
from data_core.e4_valuation_sellside_coverage import (  # noqa: E402
    SELL_SIDE_INPUT_SCHEMA_VERSION,
    VALUATION_INPUT_SCHEMA_VERSION,
    compile_receipt_bound_coverage,
)


class ReceiptBoundCoverageTest(unittest.TestCase):
    def _partial(self) -> dict:
        return {
            "schema_version": "e4-s4-partial-report-model-v1", "data_kind": "real",
            "truth_boundary": {"tier_is_c_only": True},
            "models": [{"status": "compiled", "model": {
                "ticker": "300750.SZ", "as_of": "2026-07-01T00:00:00Z",
                "evidence_set_id": "set-1", "evidence_manifest_hash": "manifest-1",
                "report_model_hash": "model-1", "sections": {"valuation": "missing_evidence", "sell_side": "missing_evidence"},
                "decision_boundary": {"tier": "C", "action": "no_action", "target_price": None, "position_range": None},
                "blockers": ["partial_model_missing_market_fundamentals_valuation_sell_side_industry_position"],
            }}],
        }

    def _receipt_row(self, *, kind: str, ticker: str = "300750.SZ", as_of: str = "2026-07-01T00:00:00Z", context: str = "set-1") -> dict:
        row = {"ticker": ticker, "as_of": as_of, "context_evidence_set_id": context, "context_manifest_hash": "manifest-1"}
        if kind == "valuation":
            row["valuation_output_hash"] = "valuation-output"
            row["binding_hash"] = digest({"receipt": "valuation"})
        else:
            row["accepted_report_ids"] = ["broker-report-1"]
            row["receipt_hash"] = digest({"receipt": "sell-side"})
        return row

    def _write(self, root: Path, name: str, payload: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _run(self, *, valuation_row: dict | None = None, sell_side_row: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial = self._write(root, "partial.json", self._partial())
            partial_sha = hashlib.sha256(partial.read_bytes()).hexdigest()
            valuation = self._write(root, "valuation.json", {"schema_version": VALUATION_INPUT_SCHEMA_VERSION, "data_kind": "real", "partial_receipt_sha256": partial_sha, "receipts": [] if valuation_row is None else [valuation_row]})
            sell_side = self._write(root, "sell-side.json", {"schema_version": SELL_SIDE_INPUT_SCHEMA_VERSION, "data_kind": "real", "partial_receipt_sha256": partial_sha, "receipts": [] if sell_side_row is None else [sell_side_row]})
            return compile_receipt_bound_coverage(partial, valuation, sell_side)

    def test_binds_matching_real_receipts_but_preserves_tier_c_no_action(self) -> None:
        result = self._run(valuation_row=self._receipt_row(kind="valuation"), sell_side_row=self._receipt_row(kind="sell_side"))
        model = result["models"][0]["model"]
        self.assertEqual(model["sections"]["valuation"], "available")
        self.assertEqual(model["sections"]["sell_side"], "available")
        self.assertEqual(model["parent_report_model_hash"], "model-1")
        self.assertNotEqual(model["report_model_hash"], "model-1")
        self.assertEqual(model["decision_boundary"], {"tier": "C", "action": "no_action", "target_price": None, "position_range": None})
        self.assertEqual(result["counts"], {"compiled": 1, "valuation_available": 1, "sell_side_available": 1})

    def test_context_or_as_of_mismatch_is_explicitly_blocked(self) -> None:
        result = self._run(valuation_row=self._receipt_row(kind="valuation", context="other-set"), sell_side_row=self._receipt_row(kind="sell_side", as_of="2026-07-02T00:00:00Z"))
        row = result["models"][0]
        self.assertEqual(row["model"]["sections"]["valuation"], "blocked")
        self.assertEqual(row["model"]["sections"]["sell_side"], "blocked")
        self.assertIn("valuation_receipt_context_mismatch", row["blockers"])
        self.assertIn("sell_side_receipt_as_of_mismatch", row["blockers"])

    def test_fixture_and_lineage_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial = self._write(root, "partial.json", self._partial())
            valuation = self._write(root, "valuation.json", {"schema_version": VALUATION_INPUT_SCHEMA_VERSION, "data_kind": "fixture", "partial_receipt_sha256": "wrong", "receipts": []})
            sell_side = self._write(root, "sell-side.json", {"schema_version": SELL_SIDE_INPUT_SCHEMA_VERSION, "data_kind": "real", "partial_receipt_sha256": "wrong", "receipts": []})
            with self.assertRaisesRegex(ValueError, "real, schema-bound"):
                compile_receipt_bound_coverage(partial, valuation, sell_side)

    def test_missing_inputs_remain_missing_and_non_actionable(self) -> None:
        result = self._run()
        row = result["models"][0]
        self.assertEqual(row["model"]["sections"]["valuation"], "missing_evidence")
        self.assertEqual(row["model"]["sections"]["sell_side"], "missing_evidence")
        self.assertFalse(result["truth_boundary"]["counts_as_tier_a_or_b"])
