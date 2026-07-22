from __future__ import annotations

import sys
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from industry_intelligence import dossier_payload, load_snapshot, overview_payload  # noqa: E402


class IndustryIntelligenceTest(unittest.TestCase):
    def test_static_shell_exposes_code_first_access_and_three_reviewable_views(self) -> None:
        html = (PRODUCT / "static" / "index.html").read_text(encoding="utf-8")
        css = (PRODUCT / "static" / "styles.css").read_text(encoding="utf-8")
        js = (PRODUCT / "static" / "app.js").read_text(encoding="utf-8")
        for marker in (
            "access-code-form", "industry-panel-segments", "industry-panel-materials",
            "industry-panel-dossiers", "/vendor/d3.v7.min.js",
        ):
            self.assertIn(marker, html)
        self.assertNotIn('id="signup-form"', html)
        self.assertIn(".bubble-chart", css)
        self.assertIn(".dossier-layout", css)
        self.assertIn("/api/auth/access-code", js)
        self.assertIn("renderSafeMarkdown", js)

    def test_archived_snapshot_contract_is_complete_and_explicit(self) -> None:
        payload = load_snapshot()
        self.assertEqual(payload["schema_version"], "industry-intelligence-snapshot-v1")
        self.assertEqual(payload["summary"]["dossier_count"], 489)
        self.assertEqual(payload["summary"]["primary_company_count"], 649)
        self.assertEqual(payload["summary"]["map_node_count"], 38)
        self.assertEqual(payload["summary"]["materials_node_count"], 94)
        self.assertEqual(len(payload["materials_map"]["nodes"]), 94)
        self.assertEqual(payload["source"]["archive_as_of"], "2026-07-02")
        self.assertIn("不是实时行情", payload["source"]["truth_boundary"])
        self.assertRegex(payload["source"]["source_sha256"], r"^[0-9a-f]{64}$")

    def test_segment_map_keeps_source_assessments_without_inferred_company_crosswalk(self) -> None:
        nodes = load_snapshot()["three_high_map"]["nodes"]
        self.assertEqual(len(nodes), 38)
        for node in nodes:
            self.assertIsInstance(node["barrier"], (int, float))
            self.assertIsInstance(node["profit"], (int, float))
            self.assertIsInstance(node["growth_radius"], (int, float))
            self.assertTrue(node["assessment"]["why"])
            self.assertNotIn("company_codes", node)
        leader = nodes[0]["assessment"]["a_leaders"][0]
        self.assertEqual(set(leader), {"name", "code", "why"})

    def test_materials_map_retains_company_level_finance_logic_and_dossier_link(self) -> None:
        nodes = load_snapshot()["materials_map"]["nodes"]
        anji = next(node for node in nodes if node["code"] == "688019")
        self.assertEqual(anji["name"], "安集科技")
        self.assertEqual(anji["finance"]["period"], "2026Q1")
        self.assertTrue(anji["logic"])
        self.assertTrue(anji["has_dossier"])

    def test_overview_is_bounded_and_dossiers_are_loaded_individually(self) -> None:
        overview = overview_payload()
        self.assertEqual(len(overview["dossiers"]), 489)
        self.assertTrue(all("md" not in item for item in overview["dossiers"]))
        dossier = dossier_payload("300223")
        self.assertEqual(dossier["dossier"]["name"], "北京君正")
        self.assertIn("一句话定位", dossier["dossier"]["md"])
        self.assertIsNone(dossier_payload("../unsafe"))
        self.assertIsNone(dossier_payload("missing"))

    def test_all_dossier_bodies_remain_nonempty_and_unique_by_code(self) -> None:
        dossiers = load_snapshot()["dossiers"]
        self.assertEqual(len(dossiers), len(set(dossiers)))
        self.assertTrue(all(value["code"] == code for code, value in dossiers.items()))
        self.assertTrue(all(len(value["md"]) >= 1_000 for value in dossiers.values()))


if __name__ == "__main__":
    unittest.main()
