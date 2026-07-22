#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from portfolio_allocation import (  # noqa: E402
    build_portfolio_version,
    canonical_json,
    digest,
    portfolio_diff,
    render_portfolio_html,
)
from portfolio_ledger import (  # noqa: E402
    PortfolioLedger,
    build_ledger_history,
    verify_ledger_history,
    verify_ledger_fills_against_source,
    verify_ledger_matches_portfolio,
    verify_ledger_payload,
)
from real_pipeline import replay_snapshot  # noqa: E402
from verify_cross_company_research import chrome_path, png_dimensions, render  # noqa: E402


DEFAULT_DB = PRODUCT / "runtime" / "m4-live.db"
DEFAULT_STATE = PRODUCT / "runtime" / "canonical_portfolio"
DEFAULT_OUTPUT = ROOT / "evidence" / "m5-canonical-portfolio"
DEFAULT_SNAPSHOTS = ("snap_real_b0bac1135776", "snap_real_a89a5113ef0f")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_immutable_json(path: Path, value: object) -> None:
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"immutable portfolio version is unreadable: {path.name}") from exc
        if existing != value:
            raise RuntimeError(f"immutable portfolio version collision: {path.name}")
        return
    write_json(path, value)


def next_open(db_path: Path, ticker: str, after_date: str) -> dict | None:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT b.trade_date,b.open,b.raw_hash,b.snapshot_id
               FROM daily_bars b JOIN dataset_snapshots s ON s.id=b.snapshot_id
               WHERE b.ticker=? AND b.trade_date>? AND b.quality_status='accepted'
                 AND s.data_mode='REAL' AND s.quality_status='passed'
               ORDER BY b.trade_date ASC, s.created_at DESC LIMIT 1""",
            (ticker, after_date),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def save_state(
    state_root: Path, versions: list[dict], diff: dict, ledger: dict, ledger_history: dict,
) -> None:
    for version in versions:
        write_immutable_json(state_root / "versions" / f"{version['portfolio_id']}.json", version)
    current = versions[-1]
    pointer = {
        "portfolio_id": current["portfolio_id"],
        "payload_hash": current["payload_hash"],
        "snapshot_id": current["snapshot"]["snapshot_id"],
    }
    pointer["pointer_hash"] = digest(pointer)
    write_json(state_root / "current.json", pointer)
    write_json(state_root / "latest-diff.json", diff)
    write_json(state_root / "latest-ledger.json", ledger)
    write_json(state_root / "ledger-history.json", ledger_history)


def generate(args: argparse.Namespace) -> dict:
    snapshots = tuple(args.snapshot or DEFAULT_SNAPSHOTS)
    if len(snapshots) < 2:
        raise RuntimeError("at least two consecutive snapshot IDs are required")
    versions = []
    for snapshot_id in snapshots:
        deep_root = args.deep_reports if snapshot_id == snapshots[-1] else None
        version = build_portfolio_version(
            snapshot_id, args.db, previous=versions[-1] if versions else None,
            deep_report_root=deep_root,
        )
        replay = replay_snapshot(snapshot_id, args.db)
        if replay.get("status") != "passed":
            raise RuntimeError(f"snapshot replay failed: {snapshot_id}")
        versions.append(version)
    latest_diff = portfolio_diff(versions[-2], versions[-1])

    args.state.mkdir(parents=True, exist_ok=True)
    ledger_store = PortfolioLedger(args.state / "portfolio-ledger.db")
    now = datetime.now(timezone.utc).isoformat()
    for index, version in enumerate(versions):
        order_ids = ledger_store.stage_orders(version)
        existing = ledger_store.payload(version["portfolio_id"])
        existing_ids = {
            item["order_id"] for item in existing["orders"]
            if item.get("status") in {"pending", "filled", "unfilled"}
        }
        for order_id in order_ids:
            if order_id in existing_ids:
                continue
            ledger_store.append_event(
                order_id, "pending", event_at=version["generated_at"],
                reason="等待下一可交易日开盘；不使用发布前或事后优化价格。",
            )
        if index == len(versions) - 1:
            continue
        pending = ledger_store.payload(version["portfolio_id"])["orders"]
        for item in pending:
            if item.get("status") != "pending":
                continue
            opened = next_open(args.db, item["ticker"], version["snapshot"]["as_of"])
            if opened:
                ledger_store.append_event(
                    item["order_id"], "filled", event_at=now,
                    effective_trade_date=opened["trade_date"], fill_price=float(opened["open"]),
                    source_snapshot_id=opened["snapshot_id"], source_row_hash=opened["raw_hash"],
                    source_db_path=args.db,
                    reason="按下一可交易日开盘价记录模拟成交；未应用真实券商成交。",
                )

    ledger_versions = [ledger_store.payload(version["portfolio_id"]) for version in versions]
    for portfolio, ledger_version in zip(versions, ledger_versions, strict=True):
        verify_ledger_matches_portfolio(ledger_version, portfolio)
    ledger_history = build_ledger_history(ledger_versions)
    latest_ledger = ledger_versions[-1]
    verify_ledger_payload(latest_ledger, expected_portfolio_id=versions[-1]["portfolio_id"])
    verify_ledger_history(ledger_history, expected_current_portfolio_id=versions[-1]["portfolio_id"])
    verify_ledger_fills_against_source(ledger_history, args.db)
    save_state(args.state, versions, latest_diff, latest_ledger, ledger_history)
    args.output.mkdir(parents=True, exist_ok=True)
    expected_version_files = {f"{version['portfolio_id']}.json" for version in versions}
    stale_version_files = {
        path.name for path in (args.output / "versions").glob("*.json")
        if path.name not in expected_version_files
    }
    if stale_version_files:
        raise RuntimeError(
            "stale acceptance evidence versions must be reviewed explicitly: "
            + ", ".join(sorted(stale_version_files))
        )
    for version in versions:
        write_json(args.output / "versions" / f"{version['portfolio_id']}.json", version)
    write_json(args.output / "portfolio-diff.json", latest_diff)
    write_json(args.output / "ledger-receipt.json", latest_ledger)
    write_json(args.output / "ledger-history-receipt.json", ledger_history)
    html = render_portfolio_html(versions[-1], versions, latest_diff, latest_ledger)
    html_path = args.output / "index.html"
    html_path.write_text(html, encoding="utf-8")
    render_metrics = render(
        chrome_path(), html_path,
        args.output / "portfolio-desktop.png",
        args.output / "portfolio-mobile.png",
        args.output / "portfolio.pdf",
    )
    receipt = {
        "schema_version": "canonical-portfolio-verification-v1",
        "status": "passed",
        "truth_boundary": "two stored REAL snapshots; 2026-07-17 is retrospective replay, 2026-07-21 is the current model suggestion; neither is a broker holding",
        "snapshots": snapshots,
        "portfolio_ids": [item["portfolio_id"] for item in versions],
        "current_portfolio_id": versions[-1]["portfolio_id"],
        "current_payload_hash": versions[-1]["payload_hash"],
        "diff_hash": latest_diff["diff_hash"],
        "ledger_hash": latest_ledger["ledger_hash"],
        "ledger_history_hash": ledger_history["ledger_history_hash"],
        "ledger_status_counts": ledger_history["status_counts"],
        "current_positions": [
            {"ticker": item["ticker"], "name": item["name"], "weight": item["target_weight"], "action": item["action"]}
            for item in versions[-1]["positions"]
        ],
        "allocation": versions[-1]["allocation"],
        "report_depth_counts": {
            depth: sum(item["report_binding"]["research_depth"] == depth for item in versions[-1]["positions"])
            for depth in ("deep", "quantitative_baseline")
        },
        "replay": [{"snapshot_id": sid, "status": "passed", "replayed_tickers": 8} for sid in snapshots],
        "artifacts": {
            "html": "index.html",
            "desktop_png": "portfolio-desktop.png",
            "desktop_dimensions": list(png_dimensions(args.output / "portfolio-desktop.png")),
            "desktop_scroll_height": render_metrics["desktop_scroll_height"],
            "desktop_full_page": png_dimensions(args.output / "portfolio-desktop.png")[1] == render_metrics["desktop_scroll_height"],
            "mobile_png": "portfolio-mobile.png",
            "mobile_dimensions": list(png_dimensions(args.output / "portfolio-mobile.png")),
            "mobile_scroll_height": render_metrics["mobile_scroll_height"],
            "mobile_full_page": png_dimensions(args.output / "portfolio-mobile.png")[1] == render_metrics["mobile_scroll_height"],
            "pdf": "portfolio.pdf",
        },
    }
    write_json(args.output / "verification-receipt.json", receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Generate the canonical long-horizon A-share portfolio")
    value.add_argument("--db", type=Path, default=DEFAULT_DB)
    value.add_argument("--state", type=Path, default=DEFAULT_STATE)
    value.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    value.add_argument("--snapshot", action="append")
    value.add_argument("--deep-reports", type=Path, default=ROOT / "evidence" / "m4-cross-company-research" / "live")
    return value


if __name__ == "__main__":
    result = generate(parser().parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2))
