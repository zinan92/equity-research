from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_features import (  # noqa: E402
    FEATURE_SCHEMA_VERSION,
    build_timeframe_features,
)


def price_points(count: int = 60) -> list[dict[str, float | str]]:
    return [
        {
            "date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100 + index,
        }
        for index in range(count)
    ]


class WeeklyFeaturesTest(unittest.TestCase):
    def test_constant_series_has_zero_macd_and_ema_after_warmup(self) -> None:
        points = [
            {"date": f"2026-01-{index + 1:02d}", "open": 100, "high": 101, "low": 99, "close": 100}
            for index in range(60)
        ]
        result = build_timeframe_features(
            {"key": "gold", "series_kind": "price", "points": points},
            timeframe="daily",
        )
        self.assertEqual(result["schema_version"], FEATURE_SCHEMA_VERSION)
        self.assertEqual(result["parameters"], {"ema_span": 50, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9})
        self.assertEqual(result["status"], "complete")
        last = result["points"][-1]
        self.assertEqual(last["ema50"], 100.0)
        self.assertEqual(last["macd"], 0.0)
        self.assertEqual(last["macd_signal"], 0.0)
        self.assertEqual(last["macd_histogram"], 0.0)

    def test_short_history_is_explicit_and_does_not_pad_ema50(self) -> None:
        result = build_timeframe_features(
            {"key": "sp500", "series_kind": "price", "points": price_points(10)},
            timeframe="weekly",
        )
        self.assertEqual(result["status"], "short_history")
        self.assertEqual(result["warmup_required"], 50)
        self.assertTrue(all(point["ema50"] is None for point in result["points"]))
        self.assertEqual(result["source_point_count"], 10)

    def test_rate_series_uses_value_and_preserves_line_semantics(self) -> None:
        points = [{"date": f"2026-01-{index + 1:02d}", "value": 4.0} for index in range(60)]
        result = build_timeframe_features(
            {"key": "us10y", "series_kind": "rate_level", "points": points},
            timeframe="daily",
        )
        self.assertEqual(result["chart_kind"], "line")
        self.assertEqual(result["points"][-1]["value"], 4.0)
        self.assertEqual(result["points"][-1]["ema50"], 4.0)

    def test_cutoff_excludes_future_rows_and_emits_five_axis_labels(self) -> None:
        points = price_points(60)
        points.append({"date": "2027-01-01", "open": 999, "high": 1000, "low": 998, "close": 999})
        result = build_timeframe_features(
            {"key": "gold", "series_kind": "price", "points": points},
            timeframe="daily",
            cutoff_at=datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(result["source_point_count"], 60)
        self.assertEqual(len(result["x_labels"]), 5)
        self.assertEqual(result["x_labels"][0]["label"], "2026-01-01")
        self.assertEqual(result["x_labels"][-1]["label"], "2026-03-01")
        self.assertEqual(result["y_labels"][0]["value"], 99.0)
        self.assertEqual(result["y_labels"][-1]["value"], 160.0)
        self.assertEqual(result["current"]["value"], 159.0)

    def test_feature_identity_changes_when_source_changes(self) -> None:
        base = {"key": "gold", "series_kind": "price", "points": price_points(60)}
        first = build_timeframe_features(base, timeframe="daily")
        changed = price_points(60)
        changed[-1] = {**changed[-1], "close": 999}
        second = build_timeframe_features({**base, "points": changed}, timeframe="daily")
        self.assertNotEqual(first["feature_identity"], second["feature_identity"])


if __name__ == "__main__":
    unittest.main()
