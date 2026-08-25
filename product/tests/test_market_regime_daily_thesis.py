from __future__ import annotations

from pathlib import Path
import copy
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_analysis import build_daily_analysis_bundle  # noqa: E402
from data_core.market_regime_llm_provider import ProviderFallbackError  # noqa: E402
from data_core.market_regime_daily_thesis import (  # noqa: E402
    DailyThesisDeliveryStore,
    DailyThesisError,
    build_daily_thesis_request,
    compile_daily_thesis,
    render_daily_markdown,
    DeepSeekDailyThesisProvider,
    _local_report_date,
    validate_daily_thesis,
)
from product.tests.test_market_regime_daily_analysis import _provider, _source_bundle  # noqa: E402


def _analysis_bundle() -> dict:
    return build_daily_analysis_bundle(_source_bundle(), provider_factory=lambda _request: _provider)


def _with_daily_snapshot(bundle: dict) -> dict:
    """Attach one independently hashed snapshot reference to the fixture bundle."""

    value = copy.deepcopy(bundle)
    image = b"verified-png-fixture"
    value["assets"][0]["snapshots"] = {
        "daily": {
            "schema_version": "market-regime-daily-chart-snapshot-v1",
            "snapshot_id": "market-regime-daily-chart-snapshot:fixture",
            "asset": {"path": "snapshots/dxy.png", "sha256": hashlib.sha256(image).hexdigest()},
        }
    }
    canonical = lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity_core = {**value["identity_core"], "assets_sha256": hashlib.sha256(canonical(value["assets"]).encode()).hexdigest()}
    value["identity_core"] = identity_core
    value["bundle_id"] = "market-regime-daily-analysis:" + hashlib.sha256(canonical(identity_core).encode()).hexdigest()
    return value


def _thesis_provider(request):
    evidence = request["evidence_ids"][:2]
    statement = lambda text: {"text": text, "evidence_ids": evidence}
    return {
        "generation_status": "model_generated_unreviewed",
        "posture": "wait",
        "headline": statement("高位资产动能分化，等待更清晰的方向选择。"),
        "what_happened": statement("风险资产和实物资产没有形成同向共振。"),
        "world_model": statement("市场更像处于高位再定价，而不是全面进攻或全面撤退。"),
        "leadership": statement("当前应优先观察相对强弱和周期一致性。"),
        "laggards": statement("落后资产的短线结构仍未完成修复。"),
        "capital_migration": statement("价格相对关系显示资金可能在风险资产与防守资产之间轮动。"),
        "theoretical_mechanism": {"text": "通常反映风险偏好变化，但也可能由资产自身供需驱动。", "evidence_ids": ["mechanism:dxy:drivers"], "claim_type": "theoretical_mechanism"},
        "watchpoints": [statement("观察风险资产日线结构是否重新转强。"), statement("观察贵金属短线结构是否继续保持。")],
        "actions": [statement("以等待确认和局部参与为主，不全面追高。")],
        "falsifiers": [statement("若多数资产重新同步走强，当前等待判断失效。")],
    }


