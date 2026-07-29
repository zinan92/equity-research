from __future__ import annotations

import sys
import unittest
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_e4_l2_m2_narrative_batch import build_summary  # noqa: E402


class NarrativeBatchVerificationTest(unittest.TestCase):
    def test_rejects_unbound_block(self):
        receipt = {
            "schema_version": "e4-l2-narrative-batch-v1", "data_kind": "real", "cohort": ["000001.SZ"] * 100,
            "configured_max_concurrency": 1, "sequential": True,
            "truth_boundary": {"official_cninfo_pdf_only": True, "page_bound_only": True},
            "rows": [{"ticker": "000001.SZ", "status": "available", "document": {"document_id": "doc", "raw_hash": "a"}}] * 100,
            "blocks": [{"document_id": "doc", "raw_hash": "wrong", "page_number": 1, "text": "x"}],
        }
        receipt["receipt_hash"] = hashlib.sha256(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "identity"):
            build_summary(receipt)
