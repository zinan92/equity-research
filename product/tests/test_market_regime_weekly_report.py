from __future__ import annotations

import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_report import (  # noqa: E402
    WeeklyReportError,
    build_weekly_report,
    render_weekly_html,
    render_weekly_markdown,
)
from data_core.market_regime_weekly_features import FEATURE_SCHEMA_VERSION  # noqa: E402
from data_core.market_regime_weekly_source import WEEKLY_KEYS  # noqa: E402
from data_core.market_regime_weekly_contract import CANDLE_RESPONSE_SCHEMA_VERSION, WEEKLY_CANDLE_CONTRACT_VERSION, WEEKLY_ASSET_REGISTRY  # noqa: E402


def source_fixture() -> dict:
    series = {}
    for index, key in enumerate(WEEKLY_KEYS):
        point = {"date": "2026-08-14", "open": 100 + index, "high": 101 + index, "low": 99 + index, "close": 100.5 + index}
        item = {"key": key, "series_kind": "spread" if key == "us2s10s" else ("rate_level" if key in {"us2y", "us10y"} else "price"), "status": "complete", "weekly_bin_count": 1, "points": [{"date": "2026-08-14", "value": 4.2}] if key in {"us2y", "us10y", "us2s10s"} else [point], "quality": "fresh", "data_kind": "fixture", "canonical_symbol": key, "unit": "basis points" if key == "us2s10s" else "index points", "source_identity": {"provider": "fixture", "key": key}}
        item["context_4h"] = {"status": "complete", "points": [{"start_at": "2026-08-14T00:00:00Z", **point, "duration_hours": 4}]} if key in {"dxy", "bitcoin", "wti", "gold", "silver"} else None
        series[key] = item
    return {"schema_version": "market-regime-weekly-source-history-v1", "registry_version": "market-regime-weekly-registry-v1", "week_end": "2026-08-14", "cutoff_at": "2026-08-14T23:59:59Z", "status": "complete", "missing_series": [], "data_kind": "fixture", "quality": "fresh", "series": series}


def analyses_fixture() -> dict:
    return {
        key: {
            "analysis_id": f"market-regime-weekly-asset-analysis:fixture:{key}",
            "asset_key": key,
            "generation_status": "model_generated_unreviewed",
            "weekly": {"text": f"{key} weekly", "evidence_ids": [f"e:{key}:w"]},
            "daily": {"text": f"{key} daily", "evidence_ids": [f"e:{key}:d"]},
            **({"four_hour": {"text": f"{key} 4h", "evidence_ids": [f"e:{key}:4h"]}} if key in {"dxy", "bitcoin", "wti", "gold", "silver"} else {}),
            "synthesis": {"text": f"{key} synthesis", "evidence_ids": [f"e:{key}:w"]},
            "position": {"state": "middle", "percentile": 0.5, "window": 1, "sample_count": 1, "text": "位置：中位。", "evidence_ids": [f"e:{key}:w"]},
            "structure": {"state": "mixed", "bias": "mixed", "text": "结构：混合。", "evidence_ids": [f"e:{key}:w", f"feature:fixture:{key}"], "timeframes": {"daily": {"evidence_ids": [f"e:{key}:d", f"feature:fixture:{key}"]}}},
            "odds": {"schema_version": "market-regime-weekly-odds-v1", "formula_version": "entry-close-boundary-v1", "state": "not_ready", "direction": "none", "timeframe": "daily", "evidence_ids": [f"e:{key}:d", f"feature:fixture:{key}"], "reason_code": "direction_unavailable", "text": "赔率尚未形成：多周期没有单一方向。"},
            "agreement": "mixed",
            "confirmation": {"text": "confirm", "evidence_ids": [f"e:{key}:w"]},
            "invalidation": {"text": "invalidate", "evidence_ids": [f"e:{key}:d"]},
            "opportunity_state": "wait",
            "rationale": {"text": "rationale", "evidence_ids": [f"e:{key}:w"]},
            "theoretical_implication": {"text": "通常由宏观驱动；但该传导并非始终稳定。", "evidence_ids": [f"mechanism:{key}:drivers"], "claim_type": "theoretical_mechanism"},
        }
        for key in WEEKLY_KEYS
    }


def ranking_fixture() -> dict:
    return {"ranking_id": "ranking:fixture", "generation_status": "model_generated_unreviewed", "important_changes": [], "ordered_assets": [{"asset_key": key, "status": "wait", "rank": index + 1, "text": "wait", "evidence_ids": [f"analysis:{key}"]} for index, key in enumerate(WEEKLY_KEYS)]}