class DailyThesisTests(unittest.TestCase):
    def test_daily_ops_metadata_is_confined_to_source_status_footer(self) -> None:
        bundle = _with_daily_snapshot(_analysis_bundle())
        thesis = compile_daily_thesis(bundle, _thesis_provider)
        markdown = render_daily_markdown({**thesis, "cutoff_at": bundle["cutoff_at"]}, bundle)
        body, footer = markdown.split("## 来源与状态", 1)
        self.assertNotIn("generation_status:", markdown)
        self.assertNotIn("数据覆盖：", body)
        self.assertIn("数据源状态", footer)
        self.assertIn("单资产解释", footer)

    def test_dual_provider_failure_is_explicitly_disclosed(self) -> None:
        bundle = copy.deepcopy(_analysis_bundle())
        first = bundle["assets"][0]["analysis"]
        first["generation_status"] = "analysis_unavailable"
        first["output"] = {
            "generation_status": "analysis_unavailable",
            "deterministic": first["deterministic"],
            "provider_status": {
                "both_failed": True,
                "primary_failure": "http_402",
                "fallback_failure": "timeout",
            },
        }
        canonical = lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        identity_core = {**bundle["identity_core"], "assets_sha256": hashlib.sha256(canonical(bundle["assets"]).encode()).hexdigest()}
        bundle["identity_core"] = identity_core
        bundle["bundle_id"] = "market-regime-daily-analysis:" + hashlib.sha256(canonical(identity_core).encode()).hexdigest()
        thesis = compile_daily_thesis(bundle, None)
        markdown = render_daily_markdown({**thesis, "cutoff_at": bundle["cutoff_at"]}, bundle)
        self.assertIn("DeepSeek 与 Codex CLI 均未生成解释", markdown)
        self.assertIn("单资产模型失败披露", markdown)

    def test_daily_markdown_places_snapshot_before_period_explanation(self) -> None:
        bundle = _with_daily_snapshot(_analysis_bundle())
        thesis = compile_daily_thesis(bundle, _thesis_provider)
        markdown = render_daily_markdown({**thesis, "cutoff_at": bundle["cutoff_at"]}, bundle)
        image_index = markdown.index("![dxy｜日线 K 线图](snapshots/dxy.png)")
        text_index = markdown.index("**日线**：", image_index)
        self.assertLess(image_index, text_index)

    def test_daily_html_renders_snapshot_image_element(self) -> None:
        from data_core.market_regime_daily_thesis import render_daily_html

        bundle = _with_daily_snapshot(_analysis_bundle())
        thesis = compile_daily_thesis(bundle, _thesis_provider)
        markdown = render_daily_markdown({**thesis, "cutoff_at": bundle["cutoff_at"]}, bundle)
        html_text = render_daily_html(markdown)
        self.assertIn('<img src="snapshots/dxy.png"', html_text)

    def test_delivery_copies_snapshot_into_markdown_archive(self) -> None:
        bundle = _with_daily_snapshot(_analysis_bundle())
        thesis = compile_daily_thesis(bundle, _thesis_provider)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_snapshot = root / "output" / "snapshots" / "dxy.png"
            output_snapshot.parent.mkdir(parents=True)
            output_snapshot.write_bytes(b"verified-png-fixture")
            store = DailyThesisDeliveryStore(runtime_root=root / "runtime", output_root=root / "output", archive_root=root / "archive")
            receipt = store.publish(thesis, bundle)
            archive_snapshot = root / "archive" / "snapshots" / "dxy.png"
            self.assertEqual(archive_snapshot.read_bytes(), output_snapshot.read_bytes())
            self.assertEqual(receipt["archive"]["sha256"], hashlib.sha256(Path(receipt["archive"]["path"]).read_bytes()).hexdigest())
            latest_html = (root / "output" / "latest.html").read_text(encoding="utf-8")
            self.assertIn('class="asset-pane reader-asset"', latest_html)
            self.assertIn('src="snapshots/dxy.png"', latest_html)

    def test_report_date_uses_shanghai_calendar(self) -> None:
        self.assertEqual(_local_report_date("2026-08-24T15:59:59Z"), "2026-08-24")
        self.assertEqual(_local_report_date("2026-08-24T16:00:00Z"), "2026-08-25")

    def test_request_contains_only_asset_analysis_and_evidence(self) -> None:
        bundle = _analysis_bundle()
        request = build_daily_thesis_request(bundle)
        self.assertEqual(len(request["assets"]), 19)
        self.assertNotIn("finance_newsletter", request)
        self.assertTrue(request.get("truth_boundary", {}).get("finance_newsletter_input") is False)

    def test_deepseek_provider_retries_with_validator_feedback(self) -> None:
        bundle = _analysis_bundle()
        request = build_daily_thesis_request(bundle)
        from data_core.market_regime_daily_thesis import _evidence_ids
        request["evidence_ids"] = sorted(_evidence_ids(bundle))
        valid = _thesis_provider(request)
        invalid = dict(valid)
        invalid["headline"] = {"text": "坏输出", "evidence_ids": []}
        with patch("deepseek_writer.call_structured_deepseek", side_effect=[(invalid, {"provider": "test"}), (valid, {"provider": "test"})]) as call:
            output, _receipt = DeepSeekDailyThesisProvider("/tmp/unused-key")(request)
        self.assertEqual(output["generation_status"], "model_generated_unreviewed")
        self.assertEqual(call.call_count, 2)

    def test_compiles_and_validates_cross_asset_thesis(self) -> None:
        bundle = _analysis_bundle()
        thesis = compile_daily_thesis(bundle, _thesis_provider)
        self.assertEqual(thesis["generation_status"], "model_generated_unreviewed")
        self.assertEqual(thesis["posture"], "wait")
        validate_daily_thesis(thesis["output"], thesis["request"])

    def test_provider_failure_is_rendered_as_unknown_not_old_thesis(self) -> None:
        bundle = _analysis_bundle()
        thesis = compile_daily_thesis(bundle, None)
        markdown = render_daily_markdown({**thesis, "cutoff_at": bundle["cutoff_at"]}, bundle)
        self.assertIn("本期综合解释尚未生成", markdown)

    def test_both_provider_failure_is_typed_with_provider_status(self) -> None:
        bundle = _analysis_bundle()
        thesis = compile_daily_thesis(
            bundle,
            lambda _request: (_ for _ in ()).throw(ProviderFallbackError("http_402", "timeout")),
        )
        self.assertEqual(thesis["generation_status"], "thesis_unavailable")
        self.assertEqual(thesis["failure_code"], "both_providers_failed")
        self.assertEqual(thesis["provider_status"]["fallback_failure"], "timeout")

    def test_direct_money_flow_claim_is_rejected(self) -> None:
        bundle = _analysis_bundle()
        def bad_provider(request):
            result = _thesis_provider(request)
            result["capital_migration"] = {"text": "资金正在流入黄金。", "evidence_ids": request["evidence_ids"][:1]}
            return result
        thesis = compile_daily_thesis(bundle, bad_provider)
        self.assertEqual(thesis["generation_status"], "thesis_unavailable")

    def test_delivery_archives_markdown_without_overwriting_weekly(self) -> None:
        bundle = _analysis_bundle()
        thesis = compile_daily_thesis(bundle, _thesis_provider)
        unsafe = dict(thesis)
        unsafe["thesis_id"] = "market-regime-daily-thesis:../../escape"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(DailyThesisError):
                DailyThesisDeliveryStore(runtime_root=root / "runtime", output_root=root / "output", archive_root=root / "archive").publish(unsafe, bundle)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = DailyThesisDeliveryStore(runtime_root=root / "runtime", output_root=root / "output", archive_root=root / "archive").publish(thesis, bundle)
            self.assertTrue(Path(receipt["archive"]["path"]).is_file())
            self.assertTrue((root / "output" / "latest.md").is_file())
            self.assertTrue((root / "output" / "latest.html").is_file())
            latest = DailyThesisDeliveryStore(runtime_root=root / "runtime", output_root=root / "output", archive_root=root / "archive").latest()
            self.assertEqual(latest["delivery_id"], receipt["delivery_id"])


if __name__ == "__main__":
    unittest.main()
