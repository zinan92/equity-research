from __future__ import annotations

import json
import fcntl
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from data_store import DB_PATH, connect, dashboard_payload, initialize
from real_pipeline import build_real_snapshot
from report_versions import archive_report, compare_reports
from research_reports import report_payload
from research_evidence import build_evidence_set, load_evidence_set


SnapshotBuilder = Callable[..., dict[str, Any]]


class RefreshInProgressError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verified_report(ticker: str, db_path: Path) -> dict[str, Any] | None:
    report = report_payload(ticker, db_path)
    return report if report and report.get("research_status") == "verified" else None


def _record_start(db_path: Path, run_id: str, previous_snapshot_id: str | None) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """INSERT INTO refresh_runs
               (id, started_at, finished_at, status, previous_snapshot_id, result_snapshot_id,
                publication_id, manifest_hash, error_summary)
               VALUES (?, ?, NULL, 'running', ?, NULL, NULL, NULL, NULL)""",
            (run_id, _now(), previous_snapshot_id),
        )
        conn.commit()


def _finish_run(db_path: Path, run_id: str, status: str, result: dict[str, Any] | None, error: str | None = None) -> None:
    snapshot_id = result.get("snapshot_id") if result else None
    publication_id = result.get("publication_id") if result else None
    with closing(connect(db_path)) as conn:
        manifest_row = conn.execute(
            "SELECT manifest_hash FROM dataset_snapshots WHERE id=?",
            (snapshot_id,),
        ).fetchone() if snapshot_id else None
        manifest_hash = manifest_row["manifest_hash"] if manifest_row else None
        conn.execute(
            """UPDATE refresh_runs SET finished_at=?, status=?, result_snapshot_id=?,
               publication_id=?, manifest_hash=?, error_summary=? WHERE id=?""",
            (_now(), status, snapshot_id, publication_id, manifest_hash, error, run_id),
        )
        conn.commit()


def _snapshot_ids(db_path: Path) -> set[str]:
    with closing(connect(db_path)) as conn:
        return {row["id"] for row in conn.execute("SELECT id FROM dataset_snapshots").fetchall()}


def _quarantine_new_snapshots(db_path: Path, known_snapshot_ids: set[str]) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """SELECT p.id AS publication_id, p.snapshot_id
               FROM publications p JOIN dataset_snapshots s ON s.id=p.snapshot_id
               ORDER BY s.created_at DESC"""
        ).fetchall()
        owned = [row for row in rows if row["snapshot_id"] not in known_snapshot_ids]
        for row in owned:
            conn.execute(
                "UPDATE publications SET status='blocked', blocked_reason='refresh failed after snapshot write' WHERE id=?",
                (row["publication_id"],),
            )
            conn.execute(
                "UPDATE dataset_snapshots SET quality_status='blocked' WHERE id=?",
                (row["snapshot_id"],),
            )
        conn.commit()
        return dict(owned[0]) if owned else None


