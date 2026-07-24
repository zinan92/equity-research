from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_m1_acceptance", ROOT / "scripts" / "verify_m1_acceptance.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M1AcceptanceManifestTest(unittest.TestCase):
    def test_checked_in_manifest_meets_the_contract(self) -> None:
        report = MODULE.verify_manifest(ROOT / "docs/reverse/m1/golden-validation-set.json", ROOT)
        self.assertTrue(report["passed"], report["problems"])
        self.assertEqual(report["company_count"], 30)
        self.assertGreaterEqual(report["high_medium_coverage"], 0.80)
        self.assertTrue(report["explicit_gap_cells"])

    def test_acceptance_report_keeps_gaps_explicit(self) -> None:
        report = (ROOT / "docs/reverse/m1-acceptance-report.md").read_text(encoding="utf-8")
        self.assertIn("GO（带明确覆盖边界）", report)
        self.assertIn("93.33%", report)
        self.assertIn("明确 gap", report)
        self.assertIn("人工/AI 研究判断", report)


if __name__ == "__main__":
    unittest.main()
