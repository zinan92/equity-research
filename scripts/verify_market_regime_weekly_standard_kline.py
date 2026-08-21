"""Browser acceptance for the real Weekly report -> standard-kline seam."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "product" / "tests"))

from data_core.market_regime_weekly_report import render_weekly_interactive_html, build_weekly_report  # noqa: E402
from test_market_regime_weekly_report import (  # noqa: E402
    analyses_fixture,
    candle_response_fixture,
    ranking_fixture,
    source_fixture,
)


def main() -> None:
    report = build_weekly_report(
        source_fixture(),
        analyses_fixture(),
        ranking_fixture(),
        candle_responses={
            "gold:weekly": candle_response_fixture("gold"),
            "us2y:weekly": candle_response_fixture("us2y", series_kind="rate_level"),
        },
    )
    with tempfile.TemporaryDirectory(prefix="weekly-standard-kline-") as directory:
        html_path = Path(directory) / "report.html"
        html_path.write_text(render_weekly_interactive_html(report), encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for width, height in ((1280, 900), (390, 844)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    page.goto(html_path.as_uri(), wait_until="load")
                    page.locator('[data-asset-nav="gold"]').click()
                    page.wait_for_timeout(250)
                    assert page.locator('[data-pane="gold"] [data-standard-kline="true"]').count() == 1
                    assert page.locator('[data-pane="gold"] [data-standard-kline-overlay]').get_attribute("data-state") == "ready"
                    assert page.evaluate("Boolean(window.LightweightCharts) && Boolean(document.querySelector('[data-chart=\"gold:weekly\"]')._standardKline.chart)")
                    page.locator('[data-asset-nav="us2y"]').click()
                    page.wait_for_timeout(250)
                    assert page.locator('[data-pane="us2y"] [data-standard-kline="true"]').count() == 1
                    assert page.locator('[data-pane="us2y"] [data-standard-kline-overlay]').get_attribute("data-state") == "ready"
                    assert page.locator('[data-pane="us2y"] [data-source]').count() == 1
                    assert page.evaluate("Boolean(window.LightweightCharts) && Boolean(document.querySelector('[data-chart=\"us2y:weekly\"]')._standardKline.lineSeries)")
                    overflow = page.evaluate("({body: document.body.scrollWidth, viewport: window.innerWidth})")
                    assert overflow["body"] <= overflow["viewport"], overflow
                    assert not errors, errors
                    page.close()
            finally:
                browser.close()
    print("weekly standard-kline browser acceptance: PASS (1280px, 390px; price + rate; no overflow; no console errors)")


if __name__ == "__main__":
    main()
