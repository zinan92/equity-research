from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
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
)
from data_core.market_regime_daily_source import DAILY_TIMEFRAMES, build_daily_source_bundle  # noqa: E402
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
        for timeframe in DAILY_TIMEFRAMES:
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
    return {"schema_version": "market-regime-daily-source-bundle-v1", "source_status": "ready", "bundle_id": "market-regime-daily-source:test", "cutoff_at": "2026-08-31T00:00:00Z", "assets": assets}


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
    def test_request_contains_three_features_and_completion_metadata(self) -> None:
        asset = _source_bundle()["assets"][0]
        request = build_daily_asset_request(asset, cutoff_at="2026-08-31T00:00:00Z")
        self.assertEqual(set(request["timeframes"]), set(DAILY_TIMEFRAMES))
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
