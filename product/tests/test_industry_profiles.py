from __future__ import annotations

import sys
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.industry_profiles import PROFILES, profile_contract  # noqa: E402
from report_contract import MODULE_SPECS  # noqa: E402


class IndustryProfilesTest(unittest.TestCase):
    def test_profiles_share_one_canonical_report_structure(self) -> None:
        modules = tuple(spec.id for spec in MODULE_SPECS)
        for profile in PROFILES.values():
            full = profile_contract(profile.profile_id, {key: 1 for key in profile.required_inputs})
            self.assertEqual(full["canonical_modules"], modules)
            self.assertEqual(full["status"], "available")

    def test_missing_inputs_fail_visible_not_silent(self) -> None:
        contract = profile_contract("bank", {"net_interest_margin": 1})
        self.assertEqual(contract["status"], "partial")
        self.assertIn("asset_quality", contract["missing_inputs"])
        self.assertTrue(contract["missing_policy"])
        with self.assertRaisesRegex(ValueError, "unknown"):
            profile_contract("ad_hoc", {})


if __name__ == "__main__":
    unittest.main()
