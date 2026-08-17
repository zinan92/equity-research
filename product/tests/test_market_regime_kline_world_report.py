from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_kline_macro_analysis import KlineWorldModelStore  # noqa: E402
from data_core.market_regime_kline_world_context import (  # noqa: E402
    KlineWorldContextStore,
    SERIES_ORDER,
    build_kline_world_context,
)
from data_core.market_regime_kline_world_report import (  # noqa: E402
    KlineWorldReportError,
    KlineWorldReportStore,
    REPORT_ID_PREFIX,
    _series_projection,
    build_world_report,
    render_html,
    render_markdown,
    validate_world_report,
)
from product.tests.test_market_regime_kline_macro_analysis import (  # noqa: E402
    FakeProvider,
    fixture_context,
    valid_output,
)
from product.tests.test_market_regime_kline_world_context import inputs  # noqa: E402


NOW = datetime(2026, 8, 16, 0, 20, tzinfo=timezone.utc)


def authorities(root: Path, *, unavailable: bool = False):
    context = fixture_context()
    context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
    context_store.publish(context)
    model_store = KlineWorldModelStore(context_store, root / "model")
    provider = None if unavailable else FakeProvider(valid_output(context))
    model = model_store.compile_latest(provider)
    return context, model, context_store, model_store


class KlineWorldReportTests(unittest.TestCase):
    def test_macro_report_keeps_exact_chart_and_cross_section_projections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            report = build_world_report(context=context, world_model=model, generated_at=NOW, allow_fixture=True)
            by_key = {row["key"]: row for row in context["series"]}
            expected_rows, expected_charts = [], []
            for key in SERIES_ORDER:
                row, chart = _series_projection(by_key[key])
                expected_rows.append(row)
                expected_charts.append(chart)
            self.assertEqual(report["cross_section"], expected_rows)
            self.assertEqual(report["charts"], expected_charts)
            self.assertEqual(len(report["relationships"]), 12)
            self.assertEqual(report["posture"], "no_view")
            self.assertEqual(
                [row["parameter"] for row in report["parameter_surface"]],
                [
                    "AS_OF",
                    "RISK_BUDGET",
                    "LONG_GATE",
                    "DISPERSION",
                    "SECTOR_PRIOR",
                    "BLACKOUT",
                    "CONFIDENCE",
                    "DATA_COVERAGE",
                ],
            )
            html = render_html(report)
            self.assertEqual(html.count("data-chart="), 17)
            self.assertEqual(html.count("data-relative="), 12)

    def test_candles_remain_green_hollow_up_and_red_filled_down(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            report = build_world_report(context=context, world_model=model, generated_at=NOW, allow_fixture=True)
            html = render_html(report)
            self.assertIn("if(cl>=o){c.strokeStyle=UP;c.strokeRect", html)
            self.assertIn("else{c.fillStyle=DOWN;c.fillRect", html)
            self.assertNotIn("c.fillStyle=color;c.lineWidth=1", html)

    def test_parameter_first_reading_order_replaces_old_analysis_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            report = build_world_report(context=context, world_model=model, generated_at=NOW, allow_fixture=True)
            html = render_html(report)
            headings = [
                "17 张完成日线证据",
                "宏观参数：同一份可回放记录",
                "哪些是洞察，哪些只是观察？",
                "哪些关键数据还没有拿到？",
                "17 个市场与 12 组相对领导关系",
            ]
            positions = [html.index(value) for value in headings]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn("资金可能正在从哪里", html)
            self.assertNotIn("世界模型如何传导，以及怎样交易", html)
            self.assertIn("RISK_BUDGET", html)
            self.assertIn("LONG_GATE", html)
            self.assertIn("本日不提供方向观点", html)
            self.assertIn("模型生成、未经人工复核", html)
            self.assertIn("系统不会自动执行交易", html)
            self.assertFalse(report["truth_boundary"]["individual_security_advice"])
            self.assertFalse(report["truth_boundary"]["automatic_execution_eligible"])
            self.assertEqual(report["macro_parameters"]["long_gate"], "CLOSED")
            self.assertEqual(report["insights"], [])
            self.assertEqual(len(report["data_ledger"]), 9)
            markdown = render_markdown(report)
            for heading in (
                "## 17 张完成日线证据",
                "## 宏观参数：同一份可回放记录",
                "## 洞察与观察",
                "## 数据台账",
                "## 17 个市场与 12 组相对领导关系",
            ):
                self.assertIn(heading, markdown)

    def test_one_parameter_surface_and_actual_dates_are_visible_in_both_formats(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            daily, macro, pack, bitcoin = inputs()
            shanghai = next(
                item
                for item in daily["instruments"]
                if item["instrument"]["key"] == "shanghai"
            )
            prior = shanghai["bars"][-1]
            shanghai["bars"].append(
                {
                    "date": "2026-08-17",
                    "open": prior["close"] + 9.5,
                    "high": prior["close"] + 11.0,
                    "low": prior["close"] + 9.0,
                    "close": prior["close"] + 10.0,
                    "volume": 999999,
                }
            )
            shanghai["bar_count"] = len(shanghai["bars"])
            shanghai["last_completed_session"] = "2026-08-17"
            context = build_kline_world_context(
                daily=daily,
                macro=macro,
                pack=pack,
                bitcoin=bitcoin,
                allow_fixture=True,
            )
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            model_store = KlineWorldModelStore(context_store, root / "model")
            model = model_store.compile_latest(FakeProvider(valid_output(context)))
            report = build_world_report(
                context=context,
                world_model=model,
                generated_at=NOW,
                allow_fixture=True,
            )
            html, markdown = render_html(report), render_markdown(report)
            self.assertEqual(len(report["parameter_surface"]), 8)
            for row in report["parameter_surface"]:
                self.assertIn(f'data-parameter-record="{row["parameter"]}"', html)
                self.assertIn(str(row["source"]), html)
                self.assertIn(str(row["rule"]), html)
                self.assertIn(f"| {row['parameter']} |", markdown)
                self.assertIn(str(row["source"]), markdown)
                self.assertIn(str(row["rule"]), markdown)
            self.assertIn("实际最新 2026-08-17 · ahead_of_as_of · 丢弃 1 行", html)
            self.assertIn("| 上证指数 | 2026-08-14 | 2026-08-17 | ahead_of_as_of | 1 |", markdown)
            self.assertTrue(
                all(
                    chart["points"][-1]["date"] == report["parameter_surface"][0]["value"]
                    for chart in report["charts"]
                )
            )

    def test_analysis_citations_are_resolvable_and_missing_ids_are_disclosed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            report = build_world_report(context=context, world_model=model, generated_at=NOW, allow_fixture=True)
            valid_ids = {
                str(reference)
                for item in context["series"]
                for reference in (item.get("series_id"), item.get("evidence_id"))
                if reference
            } | {str(item["relationship_id"]) for item in context["relationships"]}
            sections = [report["world_model"], *report["parameter_basis"], *report["insights"], *report["observations"]]
            for row in sections:
                self.assertEqual([item["reference_id"] for item in row["citations"]], row["evidence_ids"])
                self.assertTrue(set(row["evidence_ids"]).issubset(valid_ids))
            self.assertTrue(any(row["missing_items"] for row in report["parameter_basis"]))
            html = render_html(report)
            self.assertGreaterEqual(html.count('class="cite"'), 5)
            self.assertIn("showModal()", html)

    def test_unavailable_model_keeps_current_charts_without_stale_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary), unavailable=True)
            report = build_world_report(context=context, world_model=model, generated_at=NOW, allow_fixture=True)
            self.assertEqual(report["generation_status"], "interpretation_unavailable")
            self.assertEqual(report["posture"], "unknown")
            self.assertEqual(report["macro_parameters"], {})
            self.assertEqual(report["parameter_basis"], [])
            self.assertEqual(report["insights"], [])
            self.assertEqual(report["observations"], [])
            self.assertEqual(len(report["charts"]), 17)
            html = render_html(report)
            self.assertIn("本期宏观分析未通过验证", html)
            self.assertIn("不会复用旧内容", html)

    def test_report_store_replays_exact_json_html_markdown_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context, model, context_store, model_store = authorities(root)
            store = KlineWorldReportStore(context_store, model_store, root / "report", root / "output", allow_fixture=True)
            state = store.compile_latest(generated_at=NOW)
            replay_state, replay = store.latest()
            self.assertEqual(replay_state, state)
            self.assertEqual(replay["context_id"], context["context_id"])
            self.assertEqual(replay["world_model_id"], model["world_model_id"])
            self.assertTrue(replay["report_id"].startswith(REPORT_ID_PREFIX))
            html = (root / "output" / state["html"]["path"]).read_text(encoding="utf-8")
            markdown = (root / "output" / state["markdown"]["path"]).read_text(encoding="utf-8")
            self.assertEqual(html, render_html(replay))
            self.assertEqual(markdown, render_markdown(replay))

    def test_historical_report_load_survives_context_and_model_advance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_context = fixture_context()
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(first_context)
            model_store = KlineWorldModelStore(context_store, root / "model")
            model_store.compile_latest(FakeProvider(valid_output(first_context)))
            store = KlineWorldReportStore(
                context_store,
                model_store,
                root / "report",
                root / "output",
                allow_fixture=True,
            )
            first_state = store.compile_latest(generated_at=NOW)
            first_bytes = (root / "output" / first_state["html"]["path"]).read_bytes()

            daily, macro, pack, bitcoin = inputs()
            sp500 = next(
                item for item in daily["instruments"] if item["instrument"]["key"] == "sp500"
            )
            sp500["bars"][-1]["close"] += 0.1
            sp500["bars"][-1]["high"] += 0.1
            second_context = build_kline_world_context(
                daily=daily,
                macro=macro,
                pack=pack,
                bitcoin=bitcoin,
                allow_fixture=True,
            )
            context_store.publish(second_context)
            model_store.compile_latest(FakeProvider(valid_output(second_context)))
            second_state = store.compile_latest(generated_at=NOW + timedelta(hours=1))
            self.assertNotEqual(first_state["report_id"], second_state["report_id"])

            replay_state, replay = store.load(first_state["report_id"])
            self.assertEqual(replay_state, first_state)
            self.assertEqual(replay["context_id"], first_context["context_id"])
            self.assertEqual(
                (root / "output" / replay_state["html"]["path"]).read_bytes(),
                first_bytes,
            )

    def test_coherently_rebound_report_projection_cannot_disagree_with_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            report = build_world_report(context=context, world_model=model, generated_at=NOW, allow_fixture=True)
            tampered = deepcopy(report)
            tampered["world_model"]["synthesis"] = "被一致重绑但不来自模型的解释。"
            tampered["identity_core"]["world_model"]["synthesis"] = tampered["world_model"]["synthesis"]
            from data_core.market_regime_kline_world_report import _digest
            tampered["report_id"] = REPORT_ID_PREFIX + _digest(tampered["identity_core"])
            with self.assertRaisesRegex(KlineWorldReportError, "upstream_projection"):
                validate_world_report(tampered, context=context, world_model=model, allow_fixture=True)

    def test_output_hash_tamper_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, context_store, model_store = authorities(root)
            store = KlineWorldReportStore(context_store, model_store, root / "report", root / "output", allow_fixture=True)
            state = store.compile_latest(generated_at=NOW)
            html_path = root / "output" / state["html"]["path"]
            html_path.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(KlineWorldReportError, "html_hash"):
                store.latest()

    def test_fixture_report_is_rejected_without_explicit_test_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            with self.assertRaisesRegex(KlineWorldReportError, "fixture_context"):
                build_world_report(context=context, world_model=model, generated_at=NOW)


if __name__ == "__main__":
    unittest.main()
