"""Versioned slow/periodic/fast cadence policy over existing refresh receipts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Mapping


RESEARCH_CADENCE_SCHEMA_VERSION = "research-cadence-v1"


@dataclass(frozen=True)
class CadenceLane:
    name: str
    refresh_after: timedelta
    stale_after: timedelta
    dependencies: tuple[str, ...]


LANES = (
    CadenceLane("slow", timedelta(days=30), timedelta(days=45), ("official_filings", "industry_positions", "evidence_gate")),
    CadenceLane("periodic", timedelta(days=1), timedelta(days=3), ("pit_financials", "sell_side", "evidence_gate")),
    CadenceLane("fast", timedelta(hours=18), timedelta(days=2), ("market_snapshot", "events", "evidence_gate")),
)


def build_cadence_plan(*, now: datetime, last_good: Mapping[str, datetime | None]) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("cadence clock must be timezone-aware")
    rows = []
    for lane in LANES:
        completed_at = last_good.get(lane.name)
        if completed_at is not None and (completed_at.tzinfo is None or completed_at.utcoffset() is None):
            raise ValueError("last-good timestamp must be timezone-aware")
        age = now - completed_at if completed_at is not None else None
        state = "missing" if age is None else "stale" if age > lane.stale_after else "due" if age >= lane.refresh_after else "fresh"
        rows.append({**asdict(lane), "refresh_after_seconds": int(lane.refresh_after.total_seconds()), "stale_after_seconds": int(lane.stale_after.total_seconds()), "last_good_at": completed_at.isoformat() if completed_at else None, "state": state})
    return {"schema_version": RESEARCH_CADENCE_SCHEMA_VERSION, "generated_at": now.isoformat(), "lanes": rows, "truth_boundary": {"policy_only": True, "does_not_replace_snapshot_orchestrator": True, "failed_run_must_preserve_last_good": True}}
