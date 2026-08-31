from __future__ import annotations

import sys
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_mechanisms import (  # noqa: E402
    MECHANISM_SCHEMA_VERSION,
    mechanism_for_asset,
    validate_theoretical_statement,
)
from data_core.market_regime_weekly_asset_analysis import build_asset_analysis_request  # noqa: E402
from product.tests.test_market_regime_weekly_asset_analysis import asset_snapshot  # noqa: E402


class WeeklyMechanismTest(unittest.TestCase):
    def test_catalog_covers_all_weekly_assets(self) -> None:
        from data_core.market_regime_weekly_source import WEEKLY_KEYS

        for key in WEEKLY_KEYS:
            catalog = mechanism_for_asset(key)
            self.assertEqual(catalog["schema_version"], MECHANISM_SCHEMA_VERSION)
            self.assertTrue(catalog["mechanism_ids"])
            self.assertTrue(catalog["drivers"])
            self.assertTrue(catalog["usual_consequences"])
            self.assertTrue(catalog["counter_case"])

    def test_asset_request_contains_only_its_own_mechanism_catalog(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        self.assertEqual(request["mechanism"]["asset_key"], "gold")
        self.assertTrue(request["mechanism"]["mechanism_ids"])
        self.assertNotIn("sp500", repr(request["mechanism"]))

    def test_theory_statement_requires_a_catalog_mechanism_id(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        allowed = set(request["mechanism"]["mechanism_ids"])
        valid = {"text": "黄金通常在实际利率下行或避险需求上升时获得支持，但危机初期现金需求可能改变这一传导。", "evidence_ids": [next(iter(allowed))], "claim_type": "theoretical_mechanism"}
        self.assertEqual(validate_theoretical_statement(valid, allowed), valid)
        invalid = {**valid, "evidence_ids": ["gold:weekly:1"]}
        with self.assertRaisesRegex(ValueError, "mechanism_evidence_required"):
            validate_theoretical_statement(invalid, allowed)

    def test_theory_statement_rejects_current_observation_claim_type(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        mechanism_id = request["mechanism"]["mechanism_ids"][0]
        invalid = {"text": "当前黄金一定会上涨。", "evidence_ids": [mechanism_id], "claim_type": "observed_fact"}
        with self.assertRaisesRegex(ValueError, "theory_claim_type_invalid"):
            validate_theoretical_statement(invalid, {mechanism_id})

    def test_theory_statement_allows_reader_facing_research_language(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        mechanism_id = request["mechanism"]["mechanism_ids"][0]
        texts = (
            "当前美元一定会上涨并实时压制比特币。",
            "Current gold will definitely rise.",
            "美元价格是100，通常会影响风险资产，但危机时可能例外。",
            "美元已经走强，通常会收紧条件，但也可能与股票同涨。",
            "本周美元走弱，可能支持黄金；但现金需求也可能改变结果，不构成预测准确率声明。",
        )
        for text in texts:
            with self.subTest(text=text):
                value = {"text": text, "evidence_ids": [mechanism_id], "claim_type": "theoretical_mechanism"}
                self.assertEqual(validate_theoretical_statement(value, {mechanism_id}), value)

    def test_theory_statement_rejects_internal_ops_data(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        mechanism_id = request["mechanism"]["mechanism_ids"][0]
        for text in (
            "当前判断见 analysis_id 和 evidence_ids。",
            "DeepSeek 失败后由 Codex CLI fallback。",
            "provider_status=validation_error。",
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "theory_ops_data_leak"):
                validate_theoretical_statement(
                    {"text": text, "evidence_ids": [mechanism_id], "claim_type": "theoretical_mechanism"},
                    {mechanism_id},
                )

    def test_static_current_environment_qualification_is_allowed(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        mechanism_id = request["mechanism"]["mechanism_ids"][0]
        value = {"text": "当前环境下，黄金通常受实际利率与避险需求驱动，但现金需求可能使传导暂时失效。", "evidence_ids": [mechanism_id], "claim_type": "theoretical_mechanism"}
        self.assertEqual(validate_theoretical_statement(value, {mechanism_id}), value)

    def test_negated_certainty_and_asset_label_numbers_are_allowed(self) -> None:
        cases = (
            ("dxy", "美元走强通常收紧非美元资产的金融条件，但该传导并非必然成立。"),
            ("sp500", "标普500通常受盈利增长、利率和风险偏好驱动，但上涨不必然代表广泛风险偏好。"),
            ("star50", "科创50通常受科技盈利、政策与国内流动性驱动，但产业政策可能改变传导。"),
            ("nikkei", "日经225通常受全球周期与日元因素影响，但国内盈利改善可能改变结果。"),
            ("us10y", "美国10年期国债收益率通常受长期通胀预期与期限溢价驱动，但收益率与股票不必然反向。"),
        )
        for key, text in cases:
            with self.subTest(key=key):
                allowed = set(mechanism_for_asset(key)["mechanism_ids"])
                value = {"text": text, "evidence_ids": [next(iter(allowed))], "claim_type": "theoretical_mechanism"}
                self.assertEqual(validate_theoretical_statement(value, allowed), value)


if __name__ == "__main__":
    unittest.main()
