from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "product" / "static"


class SectorRotationPrototypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (STATIC / "sector-rotation.html").read_text(encoding="utf-8")
        cls.css = (STATIC / "sector-rotation.css").read_text(encoding="utf-8")
        cls.javascript = (STATIC / "sector-rotation.js").read_text(encoding="utf-8")

    def test_shell_has_same_origin_assets_and_required_reader_surfaces(self) -> None:
        self.assertIn('href="sector-rotation.css"', self.html)
        self.assertIn('src="sector-rotation.js"', self.html)
        required_ids = {
            "slot-count",
            "macro-handoff",
            "quality-state",
            "leaders",
            "improving",
            "watching",
            "sector-grid",
            "evidence-dialog",
            "evidence-chart",
            "flow-bars",
            "evidence-ledger",
        }
        for element_id in required_ids:
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertNotIn("https://", self.html + self.css + self.javascript)
        self.assertNotIn("http://", self.html + self.css + self.javascript)

    def test_exactly_twenty_peer_sector_fixtures_are_present(self) -> None:
        sector_rows = re.findall(r'^\s+\{id: "([^"]+)", label:', self.javascript, flags=re.MULTILINE)
        self.assertEqual(len(sector_rows), 20)
        self.assertEqual(len(set(sector_rows)), 20)
        for label in ("芯片", "AI应用", "发电", "白酒", "银行", "保险"):
            self.assertIn(f'label: "{label}"', self.javascript)

    def test_fixture_and_fail_closed_boundaries_are_visible(self) -> None:
        surface = self.html + self.css + self.javascript
        for phrase in (
            "FIXTURE / NOT LIVE",
            "不是当前行情结论",
            "identity mismatch",
            "proxy-only",
            "unknown",
            "不直接转成买入",
            "示例 K 线图",
            "current snapshot only",
        ):
            self.assertIn(phrase, surface)
        self.assertIn("partial", self.javascript)
        self.assertIn("accepted_alias_pending", self.javascript)

    def test_no_live_or_execution_surface_exists(self) -> None:
        surface = self.html + self.css + self.javascript
        for forbidden in (
            "fetch(",
            "WebSocket(",
            "/api/orders",
            "/api/positions",
            "自动交易",
        ):
            self.assertNotIn(forbidden, surface)
        self.assertIn("NO BROKER", surface)

    def test_responsive_and_evidence_drawer_contract_is_present(self) -> None:
        self.assertIn("@media (max-width: 800px)", self.css)
        self.assertIn("@media (max-width: 480px)", self.css)
        self.assertIn("dialog.showModal", self.javascript)
        self.assertIn("candlestickChart", self.javascript)
        self.assertIn("flowBars", self.javascript)
        self.assertIn("renderLedger", self.javascript)


if __name__ == "__main__":
    unittest.main()
