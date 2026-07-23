from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core import composite_score, opportunity_score, peg_grade  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
