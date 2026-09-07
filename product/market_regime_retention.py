"""Bounded retention for the Market Regime runtime.

The pruner only removes immutable objects in the four explicitly managed
directories.  Pointer and receipt files are never removed; their references
form the keep graph for objects that are otherwise older than the retention
window.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


RETENTION_SCHEMA_VERSION = "market-regime-prune-v1"
MANAGED_PREFIXES = (
    "intraday/snapshots/",
    "intraday/normalized/",
    "intraday/raw/",
    "api/artifacts/",
)
DEFAULT_RETENTION_DAYS = 14
_TEMP_FILE = re.compile(r"^\.[^/]+\..+$")
_TIMESTAMP_FIELDS = ("completed_at", "generated_at", "started_at", "observed_at")


class MarketRegimeRetentionError(RuntimeError):
    """The runtime retention contract cannot be evaluated safely."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _payload_time(payload: Mapping[str, Any]) -> datetime | None:
    for field in _TIMESTAMP_FIELDS:
        parsed = _parse_time(payload.get(field))
        if parsed is not None:
            return parsed
    return None


def _json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _strings(nested)


def _normalise_reference(root: Path, value: str) -> str | None:
    candidate = value.replace("\\", "/")
    if candidate.startswith("/"):
        return None
    candidate = candidate.lstrip("./")
    if ".." in Path(candidate).parts:
        return None
    if not any(candidate.startswith(prefix) for prefix in MANAGED_PREFIXES):
        return None
    target = (root / candidate).resolve()
    if root not in target.parents:
        return None
    return candidate


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def runtime_bytes(root: Path | str) -> int:
    resolved = Path(root).expanduser().resolve()
    total = 0
    if not resolved.exists():
        return 0
    for path in resolved.rglob("*"):
        if path.is_file() and not path.is_symlink():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


class MarketRegimeRetention:
    def __init__(
        self,
        root: Path | str,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        clock=_utc_now,
    ) -> None:
        if retention_days < 1:
            raise MarketRegimeRetentionError("retention_days must be at least 1")
        self.root = Path(root).expanduser().resolve()
        self.retention_days = retention_days
        self.clock = clock

    def _source_files(self) -> list[tuple[Path, Any]]:
        files: list[tuple[Path, Any]] = []
        candidates = [
            self.root / "latest.json",
            self.root / "intraday" / "latest.json",
            self.root / "api" / "latest.json",
        ]
        for directory in (self.root / "runs", self.root / "intraday" / "runs"):
            candidates.extend(sorted(directory.glob("*.json")))
        for directory in (self.root / "run-events", self.root / "intraday" / "run-events"):
            candidates.extend(sorted(directory.glob("*/*.json")))
        cutoff = self.clock().astimezone(timezone.utc) - timedelta(days=self.retention_days)
        result: list[tuple[Path, Any]] = []
        for path in candidates:
            payload = _json(path)
            if payload is None:
                continue
            relative = _relative(path, self.root)
            if relative in {"latest.json", "intraday/latest.json", "api/latest.json"}:
                result.append((path, payload))
                continue
            if relative.startswith("runs/") or relative.startswith("intraday/runs/") or relative.startswith("run-events/") or relative.startswith("intraday/run-events/"):
                timestamp = _payload_time(payload) if isinstance(payload, Mapping) else None
                if timestamp is None:
                    # An unreadable timestamp is not evidence that an object is old.
                    result.append((path, payload))
                elif timestamp >= cutoff:
                    result.append((path, payload))
        return result

    def _keep_paths(self) -> set[str]:
        keep: set[str] = set()
        for _, payload in self._source_files():
            for value in _strings(payload):
                reference = _normalise_reference(self.root, value)
                if reference:
                    keep.add(reference)
        return keep

    def _recent_run_ids(self) -> set[str]:
        ids: set[str] = set()
        cutoff = self.clock().astimezone(timezone.utc) - timedelta(days=self.retention_days)
        for path, payload in self._source_files():
            relative = _relative(path, self.root)
            if "/runs/" not in f"/{relative}" and "/run-events/" not in f"/{relative}":
                continue
            timestamp = _payload_time(payload) if isinstance(payload, Mapping) else None
            if timestamp is None or timestamp >= cutoff:
                if isinstance(payload, Mapping) and payload.get("run_id"):
                    ids.add(str(payload["run_id"]))
                elif path.parent.name not in {"runs", "run-events"}:
                    ids.add(path.parent.name)
        return ids

    @staticmethod
    def _run_id_for(relative: str) -> str | None:
        parts = relative.split("/")
        if len(parts) >= 3 and parts[0] in {"raw", "normalized"}:
            return parts[1]
        if len(parts) >= 4 and parts[0] == "intraday" and parts[1] in {"raw", "normalized"}:
            return parts[2]
        return None

    def _candidates(self) -> list[tuple[Path, os.stat_result]]:
        keep = self._keep_paths()
        recent_ids = self._recent_run_ids()
        candidates: list[tuple[Path, os.stat_result]] = []
        for prefix in MANAGED_PREFIXES:
            directory = self.root / prefix
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if not path.is_file() or path.is_symlink() or _TEMP_FILE.match(path.name):
                    continue
                relative = _relative(path, self.root)
                if relative in keep:
                    continue
                # Raw/normalized objects are grouped by run id. A recent run
                # is retained even when no pointer currently names every file.
                if self._run_id_for(relative) in recent_ids:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                candidates.append((path, stat))
        return candidates

    def plan(self) -> dict[str, Any]:
        now = self.clock().astimezone(timezone.utc)
        candidates = self._candidates()
        deletions = [
            {"path": _relative(path, self.root), "bytes": stat.st_size}
            for path, stat in candidates
        ]
        return {
            "schema_version": RETENTION_SCHEMA_VERSION,
            "root": str(self.root),
            "retention_days": self.retention_days,
            "cutoff_at": (now - timedelta(days=self.retention_days)).isoformat().replace("+00:00", "Z"),
            "planned_delete_count": len(deletions),
            "planned_delete_bytes": sum(item["bytes"] for item in deletions),
            "deletions": deletions,
            "runtime_bytes_before": runtime_bytes(self.root),
        }

    def prune(self, *, dry_run: bool = True) -> dict[str, Any]:
        plan = self.plan()
        if dry_run:
            return {**plan, "dry_run": True, "deleted_count": 0, "deleted_bytes": 0}
        deleted: list[dict[str, Any]] = []
        for item in plan["deletions"]:
            path = self.root / item["path"]
            try:
                current = path.stat()
                original = next(item for candidate, item in self._candidates() if candidate == path)
                if (current.st_ino, current.st_size, current.st_mtime_ns) != (
                    original.st_ino,
                    original.st_size,
                    original.st_mtime_ns,
                ):
                    continue
                path.unlink()
            except (FileNotFoundError, OSError, StopIteration):
                continue
            deleted.append(item)
        result = {
            **plan,
            "dry_run": False,
            "deleted_count": len(deleted),
            "deleted_bytes": sum(item["bytes"] for item in deleted),
            "deleted": deleted,
            "runtime_bytes_after": runtime_bytes(self.root),
            "completed_at": self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        return result


def prune_market_regime_runtime(root: Path | str, *, retention_days: int = DEFAULT_RETENTION_DAYS, dry_run: bool = True) -> dict[str, Any]:
    return MarketRegimeRetention(root, retention_days=retention_days).prune(dry_run=dry_run)
