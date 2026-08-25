from __future__ import annotations

from datetime import datetime, timedelta, timezone
import copy
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_analysis import (  # noqa: E402
    DailyAnalysisError,
    DailyAnalysisStore,
    build_daily_analysis_bundle,
    build_daily_asset_request,
    compile_daily_asset_analysis,
    DeepSeekDailyAssetProvider,
    validate_daily_asset_analysis,
)
from data_core.market_regime_daily_source import DAILY_TIMEFRAMES, DAILY_TIMEFRAMES_BY_ASSET, build_daily_source_bundle  # noqa: E402
from data_core.market_regime_daily_snapshots import build_daily_standard_kline_payload  # noqa: E402
from data_core.market_regime_weekly_source import WEEKLY_KEYS  # noqa: E402


def _source_bundle() -> dict:
    assets = []
    for index, key in enumerate(WEEKLY_KEYS):
        instrument = {
            "canonical_symbol": key.upper(),
            "asset_class": "etf",
            "series_kind": "price",
            "unit": "USD/share",
            "price_basis": "provider_unadjusted_trade_price",
            "semantic_role": "price_etf",
        }
        slots = {}
        for timeframe in DAILY_TIMEFRAMES_BY_ASSET[key]:
            points = []
            for offset in range(60):
                value = 100 + index + offset
                stamp = (datetime(2026, 1, 1) + timedelta(days=offset)).date().isoformat()
                points.append({"timestamp": stamp, "open": value - 1, "high": value + 1, "low": value - 2, "close": value, "volume": 1})
            slots[timeframe] = {
                "status": "ready",
                "bars": points,
                "latest_timestamp": points[-1]["timestamp"],
                "source_identity": {"provider": "fake", "response_sha256": f"{index:064x}"},
                "completion_state": "complete",
                "is_provisional": False,
            }
        assets.append({"asset_key": key, "display_name": key, "instrument": instrument, "slots": slots})
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity_core = {
        "schema_version": "market-regime-daily-source-bundle-v2",
        "registry_version": "market-regime-daily-tradeable-registry-v2",
        "generated_at": "2026-08-31T00:00:00Z",
        "cutoff_at": "2026-08-31T00:00:00Z",
        "assets_sha256": hashlib.sha256(canonical(assets).encode()).hexdigest(),
        "slot_hashes": [],
    }
    bundle_id = "market-regime-daily-source:" + hashlib.sha256(canonical(identity_core).encode()).hexdigest()
    return {
        "schema_version": "market-regime-daily-source-bundle-v2",
        "registry_version": "market-regime-daily-tradeable-registry-v2",
        "source_status": "ready",
        "data_kind": "real",
        "bundle_id": bundle_id,
        "generated_at": "2026-08-31T00:00:00Z",
        "cutoff_at": "2026-08-31T00:00:00Z",
        "assets": assets,
        "identity_core": identity_core,
        "source_policy": {"cache_policy": "bypass", "quality_policy": "strict"},
        "coverage": {
            "total_slots": sum(len(DAILY_TIMEFRAMES_BY_ASSET[item]) for item in WEEKLY_KEYS),
            "ready_slots": sum(len(DAILY_TIMEFRAMES_BY_ASSET[item]) for item in WEEKLY_KEYS),
            "unavailable_slots": 0,
            "fraction": 1.0,
            "requested_timeframes": list(DAILY_TIMEFRAMES),
            "timeframes_by_asset": {item: list(DAILY_TIMEFRAMES_BY_ASSET[item]) for item in WEEKLY_KEYS},
        },
    }


def _provider(request):
    evidence = [item for frame in request["timeframes"].values() for item in frame["evidence_ids"]]
    mechanism = request["mechanism"]["mechanism_ids"][0]
    statement = lambda text: {"text": text, "evidence_ids": evidence[:1]}
    return {
        "asset_key": request["asset_key"],
        "generation_status": "model_generated_unreviewed",
        "daily": statement("日线趋势仍在延续，证据来自冻结日线。"),
        "four_hour": statement("4小时结构提供短线节奏，证据来自冻结周期。"),
        "thirty_minute": statement("30分钟结构用于观察短线节奏，证据来自冻结周期。"),
        "synthesis": statement("多周期方向一致，等待关键位确认。"),
        "market_meaning": {"text": "通常反映风险偏好变化，但也可能由资产自身供需驱动。", "evidence_ids": [mechanism], "claim_type": "theoretical_mechanism"},
        "confirmation": statement("若下一周期继续维持当前结构，则解释得到确认。"),
        "invalidation": statement("若结构反向破坏，则当前解释失效。"),
        "rationale": statement("当前结论只基于冻结 K 线证据。"),
        "opportunity_state": "wait",
    }


