#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "scripts"))

from portfolio_allocation import digest, load_portfolio_state, validate_portfolio_version  # noqa: E402
from verify_canonical_portfolio import DEFAULT_OUTPUT, DEFAULT_STATE, verify  # noqa: E402
from verify_cross_company_research import chrome_path  # noqa: E402


def expect_rejected(label: str, action) -> dict:
    try:
        action()
    except Exception as exc:  # rejection type is part of the evidence, not control flow recovery
        return {"attack": label, "status": "rejected", "error": str(exc)}
    raise RuntimeError(f"adversarial attack was accepted: {label}")


def run(output: Path = DEFAULT_OUTPUT, state: Path = DEFAULT_STATE) -> dict:
    baseline = verify(output, state)
    attacks: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="m5-fake-diff-") as temporary:
        root = Path(temporary)
        fake_output = root / "evidence"
        fake_state = root / "state"
        shutil.copytree(output, fake_output)
        shutil.copytree(state, fake_state)
        diff_path = fake_output / "portfolio-diff.json"
        fake_diff = json.loads(diff_path.read_text(encoding="utf-8"))
        fake_diff["cash_change"] = 999
        fake_diff["changes"] = []
        fake_diff.pop("diff_hash", None)
        fake_diff["diff_hash"] = digest(fake_diff)
        diff_path.write_text(json.dumps(fake_diff, ensure_ascii=False), encoding="utf-8")
        attacks.append(expect_rejected(
            "self_hashed_fake_diff",
            lambda: verify(fake_output, fake_state),
        ))

    with tempfile.TemporaryDirectory(prefix="m5-empty-ledger-") as temporary:
        root = Path(temporary)
        fake_output = root / "evidence"
        fake_state = root / "state"
        shutil.copytree(output, fake_output)
        shutil.copytree(state, fake_state)
        current = load_portfolio_state(fake_state)
        fake_ledger = {
            "schema_version": "model-portfolio-ledger-v1",
            "portfolio_id": current["portfolio_id"],
            "orders": [],
        }
        fake_ledger["ledger_hash"] = digest(fake_ledger)
        (fake_output / "ledger-receipt.json").write_text(
            json.dumps(fake_ledger, ensure_ascii=False), encoding="utf-8",
        )
        attacks.append(expect_rejected(
            "self_hashed_empty_ledger",
            lambda: verify(fake_output, fake_state),
        ))

    with tempfile.TemporaryDirectory(prefix="m5-truncated-visual-") as temporary:
        root = Path(temporary)
        fake_output = root / "evidence"
        fake_state = root / "state"
        shutil.copytree(output, fake_output)
        shutil.copytree(state, fake_state)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Python Playwright is required for visual adversarial verification") from exc
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chrome_path(), headless=True,
                args=["--disable-background-networking", "--disable-sync"],
            )
            try:
                url = (fake_output / "index.html").resolve().as_uri()
                desktop = browser.new_page(viewport={"width": 1440, "height": 1001})
                desktop.goto(url, wait_until="load", timeout=30_000)
                desktop.screenshot(path=str(fake_output / "portfolio-desktop.png"), full_page=False)
                mobile = browser.new_page(viewport={"width": 390, "height": 845})
                mobile.goto(url, wait_until="load", timeout=30_000)
                mobile.screenshot(path=str(fake_output / "portfolio-mobile.png"), full_page=False)
            finally:
                browser.close()
        generation_path = fake_output / "verification-receipt.json"
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        generation["artifacts"].update({
            "desktop_dimensions": [1440, 1001], "desktop_scroll_height": 1001,
            "desktop_full_page": True, "mobile_dimensions": [390, 845],
            "mobile_scroll_height": 845, "mobile_full_page": True,
        })
        generation_path.write_text(json.dumps(generation, ensure_ascii=False), encoding="utf-8")
        attacks.append(expect_rejected(
            "truncated_png_with_forged_generation_receipt",
            lambda: verify(fake_output, fake_state),
        ))

    current = load_portfolio_state(state)
    semantic_forgery = deepcopy(current)
    semantic_forgery["positions"][0]["report_binding"].update({
        "is_live_research": False,
        "research_status": "blocked",
        "research_depth": "fixture",
        "contract_version": "forged",
    })
    clean = {
        key: value for key, value in semantic_forgery.items()
        if key not in {"portfolio_id", "payload_hash"}
    }
    semantic_forgery["payload_hash"] = digest(clean)
    semantic_forgery["portfolio_id"] = f"canonical_portfolio_{semantic_forgery['payload_hash'][:16]}"
    semantic_errors = validate_portfolio_version(semantic_forgery)
    if not semantic_errors:
        raise RuntimeError("rehashed report semantic forgery was accepted")
    attacks.append({
        "attack": "rehashed_report_semantic_forgery",
        "status": "rejected",
        "errors": semantic_errors,
    })

    malformed = deepcopy(current)
    malformed["positions"][0]["target_weight"] = "NaN"
    malformed_errors = validate_portfolio_version(malformed)
    if not malformed_errors:
        raise RuntimeError("non-finite portfolio weight was accepted")
    attacks.append({
        "attack": "non_finite_weight",
        "status": "rejected",
        "errors": malformed_errors,
    })

    receipt = {
        "schema_version": "canonical-portfolio-adversarial-verification-v1",
        "status": "passed",
        "baseline_status": baseline["status"],
        "attacks": attacks,
        "required_truth_checks": {
            "diff_recomputed": baseline["diff_recomputed"],
            "ledger_source_bars_verified": baseline["ledger_source_bars_verified"],
            "retrospective_truth_marker_visible": baseline["retrospective_truth_marker_visible"],
            "full_page_dom_height_verified": baseline["full_page_dom_height_verified"],
            "independent_visual_rerender_match": baseline["independent_visual_rerender_match"],
        },
    }
    return receipt


if __name__ == "__main__":
    result = run()
    destination = DEFAULT_OUTPUT / "adversarial-verification-receipt.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
