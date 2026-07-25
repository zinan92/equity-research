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
from data_core.e4_spot_audit_assignments import compile_spot_audit_assignments, render_spot_audit_guide, write_spot_audit_assignments  # noqa: E402


def partial(count: int = 20) -> dict:
    rows = []
    for index in range(count):
        ticker = f"{index + 1:06d}.SZ"
        model = {
            "schema_version": "e4-s4-partial-report-model-v1", "data_kind": "real", "ticker": ticker,
            "report_model_hash": f"{index + 1:064x}", "document_id": f"official:{index}", "raw_hash": f"{index + 10:064x}",
            "decision_boundary": {"tier": "C", "action": "no_action", "target_price": None, "position_range": None},
            "input_facts": {"market": {"quote": {"last_price": index + 1, "observed_at": "2026-07-25T00:00:00Z"}, "source_components": ["quote", "daily_bars"]}, "fundamentals": {"latest_period": {"report_period": "2026-03-31", "announced_at": "2026-04-30"}, "source_components": ["fundamentals", "balance_sheet", "income_statement", "cash_flow"]}},
        }
        rows.append({"ticker": ticker, "status": "compiled", "model": model})
    value = {"schema_version": "e4-s4-partial-report-model-v1", "data_kind": "real", "truth_boundary": {"tier_is_c_only": True}, "models": rows}
    value["receipt_hash"] = digest(value)
    return value


class SpotAuditAssignmentsTest(unittest.TestCase):
    def write(self, root: Path, value: dict) -> Path:
        path = root / "partial.json"; path.write_text(json.dumps(value), encoding="utf-8"); return path

    def test_selects_deterministic_pending_assignments_without_credit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), partial(22))
            first = compile_spot_audit_assignments(path); second = compile_spot_audit_assignments(path)
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])
        self.assertEqual((first["counts"], first["assignments"][0]["review_status"]), ({"assigned": 20, "pending_human_review": 20, "completed": 0}, "pending_human_review"))
        self.assertFalse(first["truth_boundary"]["counts_as_numeric_page_audit"])
        self.assertNotIn("runtime_raw_path", json.dumps(first))

    def test_rejects_less_than_twenty_or_tampered_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); short = self.write(root, partial(19))
            with self.assertRaisesRegex(ValueError, "insufficient"):
                compile_spot_audit_assignments(short)
            value = partial(); value["models"][0]["model"]["raw_hash"] = "bad"; tampered = self.write(root, value)
            with self.assertRaisesRegex(ValueError, "identity-valid"):
                compile_spot_audit_assignments(tampered)

    def test_writes_human_readable_guide(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); result = write_spot_audit_assignments(self.write(root, partial()), root)
            guide = Path(result["guide_path"]).read_text(encoding="utf-8")
        self.assertIn("not an audit result", guide)
        self.assertIn("000001.SZ", guide)
        self.assertEqual(result["receipt"]["counts"]["completed"], 0)


if __name__ == "__main__":
    unittest.main()
