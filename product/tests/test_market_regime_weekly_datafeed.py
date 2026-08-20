from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_contract import WEEKLY_ASSET_REGISTRY, build_weekly_candle_responses  # noqa: E402
from data_core.market_regime_weekly_datafeed import (  # noqa: E402
    EXPECTED_PROVIDER_SYMBOLS,
    WeeklyDatafeedClient,
    datafeed_request_for_asset,
    load_datafeed_weekly_source_snapshot,
)


def candle_response(asset_key: str, *, ticker: str, timeframe: str = "1d") -> dict:
    spec = WEEKLY_ASSET_REGISTRY[asset_key]
    primary_source = spec["source_id"].removeprefix("datafeed:")
    price = spec["series_kind"] == "price"
    row = {"timestamp": "2026-08-14T00:00:00+00:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10}
    if not price:
        row["open"] = row["high"] = row["low"] = row["close"] = 4.2
    return {
        "ticker": ticker,
        "provider_symbol": EXPECTED_PROVIDER_SYMBOLS.get(asset_key, ticker),
        "asset_class": spec["asset_class"],
        "timeframe": timeframe,
        "schema_version": "kline-candles-v1",
        "provider": "test_provider",
        "source_mode": primary_source,
        "requested_source": primary_source,
        "selected_source": primary_source,
        "selection_reason": "requested_or_default",
        "attempted_sources": [primary_source],
        "cache_policy": "bypass",
        "quality_policy": "strict",
        "fallback_policy": spec.get("fallback_policy", "none"),
        "fallback_sources": list(spec.get("fallback_sources", [])),
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


def four_hour_response(
    asset_key: str,
    *,
    ticker: str,
    raw_timeframe: str,
    timeframe_origin: str,
    aggregation: dict,
) -> dict:
    payload = candle_response(asset_key, ticker=ticker, timeframe="4h")
    payload["raw_timeframe"] = raw_timeframe
    payload["timeframe_origin"] = timeframe_origin
    payload["aggregation"] = aggregation
    payload["candles"] = [
        {"timestamp": "2026-08-14T16:00:00+00:00", "open": 100, "high": 104, "low": 99, "close": 103, "volume": 10},
        {"timestamp": "2026-08-14T20:00:00+00:00", "open": 103, "high": 106, "low": 102, "close": 105, "volume": 10},
    ]
    payload["latest_timestamp"] = payload["candles"][-1]["timestamp"]
    payload["provider_symbol"] = ticker
    payload["source_identity"] = {"provider": "test_provider", "provider_symbol": ticker, "interval": raw_timeframe}
    return payload


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
        self.assertEqual(datafeed_request_for_asset("gold", "weekly")["ticker"], "GC=F")
        self.assertEqual(datafeed_request_for_asset("wti", "weekly")["ticker"], "CL=F")
        self.assertEqual(datafeed_request_for_asset("shanghai", "daily")["source_id"], "datafeed:tencent_kline")
        self.assertEqual(datafeed_request_for_asset("shanghai", "daily")["ticker"], "sh000001")
        self.assertEqual(datafeed_request_for_asset("shanghai", "daily")["fallback_policy"], "explicit")
        self.assertEqual(datafeed_request_for_asset("shanghai", "daily")["fallback_sources"], ["sina_index"])
        self.assertEqual(datafeed_request_for_asset("sp500", "daily")["fallback_policy"], "none")
        self.assertEqual(datafeed_request_for_asset("sp500", "daily")["fallback_sources"], [])
        self.assertEqual(datafeed_request_for_asset("us2y", "daily")["source_id"], "datafeed:treasury_official_csv")
        self.assertEqual(datafeed_request_for_asset("us2s10s", "daily")["source_id"], "datafeed:treasury_official_csv_derived")

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

    def test_client_sends_declared_a_share_fallback(self) -> None:
        calls: list[str] = []

        def opener(request, timeout):
            calls.append(request.full_url)
            payload = candle_response("shanghai", ticker="sh000001")
            payload.update(
                {
                    "provider": "sina_finance",
                    "source_mode": "sina_index",
                    "selected_source": "sina_index",
                    "selection_reason": "explicit_fallback",
                    "attempted_sources": ["tencent_kline", "sina_index"],
                    "source_identity": {"provider": "sina_finance", "provider_symbol": "sh000001"},
                }
            )
            return FakeResponse(payload)

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("shanghai", "daily")
        query = parse_qs(urlparse(calls[0]).query)
        self.assertEqual(query["fallback_policy"], ["explicit"])
        self.assertEqual(query["fallback_sources"], ["sina_index"])
        self.assertEqual(result["selected_source"], "sina_index")
        self.assertEqual(result["selection_reason"], "explicit_fallback")
        self.assertEqual(result["attempted_sources"], ["tencent_kline", "sina_index"])

    def test_default_urlopen_receives_timeout_as_a_keyword(self) -> None:
        calls = []

        class Response(FakeResponse):
            pass

        def fake_urlopen(request, **kwargs):
            calls.append(kwargs)
            return Response(candle_response("sp500", ticker="^GSPC"))

        import data_core.market_regime_weekly_datafeed as module
        original = module.urlopen
        module.urlopen = fake_urlopen
        try:
            result = WeeklyDatafeedClient(base_url="http://datafeed.test", timeout=7).fetch("sp500", "daily")
        finally:
            module.urlopen = original
        self.assertEqual(result["status"], "ready")
        self.assertEqual(calls, [{"timeout": 7}])

    def test_http_failure_is_typed_without_fallback(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse({"detail": {"reject_reason": "upstream_error"}}, status=503)

        client = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener)
        result = client.fetch("gold", "daily")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("upstream_error", result["reject_reason"])
        self.assertEqual(result["bars"], [])

    def test_http_failure_preserves_source_identity_and_provider_symbol(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse(
                {
                    "detail": {
                        "error": "upstream_error",
                        "reject_reason": "upstream_error",
                        "provider": "tencent_finance",
                        "provider_symbol": "sh000001",
                        "selected_source": "tencent_kline",
                        "attempted_sources": ["tencent_kline"],
                        "source_identity": {"source_id": "tencent_kline", "provider_symbol": "sh000001"},
                        "raw_timeframe": "1d",
                    }
                },
                status=502,
            )

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("shanghai", "daily")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["provider"], "tencent_finance")
        self.assertEqual(result["provider_symbol"], "sh000001")
        self.assertEqual(result["selected_source"], "tencent_kline")
        self.assertEqual(result["source_identity"]["provider_symbol"], "sh000001")
        self.assertTrue(result["source_identity"]["response_sha256"])

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

    def test_wrong_upstream_semantic_identity_is_not_relabelled(self) -> None:
        def opener(_request, _timeout):
            payload = candle_response("sp500", ticker="^GSPC")
            payload.update({"canonical_symbol": "WRONG", "unit": "bogus", "semantic_role": "wrong"})
            return FakeResponse(payload)

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("sp500", "daily")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("datafeed_contract", result["reject_reason"])

    def test_native_4h_response_is_passed_through_with_typed_metadata(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse(
                four_hour_response(
                    "bitcoin",
                    ticker="BTC",
                    raw_timeframe="4h",
                    timeframe_origin="native",
                    aggregation={"kind": "none", "rule": "native_passthrough"},
                )
            )

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("bitcoin", "four_hour")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["raw_timeframe"], "4h")
        self.assertEqual(result["timeframe_origin"], "native")
        self.assertEqual(result["aggregation"]["rule"], "native_passthrough")
        self.assertEqual(len(result["bars"]), 2)
        self.assertEqual(result["source_identity"]["provider_symbol"], "BTC")

    def test_aggregated_4h_response_requires_and_preserves_1h_metadata(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse(
                four_hour_response(
                    "gold",
                    ticker="GC=F",
                    raw_timeframe="1h",
                    timeframe_origin="aggregated",
                    aggregation={
                        "kind": "ohlc_resample",
                        "rule": "fixed_4h",
                        "input_timeframe": "1h",
                        "bucket_timezone": "UTC",
                        "anchor_hour": 0,
                        "anchor_minute": 0,
                    },
                )
            )

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("gold", "four_hour")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["raw_timeframe"], "1h")
        self.assertEqual(result["timeframe_origin"], "aggregated")
        self.assertEqual(result["aggregation"]["rule"], "fixed_4h")

    def test_invalid_4h_metadata_is_unavailable_not_silently_relabelled(self) -> None:
        def opener(_request, _timeout):
            return FakeResponse(
                four_hour_response(
                    "bitcoin",
                    ticker="BTC",
                    raw_timeframe="1h",
                    timeframe_origin="native",
                    aggregation={"kind": "none", "rule": "native_passthrough"},
                )
            )

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("bitcoin", "four_hour")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("datafeed_contract", result["reject_reason"])

    def test_cached_4h_response_is_not_promoted_to_ready(self) -> None:
        def opener(_request, _timeout):
            payload = four_hour_response(
                "bitcoin",
                ticker="BTC",
                raw_timeframe="4h",
                timeframe_origin="native",
                aggregation={"kind": "none", "rule": "native_passthrough"},
            )
            payload["served_from"] = "cache"
            payload["data_kind"] = "cached"
            return FakeResponse(payload)

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("bitcoin", "four_hour")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("datafeed_contract", result["reject_reason"])

    def test_4h_bar_must_respect_declared_anchor(self) -> None:
        def opener(_request, _timeout):
            payload = four_hour_response(
                "bitcoin",
                ticker="BTC",
                raw_timeframe="4h",
                timeframe_origin="native",
                aggregation={"kind": "none", "rule": "native_passthrough"},
            )
            payload["candles"][0]["timestamp"] = "2026-08-14T18:30:00+00:00"
            return FakeResponse(payload)

        result = WeeklyDatafeedClient(base_url="http://datafeed.test", opener=opener).fetch("bitcoin", "four_hour")
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
        self.assertEqual(snapshot["series"]["gold"]["points"], [{"date": "2026-08-14", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 0.0}])
        responses = build_weekly_candle_responses(snapshot)
        self.assertEqual(responses["gold:daily"]["status"], "unavailable")
        self.assertEqual(responses["gold:weekly"]["status"], "unavailable")
        self.assertEqual(snapshot["data_kind"], "real")
        self.assertTrue(all((key, "weekly") in calls for key in WEEKLY_ASSET_REGISTRY))
        self.assertTrue(all((key, "daily") in calls for key in WEEKLY_ASSET_REGISTRY))
        self.assertTrue(all((key, "four_hour") in calls for key in ("dxy", "bitcoin", "wti", "gold", "silver")))

    def test_native_btc_4h_survives_fetch_loader_snapshot_without_double_aggregation(self) -> None:
        class NativeClient:
            def fetch(self, asset_key, timeframe, **_kwargs):
                spec = WEEKLY_ASSET_REGISTRY[asset_key]
                identity = {"provider": "binance_spot", "source_mode": "binance_spot_public", "provider_symbol": "BTCUSDT" if asset_key == "bitcoin" else asset_key}
                if timeframe == "four_hour":
                    return {
                        "status": "ready",
                        "source_identity": identity,
                        "raw_timeframe": "4h",
                        "timeframe_origin": "native",
                        "aggregation": {"kind": "none", "rule": "native_passthrough"},
                        "bars": [
                            {"timestamp": "2026-08-14T16:00:00+00:00", "open": 100, "high": 104, "low": 99, "close": 103, "volume": 10},
                            {"timestamp": "2026-08-14T20:00:00+00:00", "open": 103, "high": 106, "low": 102, "close": 105, "volume": 10},
                        ],
                    }
                row = {"timestamp": "2026-08-14", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 0}
                if spec["series_kind"] != "price":
                    row["open"] = row["high"] = row["low"] = row["close"] = row["value"] = 4.2
                return {
                    "status": "ready",
                    "series_kind": spec["series_kind"],
                    "unit": spec["unit"],
                    "price_basis": spec["price_basis"],
                    "source_identity": identity,
                    "bars": [row],
                }

        snapshot = load_datafeed_weekly_source_snapshot(
            NativeClient(),
            week_end="2026-08-14",
            cutoff_at="2026-08-15T03:00:00Z",
        )
        context = snapshot["series"]["bitcoin"]["context_4h"]
        self.assertEqual(context["status"], "complete")
        self.assertEqual(len(context["points"]), 2)
        self.assertEqual(context["source_identity"]["provider_symbol"], "BTCUSDT")
        self.assertEqual(context["points"][0]["volume"], 10.0)
        response = build_weekly_candle_responses(snapshot)["bitcoin:four_hour"]
        self.assertEqual(response["status"], "ready")
        self.assertEqual(response["cache_policy"], "bypass")
        self.assertEqual(response["quality_policy"], "strict")
        self.assertEqual(response["served_from"], "upstream")
        self.assertEqual(response["source_identity"]["provider_symbol"], "BTCUSDT")

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
        responses = build_weekly_candle_responses(snapshot)
        self.assertEqual(responses["gold:daily"]["status"], "ready")
        self.assertEqual(responses["gold:weekly"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