def candle_response_fixture(asset_key: str, *, series_kind: str | None = None) -> dict:
    spec = WEEKLY_ASSET_REGISTRY[asset_key]
    kind = series_kind or spec["series_kind"]
    primary_source = spec["source_id"].removeprefix("datafeed:")
    fallback_sources = list(spec.get("fallback_sources", []))
    provider_symbols = {
        "us2y": "2 Yr",
        "us10y": "10 Yr",
        "us2s10s": "10 Yr-2 Yr",
    }
    provider_symbol = provider_symbols.get(asset_key, spec["canonical_symbol"])
    value = 4.2 if kind in {"rate_level", "spread"} else 100.0
    row = {"timestamp": "2026-08-14T00:00:00Z", "open": value, "high": value, "low": value, "close": value, "volume": 0}
    if kind in {"rate_level", "spread"}:
        row["value"] = value
    return {
        "schema_version": CANDLE_RESPONSE_SCHEMA_VERSION,
        "weekly_contract_version": WEEKLY_CANDLE_CONTRACT_VERSION,
        "asset_key": asset_key,
        "canonical_symbol": spec["canonical_symbol"],
        "asset_class": spec["asset_class"],
        "series_kind": kind,
        "semantic_role": spec["semantic_role"],
        "timeframe": "weekly",
        "unit": spec["unit"],
        "price_basis": spec["price_basis"],
        "status": "ready",
        "provider": "test_provider",
        "provider_symbol": provider_symbol,
        "source_mode": primary_source,
        "requested_source": primary_source,
        "selected_source": primary_source,
        "selection_reason": "requested_or_default",
        "attempted_sources": [primary_source],
        "cache_policy": "bypass",
        "quality_policy": "strict",
        "fallback_policy": spec.get("fallback_policy", "none"),
        "fallback_sources": fallback_sources,
        "quality_flags": [],
        "is_synthetic": False,
        "served_from": "upstream",
        "fresh": True,
        "latest_timestamp": row["timestamp"],
        "age_seconds": 0,
        "max_age_seconds": 90,
        "execution_venue": False,
        "source_identity": {
            "provider": "test_provider",
            "provider_symbol": provider_symbol,
            "source_mode": primary_source,
            "run_id": f"run-{asset_key}",
        },
        "access_issues": [],
        "bars": [row],
    }


