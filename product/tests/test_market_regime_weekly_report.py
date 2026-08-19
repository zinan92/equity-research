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


def source_fixture() -> dict:
    series = {}
    for index, key in enumerate(WEEKLY_KEYS):
        point = {"date": "2026-08-14", "open": 100 + index, "high": 101 + index, "low": 99 + index, "close": 100.5 + index}
        item = {"key": key, "series_kind": "rate_level" if key in {"us2y", "us10y", "us2s10s"} else "price", "status": "complete", "weekly_bin_count": 1, "points": [{"date": "2026-08-14", "value": 4.2}] if key in {"us2y", "us10y", "us2s10s"} else [point], "quality": "fresh", "data_kind": "fixture", "canonical_symbol": key, "unit": "basis points" if key == "us2s10s" else "index points", "source_identity": {"provider": "fixture", "key": key}}
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
        self.assertEqual(html.count('data-chart="'), 39)
        self.assertNotIn("parameter_surface", html)
        self.assertNotIn("missing_inputs", html)
        self.assertLess(html.index("data-asset-nav"), html.index("本周机会排序"))
        self.assertIn("模型生成、未经人工复核", html)
        self.assertIn("drawLine('ema50'", html)
        self.assertIn("macd_histogram", html)
        self.assertIn("data-timeframes=", html)
        self.assertIn("单位：基点", html)

    def test_markdown_keeps_the_same_asset_count_and_disclosure(self) -> None:
        report = build_weekly_report(source_fixture(), analyses_fixture(), ranking_fixture())
        markdown = render_weekly_markdown(report)
        self.assertEqual(markdown.count("### "), 17)
        self.assertIn("WEEK_END：2026-08-14", markdown)
        self.assertIn("本周机会排序", markdown)
        self.assertIn("本地评估", markdown)

    def test_missing_analysis_keeps_card_but_marks_unavailable(self) -> None:
        analyses = analyses_fixture()
        analyses.pop("gold")
        report = build_weekly_report(source_fixture(), analyses, ranking_fixture())
        gold = next(item for item in report["cards"] if item["asset_key"] == "gold")
        self.assertEqual(gold["analysis_status"], "analysis_unavailable")
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
