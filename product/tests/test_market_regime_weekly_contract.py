from __future__ import annotations

import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_contract import (  # noqa: E402
    CANDLE_RESPONSE_SCHEMA_VERSION,
    WEEKLY_ASSET_REGISTRY,
    WEEKLY_ASSET_REGISTRY_VERSION,
    WEEKLY_CANDLE_CONTRACT_VERSION,
    WeeklyCandleContractError,
    build_unavailable_candle_response,
    build_candle_response_from_weekly_series,
    build_weekly_candle_responses,
    validate_weekly_candle_response,
)


def ready_response(*, asset_key: str = "sp500", timeframe: str = "daily") -> dict:
    spec = WEEKLY_ASSET_REGISTRY[asset_key]
    primary_source = spec["source_id"].removeprefix("datafeed:")
    return {
        "schema_version": CANDLE_RESPONSE_SCHEMA_VERSION,
        "weekly_contract_version": WEEKLY_CANDLE_CONTRACT_VERSION,
        "asset_key": asset_key,
        "canonical_symbol": spec["canonical_symbol"],
        "asset_class": spec["asset_class"],
        "series_kind": spec["series_kind"],
        "semantic_role": spec["semantic_role"],
        "timeframe": timeframe,
        "unit": spec["unit"],
        "price_basis": spec["price_basis"],
        "status": "ready",
        "provider": "yahoo_finance",
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
        "latest_timestamp": "2026-08-14T00:00:00Z",
        "age_seconds": None,
        "max_age_seconds": None,
        "execution_venue": False,
        "reject_reason": None,
        "access_issues": [],
        "source_identity": {"run_id": "run-1", "normalized_sha256": "a" * 64},
        "bars": [
            {"timestamp": "2026-08-13T00:00:00Z", "open": 99, "high": 102, "low": 98, "close": 101, "volume": 10},
            {"timestamp": "2026-08-14T00:00:00Z", "open": 101, "high": 104, "low": 100, "close": 103, "volume": 12},
        ],
    }


