from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build_v4_acceptance import build  # noqa: E402


class V4AcceptanceTests(unittest.TestCase):
    def test_receipt_is_honest_and_20_slice_is_explicit(self) -> None:
        result = build(
            acceptance_path=ROOT / "artifacts/evidence/e4-l2-m7-acceptance.json",
            official_root=ROOT / "docs/evidence/v4-m3-official",
            replay_receipt_path=ROOT / "docs/evidence/v4-m2-generalization-receipt.json",
            audit_path=ROOT / "artifacts/e4-reports/e4-l1-m6-spot-audit-assignments.json",
        )
        self.assertEqual(result["status"], "honest_baseline_not_ready")
        self.assertEqual(result["v4_baseline"]["official_bound_count"], 2)
        self.assertEqual(result["v4_baseline"]["replay_only_count"], 3)
        self.assertEqual(result["twenty_ticker_slice"]["count"], 20)
        self.assertTrue(result["twenty_ticker_slice"]["all_have_explicit_blocker"])
        self.assertFalse(result["truth_boundary"]["no_fabricated_v4_dossiers"] is False)
        self.assertEqual(result["independent_page_audit_state"]["completed_human_audits"], 0)
        self.assertEqual(result["real_100_ticker_gate"]["actual"]["spot_audits"], 0)
        self.assertEqual(result["real_100_ticker_gate"]["gap"]["spot_audits"], 20)

    def test_acceptance_receipt_can_be_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipt.json"
            result = build(
                acceptance_path=ROOT / "artifacts/evidence/e4-l2-m7-acceptance.json",
                official_root=ROOT / "docs/evidence/v4-m3-official",
                replay_receipt_path=ROOT / "docs/evidence/v4-m2-generalization-receipt.json",
                audit_path=ROOT / "artifacts/e4-reports/e4-l1-m6-spot-audit-assignments.json",
            )
            path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["contract"], "park-v4-dossier-v1")


if __name__ == "__main__":
    unittest.main()
