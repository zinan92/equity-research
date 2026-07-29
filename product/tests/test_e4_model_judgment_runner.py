from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from run_e4_model_judgments import _verify_receipt  # noqa: E402


def financial_receipt() -> dict:
    value = {
        "schema_version": "e4-m2-research-wiring-v1",
        "data_kind": "real",
        "rows": [],
    }
    value["receipt_hash"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()
    return value


def narrative_receipt() -> dict:
    value = {
        "schema_version": "e4-official-narrative-evidence-v1",
        "data_kind": "real",
        "ticker": "111111.SZ",
        "blocks": [],
        "truth_boundary": {"official_cninfo_pdf_only": True},
    }
    receipt_hash = hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    value["receipt_hash"] = receipt_hash
    value["receipt_id"] = value["schema_version"] + ":" + receipt_hash
    return value


class ModelJudgmentRunnerTest(unittest.TestCase):
    def test_known_real_receipts_are_rehashed(self) -> None:
        self.assertTrue(
            _verify_receipt(financial_receipt(), kind="financial").startswith(
                "e4-m2-research-wiring-v1:"
            )
        )
        self.assertEqual(
            _verify_receipt(narrative_receipt(), kind="narrative"),
            narrative_receipt()["receipt_id"],
        )

    def test_fixture_tamper_and_declared_id_mismatch_fail_closed(self) -> None:
        fixture = financial_receipt()
        fixture["data_kind"] = "fixture"
        with self.assertRaisesRegex(ValueError, "accepted real schema"):
            _verify_receipt(fixture, kind="financial")
        tampered = financial_receipt()
        tampered["rows"].append({"ticker": "111111.SZ"})
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            _verify_receipt(tampered, kind="financial")
        wrong_id = narrative_receipt()
        wrong_id["receipt_id"] = "forged"
        with self.assertRaisesRegex(ValueError, "id mismatch"):
            _verify_receipt(wrong_id, kind="narrative")


if __name__ == "__main__":
    unittest.main()
