from __future__ import annotations

import http.client
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import MarketRegimeDataStore  # noqa: E402
from data_core.market_regime_model import MarketRegimeAnalysisStore  # noqa: E402
from market_regime_runtime import MarketRegimeApiStore  # noqa: E402
from product.tests.test_market_regime_model import (  # noqa: E402
    RISK_ON_RATES,
    persist_snapshot,
    snapshot_for,
)


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str | None]] = []
        self.links: list[dict[str, str | None]] = []
        self.ids: set[str] = set()
        self.range_values: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if values.get("data-range"):
            self.range_values.add(str(values["data-range"]))
        if tag == "script":
            self.scripts.append(values)
        elif tag == "link":
            self.links.append(values)


def prepare_bundle(root: Path) -> dict:
    snapshot = snapshot_for(RISK_ON_RATES, name="web")
    persist_snapshot(root, snapshot)
    verified = MarketRegimeDataStore(root).latest()
    analysis = MarketRegimeAnalysisStore(root).compile_latest()
    return MarketRegimeApiStore(root).publish(verified, analysis)


class MarketRegimeWebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.runtime_root = Path(cls.temp.name)
        cls.bundle = prepare_bundle(cls.runtime_root)
        cls.environment = patch.dict(
            os.environ,
            {"PARK_MARKET_REGIME_ROOT": str(cls.runtime_root)},
        )
        cls.environment.start()
        from http.server import ThreadingHTTPServer
        from server import DashboardHandler

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.environment.stop()
        cls.temp.cleanup()

    @classmethod
    def request(cls, path: str) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(*cls.server.server_address, timeout=2)
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, headers, body

    def test_clean_route_serves_complete_local_asset_shell(self) -> None:
        status, headers, body = self.request("/market-regime")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["content-type"])
        self.assertIn("script-src 'self'", headers["content-security-policy"])
        parser = AssetParser()
        parser.feed(body.decode("utf-8"))
        self.assertEqual([script.get("src") for script in parser.scripts], ["/market-regime.js"])
        self.assertFalse(any(script.get("src") is None for script in parser.scripts))
        self.assertIn(
            "/market-regime.css",
            [link.get("href") for link in parser.links if link.get("rel") == "stylesheet"],
        )
        self.assertEqual(parser.range_values, {"22", "66", "132", "260"})
        required = {
            "hero-headline",
            "signal-risk-label",
            "signal-posture-label",
            "signal-style-label",
            "signal-leadership-label",
            "story-confirmation",
            "story-rotation",
            "story-divergence",
            "story-invalidation",
            "leadership-bars",
            "probe-cards",
            "group-us",
            "group-china",
            "group-commodities",
            "group-asia",
        }
        self.assertTrue(required.issubset(parser.ids))

    def test_assets_are_same_origin_and_encode_responsive_fallbacks(self) -> None:
        css_status, css_headers, css_body = self.request("/market-regime.css")
        js_status, js_headers, js_body = self.request("/market-regime.js")
        self.assertEqual((css_status, js_status), (200, 200))
        self.assertIn("text/css", css_headers["content-type"])
        self.assertIn("javascript", js_headers["content-type"])
        css = css_body.decode("utf-8")
        javascript = js_body.decode("utf-8")
        self.assertIn("@media (max-width: 480px)", css)
        self.assertIn("@media (max-width: 800px)", css)
        self.assertIn("overflow-x: hidden", css)
        self.assertNotIn("https://", css + javascript)
        self.assertNotIn("http://", css + javascript)
        self.assertIn('fetchJson("/api/market-regime")', javascript)
        self.assertIn('fetchJson("/api/market-regime/health")', javascript)
        self.assertIn("不会用演示数据伪装实时市场", javascript)
        self.assertIn("不以旧图伪装最新行情", javascript)

    def test_javascript_contract_contains_all_nine_assets_and_four_groups(self) -> None:
        _, _, body = self.request("/market-regime.js")
        javascript = body.decode("utf-8")
        assets = {
            "sp500",
            "nasdaq",
            "shanghai",
            "star50",
            "wti",
            "gold",
            "silver",
            "kospi",
            "nikkei",
        }
        for asset in assets:
            self.assertIn(f'"{asset}"', javascript)
        for group in ("group-us", "group-china", "group-commodities", "group-asia"):
            self.assertIn(f'"{group}"', javascript)
        _, _, html = self.request("/market-regime")
        self.assertIn("COMPLETED SESSIONS ONLY", html.decode("utf-8"))

    def test_live_same_origin_api_contract_matches_page_requirements(self) -> None:
        status, headers, body = self.request("/api/market-regime")
        self.assertEqual(status, 200)
        self.assertEqual(headers["cache-control"], "no-store")
        payload = json.loads(body)
        self.assertEqual(payload["bundle_id"], self.bundle["bundle_id"])
        self.assertEqual(len(payload["charts"]), 9)
        self.assertEqual(len(payload["probes"]), 3)
        self.assertIn("what_is_going_on", payload["analysis"])
        self.assertFalse(payload["truth_boundary"]["action_eligible"])


if __name__ == "__main__":
    unittest.main()
