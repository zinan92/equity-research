"""Downstream Daily v2 runtime and read-only API projections."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
from pathlib import Path
import os
import re
import tempfile
import time
from typing import Any, Callable, Mapping
from uuid import uuid4

from data_core.market_regime_daily_bundle import (
    MarketRegimeDailyBundleError,
    MarketRegimeDailyBundleRace,
    MarketRegimeDailyBundleStore,
)
from data_core.market_regime_daily_evidence import MarketRegimeDailyEvidenceStore
from data_core.market_regime_daily_narrative import (
    DeepSeekNarrativeProvider,
    MarketRegimeDailyNarrativeStore,
    NarrativeProvider,
)


DAILY_RUNTIME_SCHEMA_VERSION = "market-regime-daily-runtime-v1"
DAILY_HEALTH_SCHEMA_VERSION = "market-regime-daily-health-v1"
DAILY_STATUS_SCHEMA_VERSION = "market-regime-daily-status-v1"
DAILY_SCHEDULER_LOCK_RETRY_SECONDS = 30
ALLOWED_INTERVAL_HOURS = (4, 12)
STATUS_KEYS = frozenset(
    {
        "schema_version", "state", "attempt_id", "attempted_at",
        "last_success_at", "last_success_bundle_id", "served_bundle_id",
        "candidate_pack_id", "candidate_narrative_id", "candidate_bundle_id",
        "last_failure", "next_due_at", "interval_hours",
    }
)
FAILURE_CODES = frozenset(
    {
        "candidate_advanced", "bundle_integrity_failed", "bundle_validation_failed",
        "evidence_unavailable", "narrative_unavailable", "bundle_unavailable",
        "evidence_compile_failed", "narrative_compile_failed", "bundle_publish_failed",
        "daily_runtime_failed",
    }
)
FAILURE_PHASES = frozenset({"evidence", "narrative", "bundle"})
SECRET_LABEL_RE = re.compile(r"(?:sk-(?:live|test)-[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")


class MarketRegimeDailyRuntimeError(RuntimeError):
    """A Daily runtime status, bundle, or publication operation failed."""


def market_regime_daily_root(root: Path | str | None = None) -> Path:
    base = Path(root or os.getenv("PARK_MARKET_REGIME_ROOT", Path(__file__).resolve().parent / "runtime" / "market-regime"))
    return base.expanduser().resolve() / "daily-v2"


def configured_daily_interval_hours(value: int | str | None = None) -> int:
    raw = value if value is not None else os.getenv("PARK_MARKET_REGIME_INTERVAL_HOURS", "4")
    try:
        interval = int(raw)
    except (TypeError, ValueError) as exc:
        raise MarketRegimeDailyRuntimeError("daily interval must be 4 or 12 hours") from exc
    if interval not in ALLOWED_INTERVAL_HOURS:
        raise MarketRegimeDailyRuntimeError("daily interval must be 4 or 12 hours")
    return interval


def _canonical_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise MarketRegimeDailyRuntimeError("daily runtime clock must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_json(path: Path) -> dict[str, Any] | None:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise MarketRegimeDailyRuntimeError("daily status is not JSON") from exc
    if not isinstance(value, dict):
        raise MarketRegimeDailyRuntimeError("daily status must be an object")
    return value


def _try_lock(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        return None
    return descriptor


def _unlock(descriptor: int) -> None:
    fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)


def _lock_busy(path: Path) -> bool:
    # Health/GET is strictly read-only: do not create a directory or lock
    # file merely to inspect whether a scheduler is running.
    if not path.exists():
        return False
    try:
        descriptor = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        return True
    fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)
    return False


def _provider_from_environment() -> NarrativeProvider | None:
    configured = os.getenv("DEEPSEEK_API_KEY_FILE")
    if not configured:
        return None
    key_file = Path(configured).expanduser()
    if not key_file.is_file():
        return None
    return DeepSeekNarrativeProvider(
        key_file=key_file.resolve(),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
    )


def _failure_code(exc: BaseException, phase: str) -> str:
    if isinstance(exc, MarketRegimeDailyBundleRace):
        return "candidate_advanced"
    if isinstance(exc, MarketRegimeDailyBundleError):
        if "unavailable" in str(exc):
            return f"{phase}_unavailable"
        if "state" in str(exc) or "hash" in str(exc) or "identity" in str(exc):
            return "bundle_integrity_failed"
        return "bundle_validation_failed"
    return {
        "evidence": "evidence_compile_failed",
        "narrative": "narrative_compile_failed",
        "bundle": "bundle_publish_failed",
    }.get(phase, "daily_runtime_failed")


def _copy_failure(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        "at": str(value.get("at")),
        "code": str(value.get("code")),
        "phase": str(value.get("phase")),
    }


class MarketRegimeDailyRuntime:
    """Run S3 -> S4 -> S5 without touching the Live v1 state."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        interval_hours: int | str | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        evidence_store_factory: Callable[[Path, Path, Path], MarketRegimeDailyEvidenceStore] = MarketRegimeDailyEvidenceStore,
        narrative_store_factory: Callable[[MarketRegimeDailyEvidenceStore, Path], MarketRegimeDailyNarrativeStore] = MarketRegimeDailyNarrativeStore,
        bundle_store_factory: Callable[[MarketRegimeDailyEvidenceStore, MarketRegimeDailyNarrativeStore, Path], MarketRegimeDailyBundleStore] = MarketRegimeDailyBundleStore,
        provider_factory: Callable[[], NarrativeProvider | None] = _provider_from_environment,
        pipeline_lock_already_held: bool = False,
    ) -> None:
        self.root = Path(root or os.getenv("PARK_MARKET_REGIME_ROOT", Path(__file__).resolve().parent / "runtime" / "market-regime")).expanduser().resolve()
        self.daily_root = self.root / "daily-v2"
        self.evidence_root = self.daily_root / "evidence-packs"
        self.narrative_root = self.daily_root / "narratives"
        self.bundle_root = self.daily_root / "bundles"
        self.macro_root = self.root / "macro"
        self.interval_hours = configured_daily_interval_hours(interval_hours)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or time.sleep
        self.evidence_store_factory = evidence_store_factory
        self.narrative_store_factory = narrative_store_factory
        self.bundle_store_factory = bundle_store_factory
        self.provider_factory = provider_factory
        self.status_path = self.bundle_root / "status.json"
        self.lock_path = self.daily_root / "scheduler" / "refresh.lock"
        self.pipeline_lock_path = self.root / "scheduler" / "pipeline.lock"
        self.pipeline_lock_already_held = pipeline_lock_already_held

    def _stores(self) -> tuple[MarketRegimeDailyEvidenceStore, MarketRegimeDailyNarrativeStore, MarketRegimeDailyBundleStore]:
        evidence = self.evidence_store_factory(self.root, self.macro_root, self.evidence_root)
        narrative = self.narrative_store_factory(evidence, self.narrative_root)
        bundle = self.bundle_store_factory(evidence, narrative, self.bundle_root)
        return evidence, narrative, bundle

    def _read_status(self) -> dict[str, Any] | None:
        status = _read_json(self.status_path)
        if status is None:
            return None
        if set(status) != STATUS_KEYS or status.get("schema_version") != DAILY_STATUS_SCHEMA_VERSION:
            raise MarketRegimeDailyRuntimeError("daily status schema mismatch")
        if status.get("state") not in {"running", "idle", "failed"}:
            raise MarketRegimeDailyRuntimeError("daily status state is invalid")
        if status.get("interval_hours") not in ALLOWED_INTERVAL_HOURS:
            raise MarketRegimeDailyRuntimeError("daily status interval is invalid")
        for field in ("attempted_at", "last_success_at", "next_due_at"):
            value = status.get(field)
            if value is not None:
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError as exc:
                    raise MarketRegimeDailyRuntimeError("daily status timestamp is invalid") from exc
                if parsed.tzinfo is None:
                    raise MarketRegimeDailyRuntimeError("daily status timestamp is invalid")
        for field in (
            "attempt_id", "last_success_bundle_id", "served_bundle_id",
            "candidate_pack_id", "candidate_narrative_id", "candidate_bundle_id",
        ):
            value = status.get(field)
            if value is not None and (
                not isinstance(value, str)
                or len(value) > 256
                or "/" in value
                or "\\" in value
                or SECRET_LABEL_RE.search(value)
            ):
                raise MarketRegimeDailyRuntimeError("daily status identity is invalid")
        failure = status.get("last_failure")
        if failure is not None:
            if not isinstance(failure, dict) or set(failure) != {"at", "code", "phase"}:
                raise MarketRegimeDailyRuntimeError("daily status failure schema mismatch")
            if failure.get("code") not in FAILURE_CODES or failure.get("phase") not in FAILURE_PHASES:
                raise MarketRegimeDailyRuntimeError("daily status failure is invalid")
            try:
                parsed = datetime.fromisoformat(str(failure.get("at")).replace("Z", "+00:00"))
            except ValueError as exc:
                raise MarketRegimeDailyRuntimeError("daily status failure timestamp is invalid") from exc
            if parsed.tzinfo is None:
                raise MarketRegimeDailyRuntimeError("daily status failure timestamp is invalid")
        return status

    @staticmethod
    def _persisted_status(status: Mapping[str, Any]) -> dict[str, Any]:
        return {key: status.get(key) for key in STATUS_KEYS}

    def _base_status(self, previous: Mapping[str, Any] | None, *, attempt_id: str, now: str) -> dict[str, Any]:
        previous = previous or {}
        return {
            "schema_version": DAILY_STATUS_SCHEMA_VERSION,
            "state": "running",
            "attempt_id": attempt_id,
            "attempted_at": now,
            "last_success_at": previous.get("last_success_at"),
            "last_success_bundle_id": previous.get("last_success_bundle_id"),
            "served_bundle_id": previous.get("served_bundle_id"),
            "candidate_pack_id": None,
            "candidate_narrative_id": None,
            "candidate_bundle_id": None,
            "last_failure": None,
            "next_due_at": None,
            "interval_hours": self.interval_hours,
        }

    def cycle(self) -> dict[str, Any]:
        pipeline_descriptor: int | None = None
        if not self.pipeline_lock_already_held:
            pipeline_descriptor = _try_lock(self.pipeline_lock_path)
            if pipeline_descriptor is None:
                return {
                    "schema_version": DAILY_RUNTIME_SCHEMA_VERSION,
                    "state": "busy",
                    "busy": True,
                    "contention": "cohesive_pipeline",
                    "interval_hours": self.interval_hours,
                    "retry_in_seconds": DAILY_SCHEDULER_LOCK_RETRY_SECONDS,
                }
        descriptor = _try_lock(self.lock_path)
        if descriptor is None:
            if pipeline_descriptor is not None:
                _unlock(pipeline_descriptor)
            return {
                "schema_version": DAILY_RUNTIME_SCHEMA_VERSION,
                "state": "busy",
                "busy": True,
                "interval_hours": self.interval_hours,
                "retry_in_seconds": DAILY_SCHEDULER_LOCK_RETRY_SECONDS,
            }
        try:
            previous = self._read_status() or {}
            started = self.clock().astimezone(timezone.utc)
            attempt_id = f"daily-attempt-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:12]}"
            running = self._base_status(previous, attempt_id=attempt_id, now=_iso(started))
            _write_atomic(self.status_path, running)
            phase = "evidence"
            candidate_pack_id: str | None = None
            candidate_narrative_id: str | None = None
            candidate_bundle_id: str | None = None
            try:
                evidence_store, narrative_store, bundle_store = self._stores()
                evidence_store.compile_latest()
                candidate_pack_id = evidence_store.latest().get("pack_id")
                phase = "narrative"
                narrative_store.compile_latest(self.provider_factory())
                candidate_narrative_id = narrative_store.latest().get("narrative_id")
                phase = "bundle"
                candidate = bundle_store.capture_candidate()
                candidate_bundle_id = candidate.get("bundle_id")
                published = bundle_store.publish_candidate(candidate)
                artifact = published["artifact"]
                finished = self.clock().astimezone(timezone.utc)
                result = {
                    **running,
                    "state": "idle",
                    "busy": False,
                    "last_success_at": _iso(finished),
                    "last_success_bundle_id": artifact.get("bundle_id"),
                    "served_bundle_id": artifact.get("bundle_id"),
                    "candidate_pack_id": artifact.get("pack_id"),
                    "candidate_narrative_id": artifact.get("narrative_id"),
                    "candidate_bundle_id": artifact.get("bundle_id"),
                    "last_failure": None,
                    "next_due_at": _iso(finished + timedelta(hours=self.interval_hours)),
                    "action": published.get("action"),
                }
            except Exception as exc:
                finished = self.clock().astimezone(timezone.utc)
                result = {
                    **running,
                    "state": "failed",
                    "busy": False,
                    "candidate_pack_id": candidate_pack_id,
                    "candidate_narrative_id": candidate_narrative_id,
                    "candidate_bundle_id": candidate_bundle_id,
                    "last_failure": {
                        "at": _iso(finished),
                        "code": _failure_code(exc, phase),
                        "phase": phase,
                    },
                    "next_due_at": _iso(finished + timedelta(hours=self.interval_hours)),
                }
            _write_atomic(self.status_path, self._persisted_status(result))
            return result
        finally:
            _unlock(descriptor)
            if pipeline_descriptor is not None:
                _unlock(pipeline_descriptor)

    def _health_state(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            status = self._read_status()
        except MarketRegimeDailyRuntimeError:
            status = None
        try:
            _, _, bundle_store = self._stores()
            state = bundle_store.latest_state()
            served = state.get("served") if isinstance(state, Mapping) else None
            artifact = bundle_store._validate_artifact(served["artifact"]) if isinstance(served, Mapping) else None
            return status, artifact
        except MarketRegimeDailyBundleError:
            return status, None

    def health(self) -> dict[str, Any]:
        now = self.clock().astimezone(timezone.utc)
        status, artifact = self._health_state()
        busy = _lock_busy(self.lock_path)
        if status is None:
            runtime_state = "unavailable"
        else:
            runtime_state = str(status.get("state") or "unavailable")
            if runtime_state == "running" and not busy:
                runtime_state = "interrupted"
        if artifact is None:
            served = {"status": "unavailable"}
        else:
            judgment_time = ((artifact.get("evidence") or {}).get("time") or {}).get("joint_judgment_time")
            try:
                judgment = datetime.fromisoformat(str(judgment_time).replace("Z", "+00:00"))
                if judgment.tzinfo is None:
                    raise ValueError
                age_seconds = max(0, int((now - judgment.astimezone(timezone.utc)).total_seconds()))
            except (TypeError, ValueError):
                served = {"status": "unavailable"}
                artifact = None
            else:
                served = {
                    "status": "available",
                    "bundle_id": artifact.get("bundle_id"),
                    "pack_id": artifact.get("pack_id"),
                    "narrative_id": artifact.get("narrative_id"),
                    "generation_status": artifact.get("generation_status"),
                    "quality": (artifact.get("evidence") or {}).get("quality"),
                    "judgment_time": judgment_time,
                    "age_seconds": age_seconds,
                }
                if runtime_state == "failed":
                    runtime_state = "degraded"
        return {
            "schema_version": DAILY_HEALTH_SCHEMA_VERSION,
            "observed_at": _iso(now),
            "state": runtime_state,
            "busy": busy,
            "interval_hours": self.interval_hours,
            "last_attempt": None
            if status is None
            else {
                "id": status.get("attempt_id"),
                "at": status.get("attempted_at"),
                "status": status.get("state"),
            },
            "candidate": None
            if status is None
            else {
                "pack_id": status.get("candidate_pack_id"),
                "narrative_id": status.get("candidate_narrative_id"),
                "bundle_id": status.get("candidate_bundle_id"),
            },
            "served": served,
            "last_success": None
            if status is None
            else {
                "at": status.get("last_success_at"),
                "bundle_id": status.get("last_success_bundle_id"),
            },
            "failure": None if status is None else _copy_failure(status.get("last_failure")),
            "next_due_at": None if status is None else status.get("next_due_at"),
        }

    def run_forever(self) -> None:
        while True:
            result = self.cycle()
            delay = DAILY_SCHEDULER_LOCK_RETRY_SECONDS if result.get("state") == "busy" else self.interval_hours * 3600
            self.sleeper(delay)


def market_regime_daily_payload(root: Path | str | None = None) -> dict[str, Any]:
    runtime = MarketRegimeDailyRuntime(root)
    _, _, bundle_store = runtime._stores()
    try:
        return bundle_store.latest()
    except MarketRegimeDailyBundleError as exc:
        raise MarketRegimeDailyRuntimeError("daily bundle unavailable") from exc


def market_regime_daily_health_payload(root: Path | str | None = None) -> dict[str, Any]:
    return MarketRegimeDailyRuntime(root).health()