class WeeklyCandleContractTest(unittest.TestCase):
    def test_registry_has_exact_19_assets_and_timeframe_policy(self) -> None:
        self.assertEqual(len(WEEKLY_ASSET_REGISTRY), 19)
        self.assertEqual(WEEKLY_ASSET_REGISTRY_VERSION, "market-regime-weekly-tradeable-asset-registry-v2")
        cash_or_rate = {"us2y", "us10y", "us2s10s", "sp500", "nasdaq", "us_dividend", "vix", "shanghai", "star50", "china_dividend", "nikkei", "kospi"}
        for key in cash_or_rate:
            self.assertNotIn("four_hour", WEEKLY_ASSET_REGISTRY[key]["allowed_timeframes"])
        for key in ("bitcoin", "ethereum", "hype", "wti", "gold", "silver"):
            self.assertIn("four_hour", WEEKLY_ASSET_REGISTRY[key]["allowed_timeframes"])

    def test_valid_price_response_is_accepted_and_preserves_trust_fields(self) -> None:
        response = ready_response()
        validated = validate_weekly_candle_response(response)
        self.assertEqual(validated["asset_key"], "sp500")
        self.assertEqual(validated["fallback_policy"], "none")
        self.assertEqual(validated["source_identity"]["run_id"], "run-1")
        self.assertEqual(len(validated["bars"]), 2)

    def test_a_share_contract_declares_explicit_fallback_chain(self) -> None:
        response = ready_response(asset_key="shanghai")
        validated = validate_weekly_candle_response(response)

        self.assertEqual(validated["fallback_policy"], "explicit")
        self.assertEqual(validated["fallback_sources"], ["sina_index"])
        self.assertEqual(validated["attempted_sources"], ["tencent_kline"])

        fallback = dict(response)
        fallback.update(
            {
                "source_mode": "sina_index",
                "selected_source": "sina_index",
                "selection_reason": "explicit_fallback",
                "attempted_sources": ["tencent_kline", "sina_index"],
                "source_identity": {"provider": "sina_finance", "provider_symbol": "sh000001"},
            }
        )
        self.assertEqual(validate_weekly_candle_response(fallback)["selected_source"], "sina_index")

    def test_rate_and_spread_semantics_are_distinct(self) -> None:
        rate = ready_response(asset_key="us2y")
        rate["bars"] = [{"timestamp": "2026-08-14", "open": 4.2, "high": 4.2, "low": 4.2, "close": 4.2, "value": 4.2, "volume": 0}]
        self.assertEqual(validate_weekly_candle_response(rate)["series_kind"], "rate_level")
        spread = ready_response(asset_key="us2s10s")
        spread["unit"] = "basis points"
        spread["bars"] = [{"timestamp": "2026-08-14", "open": 35, "high": 35, "low": 35, "close": 35, "value": 35, "volume": 0}]
        self.assertEqual(validate_weekly_candle_response(spread)["series_kind"], "spread")
        invalid = ready_response(asset_key="us2s10s")
        invalid["series_kind"] = "rate_level"
        with self.assertRaisesRegex(WeeklyCandleContractError, "registry_series_kind_mismatch"):
            validate_weekly_candle_response(invalid)

    def test_unavailable_response_is_typed_without_bars(self) -> None:
        response = build_unavailable_candle_response("sp500", "daily", "upstream_unavailable")
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["fallback_policy"], "none")
        self.assertEqual(response["bars"], [])
        self.assertEqual(validate_weekly_candle_response(response)["reject_reason"], "upstream_unavailable")

    def test_fallback_synthetic_bad_ohlc_and_wrong_timeframe_fail_closed(self) -> None:
        response = ready_response()
        response["fallback_policy"] = "explicit"
        with self.assertRaisesRegex(WeeklyCandleContractError, "fallback_policy_invalid"):
            validate_weekly_candle_response(response)
        response = ready_response()
        response["is_synthetic"] = True
        with self.assertRaisesRegex(WeeklyCandleContractError, "synthetic_ready_forbidden"):
            validate_weekly_candle_response(response)
        response = ready_response()
        response["bars"][1]["low"] = 105
        with self.assertRaisesRegex(WeeklyCandleContractError, "bar_low_invalid"):
            validate_weekly_candle_response(response)
        response = ready_response()
        response["timeframe"] = "four_hour"
        with self.assertRaisesRegex(WeeklyCandleContractError, "timeframe_not_allowed"):
            validate_weekly_candle_response(response)

    def test_stale_or_unbounded_ready_response_fails_closed(self) -> None:
        response = ready_response()
        response["fresh"] = False
        with self.assertRaisesRegex(WeeklyCandleContractError, "stale_ready_forbidden"):
            validate_weekly_candle_response(response)
        response = ready_response()
        response["age_seconds"] = 100
        response["max_age_seconds"] = 90
        with self.assertRaisesRegex(WeeklyCandleContractError, "stale_ready_forbidden"):
            validate_weekly_candle_response(response)
        response = ready_response()
        response["latest_timestamp"] = None
        with self.assertRaisesRegex(WeeklyCandleContractError, "latest_timestamp_missing"):
            validate_weekly_candle_response(response)

    def test_four_hour_uses_context_source_identity_and_quality(self) -> None:
        source = {
            "cutoff_at": "2026-08-14T23:59:59Z",
            "series": {
                "gold": {
                    "status": "complete",
                    "data_kind": "real",
                    "quality": "fresh",
                    "source_identity": {"run_id": "daily-run"},
                    "points": [],
                    "context_4h": {
                        "status": "complete",
                        "data_kind": "real",
                        "quality": "fresh",
                        "source_identity": {"run_id": "hourly-run"},
                        "points": [{"start_at": "2026-08-14T00:00:00Z", "open": 1, "high": 2, "low": 1, "close": 2}],
                    },
                }
            },
        }
        response = build_candle_response_from_weekly_series(source, "gold", "four_hour")
        self.assertEqual(response["source_identity"]["run_id"], "hourly-run")
        self.assertIn("fresh", response["quality_flags"])
        self.assertTrue(response["fresh"])

    def test_weekly_uses_weekly_source_identity_and_quality(self) -> None:
        source = {
            "cutoff_at": "2026-08-14T23:59:59Z",
            "series": {
                "gold": {
                    "status": "complete",
                    "data_kind": "real",
                    "quality": "stale",
                    "source_identity": {"run_id": "daily-run"},
                    "weekly_source_identity": {"run_id": "weekly-run"},
                    "weekly_quality": "fresh",
                    "weekly_quality_flags": ["weekly_source"],
                    "weekly_fresh": True,
                    "weekly_data_kind": "real",
                    "points": [{"date": "2026-08-14", "open": 100, "high": 102, "low": 99, "close": 101}],
                }
            },
        }
        response = build_candle_response_from_weekly_series(source, "gold", "weekly")
        self.assertEqual(response["source_identity"]["run_id"], "weekly-run")
        self.assertIn("weekly_source", response["quality_flags"])
        self.assertTrue(response["fresh"])

    def test_unknown_source_data_kind_is_blocked(self) -> None:
        source = {
            "series": {
                "gold": {
                    "status": "complete",
                    "data_kind": "mystery",
                    "source_identity": {"run_id": "run-1"},
                    "points": [{"date": "2026-08-14", "open": 1, "high": 2, "low": 1, "close": 2}],
                }
            }
        }
        response = build_candle_response_from_weekly_series(source, "gold", "weekly")
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["reject_reason"], "data_kind_unknown")

    def test_source_failure_reason_and_identity_survive_weekly_bridge(self) -> None:
        response = build_candle_response_from_weekly_series(
            {
                "series": {
                    "gold": {
                        "daily_status": "unavailable",
                        "daily_reject_reason": "datafeed_http:502:upstream_error",
                        "daily_access_issues": ["Yahoo unavailable"],
                        "data_kind": "real",
                        "source_identity": {
                            "provider": "yahoo_finance",
                            "provider_symbol": "GC=F",
                            "response_sha256": "a" * 64,
                        },
                        "points": [],
                    }
                }
            },
            "gold",
            "daily",
        )
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["reject_reason"], "datafeed_http:502:upstream_error")
        self.assertEqual(response["source_identity"]["provider_symbol"], "GC=F")
        self.assertEqual(response["source_identity"]["response_sha256"], "a" * 64)
        self.assertEqual(response["access_issues"], ["Yahoo unavailable"])

    def test_cached_source_cannot_be_promoted_to_ready(self) -> None:
        response = build_candle_response_from_weekly_series(
            {
                "series": {
                    "gold": {
                        "status": "complete",
                        "data_kind": "cached",
                        "source_identity": {"provider": "yahoo_finance", "provider_symbol": "GC=F"},
                        "points": [{"date": "2026-08-14", "open": 100, "high": 101, "low": 99, "close": 100}],
                    }
                }
            },
            "gold",
            "weekly",
        )
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["reject_reason"], "cached_source_forbidden")

    def test_current_weekly_source_bridge_has_44_typed_responses(self) -> None:
        from product.tests.test_market_regime_weekly_runtime import source_fixture

        responses = build_weekly_candle_responses(source_fixture(data_kind="fixture"))
        self.assertEqual(len(responses), 44)
        self.assertEqual(responses["gold:weekly"]["status"], "blocked")
        self.assertTrue(responses["gold:weekly"]["is_synthetic"])


if __name__ == "__main__":
    unittest.main()
