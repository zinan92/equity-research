#!/usr/bin/env python3
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from portfolio_allocation import (  # noqa: E402
    digest,
    load_portfolio_history,
    load_portfolio_state,
    portfolio_diff,
    validate_portfolio_version,
)
from portfolio_ledger import (  # noqa: E402
    verify_ledger_history,
    verify_ledger_fills_against_source,
    verify_ledger_matches_portfolio,
    verify_ledger_payload,
)
from data_store import connect, verify_snapshot_content_attestation  # noqa: E402
from verify_cross_company_research import chrome_path, pdf_page_count, pdf_text, png_dimensions  # noqa: E402


DEFAULT_OUTPUT = ROOT / "evidence" / "m5-canonical-portfolio"
DEFAULT_STATE = PRODUCT / "runtime" / "canonical_portfolio"
DEFAULT_DB = PRODUCT / "runtime" / "m4-live.db"


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def independent_render(html_path: Path) -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Python Playwright is required for independent visual verification") from exc
    with tempfile.TemporaryDirectory(prefix="m5-independent-render-") as temporary:
        root = Path(temporary)
        desktop_path = root / "desktop.png"
        mobile_path = root / "mobile.png"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chrome_path(), headless=True,
                args=["--disable-background-networking", "--disable-sync"],
            )
            try:
                url = html_path.resolve().as_uri()
                desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
                desktop.goto(url, wait_until="load", timeout=30_000)
                desktop_height = int(desktop.evaluate("document.documentElement.scrollHeight"))
                desktop.screenshot(path=str(desktop_path), full_page=True, timeout=30_000)
                mobile = browser.new_page(viewport={"width": 390, "height": 844})
                mobile.goto(url, wait_until="load", timeout=30_000)
                mobile_height = int(mobile.evaluate("document.documentElement.scrollHeight"))
                mobile.screenshot(path=str(mobile_path), full_page=True, timeout=30_000)
            finally:
                browser.close()
        return {
            "desktop_scroll_height": desktop_height,
            "mobile_scroll_height": mobile_height,
            "desktop_sha256": file_hash(desktop_path),
            "mobile_sha256": file_hash(mobile_path),
        }


