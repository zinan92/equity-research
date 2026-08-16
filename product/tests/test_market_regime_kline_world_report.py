from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import tempfile
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_kline_world_context import KlineWorldContextStore  # noqa: E402
from data_core.market_regime_kline_world_model import KlineWorldModelStore  # noqa: E402
from data_core.market_regime_kline_world_report import (  # noqa: E402
    KlineWorldReportError,
    KlineWorldReportStore,
    REPORT_ID_PREFIX,
    build_world_report,
    render_html,
    render_markdown,
    validate_world_report,
)
from product.tests.test_market_regime_kline_world_model import (  # noqa: E402
    FakeProvider,
    fixture_context,
    valid_output,
)


NOW = datetime(2026, 8, 16, 0, 20, tzinfo=timezone.utc)


def authorities(root: Path, *, posture: str = "wait", unavailable: bool = False):
    context = fixture_context()
    context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
    context_store.publish(context)
    model_store = KlineWorldModelStore(context_store, root / "model")
    output = valid_output(context)
    output["regime"]["posture"] = posture
    provider = None if unavailable else FakeProvider(output)
    model = model_store.compile_latest(provider)
    return context, model, context_store, model_store


class KlineWorldReportTests(unittest.TestCase):
    def test_attack_wait_defense_share_one_hierarchy_and_distinct_state(self) -> None:
        for posture, label in (("attack", "进攻"), ("wait", "等待"), ("defense", "防守")):
            with self.subTest(posture=posture), tempfile.TemporaryDirectory() as temporary:
                context, model, _, _ = authorities(Path(temporary), posture=posture)
                report = build_world_report(
                    context=context,
                    world_model=model,
                    generated_at=NOW,
                    allow_fixture=True,
                )
                html = render_html(report)
                self.assertEqual(report["posture"], posture)
                self.assertEqual(report["posture_zh"], label)
                self.assertIn(f'data-posture="{posture}"', html)
                self.assertIn(f"<h1>{label}</h1>", html)
                self.assertEqual(len(report["cross_section"]), 17)
                self.assertEqual(len(report["relationships"]), 12)
                self.assertEqual(len(report["charts"]), 17)
                self.assertEqual(html.count("data-chart="), 17)
                self.assertEqual(html.count("data-relative="), 12)

    def test_north_star_reading_order_and_advice_boundary_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary), posture="defense")
            report = build_world_report(
                context=context,
                world_model=model,
                generated_at=NOW,
                allow_fixture=True,
            )
            html = render_html(report)
            headings = [
                "资金可能正在从哪里，流向哪里？",
                "这套世界模型是怎样传导的？",
                "在这个世界模型下，怎样交易？",
                "17 个市场现在分别在说什么？",
                "12 组相对领导关系",
                "当前解释哪里不一致？",
                "哪两件事会推翻当前世界模型？",
                "17 张完成日线证据",
            ]
            positions = [html.index(value) for value in headings]
            self.assertEqual(positions, sorted(positions))
            self.assertIn("本页包含市场层面的交易建议", html)
            self.assertIn("系统不会自动执行交易", html)
            self.assertNotIn("不是投资建议", html)
            self.assertNotIn("禁止交易建议", html)
            self.assertTrue(report["truth_boundary"]["contains_investment_advice"])
            self.assertFalse(report["truth_boundary"]["automatic_execution_eligible"])
            self.assertGreaterEqual(len(report["trade_plan"]), 1)

    def test_every_model_object_discloses_resolvable_citations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            report = build_world_report(
                context=context,
                world_model=model,
                generated_at=NOW,
                allow_fixture=True,
            )
            valid_ids = {
                str(reference)
                for item in context["series"]
                for reference in (item.get("series_id"), item.get("evidence_id"))
                if reference
            } | {str(item["relationship_id"]) for item in context["relationships"]}
            sections = [report["world_model"], report["regime"]]
            for name in ("flow_map", "transmission_chain", "trade_plan", "contradictions", "falsifiers"):
                sections.extend(report[name])
            for row in sections:
                self.assertEqual(
                    [item["reference_id"] for item in row["citations"]],
                    row["evidence_ids"],
                )
                self.assertTrue(set(row["evidence_ids"]).issubset(valid_ids))
            html = render_html(report)
            self.assertGreater(html.count('class="cite"'), 10)
            self.assertIn("showModal()", html)

    def test_unavailable_model_keeps_same_context_evidence_without_stale_advice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary), unavailable=True)
            report = build_world_report(
                context=context,
                world_model=model,
                generated_at=NOW,
                allow_fixture=True,
            )
            self.assertEqual(report["generation_status"], "interpretation_unavailable")
            self.assertEqual(report["posture"], "unknown")
            self.assertEqual(report["flow_map"], [])
            self.assertEqual(report["transmission_chain"], [])
            self.assertEqual(report["trade_plan"], [])
            self.assertEqual(report["falsifiers"], [])
            self.assertEqual(len(report["charts"]), 17)
            self.assertFalse(report["truth_boundary"]["contains_investment_advice"])
            html = render_html(report)
            self.assertIn("本期解释未通过验证", html)
            self.assertNotIn('class="trade-row"', html)
            self.assertIn("不会复用旧内容", html)

    def test_report_store_replays_exact_json_html_markdown_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context, model, context_store, model_store = authorities(root)
            store = KlineWorldReportStore(
                context_store,
                model_store,
                root / "report",
                root / "output",
                allow_fixture=True,
            )
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

    def test_coherently_rebound_report_projection_cannot_disagree_with_s2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            report = build_world_report(
                context=context,
                world_model=model,
                generated_at=NOW,
                allow_fixture=True,
            )
            tampered = deepcopy(report)
            tampered["world_model"]["synthesis"] = "被一致重绑但不来自 S2 的解释。"
            tampered["identity_core"]["world_model"]["synthesis"] = tampered["world_model"]["synthesis"]
            from data_core.market_regime_kline_world_report import _digest

            tampered["report_id"] = REPORT_ID_PREFIX + _digest(tampered["identity_core"])
            with self.assertRaisesRegex(KlineWorldReportError, "upstream_projection"):
                validate_world_report(
                    tampered,
                    context=context,
                    world_model=model,
                    allow_fixture=True,
                )

    def test_output_hash_tamper_fails_and_prior_state_remains_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, context_store, model_store = authorities(root)
            store = KlineWorldReportStore(
                context_store,
                model_store,
                root / "report",
                root / "output",
                allow_fixture=True,
            )
            state = store.compile_latest(generated_at=NOW)
            html_path = root / "output" / state["html"]["path"]
            html_path.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(KlineWorldReportError, "html_hash"):
                store.latest()

    def test_fixture_report_is_rejected_without_explicit_test_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, model, _, _ = authorities(Path(temporary))
            with self.assertRaisesRegex(KlineWorldReportError, "fixture_context"):
                build_world_report(
                    context=context,
                    world_model=model,
                    generated_at=NOW,
                )


if __name__ == "__main__":
    unittest.main()