class WeeklyReportTest(unittest.TestCase):
    def test_build_produces_fixed_b_workbench_slots(self) -> None:
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking_fixture())
        self.assertEqual(len(report["cards"]), 17)
        self.assertEqual(len(report["chart_slots"]), 39)
        self.assertEqual(report["cards"][0]["asset_key"], "dxy")
        self.assertEqual(report["cards"][-1]["asset_key"], "silver")

    def test_chart_slots_bind_indicator_feature_context_and_axes(self) -> None:
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking_fixture())
        slot = report["chart_slots"][0]
        self.assertEqual(slot["feature"]["schema_version"], FEATURE_SCHEMA_VERSION)
        self.assertEqual(slot["feature"]["parameters"]["ema_span"], 50)
        self.assertEqual(slot["x_labels"][0]["label"], "08-14")
        self.assertEqual(slot["y_labels"][0]["value"], 99.0)
        self.assertIn("macd_histogram", slot["points"][0])

    def test_real_candle_responses_are_projected_for_standard_kline(self) -> None:
        responses = {
            "gold:weekly": candle_response_fixture("gold"),
            "us2y:weekly": candle_response_fixture("us2y", series_kind="rate_level"),
        }
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking_fixture(), candle_responses=responses)
        gold = next(slot for slot in report["chart_slots"] if slot["slot_id"] == "gold:weekly")
        us2y = next(slot for slot in report["chart_slots"] if slot["slot_id"] == "us2y:weekly")
        self.assertEqual(gold["standard_kline"]["render_mode"], "candles")
        self.assertEqual(gold["standard_kline"]["renderer"].split("@")[0], "zinan92/standard-kline")
        self.assertEqual(us2y["standard_kline"]["render_mode"], "line")
        self.assertEqual(us2y["standard_kline"]["unit"], "percent")
        self.assertEqual(us2y["renderer_options"]["renderMode"], "line")

    def test_invalid_candle_response_does_not_fall_back_to_custom_chart(self) -> None:
        with self.assertRaisesRegex(WeeklyReportError, "standard_kline_response_invalid:gold:weekly"):
            build_weekly_report(
                source_fixture(),
                analyses_fixture(),
                ranking_fixture(),
                candle_responses={"gold:weekly": {"status": "ready", "bars": []}},
            )

    def test_summary_renders_position_and_structure_when_compiled(self) -> None:
        analyses = analyses_fixture()
        analyses["gold"]["position"] = {"state": "high", "text": "位置：高位。", "evidence_ids": ["e:gold:w"]}
        analyses["gold"]["structure"] = {"state": "continuation", "bias": "bullish", "text": "结构：趋势延续。", "evidence_ids": ["e:gold:w", "feature:fixture:gold"], "timeframes": {"daily": {"evidence_ids": ["e:gold:d", "feature:fixture:gold"]}}}
        report = build_weekly_report(source_fixture(), analyses, ranking_fixture())
        html = render_weekly_html(report)
        markdown = render_weekly_markdown(report)
        self.assertIn("summary-dimensions", html)
        self.assertIn("赔率尚未形成", html)
        self.assertIn("位置：高位。", html)
        self.assertIn("这意味着什么 · 机制解释", html)
        self.assertIn("**位置**：位置：高位。", markdown)
        self.assertIn("**赔率**：赔率尚未形成", markdown)
        self.assertIn("**这意味着什么（机制解释）**：通常由宏观驱动", markdown)

    def test_rendered_html_has_adjacent_analysis_no_ops_surface_and_b_order(self) -> None:
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking_fixture())
        html = render_weekly_html(report)
        self.assertEqual(html.count('data-asset-nav="'), 17)
        self.assertEqual(html.count("<img "), 0)
        self.assertNotIn("parameter_surface", html)
        self.assertNotIn("missing_inputs", html)
        self.assertLess(html.index("data-asset-nav"), html.index("本周机会排序"))
        self.assertIn("模型生成、未经人工复核", html)
        self.assertNotIn("StandardKline.StandardKlineChart", html)
        self.assertNotIn("setDatafeedResponse", html)
        self.assertNotIn("standard-kline-mount", html)
        self.assertNotIn("lightweight-charts", html)
        self.assertIn("data-timeframes=", html)
        self.assertIn('data-summary-order="位置,结构,赔率,多周期结论,机制解释"', html)
        self.assertNotIn(">validated<", html)
        self.assertNotIn("· wait</li>", html)
        self.assertNotIn("WEEK_END", html)
        self.assertIn("单位：基点", html)

    def test_static_reader_renders_snapshot_images_and_prefixes(self) -> None:
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking_fixture())
        for slot in report["chart_slots"]:
            token = slot["slot_id"].replace(":", "-")
            slot["snapshot"] = {
                "snapshot_id": f"market-regime-weekly-chart-snapshot:{token}",
                "asset": {"path": f"snapshots/{token}.png", "sha256": "a" * 64},
            }
        for card in report["cards"]:
            for slot in card["chart_slots"]:
                token = slot["slot_id"].replace(":", "-")
                slot["snapshot"] = {
                    "snapshot_id": f"market-regime-weekly-chart-snapshot:{token}",
                    "asset": {"path": f"snapshots/{token}.png", "sha256": "a" * 64},
                }
        html = render_weekly_html(report)
        archive_html = render_weekly_html(report, snapshot_prefix="../../snapshots/")
        self.assertEqual(html.count("<img "), 39)
        self.assertIn('src="snapshots/dxy-weekly.png"', html)
        self.assertIn('src="../../snapshots/dxy-weekly.png"', archive_html)
        self.assertIn('alt="美元指数｜周线 K 线图"', html)
        self.assertNotIn("data-chart=", html)
        self.assertNotIn("lightweight-charts", html)
        self.assertNotIn("StandardKlineChart", html)

    def test_opportunity_projection_renders_rank_order_and_display_names(self) -> None:
        ranking = ranking_fixture()
        ranking["ordered_assets"] = list(reversed(ranking["ordered_assets"]))
        for index, row in enumerate(ranking["ordered_assets"], start=1):
            row["rank"] = index
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking)
        html_tail = render_weekly_html(report).split('<section class="ranking">', 1)[1].split('</section>', 1)[0]
        markdown_tail = render_weekly_markdown(report).split("## 本周机会排序", 1)[1]
        self.assertLess(html_tail.index("白银"), html_tail.index("美元指数"))
        self.assertLess(markdown_tail.index("白银"), markdown_tail.index("美元指数"))
        self.assertNotIn("dxy", html_tail)
        self.assertNotIn("us_dividend", markdown_tail)

    def test_invalid_ranking_is_rendered_as_opportunity_list(self) -> None:
        ranking = {"generation_status": "ranking_unavailable", "failure_code": "provider_error", "ordered_assets": []}
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking)
        html = render_weekly_html(report)
        markdown = render_weekly_markdown(report)
        self.assertIn("本周机会清单", html)
        self.assertIn("## 本周机会清单", markdown)
        self.assertNotIn("本周机会排序", html)
        self.assertNotIn("本周机会排序", markdown)

    def test_partial_ranking_with_unavailable_assets_is_not_called_a_ranking(self) -> None:
        ranking = ranking_fixture()
        ranking["ordered_assets"][0].update({"status": "unavailable", "rank": None, "evidence_ids": []})
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking)
        self.assertIn("本周机会清单", render_weekly_html(report))
        self.assertIn("## 本周机会清单", render_weekly_markdown(report))

    def test_ranking_provider_failure_preserves_seventeen_availability_rows(self) -> None:
        ranking = {"generation_status": "ranking_unavailable", "failure_code": "provider_error", "ordered_assets": []}
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking)
        html = render_weekly_html(report)
        ranking_section = html.split('<section class="ranking">', 1)[1].split('</section>', 1)[0]
        self.assertEqual(ranking_section.count("<li>"), 17)
        self.assertIn("美元指数", ranking_section)

    def test_report_binds_source_snapshot_id(self) -> None:
        source = source_fixture()
        source["snapshot_id"] = "market-regime-weekly-source:" + ("a" * 64)
        report = build_weekly_report(source, analyses_fixture(), ranking_fixture())
        self.assertEqual(report["source_snapshot_id"], source["snapshot_id"])
        self.assertEqual(report["identity_core"]["source_snapshot_id"], source["snapshot_id"])

    def test_unknown_ranking_key_falls_back_to_canonical_availability_list(self) -> None:
        ranking = ranking_fixture()
        ranking["ordered_assets"][0]["asset_key"] = "unexpected_key"
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking)
        html_tail = render_weekly_html(report).split('<section class="ranking">', 1)[1].split('</section>', 1)[0]
        self.assertNotIn("unexpected_key", html_tail)
        self.assertIn("美元指数", html_tail)

    def test_markdown_keeps_the_same_asset_count_and_disclosure(self) -> None:
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking_fixture())
        markdown = render_weekly_markdown(report)
        self.assertEqual(markdown.count("### "), 17)
        self.assertIn("周末日期：2026-08-14", markdown)
        self.assertNotIn("Context", markdown)
        self.assertIn("本周机会排序", markdown)
        self.assertIn("美元指数：等待", markdown)
        self.assertIn("本地评估", markdown)

    def test_missing_analysis_keeps_card_but_marks_unavailable(self) -> None:
        analyses = analyses_fixture()
        analyses.pop("gold")
        report = build_weekly_report(source_fixture(), analyses, ranking_fixture())
        gold = next(item for item in report["cards"] if item["asset_key"] == "gold")
        self.assertEqual(gold["analysis_status"], "analysis_unavailable")
        self.assertEqual(gold["analysis"]["summary"]["order"], ["position", "structure", "odds", "synthesis", "theoretical_implication"])
        self.assertEqual(len(report["chart_slots"]), 39)

    def test_validated_analysis_without_position_structure_is_not_published_as_validated(self) -> None:
        analyses = analyses_fixture()
        analyses["gold"].pop("position")
        analyses["gold"].pop("structure")
        report = build_weekly_report(source_fixture(), analyses, ranking_fixture())
        gold = next(card for card in report["cards"] if card["asset_key"] == "gold")
        self.assertEqual(gold["analysis_status"], "analysis_unavailable")
        self.assertEqual(gold["analysis"]["failure_code"], "position_structure_missing")

    def test_malformed_theory_is_not_published_as_validated(self) -> None:
        analyses = analyses_fixture()
        analyses["gold"]["theoretical_implication"] = {
            "text": "当前美元一定会上涨。",
            "evidence_ids": ["mechanism:gold:drivers"],
            "claim_type": "theoretical_mechanism",
        }
        report = build_weekly_report(source_fixture(), analyses, ranking_fixture())
        gold = next(card for card in report["cards"] if card["asset_key"] == "gold")
        self.assertEqual(gold["analysis_status"], "analysis_unavailable")

    def test_missing_analysis_identity_is_not_published_as_validated(self) -> None:
        analyses = analyses_fixture()
        analyses["gold"].pop("analysis_id")
        report = build_weekly_report(source_fixture(), analyses, ranking_fixture())
        gold = next(card for card in report["cards"] if card["asset_key"] == "gold")
        self.assertEqual(gold["analysis_status"], "analysis_unavailable")

    def test_odds_timeframe_must_match_its_structure_evidence(self) -> None:
        analyses = analyses_fixture()
        analyses["gold"]["odds"]["timeframe"] = "weekly"
        report = build_weekly_report(source_fixture(), analyses, ranking_fixture())
        gold = next(card for card in report["cards"] if card["asset_key"] == "gold")
        self.assertEqual(gold["analysis_status"], "analysis_unavailable")

    def test_unknown_source_key_fails_closed(self) -> None:
        source = source_fixture()
        source["series"]["unknown"] = source["series"]["gold"]
        with self.assertRaisesRegex(WeeklyReportError, "source_asset_set_invalid"):
            build_weekly_report(source, analyses_fixture(), ranking_fixture())


if __name__ == "__main__":
    unittest.main()
