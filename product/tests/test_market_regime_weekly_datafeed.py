from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_contract import WEEKLY_ASSET_REGISTRY  # noqa: E402
from data_core.market_regime_weekly_datafeed import (  # noqa: E402
    WeeklyDatafeedClient,
    datafeed_request_for_asset,
    load_datafeed_weekly_source_snapshot,
)


def candle_response(asset_key: str, *, ticker: str, timeframe: str = "1d") -> dict:
    spec = WEEKLY_ASSET_REGISTRY[asset_key]
    price = spec["series_kind"] == "price"
    row = {"timestamp": "2026-08-14T00:00:00+00:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10}
    if not price:
        row["open"] = row["high"] = row["low"] = row["close"] = 4.2
    return {
        "ticker": ticker,
        "asset_class": spec["asset_class"],
        "timeframe": timeframe,
        "schema_version": "kline-candles-v1",
        "provider": "test_provider",
        "source_mode": spec["source_id"].removeprefix("datafeed:"),
        "requested_source": spec["source_id"].removeprefix("datafeed:"),
        "selected_source": spec["source_id"].removeprefix("datafeed:"),
        "cache_policy": "bypass",
        "quality_policy": "strict",
        "fallback_policy": "none",
        "quality_flags": ["research_only"],
        "is_synthetic": False,
        "served_from": "upstream",
        "fresh": None,
        "latest_timestamp": row["timestamp"],
        "age_seconds": None,
        "max_age_seconds": None,
        "execution_venue": False,
        "reject_reason": None,
        "access_issues": [],
        "candles": [row],
    }


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class WeeklyDatafeedTest(unittest.TestCase):
    def test_all_registry_rows_have_explicit_request_mapping(self) -> None:
        for key, spec in WEEKLY_ASSET_REGISTRY.items():
            request = datafeed_request_for_asset(key, "daily")
            self.assertEqual(request["source_id"], spec["source_id"])
            self.assertTrue(request["asset_class"])
            self.assertTrue(request["ticker"])
        with self.assertRaisesRegex(ValueError, "timeframe_not_allowed"):
            datafeed_request_for_asset("us2y", "four_hour")

    def test_client_sends_strict_no_fallback_policy_and_maps_response(self) -> None:
        calls: list[str] = []

        def opener(request, timeout):
            calls.append(request.full_url)
            return FakeResponse(candle_response("sp500", ticker="^GSPC"))

        client = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener)
        result = client.fetch("sp500", "daily", start="2025-01-01", end="2026-08-15")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["source_identity"]["provider"], "test_provider")
        query = parse_qs(urlparse(calls[0]).query)
        self.assertEqual(query["fallback_policy"], ["none"])
        self.assertEqual(query["cache_policy"], ["bypass"])
        self.assertEqual(query["quality"], ["strict"])

    def test_http_failure_is_typed_without_fallback(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse({"detail": {"reject_reason": "upstream_error"}}, status=503)

        client = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener)
        result = client.fetch("gold", "daily")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("upstream_error", result["reject_reason"])
        self.assertEqual(result["bars"], [])

    def test_malformed_success_payload_is_typed_unavailable(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse({"unexpected": []})

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("sp500", "daily")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("datafeed_contract", result["reject_reason"])

    def test_non_object_success_payload_is_typed_unavailable(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse([])

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("sp500", "daily")
        self.assertEqual(result["status"], "unavailable")

    def test_wrong_upstream_identity_is_not_relabelled(self) -> None:
        def opener(_request, _timeout):
            payload = candle_response("sp500", ticker="WRONG")
            return FakeResponse(payload)

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("sp500", "daily")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("datafeed_contract", result["reject_reason"])

    def test_source_loader_preserves_all_39_slots_and_partial_states(self) -> None:
        calls: list[tuple[str, str]] = []
        class FakeClient:
            def fetch(self, asset_key, timeframe, **_kwargs):
                calls.append((asset_key, timeframe))
                if asset_key == "gold" and timeframe == "daily":
                    return {"status": "unavailable", "reject_reason": "stale"}
                spec = WEEKLY_ASSET_REGISTRY[asset_key]
                row = {"timestamp": "2026-08-14T00:00:00+00:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 0}
                if spec["series_kind"] != "price":
                    row["open"] = row["high"] = row["low"] = row["close"] = 4.2
                    row["value"] = 4.2
                return {"status": "ready", "series_kind": spec["series_kind"], "unit": spec["unit"], "price_basis": spec["price_basis"], "canonical_symbol": spec["canonical_symbol"], "source_identity": {"provider": "test", "run_id": "r"}, "bars": [row]}

        snapshot = load_datafeed_weekly_source_snapshot(FakeClient(), week_end="2026-08-14", cutoff_at="2026-08-14T23:59:59Z")
        self.assertEqual(set(snapshot["series"]), set(WEEKLY_ASSET_REGISTRY))
        self.assertEqual(snapshot["series"]["gold"]["daily_status"], "unavailable")
        self.assertEqual(snapshot["series"]["gold"]["status"], "short_history")
        self.assertEqual(snapshot["series"]["gold"]["points"], [{"date": "2026-08-14", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0}])
        self.assertEqual(snapshot["data_kind"], "real")
        self.assertTrue(all((key, "weekly") in calls for key in WEEKLY_ASSET_REGISTRY))
        self.assertTrue(all((key, "daily") in calls for key in WEEKLY_ASSET_REGISTRY))
        self.assertTrue(all((key, "four_hour") in calls for key in ("dxy", "bitcoin", "wti", "gold", "silver")))

    def test_weekly_unavailable_does_not_fall_back_to_daily_aggregation(self) -> None:
        class WeeklyFailureClient:
            def fetch(self, asset_key, timeframe, **_kwargs):
                spec = WEEKLY_ASSET_REGISTRY[asset_key]
                if asset_key == "gold" and timeframe == "weekly":
                    return {"status": "unavailable", "reject_reason": "upstream_error"}
                row = {"timestamp": "2026-08-14T00:00:00+00:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 0}
                if spec["series_kind"] != "price":
                    row["open"] = row["high"] = row["low"] = row["close"] = row["value"] = 4.2
                return {"status": "ready", "series_kind": spec["series_kind"], "unit": spec["unit"], "price_basis": spec["price_basis"], "canonical_symbol": spec["canonical_symbol"], "source_identity": {"provider": "test", "run_id": "r"}, "bars": [row]}

        snapshot = load_datafeed_weekly_source_snapshot(WeeklyFailureClient(), week_end="2026-08-14", cutoff_at="2026-08-14T23:59:59Z")
        self.assertEqual(snapshot["series"]["gold"]["status"], "unavailable")
        self.assertEqual(snapshot["series"]["gold"]["points"], [])


if __name__ == "__main__":
    unittest.main()
