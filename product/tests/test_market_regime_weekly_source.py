from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import sys
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_source import (  # noqa: E402
    CONTEXT_4H_KEYS,
    WEEKLY_KEYS,
    WeeklySourceHistoryError,
    WeeklySourceHistoryStore,
    aggregate_4h_series,
    aggregate_weekly_series,
    build_weekly_source_snapshot,
    build_weekly_source_snapshot_from_authorities,
)


class WeeklySourceAggregationTest(unittest.TestCase):
    def test_registry_has_the_fixed_17_series_and_five_context_series(self) -> None:
        self.assertEqual(len(WEEKLY_KEYS), 17)
        self.assertEqual(
            CONTEXT_4H_KEYS,
            ("dxy", "bitcoin", "wti", "gold", "silver"),
        )
        self.assertTrue(set(CONTEXT_4H_KEYS).issubset(WEEKLY_KEYS))

    def test_weekly_price_ohlc_uses_first_open_extremes_and_last_close(self) -> None:
        points = [
            {"date": "2026-08-10", "open": 100, "high": 105, "low": 98, "close": 103},
            {"date": "2026-08-11", "open": 103, "high": 108, "low": 101, "close": 106},
            {"date": "2026-08-13", "open": 106, "high": 107, "low": 99, "close": 100},
            {"date": "2026-08-14", "open": 100, "high": 110, "low": 97, "close": 109},
        ]
        result = aggregate_weekly_series(
            {"key": "gold", "series_kind": "price", "timezone": "America/New_York", "points": points},
            week_end=date(2026, 8, 14),
            week_count=1,
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["points"], [{
            "date": "2026-08-14",
            "open": 100,
            "high": 110,
            "low": 97,
            "close": 109,
        }])

    def test_weekly_rate_uses_last_level_and_never_emits_ohlc(self) -> None:
        result = aggregate_weekly_series(
            {
                "key": "us10y",
                "series_kind": "rate_level",
                "timezone": "America/New_York",
                "unit": "percent",
                "points": [
                    {"date": "2026-08-10", "value": 4.30},
                    {"date": "2026-08-14", "value": 4.42},
                ],
            },
            week_end=date(2026, 8, 14),
            week_count=1,
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["points"], [{"date": "2026-08-14", "value": 4.42}])
        self.assertNotIn("open", result["points"][0])

    def test_four_hour_anchor_requires_four_consecutive_completed_hours(self) -> None:
        zone = ZoneInfo("America/New_York")
        start = datetime(2026, 8, 13, 18, tzinfo=zone)
        complete = [
            {
                "timestamp": int((start + timedelta(hours=i)).timestamp()),
                "open": 100 + i,
                "high": 105 + i,
                "low": 98 + i,
                "close": 103 + i,
            }
            for i in range(4)
        ]
        missing_bucket = [
            {
                "timestamp": int((start + timedelta(hours=8 + i)).timestamp()),
                "open": 110 + i,
                "high": 115 + i,
                "low": 108 + i,
                "close": 113 + i,
            }
            for i in (0, 1, 3)
        ]
        result = aggregate_4h_series(
            {"key": "gold", "timezone": "America/New_York", "anchor_hour": 18, "points": complete + missing_bucket},
            cutoff_at=datetime(2026, 8, 14, 3, tzinfo=timezone.utc),
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["points"]), 1)
        self.assertEqual(result["points"][0]["open"], 100)
        self.assertEqual(result["points"][0]["close"], 106)

    def test_short_history_is_explicit_and_never_padded(self) -> None:
        snapshot = build_weekly_source_snapshot(
            {
                "gold": {
                    "series_kind": "price",
                    "timezone": "America/New_York",
                    "points": [
                        {"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}
                    ],
                }
            },
            week_end=date(2026, 8, 14),
            week_count=2,
        )
        self.assertEqual(snapshot["status"], "partial")
        self.assertEqual(snapshot["series"]["gold"]["status"], "short_history")
        self.assertEqual(len(snapshot["series"]["gold"]["points"]), 1)

    def test_unknown_series_key_fails_closed(self) -> None:
        with self.assertRaisesRegex(WeeklySourceHistoryError, "unknown_weekly_key"):
            build_weekly_source_snapshot(
                {"not_a_market": {"series_kind": "price", "points": []}},
                week_end=date(2026, 8, 14),
            )

    def test_store_replays_content_addressed_snapshot_and_receipt(self) -> None:
        with self.subTest("publish and replay"):
            import tempfile

            with tempfile.TemporaryDirectory() as temporary:
                snapshot = build_weekly_source_snapshot(
                    {
                        "gold": {
                            "series_kind": "price",
                            "timezone": "America/New_York",
                            "points": [
                                {"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}
                            ],
                        }
                    },
                    week_end=date(2026, 8, 14),
                    week_count=1,
                )
                store = WeeklySourceHistoryStore(Path(temporary))
                state = store.publish(snapshot)
                replayed = store.latest()
                self.assertEqual(replayed["snapshot_id"], state["snapshot_id"])
                self.assertEqual(replayed["series"]["gold"]["points"][0]["close"], 100.0)

    def test_store_rejects_artifact_hash_tamper(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            snapshot = build_weekly_source_snapshot(
                {
                    "gold": {
                        "series_kind": "price",
                        "timezone": "America/New_York",
                        "points": [
                            {"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}
                        ],
                    }
                },
                week_end=date(2026, 8, 14),
                week_count=1,
            )
            store = WeeklySourceHistoryStore(Path(temporary))
            state = store.publish(snapshot)
            artifact = Path(temporary) / state["artifact"]["path"]
            artifact.write_text(artifact.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
            with self.assertRaisesRegex(WeeklySourceHistoryError, "artifact_hash_mismatch"):
                store.latest()

    def test_store_rejects_reference_path_escape(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            snapshot = build_weekly_source_snapshot(
                {"gold": {"series_kind": "price", "timezone": "America/New_York", "points": [{"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}]}},
                week_end=date(2026, 8, 14),
                week_count=1,
            )
            store = WeeklySourceHistoryStore(Path(temporary))
            store.publish(snapshot)
            latest_path = Path(temporary) / "latest.json"
            state = json.loads(latest_path.read_text(encoding="utf-8"))
            state["artifact"]["path"] = "../escape.json"
            latest_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(WeeklySourceHistoryError, "weekly_reference_path"):
                store.latest()

    def test_authority_adapter_preserves_upstream_identity(self) -> None:
        snapshot = build_weekly_source_snapshot_from_authorities(
            daily_snapshot={
                "run_id": "daily-run",
                "instruments": [
                    {
                        "instrument": {"key": "gold", "exchange_timezone": "America/New_York", "unit": "USD/troy ounce", "price_basis": "provider_continuous_front_month_unadjusted"},
                        "bars": [{"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}],
                        "quality": "fresh",
                        "data_kind": "real",
                        "run_id": "daily-run",
                        "normalized_artifact": {"path": "normalized/daily-run/gold.json", "sha256": "a" * 64},
                        "publication_eligible": False,
                    }
                ],
            },
            macro_snapshot={"run_id": "macro-run", "factors": []},
            bitcoin_artifact={"bitcoin_id": "bitcoin-id", "bars": []},
            week_end=date(2026, 8, 14),
            week_count=1,
            require_all=False,
        )
        gold = snapshot["series"]["gold"]
        self.assertEqual(gold["source_identity"]["run_id"], "daily-run")
        self.assertEqual(gold["data_kind"], "real")
        self.assertEqual(gold["rights"]["publication_eligible"], False)


if __name__ == "__main__":
    unittest.main()
