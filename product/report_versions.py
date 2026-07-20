from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_store import DB_PATH, connect, initialize


TRACKED_FIELDS = (
    ("market.price", "参考价", "元", 2),
    ("market.pe_ttm", "市盈率", "倍", 2),
    ("market.pb", "市净率", "倍", 2),
    ("market.return_60d", "中期收益", "%", 1),
    ("market.volatility_60d", "波动率", "%", 1),
    ("market.composite_score", "综合评分", "分", 1),
    ("financials.series.0.revenue_yoy", "最新收入增速", "%", 1),
    ("financials.series.0.net_profit_yoy", "最新利润增速", "%", 1),
    ("financials.series.0.gross_margin", "最新毛利率", "%", 1),
    ("executive.decision_review_weight", "建议复核仓位", "%", 1),
    ("executive.current_executable_weight", "已批准执行仓位", "%", 1),
    ("executive.max_target_weight", "条件仓位上限", "%", 1),
)

TRACKED_CONTEXT_FIELDS = (
    ("as_of", "数据截止日"),
    ("financials.latest_period", "最新财报期"),
    ("portfolio_context.market_regime", "市场状态"),
    ("portfolio_context.cash_weight", "组合现金仓位"),
)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _clean_report(report: dict[str, Any]) -> dict[str, Any]:
    clean = json.loads(json.dumps(report, ensure_ascii=False, default=str))
    clean.pop("update_diff", None)
    return clean


def archive_report(report: dict[str, Any], db_path: Path = DB_PATH) -> dict[str, Any]:
    verified_deep = report.get("research_status") == "verified"
    verified_baseline = report.get("research_status") == "baseline" and report.get("data_status") == "verified"
    if not (verified_deep or verified_baseline):
        raise ValueError("only verified deep reports or data-verified research baselines can be archived")
    initialize(db_path)
    snapshot_id = str(report["generated_from"]["snapshot_id"])
    ticker = str(report["ticker"]).upper()
    clean = _clean_report(report)
    declared_hash = clean.pop("report_hash", None)
    report_hash = _canonical_hash(clean)
    if declared_hash and declared_hash != report_hash:
        raise ValueError("report_hash does not match deterministic report content")
    clean["report_hash"] = report_hash
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect(db_path)) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO research_report_versions
               (snapshot_id, ticker, report_hash, report_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (snapshot_id, ticker, report_hash, json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str), created_at),
        )
        row = conn.execute(
            "SELECT report_hash, created_at FROM research_report_versions WHERE ticker=? AND report_hash=?",
            (ticker, report_hash),
        ).fetchone()
        conn.commit()
    return {"snapshot_id": snapshot_id, "ticker": ticker, "report_hash": row["report_hash"], "created_at": row["created_at"]}


def _get(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compare_reports(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    current_snapshot = current.get("generated_from", {}).get("snapshot_id")
    if not previous:
        report_kind = "公司深度研报" if current.get("research_depth") == "deep" else "量化研究基线"
        return {
            "status": "baseline",
            "current_snapshot_id": current_snapshot,
            "previous_snapshot_id": None,
            "headline": f"这是首个已存档的{report_kind}版本，后续更新将从这里开始比较。",
            "changes": [],
            "unchanged_count": 0,
        }
    changes: list[dict[str, Any]] = []
    unchanged_count = 0
    for path, label, unit, digits in TRACKED_FIELDS:
        before, after = _number(_get(previous, path)), _number(_get(current, path))
        if before is None and after is None:
            continue
        if before is not None and after is not None and abs(after - before) < 10 ** (-(digits + 1)):
            unchanged_count += 1
            continue
        delta = after - before if before is not None and after is not None else None
        delta_pct = (after / before - 1) * 100 if before not in (None, 0) and after is not None else None
        changes.append({
            "field": path,
            "label": label,
            "before": before,
            "after": after,
            "unit": unit,
            "delta": round(delta, digits) if delta is not None else None,
            "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
            "direction": "up" if delta is not None and delta > 0 else "down" if delta is not None and delta < 0 else "changed",
        })
    for path, label in TRACKED_CONTEXT_FIELDS:
        before, after = _get(previous, path), _get(current, path)
        if before == after:
            unchanged_count += 1
            continue
        changes.append({
            "field": path, "label": label, "before": before, "after": after,
            "unit": "", "delta": None, "delta_pct": None, "direction": "changed",
        })
    previous_weights = _get(previous, "portfolio_context.weights") or {}
    current_weights = _get(current, "portfolio_context.weights") or {}
    for ticker in sorted(set(previous_weights) | set(current_weights)):
        before, after = _number(previous_weights.get(ticker)), _number(current_weights.get(ticker))
        if before == after:
            unchanged_count += 1
            continue
        delta = after - before if before is not None and after is not None else None
        changes.append({
            "field": f"portfolio_context.weights.{ticker}",
            "label": f"{ticker} 目标仓位", "before": before, "after": after,
            "unit": "%", "delta": round(delta, 1) if delta is not None else None,
            "delta_pct": None,
            "direction": "up" if delta is not None and delta > 0 else "down" if delta is not None and delta < 0 else "changed",
        })
    current_profile = current.get("research_profile_hash")
    previous_profile = previous.get("research_profile_hash")
    profile_changed = (
        current_profile != previous_profile
        or current.get("research_logic_hash") != previous.get("research_logic_hash")
    )
    if changes:
        labels = "、".join(item["label"] for item in changes[:3])
        headline = f"本次共有 {len(changes)} 项关键量化输入变化，重点是{labels}。"
    elif profile_changed:
        headline = "量化输入没有显著变化，但公司研究底稿版本已经更新。"
    else:
        headline = "关键量化输入与公司研究底稿均未发生显著变化。"
    return {
        "status": "changed" if changes or profile_changed else "unchanged",
        "current_snapshot_id": current_snapshot,
        "previous_snapshot_id": previous.get("generated_from", {}).get("snapshot_id"),
        "current_as_of": current.get("as_of"),
        "previous_as_of": previous.get("as_of"),
        "headline": headline,
        "changes": changes,
        "unchanged_count": unchanged_count,
        "research_profile_changed": profile_changed,
        "ai_narrative_status": "approved" if current.get("ai_narrative") else "pending_refresh_and_editorial_review",
    }


def latest_report_diff(
    ticker: str,
    current_snapshot_id: str,
    current_report: dict[str, Any],
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """SELECT snapshot_id, report_hash, report_json, created_at
               FROM research_report_versions
               WHERE ticker=? ORDER BY created_at DESC""",
            (ticker.upper(),),
        ).fetchall()
    previous = None
    current_hash = current_report.get("report_hash")
    for row in rows:
        if row["report_hash"] != current_hash:
            previous = json.loads(row["report_json"])
            break
    return compare_reports(current_report, previous)


def report_version_history(ticker: str, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """SELECT snapshot_id, report_hash, report_json, created_at
               FROM research_report_versions WHERE ticker=? ORDER BY created_at DESC""",
            (ticker.upper(),),
        ).fetchall()
    result = []
    for row in rows:
        report = json.loads(row["report_json"])
        result.append({
            "snapshot_id": row["snapshot_id"],
            "report_hash": row["report_hash"],
            "created_at": row["created_at"],
            "as_of": report.get("as_of"),
            "known_at": report.get("known_at"),
            "title": report.get("title"),
            "research_status": report.get("research_status"),
        })
    return result
