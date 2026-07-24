"""Deterministic, local observability receipts for canonical research refreshes.

This module consumes existing refresh receipts.  It never sends telemetry or
raw provider bodies outside the product runtime.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .contracts import digest


OBSERVABILITY_SCHEMA_VERSION = "source-observability-v1"


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def build_source_health(
    attempts: Iterable[dict[str, Any]],
    *,
    selected_adapter: str | None,
    required_tickers: Iterable[str],
    now: datetime,
    maximum_age: timedelta = timedelta(days=1),
) -> list[dict[str, Any]]:
    """Summarize source attempts without treating fallback failure as coverage loss.

    Coverage impact is only assigned to the selected source.  An unselected
    primary failure that was successfully recovered by an explicit fallback is
    visible as degraded but has zero required-coverage impact.
    """
    if now.tzinfo is None:
        raise ValueError("observability clock must be timezone-aware")
    expected = sorted({str(ticker).upper() for ticker in required_tickers})
    grouped: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        adapter = attempt.get("adapter")
        if isinstance(adapter, str) and adapter:
            grouped.setdefault(adapter, []).append(attempt)
    health: list[dict[str, Any]] = []
    for adapter in sorted(grouped):
        rows = grouped[adapter]
        latest = rows[-1]
        succeeded = any(row.get("status") == "success" for row in rows)
        selected = adapter == selected_adapter
        data_kind = next((row.get("data_kind") for row in reversed(rows) if row.get("data_kind")), None)
        target_date = next((row.get("target_trade_date") for row in reversed(rows) if row.get("target_trade_date")), None)
        freshness_at = None
        stale = False
        if isinstance(target_date, str):
            try:
                freshness_at = datetime.fromisoformat(target_date).replace(tzinfo=timezone.utc)
                stale = freshness_at < now.astimezone(timezone.utc) - maximum_age
            except ValueError:
                stale = True
        production_eligible = data_kind == "real"
        impact = expected if selected and (not succeeded or stale or not production_eligible) else []
        health.append({
            "adapter": adapter,
            "role": latest.get("role"),
            "selected": selected,
            "availability": "available" if succeeded else "failed",
            "last_success_at": next((row.get("finished_at") for row in reversed(rows) if row.get("status") == "success"), None),
            "freshness_at": _iso(freshness_at) if freshness_at else None,
            "freshness": "stale" if stale else "fresh" if freshness_at else "unknown",
            "data_kind": data_kind,
            "production_eligible": production_eligible,
            "consecutive_failures": 0 if succeeded else len(rows),
            "affected_required_tickers": impact,
            "coverage_impact": len(impact),
        })
    return health


def build_run_trace(
    receipt: dict[str, Any],
    *,
    required_tickers: Iterable[str],
    now: datetime,
) -> dict[str, Any]:
    """Create an identity-only trace joined to source health and snapshot evidence."""
    health = build_source_health(
        receipt.get("attempts") or [],
        selected_adapter=receipt.get("selected_adapter"),
        required_tickers=required_tickers,
        now=now,
    )
    selected = next((item for item in health if item["selected"]), None)
    production_healthy = bool(
        receipt.get("status") in {"success", "reused"}
        and selected
        and selected["availability"] == "available"
        and selected["freshness"] == "fresh"
        and selected["production_eligible"]
        and selected["coverage_impact"] == 0
        and ((receipt.get("snapshot") or {}).get("snapshot_id") or receipt.get("active", {}).get("snapshot_id"))
    )
    trace = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "run_id": receipt.get("run_id"),
        "canonical_status": receipt.get("canonical_status", receipt.get("status")),
        "selected_adapter": receipt.get("selected_adapter"),
        "snapshot_id": (receipt.get("snapshot") or {}).get("snapshot_id") or (receipt.get("active") or {}).get("snapshot_id"),
        "evidence_manifest_hash": ((receipt.get("snapshot") or {}).get("manifest_hash")),
        "source_health": health,
        "production_health": "healthy" if production_healthy else "attention",
        "generated_at": _iso(now),
    }
    trace["trace_hash"] = digest(trace)
    return trace


def alert_candidates(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Only material, required-coverage or non-production selected-source states alert."""
    candidates = []
    for source in trace.get("source_health") or []:
        if not source.get("selected"):
            continue
        reasons = []
        if source["availability"] != "available":
            reasons.append("source_unavailable")
        if source["freshness"] in {"stale", "unknown"}:
            reasons.append("source_stale")
        if not source["production_eligible"]:
            reasons.append("non_production_source")
        if not reasons:
            continue
        impact = int(source.get("coverage_impact") or 0)
        candidates.append({
            "alert_key": f"{source['adapter']}:{'+'.join(reasons)}",
            "adapter": source["adapter"],
            "reasons": reasons,
            "severity": "critical" if impact else "warning",
            "coverage_impact": impact,
            "affected_required_tickers": source.get("affected_required_tickers") or [],
            "trace_hash": trace["trace_hash"],
        })
    return candidates


class SourceObservabilityLedger:
    """Persist deduplicated alert lifecycle receipts under the existing runtime root."""

    def __init__(self, state_root: Path) -> None:
        self.path = state_root / "observability" / "source-alerts.json"

    def record(self, receipt: dict[str, Any], *, required_tickers: Iterable[str], now: datetime) -> dict[str, Any]:
        trace = build_run_trace(receipt, required_tickers=required_tickers, now=now)
        previous = _load_json(self.path) or {"alerts": []}
        prior = {item["alert_key"]: item for item in previous.get("alerts") or [] if isinstance(item, dict) and item.get("alert_key")}
        current = {item["alert_key"]: item for item in alert_candidates(trace)}
        timestamp = _iso(now)
        alerts = []
        for key in sorted(set(prior) | set(current)):
            before, candidate = prior.get(key), current.get(key)
            if candidate:
                alerts.append({
                    **candidate,
                    "status": "open",
                    "opened_at": before.get("opened_at", timestamp) if before else timestamp,
                    "last_seen_at": timestamp,
                    "recovered_at": None,
                })
            elif before and before.get("status") == "open":
                alerts.append({**before, "status": "recovered", "recovered_at": timestamp, "last_seen_at": timestamp})
            elif before:
                alerts.append(before)
        result = {"schema_version": OBSERVABILITY_SCHEMA_VERSION, "trace": trace, "alerts": alerts}
        result["receipt_hash"] = digest(result)
        _atomic_json(self.path, result)
        return result
