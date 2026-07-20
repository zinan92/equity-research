from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from data_store import DB_PATH, DEMO_POSITIONS, dashboard_payload, initialize
from refresh_engine import run_refresh
from report_versions import archive_report, report_version_history
from research_reports import report_payload


BATCH_SCHEMA_VERSION = "research-batch-v1"
BATCH_ROOT = DB_PATH.parent / "research_batches"
ReportBuilder = Callable[..., dict[str, Any] | None]
ArtifactWriter = Callable[[Path, dict[str, Any]], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _active_identity(db_path: Path) -> dict[str, Any]:
    dashboard = dashboard_payload(db_path)
    return {
        "snapshot_id": dashboard["snapshot"]["id"],
        "publication_id": dashboard["publication"]["id"],
        "data_mode": dashboard["snapshot"]["data_mode"],
        "snapshot_quality": dashboard["snapshot"]["quality_status"],
        "publication_status": dashboard["publication"]["status"],
    }


def _resolve_tickers(requested: Iterable[str] | None) -> list[tuple[str, str]]:
    catalogue = {item["ticker"]: item["name"] for item in DEMO_POSITIONS}
    tickers = [str(ticker).upper() for ticker in requested] if requested else list(catalogue)
    unknown = [ticker for ticker in tickers if ticker not in catalogue]
    if unknown:
        raise ValueError(f"unsupported batch ticker(s): {', '.join(unknown)}")
    if len(tickers) != len(set(tickers)):
        raise ValueError("batch ticker list contains duplicates")
    if set(tickers) != set(catalogue) or len(tickers) != len(catalogue):
        raise ValueError("a production research batch must contain the exact configured eight-stock universe")
    return [(ticker, catalogue[ticker]) for ticker in tickers]


@contextmanager
def _process_batch_lock(db_path: Path):
    lock_path = db_path.with_suffix(f"{db_path.suffix}.batch.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another research batch is already running") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _batch_id(snapshot_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_tail = snapshot_id.removeprefix("snap_")[:18]
    return f"batch_{stamp}_{snapshot_tail}_{uuid.uuid4().hex[:6]}"


def _materialize_one(
    ticker: str,
    name: str,
    snapshot_id: str,
    db_path: Path,
    batch_dir: Path,
    report_builder: ReportBuilder,
    artifact_writer: ArtifactWriter,
    publication_id: str,
) -> dict[str, Any]:
    existing_hashes = {item["report_hash"] for item in report_version_history(ticker, db_path)}
    try:
        report = report_builder(ticker, db_path, snapshot_id=snapshot_id)
        if not report:
            raise RuntimeError("report builder returned no report")
        verified_deep = report.get("research_status") == "verified"
        verified_baseline = report.get("research_status") == "baseline" and report.get("data_status") == "verified"
        if not (verified_deep or verified_baseline):
            return {
                "ticker": ticker, "name": name, "status": "blocked",
                "research_status": report.get("research_status"),
                "research_depth": report.get("research_depth"),
                "error": report.get("message") or "report did not pass research gate",
            }
        generated_from = report.get("generated_from") or {}
        if report.get("ticker") != ticker:
            raise RuntimeError(f"report ticker identity mismatch: expected {ticker}, got {report.get('ticker')}")
        if report.get("name") != name:
            raise RuntimeError(f"report company identity mismatch: expected {name}, got {report.get('name')}")
        if generated_from.get("snapshot_id") != snapshot_id:
            raise RuntimeError("report snapshot identity mismatch")
        if generated_from.get("publication_id") != publication_id:
            raise RuntimeError("report publication identity mismatch")
        if report.get("data_mode") != "REAL":
            raise RuntimeError("report data mode is not REAL")
        artifact_path = batch_dir / "reports" / f"{ticker}.json"
        artifact_writer(artifact_path, report)
        try:
            archive = archive_report(report, db_path)
        except Exception:
            artifact_path.unlink(missing_ok=True)
            raise
        return {
            "ticker": ticker, "name": name,
            "status": "reused" if archive["report_hash"] in existing_hashes else "success",
            "research_status": report["research_status"], "research_depth": report["research_depth"],
            "report_hash": archive["report_hash"], "version_created_at": archive["created_at"],
            "artifact_path": str(artifact_path), "error": None,
        }
    except Exception as exc:
        return {
            "ticker": ticker, "name": name, "status": "failed",
            "research_status": None, "research_depth": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _run_batch_unlocked(
    db_path: Path = DB_PATH,
    *,
    tickers: Iterable[str] | None = None,
    refresh: bool = True,
    timeout: float = 12.0,
    output_root: Path | None = None,
    report_builder: ReportBuilder = report_payload,
    refresh_runner: Callable[..., dict[str, Any]] = run_refresh,
    artifact_writer: ArtifactWriter = _write_json_atomic,
) -> dict[str, Any]:
    """Refresh once, then independently materialize every requested research report."""
    initialize(db_path)
    requested = _resolve_tickers(tickers)
    root = output_root or (db_path.parent / "research_batches")
    started_at = _now()
    refresh_result: dict[str, Any] | None = None
    identity: dict[str, Any]
    try:
        if refresh:
            refresh_result = refresh_runner(db_path, ticker="300750.SZ", timeout=timeout)
        identity = _active_identity(db_path)
        if refresh_result and identity["snapshot_id"] != refresh_result.get("snapshot_id"):
            raise RuntimeError("active snapshot does not match refresh result")
        if identity["data_mode"] != "REAL" or identity["snapshot_quality"] != "passed":
            raise RuntimeError("active snapshot is not a quality-passed REAL snapshot")
        if identity["publication_status"] not in {"quality_passed", "approved", "published"}:
            raise RuntimeError("active publication has not passed the quality gate")
    except Exception as exc:
        batch_id = _batch_id("snapshot_unavailable")
        batch_dir = root / batch_id
        receipt = {
            "schema_version": BATCH_SCHEMA_VERSION, "batch_id": batch_id,
            "started_at": started_at, "finished_at": _now(), "status": "failed",
            "snapshot_id": None, "publication_id": None,
            "refresh": refresh_result or {"status": "failed", "error": f"{type(exc).__name__}: {exc}"},
            "requested_count": len(requested), "success_count": 0, "reused_count": 0,
            "blocked_count": 0, "failed_count": len(requested), "reports": [],
            "quality_gate": {"status": "failed", "reason": "data refresh or active snapshot identity failed"},
        }
        receipt["index_path"] = str(batch_dir / "index.json")
        _write_json_atomic(Path(receipt["index_path"]), receipt)
        _write_json_atomic(root / "latest.json", receipt)
        return receipt

    batch_id = _batch_id(identity["snapshot_id"])
    batch_dir = root / batch_id
    reports = [
        _materialize_one(
            ticker, name, identity["snapshot_id"], db_path, batch_dir, report_builder,
            artifact_writer, identity["publication_id"],
        )
        for ticker, name in requested
    ]
    counts = {status: sum(item["status"] == status for item in reports) for status in ("success", "reused", "blocked", "failed")}
    complete = counts["success"] + counts["reused"] == len(requested)
    receipt = {
        "schema_version": BATCH_SCHEMA_VERSION, "batch_id": batch_id,
        "started_at": started_at, "finished_at": _now(), "status": "success" if complete else "partial",
        "snapshot_id": identity["snapshot_id"], "publication_id": identity["publication_id"],
        "refresh": refresh_result or {"status": "skipped", "reason": "materialized from active immutable snapshot"},
        "requested_count": len(requested), "success_count": counts["success"], "reused_count": counts["reused"],
        "blocked_count": counts["blocked"], "failed_count": counts["failed"], "reports": reports,
        "quality_gate": {
            "status": "passed" if complete else "failed",
            "required_reports": len(requested), "verified_reports": counts["success"] + counts["reused"],
        },
    }
    receipt["index_path"] = str(batch_dir / "index.json")
    _write_json_atomic(Path(receipt["index_path"]), receipt)
    _write_json_atomic(root / "latest.json", receipt)
    return receipt


def run_batch(
    db_path: Path = DB_PATH,
    *,
    tickers: Iterable[str] | None = None,
    refresh: bool = True,
    timeout: float = 12.0,
    output_root: Path | None = None,
    report_builder: ReportBuilder = report_payload,
    refresh_runner: Callable[..., dict[str, Any]] = run_refresh,
    artifact_writer: ArtifactWriter = _write_json_atomic,
) -> dict[str, Any]:
    with _process_batch_lock(db_path):
        return _run_batch_unlocked(
            db_path, tickers=tickers, refresh=refresh, timeout=timeout,
            output_root=output_root, report_builder=report_builder,
            refresh_runner=refresh_runner, artifact_writer=artifact_writer,
        )


def latest_batch(db_path: Path = DB_PATH, output_root: Path | None = None) -> dict[str, Any] | None:
    path = (output_root or (db_path.parent / "research_batches")) / "latest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the first eight A-share research reports from one snapshot")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--ticker", action="append", dest="tickers", help="limit the batch; repeat for multiple tickers")
    parser.add_argument("--no-refresh", action="store_true", help="reuse the active quality-passed immutable snapshot")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_batch(
        args.db, tickers=args.tickers, refresh=not args.no_refresh,
        timeout=args.timeout, output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