class DailyAnalysisTests(unittest.TestCase):
    def test_deepseek_asset_provider_retries_old_shape_with_validator_feedback(self) -> None:
        request = build_daily_asset_request(_source_bundle()["assets"][0], cutoff_at="2026-08-31T00:00:00Z")
        evidence = request["timeframes"]["daily"]["evidence_ids"][:1]
        mechanism = request["mechanism"]["mechanism_ids"][:1]
        valid = {
            "asset_key": request["asset_key"],
            "generation_status": "model_generated_unreviewed",
            "daily": {"text": "日线结构保持，等待关键位确认。", "evidence_ids": evidence},
            "synthesis": {"text": "日线证据支持等待。", "evidence_ids": evidence},
            "market_meaning": {"text": "通常反映风险偏好变化，但也可能由资产自身供需驱动。", "evidence_ids": mechanism, "claim_type": "theoretical_mechanism"},
            "confirmation": {"text": "若结构继续保持，则得到确认。", "evidence_ids": evidence},
            "invalidation": {"text": "若结构破坏，则当前解释失效。", "evidence_ids": evidence},
            "rationale": {"text": "当前结论只基于冻结 K 线证据。", "evidence_ids": evidence},
            "opportunity_state": "wait",
        }
        old_shape = {"asset_key": request["asset_key"], "generation_status": "complete", "daily": "旧格式字符串"}
        with patch("deepseek_writer.call_structured_deepseek", side_effect=[(old_shape, {"provider": "test"}), (valid, {"provider": "test"})]) as call:
            output, receipt = DeepSeekDailyAssetProvider("/tmp/unused-key")(request)
        self.assertEqual(output["generation_status"], "model_generated_unreviewed")
        self.assertEqual(receipt["attempt_count"], 2)
        self.assertEqual(call.call_count, 2)

    def test_request_contains_three_features_and_completion_metadata(self) -> None:
        asset = _source_bundle()["assets"][0]
        request = build_daily_asset_request(asset, cutoff_at="2026-08-31T00:00:00Z")
        self.assertEqual(set(request["timeframes"]), set(DAILY_TIMEFRAMES_BY_ASSET["dxy"]))
        self.assertTrue(all(frame["features"]["feature_identity"] for frame in request["timeframes"].values()))
        self.assertTrue(all(frame["completion_state"] == "complete" for frame in request["timeframes"].values()))

    def test_compiles_all_assets_with_isolated_model_output(self) -> None:
        bundle = build_daily_analysis_bundle(_source_bundle(), provider_factory=lambda _request: _provider)
        self.assertEqual(len(bundle["assets"]), len(WEEKLY_KEYS))
        self.assertEqual(bundle["analysis_status"], "ready")
        self.assertTrue(all(item["analysis"]["generation_status"] == "model_generated_unreviewed" for item in bundle["assets"]))

    def test_provider_failure_is_typed_without_stale_fallback(self) -> None:
        request = build_daily_asset_request(_source_bundle()["assets"][0], cutoff_at="2026-08-31T00:00:00Z")
        result = compile_daily_asset_analysis(request, provider=None)
        self.assertEqual(result["generation_status"], "analysis_unavailable")
        self.assertEqual(result["failure_code"], "provider_unavailable")
        self.assertIn("output", result)
        self.assertIn("deterministic", result["output"])

    def test_unavailable_period_must_be_disclosed_and_cannot_be_neutralized(self) -> None:
        asset = copy.deepcopy(_source_bundle()["assets"][0])
        asset["slots"]["daily"].update({"status": "unavailable", "bars": [], "reason_code": "upstream_error"})
        request = build_daily_asset_request(asset, cutoff_at="2026-08-31T00:00:00Z")
        output = _provider(request)
        output["daily"] = {"text": "日线横盘。", "evidence_ids": [request["timeframes"]["daily"]["evidence_ids"][0]]}
        with self.assertRaises(DailyAnalysisError):
            validate_daily_asset_analysis(output, request)

    def test_mechanism_id_cannot_cite_a_current_period_statement(self) -> None:
        request = build_daily_asset_request(_source_bundle()["assets"][0], cutoff_at="2026-08-31T00:00:00Z")
        output = _provider(request)
        output["daily"]["evidence_ids"] = [request["mechanism"]["mechanism_ids"][0]]
        with self.assertRaises(DailyAnalysisError):
            validate_daily_asset_analysis(output, request)

    def test_ready_period_rejects_unbound_numeric_observation(self) -> None:
        request = build_daily_asset_request(_source_bundle()["assets"][0], cutoff_at="2026-08-31T00:00:00Z")
        output = _provider(request)
        output["daily"]["text"] = "日线价格收于9999，趋势延续。"
        with self.assertRaises(DailyAnalysisError):
            validate_daily_asset_analysis(output, request)

    def test_standard_kline_payload_keeps_static_renderer_contract(self) -> None:
        asset = _source_bundle()["assets"][0]
        payload = build_daily_standard_kline_payload(asset, "daily")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["renderer"], "zinan92/standard-kline@07acafa79e72af10d17b5a10b7bb11625fd709c2")
        self.assertEqual(payload["renderer_options"]["indicators"]["ema"], [50])
        self.assertEqual(len(payload["candles"]), 60)

    def test_analysis_store_readback_and_asset_hash(self) -> None:
        bundle = build_daily_analysis_bundle(_source_bundle(), provider_factory=lambda _request: _provider)
        with tempfile.TemporaryDirectory() as directory:
            store = DailyAnalysisStore(Path(directory))
            pointer = store.publish(bundle)
            self.assertEqual(store.latest()["bundle_id"], pointer["bundle_id"])
            tampered = dict(bundle)
            tampered["assets"] = [*bundle["assets"]]
            tampered["assets"][0] = {**tampered["assets"][0], "display_name": "tampered"}
            with self.assertRaises(DailyAnalysisError):
                store.publish(tampered)


if __name__ == "__main__":
    unittest.main()
