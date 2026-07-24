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

from data_core.e4_context_pack_models import compile_context_pack_models  # noqa: E402


AS_OF = "2026-07-25T00:00:00Z"


class ContextPackModelsTest(unittest.TestCase):
    def _write(self, root: Path, name: str, value: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _inputs(self, root: Path) -> tuple[Path, Path, Path]:
        official_sha = "a" * 64
        source = {"source_key": "eastmoney", "raw_hash": "b" * 64, "manifest_hash": "c" * 64, "known_at": AS_OF, "publishable": True}
        market = {"schema_version": "e4-s4-market-fundamentals-batch-v1", "data_kind": "real", "official_receipt_sha256": official_sha, "truth_boundary": {"counts_as_tier_a_or_b": False}, "tickers": [{"ticker": "300750.SZ", "data_kind": "real", "market_available": True, "fundamentals_available": True, "source_receipts": {key: source for key in ("quote", "daily_bars", "fundamentals", "balance_sheet", "income_statement", "cash_flow")}}]}
        market_path = self._write(root, "market.json", market)
        partial = {"schema_version": "e4-s4-partial-report-model-v1", "data_kind": "real", "input_receipt_sha256": official_sha, "companion_receipt_sha256": hashlib.sha256(market_path.read_bytes()).hexdigest(), "truth_boundary": {"tier_is_c_only": True}, "models": [{"ticker": "300750.SZ", "status": "compiled", "model": {"ticker": "300750.SZ", "as_of": AS_OF, "evidence_set_id": "set-1", "evidence_manifest_hash": "manifest-1", "raw_hash": "d" * 64, "document_id": "official:1", "report_model_hash": "model-1", "sections": {"valuation": "missing_evidence", "sell_side": "missing_evidence"}, "decision_boundary": {"tier": "C", "action": "no_action", "target_price": None, "position_range": None}, "blockers": ["partial_model_missing_market_fundamentals_valuation_sell_side_industry_position"]}}]}
        partial_path = self._write(root, "partial.json", partial)
        matrix = {"schema_version": "e4-s4-sell-side-matrix-v1", "data_kind": "real", "as_of": AS_OF, "truth_boundary": {"counts_as_tier_a_or_b": False}, "matrices": [{"ticker": "300750.SZ", "status": "compiled", "matrix": {"matrix_id": "matrix-1", "as_of": AS_OF, "input_hash": "e" * 64, "rows": [{"report_id": "report-1"}]}}]}
        return partial_path, market_path, self._write(root, "matrix.json", matrix)

    def test_matching_real_inputs_create_deterministic_tier_c_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._inputs(Path(directory))
            first = compile_context_pack_models(*paths, as_of=AS_OF)
            second = compile_context_pack_models(*paths, as_of=AS_OF)
            row = first["models"][0]
            self.assertEqual(first, second)
            self.assertEqual(row["context_pack"]["market_fundamentals"]["status"], "available")
            self.assertEqual(row["context_pack"]["sell_side"]["report_ids"], ["report-1"])
            self.assertEqual(row["model"]["decision_boundary"]["tier"], "C")
            self.assertFalse(first["truth_boundary"]["counts_as_tier_a_or_b"])

    def test_lineage_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            partial, market, matrix = self._inputs(Path(directory))
            value = json.loads(market.read_text())
            value["official_receipt_sha256"] = "f" * 64
            market.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "official lineage"):
                compile_context_pack_models(partial, market, matrix, as_of=AS_OF)

    def test_cutoff_mismatch_is_explicitly_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            partial, market, matrix = self._inputs(Path(directory))
            value = json.loads(market.read_text())
            value["tickers"][0]["source_receipts"]["quote"] = {**value["tickers"][0]["source_receipts"]["quote"], "known_at": "2026-07-24T00:00:00Z"}
            market.write_text(json.dumps(value), encoding="utf-8")
            partial_value = json.loads(partial.read_text())
            partial_value["companion_receipt_sha256"] = hashlib.sha256(market.read_bytes()).hexdigest()
            partial.write_text(json.dumps(partial_value), encoding="utf-8")
            result = compile_context_pack_models(partial, market, matrix, as_of=AS_OF)
            self.assertEqual(result["models"][0]["context_pack"]["market_fundamentals"]["status"], "blocked")
            self.assertIn("market_fundamentals_quote_cutoff_mismatch", result["models"][0]["blockers"])

    def test_missing_sell_side_matrix_remains_missing_not_borrowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            partial, market, matrix = self._inputs(Path(directory))
            value = json.loads(matrix.read_text()); value["matrices"] = []
            matrix.write_text(json.dumps(value), encoding="utf-8")
            result = compile_context_pack_models(partial, market, matrix, as_of=AS_OF)
            self.assertEqual(result["models"][0]["context_pack"]["sell_side"]["status"], "missing_evidence")
            self.assertEqual(result["models"][0]["model"]["sections"]["sell_side"], "missing_evidence")
