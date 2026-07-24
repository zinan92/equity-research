"""Bounded multi-ticker report task execution over immutable research inputs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Any, Callable, Iterable

from .local_cache import SQLiteReportTaskCache


REPORT_TASK_RUNTIME_VERSION = "park-report-task-runtime-v1"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class ReportTask:
    ticker: str
    snapshot_id: str
    evidence_manifest_hash: str

    def validate(self) -> None:
        if not self.ticker.strip() or not self.snapshot_id.strip():
            raise ValueError("report task ticker and snapshot identity are required")
        if len(self.evidence_manifest_hash) != 64 or any(char not in "0123456789abcdef" for char in self.evidence_manifest_hash):
            raise ValueError("report task evidence manifest must be SHA-256")

    @property
    def cache_key(self) -> str:
        self.validate()
        return _hash({"ticker": self.ticker.upper(), "snapshot_id": self.snapshot_id, "evidence_manifest_hash": self.evidence_manifest_hash})


@dataclass(frozen=True)
class ReportTaskResult:
    task: ReportTask
    status: str
    report_export_hash: str | None
    artifact: dict[str, Any] | None
    reason: str | None = None

    def validate(self) -> None:
        self.task.validate()
        if self.status not in {"completed", "partial", "failed", "reused"}:
            raise ValueError("unsupported report task status")
        if self.status in {"completed", "reused"} and (not self.report_export_hash or self.artifact is None):
            raise ValueError("completed task requires artifact and report export hash")
        if self.status in {"partial", "failed"} and not self.reason:
            raise ValueError("partial or failed task requires an explicit reason")


ReportTaskBuilder = Callable[[ReportTask], ReportTaskResult]


def _state_path(state_root: Path, batch_key: str) -> Path:
    return state_root / f"{batch_key}.json"


def _batch_key(tasks: tuple[ReportTask, ...]) -> str:
    return "report_batch_" + _hash([asdict(task) for task in tasks])[:40]


def _load_results(path: Path) -> dict[str, ReportTaskResult]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results") or []
    result: dict[str, ReportTaskResult] = {}
    for row in rows:
        task = ReportTask(**row["task"])
        item = ReportTaskResult(task, row["status"], row.get("report_export_hash"), row.get("artifact"), row.get("reason"))
        item.validate()
        result[task.cache_key] = item
    return result


def run_report_task_batch(
    tasks: Iterable[ReportTask], *, state_root: str | Path, cache: SQLiteReportTaskCache,
    builder: ReportTaskBuilder, max_concurrency: int = 1, min_interval_seconds: float = 0.0,
    sleep_fn: Callable[[float], None] = sleep,
) -> dict[str, Any]:
    """Run a deterministic queue and persist after every task for safe resume.

    Tasks are intentionally executed serially in canonical ticker order. The
    explicit concurrency parameter is validated and published in each receipt;
    future provider-safe parallelism may only use it after a separate rate-limit
    contract. This runner never hides a partial/failed task behind a report.
    """
    if type(max_concurrency) is not int or max_concurrency < 1:
        raise ValueError("max_concurrency must be a positive integer")
    if min_interval_seconds < 0:
        raise ValueError("min_interval_seconds must be nonnegative")
    canonical_tasks = tuple(sorted(tasks, key=lambda task: (task.ticker.upper(), task.snapshot_id, task.evidence_manifest_hash)))
    if not canonical_tasks:
        raise ValueError("report task batch cannot be empty")
    if len({task.cache_key for task in canonical_tasks}) != len(canonical_tasks):
        raise ValueError("report task batch contains duplicate immutable identities")
    for task in canonical_tasks:
        task.validate()

    root = Path(state_root)
    key = _batch_key(canonical_tasks)
    path = _state_path(root, key)
    previous = _load_results(path)
    results: dict[str, ReportTaskResult] = dict(previous)
    started_at = _now()
    executed = 0
    for task in canonical_tasks:
        task_key = task.cache_key
        prior = results.get(task_key)
        if prior and prior.status in {"completed", "reused"}:
            continue
        cached = cache.get(cache_key=task_key, ticker=task.ticker, snapshot_id=task.snapshot_id, evidence_manifest_hash=task.evidence_manifest_hash)
        if cached:
            item = ReportTaskResult(task, "reused", cached.report_export_hash, cached.artifact)
        else:
            try:
                item = builder(task)
                item.validate()
                if item.task != task:
                    raise ValueError("report builder returned another task identity")
                if item.status == "completed":
                    cache.put(cache_key=task_key, ticker=task.ticker, snapshot_id=task.snapshot_id, evidence_manifest_hash=task.evidence_manifest_hash, report_export_hash=str(item.report_export_hash), artifact=dict(item.artifact or {}))
            except Exception as exc:
                item = ReportTaskResult(task, "failed", None, None, f"{type(exc).__name__}: {exc}")
        results[task_key] = item
        executed += 1
        payload = _receipt(key, canonical_tasks, results, started_at, max_concurrency, min_interval_seconds, resumed=bool(previous))
        _write_atomic(path, payload)
        if min_interval_seconds and executed < len(canonical_tasks):
            sleep_fn(min_interval_seconds)
    payload = _receipt(key, canonical_tasks, results, started_at, max_concurrency, min_interval_seconds, resumed=bool(previous))
    _write_atomic(path, payload)
    return payload


def _receipt(batch_key: str, tasks: tuple[ReportTask, ...], results: dict[str, ReportTaskResult], started_at: str, max_concurrency: int, min_interval_seconds: float, *, resumed: bool) -> dict[str, Any]:
    ordered = [results.get(task.cache_key) or ReportTaskResult(task, "failed", None, None, "not_started") for task in tasks]
    counts = {status: sum(item.status == status for item in ordered) for status in ("completed", "partial", "failed", "reused")}
    if counts["failed"]:
        status = "partial"
    elif counts["partial"]:
        status = "partial"
    else:
        status = "completed"
    return {
        "schema_version": REPORT_TASK_RUNTIME_VERSION, "batch_key": batch_key,
        "started_at": started_at, "finished_at": _now(), "resumed": resumed,
        "execution": {"configured_max_concurrency": max_concurrency, "effective_concurrency": 1, "min_interval_seconds": min_interval_seconds, "queue_order": [task.ticker.upper() for task in tasks]},
        "status": status, "counts": counts,
        "results": [{"task": asdict(item.task), "status": item.status, "report_export_hash": item.report_export_hash, "artifact": item.artifact, "reason": item.reason} for item in ordered],
    }
