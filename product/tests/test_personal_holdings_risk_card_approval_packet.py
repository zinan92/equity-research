from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_personal_holdings_risk_card_approval_packet import (
    apply_outputs,
    build_outputs,
)
from scripts.verify_personal_holdings_risk_card_entry import (
    REQUIRED_APPROVALS,
    digest,
    load_json,
    scope_hash,
)


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "evidence/market-regime-m1/entry-readiness.json"


class PersonalHoldingsRiskCardApprovalPacketTests(unittest.TestCase):
    def test_canonical_build_is_deterministic_and_committed(self) -> None:
        payload = load_json(CANONICAL)
        first = build_outputs(payload)
        second = build_outputs(copy.deepcopy(payload))
        self.assertEqual(first, second)
        self.assertEqual(10, len(first))
        self.assertEqual([], apply_outputs(ROOT, first, check=True))

    def test_every_request_binds_exact_scope_and_is_not_send_authorized(self) -> None:
        payload = load_json(CANONICAL)
        outputs = build_outputs(payload)
        expected_scope_hash = scope_hash(payload)
        json_outputs = {
            path: json.loads(content)
            for path, content in outputs.items()
            if path.suffix == ".json"
        }
        self.assertEqual(set(REQUIRED_APPROVALS), {
            request["approval_key"] for request in json_outputs.values()
        })
        for request in json_outputs.values():
            self.assertEqual("draft_not_sent", request["request_status"])
            self.assertIs(False, request["outbound_action_authorized"])
            self.assertEqual(expected_scope_hash, request["scope_hash"])
            self.assertEqual(payload["receipt_hash"], request["source_receipt_hash"])
            unsigned = {
                key: value for key, value in request.items() if key != "packet_hash"
            }
            self.assertEqual(digest(unsigned), request["packet_hash"])

    def test_check_mode_detects_stale_generated_file(self) -> None:
        outputs = build_outputs(load_json(CANONICAL))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual([], apply_outputs(root, outputs, check=False))
            self.assertEqual([], apply_outputs(root, outputs, check=True))
            path = root / next(iter(outputs))
            path.write_text("tampered\n", encoding="utf-8")
            mismatches = apply_outputs(root, outputs, check=True)
            self.assertEqual(1, len(mismatches))
            self.assertTrue(mismatches[0].startswith("stale:"))

    def test_packets_do_not_contain_secret_material_or_personal_values(self) -> None:
        serialized = "\n".join(build_outputs(load_json(CANONICAL)).values())
        forbidden_fragments = (
            "BEGIN PRIVATE KEY",
            "ghp_",
            "sk-proj-",
            "Authorization: Bearer",
            "cookie=",
        )
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, serialized)


if __name__ == "__main__":
    unittest.main()
