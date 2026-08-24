from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_source import (  # noqa: E402
    DAILY_TIMEFRAMES,
    DailyDatafeedClient,
    DailySourceStore,
    build_daily_source_bundle,
    daily_request_for_asset,
)
from data_core.market_regime_weekly_source import WEEKLY_KEYS  # noqa: E402


class _Response:
    def __init__(self, payload: dict, *, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _Opener:
    def __init__(self, *, unavailable: set[tuple[str, str]] | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, list[str]]]] = []
        self.unavailable = unavailable or set()

    def __call__(self, request, timeout: float) -> _Response:
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        asset_class, ticker = parsed.path.rsplit("/", 2)[-2:]
        timeframe = query["timeframe"][0]
        requested_source = query["source"][0]
        self.calls.append((ticker, timeframe, query))
        if (ticker, timeframe) in self.unavailable:
            return _Response(
                {
                    "error": "upstream_error",
                    "detail": "unsupported symbol/timeframe",
                    "ticker": ticker,
                    "asset_class": asset_class,
                    "timeframe": timeframe,
                    "requested_source": requested_source,
                    "selected_source": requested_source,
                    "attempted_sources": [requested_source],
                    "cache_policy": "bypass",
                    "quality_policy": "strict",
                    "fallback_policy": query["fallback_policy"][0],
                    "source_identity": {"provider_symbol": ticker},
                },
                status=503,
            )
        stamp = {
            "1d": "2026-08-24",
            "4h": "2026-08-24T12:00:00Z",
            "30m": "2026-08-24T12:30:00Z",
        }[timeframe]
        is_rate = ticker in {"DGS2", "DGS10", "T10Y2Y"}
        bar = {
            "timestamp": stamp,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 0.0,
        }
        if is_rate:
            bar["value"] = 1.0
        transform = {
            "raw_timeframe": timeframe,
            "timeframe_origin": "native",
            "aggregation": {"kind": "none", "rule": "native_passthrough"},
        }
        return _Response(
            {
                "ticker": ticker,
                "asset_class": asset_class,
                "timeframe": timeframe,
                "count": 1,
                **transform,
                "provider": "fake_provider",
                "provider_symbol": ticker,
                "source_mode": requested_source,
                "requested_source": requested_source,
                "selected_source": requested_source,
                "selection_reason": "requested_or_default",
                "attempted_sources": [requested_source],
                "cache_policy": "bypass",
                "quality_policy": "strict",
                "fallback_policy": query["fallback_policy"][0],
                "served_from": "upstream",
                "is_synthetic": False,
                "fresh": True,
                "latest_timestamp": stamp,
                "source_identity": {"provider_symbol": ticker},
                "candles": [bar],
            }
        )


class DailySourceTests(unittest.TestCase):
    def test_request_policy_is_strict_and_only_a_share_has_explicit_fallback(self) -> None:
        ashare = daily_request_for_asset("shanghai", "thirty_minute")
        self.assertEqual(ashare["fallback_policy"], "explicit")
        self.assertEqual(ashare["fallback_sources"], ["sina_index"])
        other = daily_request_for_asset("gold", "thirty_minute")
        self.assertEqual(other["fallback_policy"], "none")
        self.assertEqual(other["fallback_sources"], [])

    def test_bundle_attempts_all_19_assets_and_three_timeframes(self) -> None:
        opener = _Opener()
        client = DailyDatafeedClient(opener=opener, timeout=1)
        bundle = build_daily_source_bundle(
            client,
            generated_at=datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc),
            limit=10,
            max_workers=2,
        )
        self.assertEqual(len(bundle["assets"]), len(WEEKLY_KEYS))
        self.assertEqual(bundle["coverage"]["total_slots"], len(WEEKLY_KEYS) * len(DAILY_TIMEFRAMES))
        self.assertEqual(len(opener.calls), len(WEEKLY_KEYS) * len(DAILY_TIMEFRAMES))
        for asset in bundle["assets"]:
            self.assertEqual(set(asset["slots"]), set(DAILY_TIMEFRAMES))
            self.assertTrue(all(slot["status"] == "ready" for slot in asset["slots"].values()))

    def test_unavailable_slot_is_explicit_and_does_not_block_bundle(self) -> None:
        opener = _Opener(unavailable={("GC=F", "30m")})
        client = DailyDatafeedClient(opener=opener, timeout=1)
        bundle = build_daily_source_bundle(
            client,
            generated_at=datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc),
            limit=10,
            max_workers=2,
        )
        gold = next(asset for asset in bundle["assets"] if asset["asset_key"] == "gold")
        self.assertEqual(gold["slots"]["thirty_minute"]["status"], "unavailable")
        self.assertEqual(gold["slots"]["thirty_minute"]["bars"], [])
        self.assertIn("unsupported", gold["slots"]["thirty_minute"]["reject_reason"])
        self.assertEqual(bundle["source_status"], "partial")
        self.assertEqual(bundle["coverage"]["unavailable_slots"], 1)

    def test_store_publishes_and_reads_content_addressed_pointer(self) -> None:
        opener = _Opener()
        bundle = build_daily_source_bundle(
            DailyDatafeedClient(opener=opener, timeout=1),
            generated_at=datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc),
            limit=10,
            max_workers=2,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = DailySourceStore(Path(directory))
            pointer = store.publish(bundle)
            loaded = store.latest()
            self.assertEqual(pointer["bundle_id"], bundle["bundle_id"])
            self.assertEqual(loaded["bundle_id"], bundle["bundle_id"])
            self.assertTrue((Path(directory) / pointer["artifact"]["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
