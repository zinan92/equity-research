from __future__ import annotations

import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_odds import (  # noqa: E402
    ODDS_FORMULA_VERSION,
    ODDS_SCHEMA_VERSION,
    WeeklyOddsError,
    build_odds,
    validate_odds,
)


def request(*, closes: list[float]) -> dict:
    points = [{"close": close, "low": close - 4, "high": close + 8} for close in closes]
    return {
        "timeframes": {
            "daily": {
                "evidence_ids": ["gold:daily:source", "feature:daily-feature"],
                "features": {"status": "complete", "feature_identity": "daily-feature", "points": points},
            }
        }
    }


def two_frame_request() -> dict:
    daily = request(closes=[100, 102])["timeframes"]["daily"]
    daily["features"]["status"] = "short_history"
    weekly = request(closes=[100, 102])["timeframes"]["daily"]
    weekly["evidence_ids"] = ["gold:weekly:source", "feature:weekly-feature"]
    weekly["features"]["feature_identity"] = "weekly-feature"
    return {"timeframes": {"daily": daily, "weekly": weekly}}


class WeeklyOddsTest(unittest.TestCase):
    def test_long_setup_uses_observed_boundaries_and_reproducible_ratio(self) -> None:
        result = build_odds(request(closes=[100, 102]), {"bias": "bullish"})
        self.assertEqual(result["schema_version"], ODDS_SCHEMA_VERSION)
        self.assertEqual(result["formula_version"], ODDS_FORMULA_VERSION)
        self.assertEqual(result["direction"], "long")
        self.assertEqual(result["entry_reference"], 102.0)
        self.assertEqual(result["stop"], 96.0)
        self.assertEqual(result["target"], 110.0)
        self.assertAlmostEqual(result["risk_reward"], 8 / 6)
        self.assertEqual(result["state"], "marginal")
        self.assertEqual(validate_odds(result), result)

    def test_short_setup_uses_observed_boundaries(self) -> None:
        result = build_odds(request(closes=[108, 102]), {"bias": "bearish"})
        self.assertEqual(result["direction"], "short")
        self.assertEqual(result["stop"], 116.0)
        self.assertEqual(result["target"], 98.0)
        self.assertAlmostEqual(result["risk_reward"], 4 / 14)
        self.assertEqual(result["state"], "unfavorable")

    def test_missing_direction_is_not_ready_without_r_number(self) -> None:
        result = build_odds(request(closes=[100, 102]), {"bias": "mixed"})
        self.assertEqual(result["state"], "not_ready")
        self.assertNotIn("risk_reward", result)
        self.assertEqual(validate_odds(result), result)

    def test_insufficient_history_is_not_ready(self) -> None:
        result = build_odds(request(closes=[100]), {"bias": "bullish"})
        self.assertEqual(result["reason_code"], "insufficient_boundary_history")
        self.assertNotIn("risk_reward", result)

    def test_short_history_daily_uses_verified_weekly_boundary(self) -> None:
        result = build_odds(two_frame_request(), {"bias": "bullish"})
        self.assertEqual(result["timeframe"], "weekly")

    def test_mismatched_feature_evidence_fails_closed(self) -> None:
        result = build_odds(request(closes=[100, 102]), {"bias": "bullish"})
        result["evidence_ids"] = ["gold:daily:source", "feature:not-selected"]
        with self.assertRaisesRegex(WeeklyOddsError, "odds_feature_evidence_mismatch"):
            validate_odds(result, allowed_feature_ids={"feature:daily-feature"})
        result = build_odds(request(closes=[100, 102]), {"bias": "bullish"})
        result["evidence_ids"] = ["feature:daily-feature", "not-in-source"]
        with self.assertRaisesRegex(WeeklyOddsError, "odds_evidence_mismatch"):
            validate_odds(result, allowed_evidence_ids={"gold:daily:source", "feature:daily-feature"})

    def test_ready_none_direction_fails_closed(self) -> None:
        result = build_odds(request(closes=[100, 102]), {"bias": "bullish"})
        result["direction"] = "none"
        with self.assertRaisesRegex(WeeklyOddsError, "odds_ready_direction_invalid"):
            validate_odds(result, allowed_feature_ids={"feature:daily-feature"})

    def test_tampered_formula_or_order_fails_closed(self) -> None:
        result = build_odds(request(closes=[100, 102]), {"bias": "bullish"})
        result["risk_reward"] = 9
        with self.assertRaisesRegex(WeeklyOddsError, "odds_formula_mismatch"):
            validate_odds(result)
        result = build_odds(request(closes=[100, 102]), {"bias": "bullish"})
        result["target"] = 90
        with self.assertRaisesRegex(WeeklyOddsError, "odds_long_order_invalid"):
            validate_odds(result)


if __name__ == "__main__":
    unittest.main()
