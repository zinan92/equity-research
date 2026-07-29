from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_e4_model_judgments.py"
GENERATOR = ROOT / "product" / "data_core" / "e4_model_judgments.py"
ARTIFACT = ROOT / "artifacts" / "e4-reports" / "300750.SZ.judgments.json"
SPEC = importlib.util.spec_from_file_location("e4_model_judgment_verifier", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def _canonical_hash(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _outer_hash(receipt):
    payload = {
        key: value
        for key, value in receipt.items()
        if key != "receipt_hash"
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class ModelJudgmentVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_real_catl_receipt_passes(self) -> None:
        result = VERIFIER.verify(self.receipt, GENERATOR)
        self.assertEqual(result["status"], "passed", result["errors"])

    def test_rehashed_falsification_tamper_fails(self) -> None:
        tampered = deepcopy(self.receipt)
        test = tampered["content"]["falsification_tests"]["tests"][0]
        test["threshold"] = "999"
        tampered["content_hash"] = _canonical_hash(tampered["content"])
        tampered["receipt_hash"] = _outer_hash(tampered)
        result = VERIFIER.verify(tampered, GENERATOR)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("threshold display mismatch" in item for item in result["errors"])
        )


if __name__ == "__main__":
    unittest.main()
