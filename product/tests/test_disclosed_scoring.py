from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core import composite_score, opportunity_score, peg_grade  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "validate_disclosed_scoring",
    ROOT / "scripts" / "validate_disclosed_scoring.py",
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class DisclosedScoringTest(unittest.TestCase):
    def test_composite_normalizes_quantifiable_61_percent(self):
        self.assertEqual(composite_score(growth=100, quality=80, value=50, attention=100), 85)

    def test_opportunity_uses_archive_rounding(self):
        self.assertEqual(opportunity_score(growth=100, quality=80, value=50), 78)
        self.assertEqual(opportunity_score(growth=100, quality=91, value=56), 83)

    def test_peg_thresholds(self):
        self.assertEqual(peg_grade(0.99), "便宜")
        self.assertEqual(peg_grade(1.0), "合理")
        self.assertEqual(peg_grade(2.0), "偏贵")
        self.assertEqual(peg_grade(4.0), "偏贵")
        self.assertEqual(peg_grade(4.01), "极贵")
        self.assertIsNone(peg_grade(None))

    def test_missing_or_boolean_inputs_are_not_scored(self):
        with self.assertRaises(ValueError):
            composite_score(growth=True, quality=1, value=1, attention=1)
        with self.assertRaises(ValueError):
            peg_grade("1")
        with self.assertRaises(ValueError):
            peg_grade(float("nan"))

    def test_validator_gates_on_exact_649_company_main_universe(self):
        score_row = {
            "universe": "main",
            "code": "TEST",
            "s": {"growth": 100, "quality": 80, "value": 50, "attention": 100, "composite": 85},
            "opp": 78,
        }
        level_row = {"code": "TEST", "score": 80, "grade": "A", "peg_grade": "合理"}
        market_row = {"code": "TEST", "peg": 1.5}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / name for name in ("scores.json", "levels.json", "market.json")]
            for path, records in zip(
                paths,
                ([dict(score_row, code=f"T{i}") for i in range(649)], [level_row], [market_row]),
                strict=True,
            ):
                path.write_text(json.dumps({"records": records}), encoding="utf-8")
            self.assertTrue(VALIDATOR.validate(*paths)["passed"])

            paths[0].write_text(
                json.dumps({"records": [dict(score_row, code=f"T{i}") for i in range(648)]}),
                encoding="utf-8",
            )
            self.assertFalse(VALIDATOR.validate(*paths)["passed"])


if __name__ == "__main__":
    unittest.main()
