from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_analysis import build_daily_analysis_bundle  # noqa: E402
from data_core.market_regime_daily_thesis import (  # noqa: E402
    DailyThesisDeliveryStore,
    DailyThesisError,
    build_daily_thesis_request,
    compile_daily_thesis,
    render_daily_markdown,
    validate_daily_thesis,
)
from product.tests.test_market_regime_daily_analysis import _provider, _source_bundle  # noqa: E402


def _analysis_bundle() -> dict:
    return build_daily_analysis_bundle(_source_bundle(), provider_factory=lambda _request: _provider)


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
    def test_request_contains_only_asset_analysis_and_evidence(self) -> None:
        bundle = _analysis_bundle()
        request = build_daily_thesis_request(bundle)
        self.assertEqual(len(request["assets"]), 19)
        self.assertNotIn("finance_newsletter", request)
        self.assertTrue(request.get("truth_boundary", {}).get("finance_newsletter_input") is False)

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
        self.assertIn("综合 thesis 不可用", markdown)

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
            self.assertTrue(Path(receipt["archive_path"]).is_file())
            self.assertTrue((root / "output" / "latest.md").is_file())
            self.assertTrue((root / "output" / "latest.html").is_file())
            latest = DailyThesisDeliveryStore(runtime_root=root / "runtime", output_root=root / "output", archive_root=root / "archive").latest()
            self.assertEqual(latest["delivery_id"], receipt["delivery_id"])


if __name__ == "__main__":
    unittest.main()