@contextmanager
def _process_refresh_lock(db_path: Path):
    lock_path = db_path.with_suffix(f"{db_path.suffix}.refresh.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RefreshInProgressError("another refresh process is already running") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _run_refresh_locked(
    db_path: Path = DB_PATH,
    *,
    ticker: str = "300750.SZ",
    timeout: float = 10.0,
    builder: SnapshotBuilder = build_real_snapshot,
) -> dict[str, Any]:
    """Run one fail-closed update from collection through versioned report diff."""
    initialize(db_path)
    before_dashboard = dashboard_payload(db_path)
    previous_snapshot_id = before_dashboard["snapshot"]["id"]
    known_snapshot_ids = _snapshot_ids(db_path)
    previous_report = _verified_report(ticker, db_path)
    if previous_report:
        archive_report(previous_report, db_path)

    run_id = f"refresh_{uuid.uuid4().hex[:12]}"
    _record_start(db_path, run_id, previous_snapshot_id)
    try:
        try:
            result = builder(db_path, timeout=timeout)
        except Exception as first_error:
            transient = any(
                marker in f"{type(first_error).__name__}: {first_error}".lower()
                for marker in ("urlerror", "ssl", "timeout", "tempor", "coverage")
            )
            if not transient:
                raise
            time.sleep(0.6)
            result = builder(db_path, timeout=timeout)
        with closing(connect(db_path)) as conn:
            identity = conn.execute(
                """SELECT p.snapshot_id, p.status AS publication_status,
                          s.quality_status AS snapshot_status
                   FROM publications p JOIN dataset_snapshots s ON s.id=p.snapshot_id
                   WHERE p.id=?""",
                (result.get("publication_id"),),
            ).fetchone()
        if (
            not identity
            or identity["snapshot_id"] != result.get("snapshot_id")
            or identity["publication_status"] not in {"quality_passed", "approved", "published"}
            or identity["snapshot_status"] != "passed"
        ):
            raise RuntimeError("builder result is not an active quality-passed snapshot/publication pair")
        after_dashboard = dashboard_payload(db_path)
        if (
            after_dashboard["snapshot"]["id"] != result.get("snapshot_id")
            or after_dashboard["publication"]["id"] != result.get("publication_id")
        ):
            raise RuntimeError("builder result does not match the active dashboard version")
        if ticker.upper() == "300750.SZ":
            evidence_set = load_evidence_set(ticker, result["snapshot_id"], db_path)
            if not evidence_set:
                evidence_set = build_evidence_set(ticker, result["snapshot_id"], db_path, knowledge_cutoff=_now())
            if evidence_set["status"] != "passed":
                raise RuntimeError(f"company evidence gate failed for refreshed snapshot: {evidence_set['gate']['failures']}")
        current_report = report_payload(ticker, db_path, snapshot_id=result["snapshot_id"])
        if not current_report:
            raise RuntimeError("refresh produced no verified deterministic report")
        if current_report.get("generated_from", {}).get("snapshot_id") != result.get("snapshot_id"):
            raise RuntimeError("report snapshot identity does not match builder result")
        archive = archive_report(current_report, db_path)
        diff = compare_reports(current_report, previous_report if previous_report and previous_report["generated_from"]["snapshot_id"] != current_report["generated_from"]["snapshot_id"] else None)
        status = "reused" if result.get("reused") else "success"
        _finish_run(db_path, run_id, status, result)
        return {
            "run_id": run_id,
            "status": status,
            "snapshot_id": result["snapshot_id"],
            "publication_id": result["publication_id"],
            "previous_snapshot_id": previous_snapshot_id,
            "reused": bool(result.get("reused")),
            "report_version": archive,
            "update_diff": diff,
            "deepseek_status": "pending_refresh_and_editorial_review" if not current_report.get("ai_narrative") else "approved",
        }
    except Exception as exc:
        quarantined = _quarantine_new_snapshots(db_path, known_snapshot_ids)
        message = f"{type(exc).__name__}: {exc}"
        _finish_run(db_path, run_id, "failed", quarantined, message[:1000])
        raise RuntimeError(f"research refresh failed closed; previous snapshot preserved: {message}") from exc


def run_refresh(
    db_path: Path = DB_PATH,
    *,
    ticker: str = "300750.SZ",
    timeout: float = 10.0,
    builder: SnapshotBuilder = build_real_snapshot,
) -> dict[str, Any]:
    """Run one cross-process serialized, fail-closed research update."""
    with _process_refresh_lock(db_path):
        return _run_refresh_locked(db_path, ticker=ticker, timeout=timeout, builder=builder)


def refresh_status(db_path: Path = DB_PATH, limit: int = 10) -> dict[str, Any]:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """SELECT id, started_at, finished_at, status, previous_snapshot_id,
                      result_snapshot_id, publication_id, manifest_hash, error_summary
               FROM refresh_runs ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return {"runs": [dict(row) for row in rows]}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Refresh the A-share research product and archive the report diff")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--ticker", default="300750.SZ")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    try:
        result = run_refresh(args.db, ticker=args.ticker, timeout=args.timeout)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
