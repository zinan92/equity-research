#!/usr/bin/env python3
"""Browser/API acceptance for the real-data Weekly live prototype."""

from __future__ import annotations

import argparse
import json
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8907")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with urlopen(f"{base}/api/weekly-report", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert len(payload["assets"]) == 17
    assert payload["analysis_validated"] >= 1
    assert payload["report_id"].startswith("market-regime-weekly-report:")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width, height in ((1440, 1024), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_selector("#app:not([hidden])")
                assert page.locator("[data-asset]").count() == 17
                assert page.locator("canvas.mini-chart").count() == 17
                assert page.locator("canvas.mini-chart").first.evaluate("canvas => canvas.width >= canvas.clientWidth * 2")
                assert page.evaluate("Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)")
                assert page.evaluate("document.body.scrollWidth <= window.innerWidth")
                page.locator('[data-asset="dxy"]').first.click()
                page.wait_for_selector("#detail:not([hidden])")
                assert page.locator("#detail .period").count() == 3
                assert page.locator("#detail canvas.detail-chart").count() == 3
                assert page.locator("#detail canvas.detail-chart").first.evaluate("canvas => canvas.width >= canvas.clientWidth * 2")
                assert not errors, errors
                page.close()
        finally:
            browser.close()
    print(f"weekly live acceptance: PASS ({payload['analysis_validated']}/17 validated; API + overview + asset detail; 1440px/390px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
