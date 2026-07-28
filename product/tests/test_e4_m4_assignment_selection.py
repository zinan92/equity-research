from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_e4_m4_assignments.py"
SPEC = importlib.util.spec_from_file_location("e4_m4_assignments", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M4AssignmentSelectionTest(unittest.TestCase):
    def test_note_reference_and_tiny_value_are_not_audit_candidates(self) -> None:
        facts = [
            {
                "metric": "cash", "value": 1, "column_identity": "current_period",
                "quoted_label": "货币资金", "quoted_anchor": "货币资金 六、1 2,924,099,340.75",
            },
            {
                "metric": "total_assets", "value": 2_924_099_340.75, "column_identity": "period_end",
                "quoted_label": "资产总计", "quoted_anchor": "资产总计 2,924,099,340.75 3,115,628,975.55",
            },
        ]
        selected = MODULE._select_fact(facts)
        self.assertEqual((selected["metric"], selected["value"]), ("total_assets", 2_924_099_340.75))


if __name__ == "__main__":
    unittest.main()