def verify(
    output: Path = DEFAULT_OUTPUT, state: Path = DEFAULT_STATE, source_db: Path = DEFAULT_DB,
) -> dict:
    current = load_portfolio_state(state)
    history = load_portfolio_history(state)
    if len(history) < 2:
        raise RuntimeError("two canonical portfolio versions are required")
    if any(validate_portfolio_version(item) for item in history):
        raise RuntimeError("portfolio history contains an invalid version")
    first, latest = history[-2], history[-1]
    if latest["portfolio_id"] != current["portfolio_id"]:
        raise RuntimeError("current pointer is not the latest version")
    diff = json.loads((output / "portfolio-diff.json").read_text(encoding="utf-8"))
    diff_without_hash = dict(diff)
    declared_diff_hash = diff_without_hash.pop("diff_hash")
    if digest(diff_without_hash) != declared_diff_hash:
        raise RuntimeError("portfolio diff hash mismatch")
    if diff != portfolio_diff(first, latest):
        raise RuntimeError("portfolio diff does not match the two exact versions")
    ledger = json.loads((output / "ledger-receipt.json").read_text(encoding="utf-8"))
    verify_ledger_payload(ledger, expected_portfolio_id=current["portfolio_id"])
    declared_ledger_hash = ledger["ledger_hash"]
    ledger_history = json.loads((output / "ledger-history-receipt.json").read_text(encoding="utf-8"))
    verify_ledger_history(ledger_history, expected_current_portfolio_id=current["portfolio_id"])
    verify_ledger_fills_against_source(ledger_history, source_db)
    if ledger != ledger_history["versions"][-1]:
        raise RuntimeError("current ledger differs from the final ledger history version")
    if [item["portfolio_id"] for item in ledger_history["versions"]] != [item["portfolio_id"] for item in history]:
        raise RuntimeError("ledger history does not match portfolio history")
    portfolio_by_id = {item["portfolio_id"]: item for item in history}
    attested_sources: set[str] = set()
    with closing(connect(source_db)) as connection:
        for ledger_version in ledger_history["versions"]:
            portfolio = portfolio_by_id[ledger_version["portfolio_id"]]
            verify_ledger_matches_portfolio(ledger_version, portfolio)
            expected = {
                item["ticker"]: item for item in portfolio["positions"]
                if float(item.get("drifted_weight") or 0) != float(item["target_weight"])
            }
            actual = {item["ticker"]: item for item in ledger_version["orders"]}
            if set(actual) != set(expected):
                raise RuntimeError("model ledger orders do not match drift-to-target changes")
            for ticker, order in actual.items():
                position = expected[ticker]
                expected_previous = float(position.get("previous_target_weight") or 0)
                expected_drifted = float(position.get("drifted_weight") or 0)
                if any(abs(a - b) > 1e-6 for a, b in (
                    (float(order["previous_target_weight"]), expected_previous),
                    (float(order["drifted_weight"]), expected_drifted),
                    (float(order["target_weight"]), float(position["target_weight"])),
                    (float(order["weight_drift"]), round(float(position["target_weight"]) - expected_drifted, 4)),
                )):
                    raise RuntimeError(f"model ledger weights do not reconcile: {ticker}")
                if order["status"] != "filled":
                    continue
                source_snapshot = order["source_snapshot_id"]
                if source_snapshot not in attested_sources:
                    verify_snapshot_content_attestation(connection, source_snapshot)
                    attested_sources.add(source_snapshot)
                bar = connection.execute(
                    """SELECT b.snapshot_id,b.trade_date,b.open,b.raw_hash,
                              s.data_mode,s.quality_status
                       FROM daily_bars b JOIN dataset_snapshots s ON s.id=b.snapshot_id
                       WHERE b.ticker=? AND b.trade_date>? AND b.quality_status='accepted'
                         AND s.data_mode='REAL' AND s.quality_status='passed'
                       ORDER BY b.trade_date ASC,s.created_at DESC LIMIT 1""",
                    (ticker, order["scheduled_after"]),
                ).fetchone()
                if (
                    not bar or bar["snapshot_id"] != source_snapshot
                    or bar["trade_date"] != order["effective_trade_date"]
                    or bar["data_mode"] != "REAL" or bar["quality_status"] != "passed"
                    or abs(float(bar["open"]) - float(order["fill_price"])) > 1e-9
                    or bar["raw_hash"] != order["source_row_hash"]
                ):
                    raise RuntimeError(f"model ledger fill does not match authoritative source bar: {ticker}")
    if ledger_history["status_counts"]["filled"] < 1 or ledger_history["status_counts"]["pending"] < 1:
        raise RuntimeError("acceptance ledger must contain historical fills and current pending actions")
    html = (output / "index.html").read_text(encoding="utf-8")
    for item in current["positions"]:
        visible_values = (
            item["ticker"], item["name"], f"{item['target_weight']:.0f}%", item["industry"],
            item["execution_observation_range"], str(item["confidence"]), item["primary_risk"],
            item["report_binding"]["research_depth"],
        )
        if any(str(value) not in html for value in visible_values):
            raise RuntimeError(f"portfolio HTML is missing a visible allocation: {item['ticker']}")
    for marker in ("历史补算 · 非当日发布", "当前验证版本", "上期目标 → 漂移权重 → 本期目标"):
        if marker not in html:
            raise RuntimeError(f"portfolio HTML is missing a truth/ledger marker: {marker}")
    desktop = png_dimensions(output / "portfolio-desktop.png")
    mobile = png_dimensions(output / "portfolio-mobile.png")
    if desktop[0] != 1440 or desktop[1] <= 1000 or mobile[0] != 390 or mobile[1] <= 844:
        raise RuntimeError("portfolio screenshots are not full-page desktop/mobile evidence")
    if pdf_page_count(output / "portfolio.pdf") < 2:
        raise RuntimeError("portfolio PDF is unexpectedly short")
    if "历史补算" not in pdf_text(output / "portfolio.pdf"):
        raise RuntimeError("portfolio PDF is missing the retrospective truth marker")
    generation_receipt = json.loads((output / "verification-receipt.json").read_text(encoding="utf-8"))
    render_receipt = generation_receipt.get("artifacts") or {}
    independently_rendered = independent_render(output / "index.html")
    if (
        render_receipt.get("desktop_full_page") is not True
        or render_receipt.get("mobile_full_page") is not True
        or desktop[1] != render_receipt.get("desktop_scroll_height")
        or mobile[1] != render_receipt.get("mobile_scroll_height")
    ):
        raise RuntimeError("portfolio screenshots do not match measured DOM scroll heights")
    if (
        desktop[1] != independently_rendered["desktop_scroll_height"]
        or mobile[1] != independently_rendered["mobile_scroll_height"]
        or file_hash(output / "portfolio-desktop.png") != independently_rendered["desktop_sha256"]
        or file_hash(output / "portfolio-mobile.png") != independently_rendered["mobile_sha256"]
    ):
        raise RuntimeError("portfolio screenshots do not match the independent HTML re-render")
    receipt = {
        "schema_version": "canonical-portfolio-independent-verifier-v1",
        "status": "passed",
        "portfolio_count": len(history),
        "current_portfolio_id": current["portfolio_id"],
        "snapshots": [item["snapshot"]["snapshot_id"] for item in history],
        "current_stock_count": len(current["positions"]),
        "allocation": current["allocation"],
        "constraints": {
            "stock_count_6_12": True,
            "single_stock_5_15": True,
            "industry_max_30": True,
            "cash_10_40": True,
            "total_100": True,
        },
        "report_identity_bound": all(item["report_binding"]["report_hash"] for item in current["positions"]),
        "deep_report_count": sum(item["report_binding"]["research_depth"] == "deep" for item in current["positions"]),
        "diff_hash": declared_diff_hash,
        "ledger_hash": declared_ledger_hash,
        "ledger_history_hash": ledger_history["ledger_history_hash"],
        "ledger_status_counts": ledger_history["status_counts"],
        "ledger_source_bars_verified": True,
        "diff_recomputed": True,
        "retrospective_truth_marker_visible": True,
        "full_page_dom_height_verified": True,
        "independent_visual_rerender_match": True,
        "artifacts": {
            name: {"sha256": file_hash(output / name)}
            for name in ("index.html", "portfolio-desktop.png", "portfolio-mobile.png", "portfolio.pdf")
        },
    }
    return receipt


if __name__ == "__main__":
    result = verify()
    DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
    (DEFAULT_OUTPUT / "independent-verification-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
