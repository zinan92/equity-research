"""Thin scheduling and audit layer over the canonical refresh state machine.

The module deliberately does not collect data or create snapshots itself.
It turns an authoritative list of expected trade dates into a refresh plan,
delegates execution to :class:`CanonicalResearchRefresh`, and saves one compact
receipt that proves ingestion, quality, raw-bound snapshot identity and replay.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .contracts import digest
from .research_refresh import CanonicalResearchRefresh
from .store import DataFoundation


SHANGHAI = ZoneInfo("Asia/Shanghai")
ORCHESTRATION_SCHEMA_VERSION = "snapshot-orchestration-v1"


@dataclass(frozen=True, order=True)
class CanonicalGap:
    trade_date: str
    ticker: str
    component: str
    detail: str


@dataclass(frozen=True)
class RefreshPlan:
    schema_version: str
    generated_at: str
    schedule_time: str
    due: bool
    mode: str
    eligible_trade_dates: tuple[str, ...]
    backfill_dates: tuple[str, ...]
    gaps: tuple[CanonicalGap, ...]
    reason: str

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["gaps"] = [asdict(gap) for gap in self.gaps]
        return value


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _eligible_dates(
    expected_trade_dates: Iterable[str], now: datetime, schedule_time: time
) -> tuple[str, ...]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("orchestration clock must be timezone-aware")
    local = now.astimezone(SHANGHAI)
    values = sorted(set(str(value) for value in expected_trade_dates))
    for value in values:
        datetime.fromisoformat(value)
    return tuple(
        value
        for value in values
        if datetime.fromisoformat(value).date() < local.date()
        or (
            datetime.fromisoformat(value).date() == local.date()
            and local.time() >= schedule_time
        )
    )


def detect_canonical_gaps(
    foundation: DataFoundation,
    *,
    universe: Iterable[str],
    expected_trade_dates: Iterable[str],
) -> tuple[CanonicalGap, ...]:
    """Find missing canonical identities without using a global maximum date.

    ``expected_trade_dates`` must come from the caller's authoritative calendar;
    this layer never invents a weekday calendar. A normal session needs status,
    adjustment factor and OHLCV. A suspended session needs status and factor but
    no synthetic zero-volume bar.
    """

    tickers = tuple(dict.fromkeys(str(ticker).upper() for ticker in universe))
    dates = tuple(sorted(set(str(value) for value in expected_trade_dates)))
    if not tickers or not dates:
        return ()
    foundation.initialize()
    gaps: list[CanonicalGap] = []
    with foundation.connect() as connection:
        instruments = {
            row["ticker"]: dict(row)
            for row in connection.execute(
                f"SELECT instrument_id, ticker, exchange FROM core_instruments "
                f"WHERE ticker IN ({','.join('?' for _ in tickers)})",
                tickers,
            ).fetchall()
        }
        for ticker in tickers:
            instrument = instruments.get(ticker)
            if not instrument:
                gaps.extend(
                    CanonicalGap(trade_date, ticker, "instrument", "canonical identity missing")
                    for trade_date in dates
                )
                continue
            instrument_id = instrument["instrument_id"]
            exchange = instrument["exchange"]
            for trade_date in dates:
                calendar = connection.execute(
                    "SELECT is_open FROM core_trading_calendar WHERE exchange=? AND trade_date=?",
                    (exchange, trade_date),
                ).fetchone()
                if not calendar or int(calendar["is_open"]) != 1:
                    gaps.append(CanonicalGap(trade_date, ticker, "calendar", "open-session row missing"))
                    continue
                status = connection.execute(
                    "SELECT trading_status FROM core_instrument_status "
                    "WHERE instrument_id=? AND trade_date=?",
                    (instrument_id, trade_date),
                ).fetchone()
                if not status:
                    gaps.append(CanonicalGap(trade_date, ticker, "status", "trading status missing"))
                    continue
                factor = connection.execute(
                    "SELECT 1 FROM core_adjustment_factors "
                    "WHERE instrument_id=? AND trade_date=? LIMIT 1",
                    (instrument_id, trade_date),
                ).fetchone()
                if not factor:
                    gaps.append(CanonicalGap(trade_date, ticker, "factor", "adjustment factor missing"))
                if status["trading_status"] == "normal":
                    bar = connection.execute(
                        "SELECT 1 FROM core_daily_bars WHERE instrument_id=? AND trade_date=? LIMIT 1",
                        (instrument_id, trade_date),
                    ).fetchone()
                    if not bar:
                        gaps.append(CanonicalGap(trade_date, ticker, "bar", "normal-session OHLCV missing"))
    return tuple(sorted(gaps))


def build_refresh_plan(
    foundation: DataFoundation,
    *,
    universe: Iterable[str],
    expected_trade_dates: Iterable[str],
    now: datetime,
    schedule_time: time = time(17, 30),
) -> RefreshPlan:
    eligible = _eligible_dates(expected_trade_dates, now, schedule_time)
    gaps = detect_canonical_gaps(
        foundation, universe=universe, expected_trade_dates=eligible
    )
    backfill_dates = tuple(sorted({gap.trade_date for gap in gaps}))
    mode = "idle"
    if backfill_dates:
        mode = "backfill" if len(backfill_dates) > 1 else "incremental"
    reason = (
        f"{len(gaps)} canonical gaps across {len(backfill_dates)} trade dates"
        if gaps
        else "canonical coverage complete for all eligible trade dates"
    )
    return RefreshPlan(
        schema_version=ORCHESTRATION_SCHEMA_VERSION,
        generated_at=now.isoformat(),
        schedule_time=schedule_time.isoformat(timespec="minutes"),
        due=bool(gaps),
        mode=mode,
        eligible_trade_dates=eligible,
        backfill_dates=backfill_dates,
        gaps=gaps,
        reason=reason,
    )


def snapshot_audit(foundation: DataFoundation, snapshot_id: str) -> dict[str, Any]:
    """Return a verified, raw-bound identity receipt for one frozen snapshot."""

    replay_digest = foundation.replay_digest(snapshot_id)
    with foundation.connect() as connection:
        row = connection.execute(
            "SELECT manifest_json, manifest_hash, quality_evaluation_id, quality_digest "
            "FROM core_snapshot_manifests WHERE snapshot_id=? AND quality_status='passed'",
            (snapshot_id,),
        ).fetchone()
        if not row:
            raise KeyError(snapshot_id)
        manifest = json.loads(row["manifest_json"])
    raw_hashes = tuple(manifest.get("raw_hashes") or ())
    if not raw_hashes or manifest.get("raw_hash_digest") != digest(list(raw_hashes)):
        raise RuntimeError("snapshot manifest does not explicitly bind valid raw hashes")
    return {
        "snapshot_id": snapshot_id,
        "manifest_hash": row["manifest_hash"],
        "quality_evaluation_id": row["quality_evaluation_id"],
        "quality_digest": row["quality_digest"],
        "raw_hashes": list(raw_hashes),
        "raw_hash_digest": manifest["raw_hash_digest"],
        "replay_digest": replay_digest,
        "replay_status": "passed",
    }


class SnapshotOrchestrator:
    """Schedule and audit the existing canonical refresh; never fork its state."""

    def __init__(self, refresh: CanonicalResearchRefresh) -> None:
        self.refresh = refresh

    def run(
        self,
        *,
        expected_trade_dates: Iterable[str],
        now: datetime,
        force: bool = False,
        interrupt_after: str | None = None,
    ) -> dict[str, Any]:
        plan = build_refresh_plan(
            self.refresh.foundation,
            universe=self.refresh.universe,
            expected_trade_dates=expected_trade_dates,
            now=now,
        )
        if not force and not plan.due:
            receipt = {
                "schema_version": ORCHESTRATION_SCHEMA_VERSION,
                "check_id": f"schedule_{digest(plan.as_json())[:16]}",
                "status": "skipped",
                "plan": plan.as_json(),
                "active": self.refresh.status().get("active"),
                "network_called": False,
            }
            receipt["receipt_hash"] = digest(receipt)
            _atomic_json(
                self.refresh.state_root / "schedule-checks" / f"{receipt['check_id']}.json",
                receipt,
            )
            _atomic_json(self.refresh.state_root / "orchestration-latest.json", receipt)
            return receipt
        result = self.refresh.run(now=now, interrupt_after=interrupt_after)
        canonical_status = result["status"]
        isolated_partial = canonical_status == "partial"
        active_preserved = result.get("active_preserved")
        error = result.get("error")
        if isolated_partial:
            active_preserved = self.refresh.status().get("active")
            error = (
                "canonical refresh blocked before activation: "
                f"{result.get('report_gate', {}).get('passed', 0)}/"
                f"{result.get('report_gate', {}).get('required', 0)} artifacts passed"
            )
        receipt: dict[str, Any] = {
            "schema_version": ORCHESTRATION_SCHEMA_VERSION,
            "run_id": result["run_id"],
            "status": "failed" if isolated_partial else canonical_status,
            "canonical_status": canonical_status,
            "canonical_stage": result.get("stage"),
            "plan": plan.as_json(),
            "selected_adapter": result.get("selected_adapter"),
            "attempts": result.get("attempts") or [],
            "ingestion_runs": result.get("ingestion_runs") or [],
            "quality_result": result.get("quality_result"),
            "previous_active": result.get("previous_active"),
            "active": result.get("active"),
            "active_preserved": active_preserved,
            "error": error,
        }
        if result.get("snapshot_id"):
            receipt["snapshot"] = snapshot_audit(
                self.refresh.foundation, result["snapshot_id"]
            )
        after = detect_canonical_gaps(
            self.refresh.foundation,
            universe=self.refresh.universe,
            expected_trade_dates=plan.eligible_trade_dates,
        )
        receipt["remaining_gaps"] = [asdict(gap) for gap in after]
        receipt["receipt_hash"] = digest(receipt)
        path = self.refresh.state_root / "runs" / result["run_id"] / "orchestration.json"
        _atomic_json(path, receipt)
        _atomic_json(self.refresh.state_root / "orchestration-latest.json", receipt)
        return receipt
