from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_round7_section_contract.py"
SPEC = importlib.util.spec_from_file_location("verify_round7_section_contract", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class Round7SectionContractVerifierTest(unittest.TestCase):
    def test_verifier_proves_contract_and_safety_boundary(self) -> None:
        receipt = MODULE.verify()
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(len(receipt["section_contract"]["section_ids"]), 9)
        self.assertEqual(receipt["checks"]["reviewed_all_full_tier"], "A")
        self.assertEqual(receipt["checks"]["unreviewed_tier"], "B")
        self.assertEqual(
            receipt["checks"]["unreviewed_blocked_fields"],
            ["action", "target_price", "position_range"],
        )
        self.assertFalse(receipt["publication_appendices_count_toward_tier"])


if __name__ == "__main__":
    unittest.main()
