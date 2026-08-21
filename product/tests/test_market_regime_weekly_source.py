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
    build_public_4h_context,
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
        self.assertEqual(result["daily_points"][-1]["date"], "2026-08-14")

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

    def test_registry_metadata_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(WeeklySourceHistoryError, "weekly_registry_mismatch:gold:timezone"):
            aggregate_weekly_series(
                {"key": "gold", "series_kind": "price", "timezone": "Asia/Shanghai", "points": []},
                week_end=date(2026, 8, 14),
                week_count=1,
            )

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
                "volume": 10 + i,
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
        self.assertEqual(result["points"][0]["volume"], 46.0)

    def test_four_hour_context_preserves_its_own_source_identity(self) -> None:
        start = datetime(2026, 8, 13, 18, tzinfo=timezone.utc)
        hourly = [
            {"timestamp": int((start + timedelta(hours=i)).timestamp()), "open": 100 + i, "high": 105 + i, "low": 98 + i, "close": 103 + i}
            for i in range(4)
        ]
        snapshot = build_weekly_source_snapshot(
            {
                "gold": {
                    "series_kind": "price",
                    "timezone": "America/New_York",
                    "points": [{"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}],
                    "hourly_points": hourly,
                    "source_identity": {"run_id": "daily"},
                    "hourly_source_identity": {"run_id": "hourly"},
                }
            },
            week_end=date(2026, 8, 14),
            cutoff_at=datetime(2026, 8, 14, 23, 59, 59, tzinfo=timezone.utc),
            week_count=1,
        )
        self.assertEqual(snapshot["series"]["gold"]["context_4h"]["source_identity"]["run_id"], "hourly")

    def test_raw_hourly_failure_evidence_survives_4h_fallback(self) -> None:
        result = aggregate_4h_series(
            {
                "key": "gold",
                "timezone": "America/New_York",
                "points": [],
                "reject_reason": "datafeed_http:502:upstream_error",
                "access_issues": ["Yahoo unavailable"],
                "source_identity": {"provider": "yahoo_finance", "provider_symbol": "GC=F"},
            },
            cutoff_at=datetime(2026, 8, 14, 23, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reject_reason"], "datafeed_http:502:upstream_error")
        self.assertEqual(result["access_issues"], ["Yahoo unavailable"])

    def test_raw_hourly_malformed_or_nonfinite_rows_fail_closed(self) -> None:
        with self.assertRaisesRegex(WeeklySourceHistoryError, "four_hour_raw_row_invalid"):
            aggregate_4h_series(
                {"key": "gold", "timezone": "America/New_York", "points": [None]},
                cutoff_at=datetime(2026, 8, 14, 3, tzinfo=timezone.utc),
            )
        zone = ZoneInfo("America/New_York")
        start = datetime(2026, 8, 13, 18, tzinfo=zone)
        rows = [
            {"timestamp": int((start + timedelta(hours=i)).timestamp()), "open": 100, "high": 101, "low": 99, "close": 100, "volume": -1}
            for i in range(4)
        ]
        with self.assertRaisesRegex(WeeklySourceHistoryError, "volume_negative"):
            aggregate_4h_series(
                {"key": "gold", "timezone": "America/New_York", "anchor_hour": 18, "points": rows},
                cutoff_at=datetime(2026, 8, 14, 3, tzinfo=timezone.utc),
            )

    def test_public_native_4h_bars_are_not_aggregated_again(self) -> None:
        public_bars = [
            {"timestamp": "2026-08-14T16:00:00+00:00", "open": 100, "high": 104, "low": 99, "close": 103},
            {"timestamp": "2026-08-14T20:00:00+00:00", "open": 103, "high": 106, "low": 102, "close": 105},
        ]
        context = build_public_4h_context(
            {
                "key": "bitcoin",
                "timezone": "UTC",
                "raw_timeframe": "4h",
                "timeframe_origin": "native",
                "aggregation": {"kind": "none", "rule": "native_passthrough"},
                "points": public_bars,
                "source_identity": {"provider": "binance_spot", "provider_symbol": "BTCUSDT"},
                "data_kind": "real",
            },
            cutoff_at=datetime(2026, 8, 15, 3, tzinfo=timezone.utc),
        )
        self.assertEqual(context["status"], "complete")
        self.assertEqual(len(context["points"]), 2)
        self.assertEqual(context["points"][0]["start_at"], "2026-08-14T16:00:00Z")
        self.assertEqual(context["source_identity"]["provider_symbol"], "BTCUSDT")

    def test_public_1h_derived_4h_bars_are_not_bucketed_again(self) -> None:
        context = build_public_4h_context(
            {
                "key": "gold",
                "timezone": "America/New_York",
                "raw_timeframe": "1h",
                "timeframe_origin": "aggregated",
                "aggregation": {
                    "kind": "ohlc_resample",
                    "rule": "fixed_4h",
                    "input_timeframe": "1h",
                    "bucket_timezone": "UTC",
                    "anchor_hour": 0,
                    "anchor_minute": 0,
                },
                "points": [
                    {"timestamp": "2026-08-14T16:00:00+00:00", "open": 100, "high": 104, "low": 99, "close": 103},
                ],
                "source_identity": {"provider": "yahoo_finance", "provider_symbol": "GC=F"},
                "data_kind": "real",
            },
            cutoff_at=datetime(2026, 8, 14, 23, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(context["status"], "complete")
        self.assertEqual(len(context["points"]), 1)
        self.assertEqual(context["raw_timeframe"], "1h")
        self.assertEqual(context["timeframe_origin"], "aggregated")

    def test_public_4h_preserves_provider_drop_count(self) -> None:
        context = build_public_4h_context(
            {
                "key": "gold",
                "timezone": "UTC",
                "raw_timeframe": "1h",
                "timeframe_origin": "aggregated",
                "aggregation": {
                    "kind": "ohlc_resample",
                    "rule": "fixed_4h",
                    "input_timeframe": "1h",
                    "bucket_timezone": "UTC",
                    "anchor_hour": 0,
                    "anchor_minute": 0,
                    "dropped_incomplete_buckets": 12,
                },
                "points": [
                    {"timestamp": "2026-08-14T16:00:00+00:00", "open": 100, "high": 104, "low": 99, "close": 103},
                ],
                "source_identity": {"provider": "yahoo_finance", "provider_symbol": "GC=F"},
                "data_kind": "real",
            },
            cutoff_at=datetime(2026, 8, 14, 23, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(context["dropped_incomplete_bucket_count"], 12)
        self.assertEqual(context["dropped_incomplete_buckets"], [])

    def test_public_native_4h_requires_none_aggregation_kind_and_valid_timezone(self) -> None:
        base = {
            "key": "gold",
            "timezone": "UTC",
            "raw_timeframe": "4h",
            "timeframe_origin": "native",
            "aggregation": {"kind": "ohlc_resample", "rule": "native_passthrough"},
            "points": [],
        }
        with self.assertRaisesRegex(WeeklySourceHistoryError, "four_hour_native_metadata_invalid"):
            build_public_4h_context(base, cutoff_at=datetime(2026, 8, 15, tzinfo=timezone.utc))
        base["aggregation"] = {"kind": "none", "rule": "native_passthrough", "bucket_timezone": "Mars/Olympus"}
        with self.assertRaisesRegex(WeeklySourceHistoryError, "four_hour_anchor_invalid"):
            build_public_4h_context(base, cutoff_at=datetime(2026, 8, 15, tzinfo=timezone.utc))

    def test_weekly_target_current_monday_bar_is_not_promoted(self) -> None:
        current_monday = date.today() - timedelta(days=date.today().weekday())
        result = aggregate_weekly_series(
            {
                "key": "gold",
                "series_kind": "price",
                "timezone": "America/New_York",
                "points": [{"date": (current_monday + timedelta(days=4)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100}],
            },
            week_end=current_monday + timedelta(days=4),
            week_count=1,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["points"], [])

    def test_weekly_and_raw_hourly_volume_are_preserved_when_present(self) -> None:
        weekly = aggregate_weekly_series(
            {
                "key": "gold",
                "series_kind": "price",
                "timezone": "America/New_York",
                "points": [
                    {"date": "2026-08-10", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 3},
                    {"date": "2026-08-14", "open": 100, "high": 102, "low": 98, "close": 101, "volume": 4},
                ],
            },
            week_end=date(2026, 8, 14),
            week_count=1,
        )
        self.assertEqual(weekly["points"][0]["volume"], 7.0)

    def test_snapshot_uses_public_4h_metadata_seam(self) -> None:
        snapshot = build_weekly_source_snapshot(
            {
                "bitcoin": {
                    "series_kind": "price",
                    "timezone": "UTC",
                    "points": [{"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}],
                    "hourly_points": [
                        {"timestamp": "2026-08-14T16:00:00+00:00", "open": 100, "high": 104, "low": 99, "close": 103},
                        {"timestamp": "2026-08-14T20:00:00+00:00", "open": 103, "high": 106, "low": 102, "close": 105},
                    ],
                    "hourly_raw_timeframe": "4h",
                    "hourly_timeframe_origin": "native",
                    "hourly_aggregation": {"kind": "none", "rule": "native_passthrough"},
                    "hourly_source_identity": {"provider": "binance_spot", "provider_symbol": "BTCUSDT"},
                    "data_kind": "real",
                }
            },
            week_end=date(2026, 8, 14),
            cutoff_at=datetime(2026, 8, 15, 3, tzinfo=timezone.utc),
            week_count=1,
        )
        context = snapshot["series"]["bitcoin"]["context_4h"]
        self.assertEqual(context["status"], "complete")
        self.assertEqual(len(context["points"]), 2)
        self.assertEqual(context["source_identity"]["provider_symbol"], "BTCUSDT")

    def test_ready_4h_without_transform_metadata_becomes_one_typed_unavailable_context(self) -> None:
        snapshot = build_weekly_source_snapshot(
            {
                "bitcoin": {
                    "series_kind": "price",
                    "timezone": "UTC",
                    "points": [{"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}],
                    "hourly_status": "ready",
                    "hourly_points": [{"timestamp": "2026-08-14T16:00:00+00:00", "open": 100, "high": 104, "low": 99, "close": 103}],
                    "hourly_source_identity": {"provider": "binance_spot", "provider_symbol": "BTCUSDT"},
                    "data_kind": "real",
                }
            },
            week_end=date(2026, 8, 14),
            cutoff_at=datetime(2026, 8, 15, 3, tzinfo=timezone.utc),
            week_count=1,
        )
        context = snapshot["series"]["bitcoin"]["context_4h"]
        self.assertEqual(context["status"], "unavailable")
        self.assertEqual(context["reject_reason"], "four_hour_transform_metadata_missing")

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
                        "source_identity": {"provider": "yahoo_chart", "symbol": "GC=F", "interval": "1d", "normalized_sha256": "b" * 64},
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
        self.assertEqual(gold["source_identity"]["provider"], "yahoo_chart")
        self.assertEqual(gold["source_identity"]["normalized_sha256"], "b" * 64)
        self.assertEqual(gold["data_kind"], "real")
        self.assertEqual(gold["rights"]["publication_eligible"], False)

    def test_authority_adapter_keeps_parent_run_when_child_identity_is_missing(self) -> None:
        snapshot = build_weekly_source_snapshot_from_authorities(
            daily_snapshot={
                "run_id": "daily-parent",
                "instruments": [{
                    "instrument": {"key": "gold", "exchange_timezone": "America/New_York", "unit": "USD/troy ounce", "price_basis": "provider_continuous_front_month_unadjusted"},
                    "bars": [{"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}],
                    "quality": "fresh", "data_kind": "real", "publication_eligible": False,
                }],
            },
            macro_snapshot={
                "run_id": "macro-parent",
                "factors": [{"factor": {"key": "us2y"}, "observations": [{"date": "2026-08-14", "value": 4.2}], "quality": "fresh", "data_kind": "real"}],
            },
            bitcoin_artifact={"bitcoin_id": "bitcoin-id", "bars": []},
            week_end=date(2026, 8, 14),
            week_count=1,
            require_all=False,
        )
        self.assertEqual(snapshot["series"]["gold"]["source_identity"]["run_id"], "daily-parent")
        self.assertEqual(snapshot["series"]["us2y"]["source_identity"]["run_id"], "macro-parent")


if __name__ == "__main__":
    unittest.main()
