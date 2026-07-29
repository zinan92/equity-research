from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from verify_performance_budget import run_harness  # noqa: E402


class VerifyPerformanceBudgetTest(unittest.TestCase):
    def test_harness_persists_a_ten_x_receipt_without_faking_provider_costs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "external-runtime"
            receipt = run_harness(root, task_count=20)
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["task_count"], 20)
            self.assertTrue((root / "performance-budget-receipt.json").is_file())
            self.assertEqual(receipt["costs"]["unknown_cost_categories"], ["model_tokens", "parse", "storage"])
            self.assertTrue(receipt["truth_boundary"]["synthetic_task_identities"])


if __name__ == "__main__":
    unittest.main()
