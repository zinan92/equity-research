from __future__ import annotations

import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_asset_analysis import (  # noqa: E402
    SCHEMA_VERSION,
    WeeklyAssetAnalysisError,
    build_asset_analysis_request,
    build_terminal_vector,
    compile_asset_analysis,
    validate_asset_analysis,
)
from data_core.market_regime_weekly_features import build_timeframe_features  # noqa: E402


def asset_snapshot(*, with_4h: bool = True) -> dict:
    result = {
        "key": "gold",
        "canonical_symbol": "GC=F",
        "series_kind": "price",
        "week_end": "2026-08-14",
        "data_kind": "fixture",
        "source_identity": {"provider": "fixture", "key": "gold"},
        "weekly": {"points": [{"date": "2026-08-14", "open": 100, "high": 110, "low": 98, "close": 108}], "evidence_ids": ["gold:weekly:1"]},
        "daily": {"points": [{"date": "2026-08-14", "open": 106, "high": 109, "low": 104, "close": 108}], "evidence_ids": ["gold:daily:1"]},
    }
    if with_4h:
        result["four_hour"] = {"points": [{"start_at": "2026-08-14T00:00:00Z", "open": 107, "high": 109, "low": 106, "close": 108}], "evidence_ids": ["gold:4h:1"]}
    for timeframe in ("weekly", "daily", "four_hour"):
        if timeframe not in result:
            continue
        feature = build_timeframe_features(
            {"key": "gold", "series_kind": "price", "source_identity": result["source_identity"], "points": result[timeframe]["points"]},
            timeframe=timeframe,
        )
        result[timeframe]["features"] = feature
        result[timeframe]["evidence_ids"].append(f"feature:{feature['feature_identity']}")
    return result


def valid_output(request: dict) -> dict:
    citations = [item for tf in request["timeframes"].values() for item in tf["evidence_ids"]]
    mechanism_id = request["mechanism"]["mechanism_ids"][0]
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
        "theoretical_implication": {"text": "通常由实际利率、美元与避险需求共同驱动；但危机初期现金需求也可能令该机制暂时失效。", "evidence_ids": [mechanism_id], "claim_type": "theoretical_mechanism"},
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

    def test_input_registry_mismatch_fails_closed(self) -> None:
        snapshot = asset_snapshot()
        snapshot["canonical_symbol"] = "FAKE"
        with self.assertRaisesRegex(WeeklyAssetAnalysisError, "asset_registry_mismatch:gold:canonical_symbol"):
            build_asset_analysis_request(snapshot)

    def test_unknown_evidence_id_fails_closed(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        output = valid_output(request)
        output["daily"]["evidence_ids"] = ["not-in-request"]
        with self.assertRaisesRegex(WeeklyAssetAnalysisError, "evidence_id_unknown"):
            validate_asset_analysis(output, request)

    def test_theory_requires_mechanism_citation_and_claim_type(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        output = valid_output(request)
        output["theoretical_implication"]["evidence_ids"] = ["gold:weekly:1"]
        with self.assertRaisesRegex(WeeklyAssetAnalysisError, "mechanism_evidence_required"):
            validate_asset_analysis(output, request)
        output = valid_output(request)
        output["theoretical_implication"]["claim_type"] = "observed_fact"
        with self.assertRaisesRegex(WeeklyAssetAnalysisError, "theory_claim_type_invalid"):
            validate_asset_analysis(output, request)

    def test_model_cannot_supply_odds_levels(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        output = valid_output(request)
        output["odds"] = {"direction": "long", "entry_reference": 1}
        with self.assertRaisesRegex(WeeklyAssetAnalysisError, "analysis_odds_must_be_code_owned"):
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
        self.assertEqual(artifact["identity_core"]["schema_version"], SCHEMA_VERSION)
        self.assertEqual(artifact["request_asset_key"], "gold")
        self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")
        self.assertEqual(artifact["receipt"]["request_hash"], artifact["identity_core"]["request_hash"])
        self.assertEqual(artifact["receipt"]["output_hash"], artifact["output_hash"])
        self.assertIn("odds", artifact)
        self.assertEqual(artifact["odds"]["schema_version"], "market-regime-weekly-odds-v1")

    def test_provider_failure_keeps_code_owned_dimensions(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        artifact = compile_asset_analysis(request, lambda _: (_ for _ in ()).throw(TimeoutError("provider timeout")))
        self.assertEqual(artifact["generation_status"], "analysis_unavailable")
        self.assertEqual(artifact["failure_code"], "provider_error")
        self.assertEqual(artifact["deterministic_status"], "validated")
        self.assertIn("position", artifact)
        self.assertIn("structure", artifact)
        self.assertIn("odds", artifact)
        self.assertTrue(artifact["analysis_id"].startswith("market-regime-weekly-asset-analysis:"))

    def test_missing_provider_keeps_code_owned_dimensions(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        artifact = compile_asset_analysis(request, None)
        self.assertEqual(artifact["failure_code"], "provider_unavailable")
        self.assertEqual(artifact["deterministic_status"], "validated")
        self.assertIn("position", artifact)
        self.assertIn("structure", artifact)
        self.assertIn("odds", artifact)

    def test_malformed_derived_feature_returns_typed_unavailable(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        bad_point = dict(request["timeframes"]["daily"]["features"]["points"][0])
        bad_point["close"] = "bad"
        request["timeframes"]["daily"]["features"]["points"].append(bad_point)
        artifact = compile_asset_analysis(request, lambda _: valid_output(request))
        self.assertEqual(artifact["generation_status"], "analysis_unavailable")
        self.assertEqual(artifact["failure_code"], "derived_feature_invalid")

    def test_terminal_vector_keeps_unavailable_slots_and_order(self) -> None:
        request = build_asset_analysis_request(asset_snapshot(with_4h=False))
        gold = compile_asset_analysis(request, lambda _: valid_output(request))
        vector = build_terminal_vector({"gold": gold})
        self.assertEqual(len(vector), 19)
        self.assertEqual(vector[0]["asset_key"], "dxy")
        self.assertEqual(vector[-1]["asset_key"], "silver")
        gold_slot = next(item for item in vector if item["asset_key"] == "gold")
        self.assertEqual(gold_slot["status"], "validated")
        self.assertEqual(next(item for item in vector if item["asset_key"] == "sp500")["status"], "analysis_unavailable")


if __name__ == "__main__":
    unittest.main()
