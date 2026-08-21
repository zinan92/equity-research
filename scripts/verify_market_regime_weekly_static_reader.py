#!/usr/bin/env python3
"""Browser acceptance for the shareable static Weekly reader."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the static Weekly HTML reader")
    parser.add_argument(
        "--html",
        type=Path,
        default=Path.home() / "Desktop" / "宏观K线周报" / "latest.html",
    )
    args = parser.parse_args()
    html_path = args.html.expanduser().resolve()
    if not html_path.is_file():
        raise SystemExit(f"static_reader_missing:{html_path}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width, height in ((1280, 900), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.goto(html_path.as_uri(), wait_until="load")
                page.wait_for_timeout(100)
                image_count = page.locator("img").count()
                assert image_count == 39, (width, image_count)
                assert page.locator("[data-asset-nav]").count() == 17
                assert page.locator("[data-chart]").count() == 0
                assert not page.locator("script").count()
                assert page.locator("text=本周机会排序").count() + page.locator("text=本周机会清单").count() == 1
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(150)
                images_loaded = page.evaluate("Array.from(document.images).every(image => image.complete)")
                assert images_loaded, (width, "snapshot image not loaded")
                overflow = page.evaluate("({body: document.body.scrollWidth, viewport: window.innerWidth})")
                assert overflow["body"] <= overflow["viewport"], (width, overflow)
                assert not errors, (width, errors)
                page.close()
        finally:
            browser.close()
    print("weekly static reader acceptance: PASS (39 images; 17 assets; 1280px/390px; no scripts; no overflow)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
