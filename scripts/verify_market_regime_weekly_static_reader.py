#!/usr/bin/env python3
"""Browser acceptance for the shareable static Weekly reader."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def _require(condition: bool, detail: object) -> None:
    if not condition:
        raise RuntimeError(f"static_reader_assertion:{detail}")


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
                _require(image_count == 39, (width, image_count))
                _require(page.locator("[data-asset-nav]").count() == 17, (width, "asset_nav_count"))
                _require(page.locator("[data-chart]").count() == 0, (width, "interactive_chart_mount"))
                _require(not page.locator("script").count(), (width, "script_present"))
                _require(
                    page.locator("text=本周机会排序").count() + page.locator("text=本周机会清单").count() == 1,
                    (width, "opportunity_title"),
                )
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(150)
                images_loaded = page.evaluate(
                    "Array.from(document.images).every(image => image.complete && image.naturalWidth > 0 && image.naturalHeight > 0)"
                )
                _require(images_loaded, (width, "snapshot image not loaded"))
                overflow = page.evaluate("({body: document.body.scrollWidth, viewport: window.innerWidth})")
                _require(overflow["body"] <= overflow["viewport"], (width, overflow))
                _require(not errors, (width, errors))
                page.close()
        finally:
            browser.close()
    print("weekly static reader acceptance: PASS (39 images; 17 assets; 1280px/390px; no scripts; no overflow)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
