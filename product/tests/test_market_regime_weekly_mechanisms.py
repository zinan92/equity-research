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

    def test_theory_statement_rejects_current_certain_or_english_prose(self) -> None:
        request = build_asset_analysis_request(asset_snapshot())
        mechanism_id = request["mechanism"]["mechanism_ids"][0]
        for text, code in (
            ("当前美元一定会上涨并实时压制比特币。", "theory_current_or_certain_claim"),
            ("Current gold will definitely rise.", "theory_language_not_chinese"),
            ("美元价格是100，通常会影响风险资产，但危机时可能例外。", "theory_numeric_observation"),
            ("美元已经走强，通常会收紧条件，但也可能与股票同涨。", "theory_current_or_certain_claim"),
            ("本报告显示美元走弱，通常会支持黄金，但现金需求可能例外。", "theory_current_or_certain_claim"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, code):
                validate_theoretical_statement(
                    {"text": text, "evidence_ids": [mechanism_id], "claim_type": "theoretical_mechanism"},
                    {mechanism_id},
                )


if __name__ == "__main__":
    unittest.main()
