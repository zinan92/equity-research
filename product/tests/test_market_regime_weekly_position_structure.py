from __future__ import annotations

from datetime import date, timedelta
import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_features import build_timeframe_features  # noqa: E402
from data_core.market_regime_weekly_position_structure import (  # noqa: E402
    build_position_structure,
)


def points(*, start: float, step: float, count: int = 60) -> list[dict[str, float | str]]:
    return [
        {
            "date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "open": start + step * index,
            "high": start + step * index + 1,
            "low": start + step * index - 1,
            "close": start + step * index,
        }
        for index in range(count)
    ]


def frame(key: str, values: list[dict[str, float | str]], timeframe: str, evidence: str) -> dict:
    feature = build_timeframe_features(
        {"key": key, "series_kind": "price", "source_identity": {"provider": "fixture", "key": key}, "points": values},
        timeframe=timeframe,
    )
    return {"points": values, "features": feature, "evidence_ids": [evidence], "unit": "index points", "status": "complete"}


class WeeklyPositionStructureTest(unittest.TestCase):
    def test_position_is_high_for_price_near_top_of_window(self) -> None:
        request = {"asset_key": "gold", "timeframes": {"weekly": frame("gold", points(start=100, step=1), "weekly", "gold:w"), "daily": frame("gold", points(start=100, step=1), "daily", "gold:d")}}
        result = build_position_structure(request)
        self.assertEqual(result["position"]["state"], "high")
        self.assertGreater(result["position"]["percentile"], 0.9)
        self.assertIn("gold:w", result["position"]["evidence_ids"])

    def test_structure_identifies_bullish_continuation(self) -> None:
        request = {"asset_key": "gold", "timeframes": {"weekly": frame("gold", points(start=100, step=1), "weekly", "gold:w")}}
        result = build_position_structure(request)
        self.assertEqual(result["structure"]["state"], "continuation")
        self.assertEqual(result["structure"]["bias"], "bullish")

    def test_structure_marks_disagreement_as_mixed(self) -> None:
        request = {"asset_key": "gold", "timeframes": {"weekly": frame("gold", points(start=160, step=1), "weekly", "gold:w"), "daily": frame("gold", points(start=160, step=-1), "daily", "gold:d")}}
        result = build_position_structure(request)
        self.assertEqual(result["structure"]["state"], "mixed")
        self.assertEqual(result["structure"]["bias"], "mixed")
        self.assertEqual(set(result["structure"]["evidence_ids"]), {"gold:w", "gold:d"})

    def test_missing_timeframes_are_unknown_not_inferred(self) -> None:
        result = build_position_structure({"asset_key": "gold", "timeframes": {}})
        self.assertEqual(result["position"]["state"], "unknown")
        self.assertEqual(result["structure"]["state"], "unknown")
        self.assertEqual(result["position"]["evidence_ids"], [])


if __name__ == "__main__":
    unittest.main()
