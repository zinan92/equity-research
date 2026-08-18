from __future__ import annotations

import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_asset_analysis import (  # noqa: E402
    WeeklyAssetAnalysisError,
    build_asset_analysis_request,
    build_terminal_vector,
    compile_asset_analysis,
    validate_asset_analysis,
)


def asset_snapshot(*, with_4h: bool = True) -> dict:
    result = {
        "key": "gold",
        "canonical_symbol": "GC=F",
        "series_kind": "price",
        "week_end": "2026-08-14",
        "data_kind": "fixture",
        "weekly": {"points": [{"date": "2026-08-14", "open": 100, "high": 110, "low": 98, "close": 108}], "evidence_ids": ["gold:weekly:1"]},
        "daily": {"points": [{"date": "2026-08-14", "open": 106, "high": 109, "low": 104, "close": 108}], "evidence_ids": ["gold:daily:1"]},
    }
    if with_4h:
        result["four_hour"] = {"points": [{"start_at": "2026-08-14T00:00:00Z", "open": 107, "high": 109, "low": 106, "close": 108}], "evidence_ids": ["gold:4h:1"]}
    return result


def valid_output(request: dict) -> dict:
    citations = [item for tf in request["timeframes"].values() for item in tf["evidence_ids"]]
    result = {
        "asset_key": "gold",
        "generation_status": "model_generated_unreviewed",
        "weekly": {"text": "周线处于区间上部，最近一根周 K 偏强。", "evidence_ids": ["gold:weekly:1"]},
        "daily": {"text": "日线维持抬高低点结构。", "evidence_ids": ["gold:daily:1"]},
        "synthesis": {"text": "周线与日线方向一致，但仍需确认压力位。", "evidence_ids": citations[:2]},
        "agreement": "aligned_bullish",
        "confirmation": {"text": "完整周期收盘站上近期高点。", "evidence_ids": citations[:1]},
        "invalidation": {"text": "完整周期收盘跌破近期低点。", "evidence_ids": citations[:1]},
        "opportunity_state": "participate",
        "rationale": {"text": "结构清晰，等待确认。", "evidence_ids": citations[:2]},
    }
    if "four_hour" in request["timeframes"]:
        result["four_hour"] = {"text": "4H 回踩后仍守住结构。", "evidence_ids": ["gold:4h:1"]}
    return result


class WeeklyAssetAnalysisTest(unittest.TestCase):
    def test_request_contains_only_one_asset_and_available_timeframes(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        self.assertEqual(request["asset_key"], "gold")
        self.assertEqual(set(request["timeframes"]), {"weekly", "daily", "four_hour"})
        self.assertNotIn("sp500", repr(request))

    def test_valid_output_is_accepted_at_public_seam(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        validated = validate_asset_analysis(valid_output(request), request)
        self.assertEqual(validated["opportunity_state"], "participate")
        self.assertEqual(validated["asset_key"], "gold")

    def test_unknown_evidence_id_fails_closed(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        output = valid_output(request)
        output["daily"]["evidence_ids"] = ["not-in-request"]
        with self.assertRaisesRegex(WeeklyAssetAnalysisError, "evidence_id_unknown"):
            validate_asset_analysis(output, request)

    def test_missing_4h_is_a_valid_absence_not_daily_substitution(self) -> None:
        request = build_asset_analysis_request(asset_snapshot(with_4h=False))
        output = valid_output(request)
        self.assertNotIn("four_hour", output)
        self.assertEqual(validate_asset_analysis(output, request)["asset_key"], "gold")

    def test_provider_compile_binds_request_and_output_identity(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        artifact = compile_asset_analysis(request, lambda _: valid_output(request))
        self.assertTrue(artifact["analysis_id"].startswith("market-regime-weekly-asset-analysis:"))
        self.assertEqual(artifact["request_asset_key"], "gold")
        self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")

    def test_terminal_vector_keeps_unavailable_slots_and_order(self) -> None:
        request = build_asset_analysis_request(asset_snapshot(with_4h=False))
        gold = compile_asset_analysis(request, lambda _: valid_output(request))
        vector = build_terminal_vector({"gold": gold})
        self.assertEqual(len(vector), 17)
        self.assertEqual(vector[0]["asset_key"], "dxy")
        self.assertEqual(vector[-1]["asset_key"], "silver")
        gold_slot = next(item for item in vector if item["asset_key"] == "gold")
        self.assertEqual(gold_slot["status"], "validated")
        self.assertEqual(next(item for item in vector if item["asset_key"] == "sp500")["status"], "analysis_unavailable")


if __name__ == "__main__":
    unittest.main()
