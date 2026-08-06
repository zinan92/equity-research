"""Read-only Market Regime API projection and serial refresh scheduler."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Mapping

from data_core.market_regime_data import MarketRegimeDataStore
from data_core.market_regime_model import MarketRegimeAnalysisStore


API_SCHEMA_VERSION = "market-regime-api-v1"
SCHEDULER_SCHEMA_VERSION = "market-regime-scheduler-v1"
ALLOWED_INTERVAL_HOURS = (4, 12)
PRIMARY_CHART_KEYS = (
    "sp500",
    "nasdaq",
    "shanghai",
    "star50",
    "wti",
    "gold",
    "silver",
    "kospi",
    "nikkei",
)
PROBE_KEYS = ("vix", "china_dividend", "us_dividend")


class MarketRegimeRuntimeError(RuntimeError):
    """The runtime bundle, schedule, or refresh cycle is invalid."""


def market_regime_root() -> Path:
    default = Path(__file__).resolve().parent / "runtime" / "market-regime"
    return Path(os.getenv("PARK_MARKET_REGIME_ROOT", default)).expanduser().resolve()


def configured_interval_hours(value: int | str | None = None) -> int:
    raw = value if value is not None else os.getenv("PARK_MARKET_REGIME_INTERVAL_HOURS", "4")
    try:
        interval = int(raw)
    except (TypeError, ValueError) as exc:
        raise MarketRegimeRuntimeError("market-regime interval must be 4 or 12 hours") from exc
    if interval not in ALLOWED_INTERVAL_HOURS:
        raise MarketRegimeRuntimeError("market-regime interval must be 4 or 12 hours")
    return interval


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise MarketRegimeRuntimeError("scheduler clock must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_immutable(path: Path, payload: Mapping[str, Any]) -> str:
    encoded = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != encoded:
            raise MarketRegimeRuntimeError(f"market-regime API identity collision: {path.name}")
        return sha256(existing).hexdigest()
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return sha256(encoded).hexdigest()


def _instrument_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    instrument = item.get("instrument") or {}
    source = item.get("source") or {}
    projected = {
        "instrument": instrument,
        "quality": item.get("quality"),
        "data_kind": item.get("data_kind", "unknown"),
        "bar_count": item.get("bar_count", 0),
        "bars": item.get("bars") or [],
        "last_completed_session": item.get("last_completed_session"),
        "last_completed_close_at": item.get("last_completed_close_at"),
        "age_hours": item.get("age_hours"),
        "provider_silence_hours": item.get("provider_silence_hours"),
        "price_basis": item.get("price_basis") or instrument.get("price_basis"),
        "normalized_artifact": item.get("normalized_artifact"),
        "source": {
            "requested_url": source.get("requested_url"),
            "final_url": source.get("final_url"),
            "status_code": source.get("status_code"),
            "content_type": source.get("content_type"),
            "fetched_at": source.get("fetched_at"),
            "raw_sha256": source.get("raw_sha256"),
        },
    }
    if item.get("refresh_failure"):
        failure = item["refresh_failure"]
        projected["refresh_failure"] = {
            "reason": failure.get("reason"),
            "bounded_raw_excerpt": failure.get("bounded_raw_excerpt"),
        }
    return projected


def build_market_regime_api_payload(
    snapshot: Mapping[str, Any], analysis: Mapping[str, Any]
) -> dict[str, Any]:
    if analysis.get("source_run_id") != snapshot.get("run_id"):
        raise MarketRegimeRuntimeError("analysis and data snapshot run identities differ")
    items = snapshot.get("instruments") or []
    if not isinstance(items, list):
        raise MarketRegimeRuntimeError("market-regime snapshot instruments are invalid")
    by_key: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise MarketRegimeRuntimeError("market-regime snapshot instrument is invalid")
        key = str((item.get("instrument") or {}).get("key") or "")
        if not key or key in by_key:
            raise MarketRegimeRuntimeError("market-regime snapshot instrument identity is invalid")
        by_key[key] = item
    missing = [key for key in (*PRIMARY_CHART_KEYS, *PROBE_KEYS) if key not in by_key]
    if missing:
        raise MarketRegimeRuntimeError(f"market-regime API snapshot is missing: {', '.join(missing)}")
    payload = {
        "schema_version": API_SCHEMA_VERSION,
        "source_run_id": snapshot.get("run_id"),
        "analysis_id": analysis.get("analysis_id"),
        "generated_at": analysis.get("generated_at"),
        "verdict_as_of": analysis.get("verdict_as_of"),
        "latest_evidence_at": analysis.get("latest_evidence_at"),
        "data_quality": snapshot.get("quality"),
        "analysis_status": analysis.get("status"),
        "data_kind": analysis.get("data_kind"),
        "license": snapshot.get("license"),
        "truth_boundary": analysis.get("truth_boundary"),
        "analysis": analysis,
        "charts": [_instrument_projection(by_key[key]) for key in PRIMARY_CHART_KEYS],
        "probes": [_instrument_projection(by_key[key]) for key in PROBE_KEYS],
    }
    identity = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {**payload, "bundle_id": f"market-regime-api:{identity}"}


class MarketRegimeApiStore:
    """Publish and verify one cohesive, last-successful API bundle."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def publish(self, snapshot: Mapping[str, Any], analysis: Mapping[str, Any]) -> dict[str, Any]:
        payload = build_market_regime_api_payload(snapshot, analysis)
        identity = payload["bundle_id"].split(":", 1)[1]
        relative = f"api/artifacts/{identity}.json"
        artifact_hash = _write_immutable(self.root / relative, payload)
        pointer = {
            "schema_version": API_SCHEMA_VERSION,
            "bundle_id": payload["bundle_id"],
            "source_run_id": payload["source_run_id"],
            "analysis_id": payload["analysis_id"],
            "artifact": {"path": relative, "sha256": artifact_hash},
        }
        _write_atomic(self.root / "api" / "latest.json", pointer)
        return payload

    def latest(self) -> dict[str, Any]:
        try:
            pointer = json.loads((self.root / "api" / "latest.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MarketRegimeRuntimeError("market-regime API bundle is unavailable") from exc
        except json.JSONDecodeError as exc:
            raise MarketRegimeRuntimeError("market-regime API pointer is not JSON") from exc
        if not isinstance(pointer, dict) or pointer.get("schema_version") != API_SCHEMA_VERSION:
            raise MarketRegimeRuntimeError("market-regime API pointer schema mismatch")
        reference = pointer.get("artifact")
        if not isinstance(reference, dict):
            raise MarketRegimeRuntimeError("market-regime API artifact reference is incomplete")
        relative = str(reference.get("path") or "")
        expected_hash = str(reference.get("sha256") or "")
        if not relative.startswith("api/artifacts/") or len(expected_hash) != 64:
            raise MarketRegimeRuntimeError("market-regime API artifact reference is incomplete")
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise MarketRegimeRuntimeError("market-regime API artifact path escapes runtime root")
        try:
            encoded = target.read_bytes()
        except FileNotFoundError as exc:
            raise MarketRegimeRuntimeError("market-regime API artifact is missing") from exc
        if sha256(encoded).hexdigest() != expected_hash:
            raise MarketRegimeRuntimeError("market-regime API artifact hash mismatch")
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise MarketRegimeRuntimeError("market-regime API artifact is not JSON") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != API_SCHEMA_VERSION:
            raise MarketRegimeRuntimeError("market-regime API artifact schema mismatch")
        identity_payload = {key: value for key, value in payload.items() if key != "bundle_id"}
        identity = sha256(_canonical_json(identity_payload).encode("utf-8")).hexdigest()
        if (
            payload.get("bundle_id") != f"market-regime-api:{identity}"
            or pointer.get("bundle_id") != payload.get("bundle_id")
            or pointer.get("source_run_id") != payload.get("source_run_id")
            or pointer.get("analysis_id") != payload.get("analysis_id")
            or relative != f"api/artifacts/{identity}.json"
        ):
            raise MarketRegimeRuntimeError("market-regime API artifact identity mismatch")
        return payload


class MarketRegimeRuntime:
    """Serial scheduler that advances the API bundle only after a full cycle."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        interval_hours: int | str | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        data_store_factory: Callable[[Path], Any] = MarketRegimeDataStore,
        analysis_store_factory: Callable[[Path], Any] = MarketRegimeAnalysisStore,
        api_store_factory: Callable[[Path], Any] = MarketRegimeApiStore,
    ) -> None:
        self.root = Path(root or market_regime_root()).expanduser().resolve()
        self.interval_hours = configured_interval_hours(interval_hours)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or time.sleep
        self.data_store_factory = data_store_factory
        self.analysis_store_factory = analysis_store_factory
        self.api_store_factory = api_store_factory
        self.status_path = self.root / "scheduler" / "status.json"
        self.lock_path = self.root / "scheduler" / "refresh.lock"

    def _read_status(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise MarketRegimeRuntimeError("market-regime scheduler status is not JSON") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEDULER_SCHEMA_VERSION:
            raise MarketRegimeRuntimeError("market-regime scheduler status schema mismatch")
        return payload

    def _try_lock(self) -> int | None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
        return descriptor

    @staticmethod
    def _unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    def _lock_busy(self) -> bool:
        try:
            descriptor = os.open(self.lock_path, os.O_RDWR)
        except FileNotFoundError:
            return False
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return True
        self._unlock(descriptor)
        return False

    def cycle(self) -> dict[str, Any]:
        descriptor = self._try_lock()
        if descriptor is None:
            return {
                "schema_version": SCHEDULER_SCHEMA_VERSION,
                "state": "busy",
                "busy": True,
                "interval_hours": self.interval_hours,
            }
        try:
            previous = self._read_status() or {}
            started = self.clock()
            running = {
                "schema_version": SCHEDULER_SCHEMA_VERSION,
                "state": "running",
                "busy": True,
                "interval_hours": self.interval_hours,
                "last_attempt_at": _iso(started),
                "last_success_at": previous.get("last_success_at"),
                "last_failure": previous.get("last_failure"),
                "next_due_at": None,
                "source_run_id": previous.get("source_run_id"),
                "analysis_id": previous.get("analysis_id"),
                "bundle_id": previous.get("bundle_id"),
                "data_quality": previous.get("data_quality"),
                "analysis_status": previous.get("analysis_status"),
            }
            _write_atomic(self.status_path, running)
            try:
                data_store = self.data_store_factory(self.root)
                refreshed = data_store.refresh()
                snapshot = data_store.latest()
                if refreshed.get("run_id") != snapshot.get("run_id"):
                    raise MarketRegimeRuntimeError(
                        "refresh result differs from verified latest snapshot"
                    )
                analysis_store = self.analysis_store_factory(self.root)
                compiled = analysis_store.compile_latest()
                analysis = analysis_store.latest()
                if compiled.get("analysis_id") != analysis.get("analysis_id"):
                    raise MarketRegimeRuntimeError(
                        "compiled result differs from verified latest analysis"
                    )
                api_store = self.api_store_factory(self.root)
                published = api_store.publish(snapshot, analysis)
                bundle = api_store.latest()
                if published.get("bundle_id") != bundle.get("bundle_id"):
                    raise MarketRegimeRuntimeError(
                        "published result differs from verified latest API bundle"
                    )
                finished = self.clock()
                result = {
                    **running,
                    "state": "idle",
                    "busy": False,
                    "last_success_at": _iso(finished),
                    "next_due_at": _iso(finished + timedelta(hours=self.interval_hours)),
                    "source_run_id": snapshot.get("run_id"),
                    "analysis_id": analysis.get("analysis_id"),
                    "bundle_id": bundle.get("bundle_id"),
                    "data_quality": snapshot.get("quality"),
                    "analysis_status": analysis.get("status"),
                    "last_error": None,
                }
            except Exception as exc:
                finished = self.clock()
                failure = {
                    "at": _iso(finished),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
                result = {
                    **running,
                    "state": "failed",
                    "busy": False,
                    "last_failure": failure,
                    "last_error": failure,
                    "next_due_at": _iso(finished + timedelta(hours=self.interval_hours)),
                }
            _write_atomic(self.status_path, result)
            return result
        finally:
            self._unlock(descriptor)

    def health(self) -> dict[str, Any]:
        busy = self._lock_busy()
        status = self._read_status()
        if status is None:
            scheduler = {
                "schema_version": SCHEDULER_SCHEMA_VERSION,
                "state": "unavailable",
                "busy": busy,
                "interval_hours": self.interval_hours,
            }
        else:
            scheduler = {**status, "busy": busy}
            if status.get("state") == "running" and not busy:
                scheduler["state"] = "interrupted"
        try:
            bundle = self.api_store_factory(self.root).latest()
        except MarketRegimeRuntimeError as exc:
            latest = {"status": "unavailable", "detail": str(exc)}
        else:
            latest = {
                "status": "available",
                "bundle_id": bundle.get("bundle_id"),
                "source_run_id": bundle.get("source_run_id"),
                "analysis_id": bundle.get("analysis_id"),
                "data_quality": bundle.get("data_quality"),
                "analysis_status": bundle.get("analysis_status"),
                "verdict_as_of": bundle.get("verdict_as_of"),
            }
        return {
            "schema_version": SCHEDULER_SCHEMA_VERSION,
            "scheduler": scheduler,
            "latest": latest,
        }

    def run_forever(self) -> None:
        while True:
            self.cycle()
            self.sleeper(self.interval_hours * 3600)


def market_regime_payload(root: Path | str | None = None) -> dict[str, Any]:
    return MarketRegimeApiStore(root or market_regime_root()).latest()


def market_regime_health_payload(root: Path | str | None = None) -> dict[str, Any]:
    return MarketRegimeRuntime(root or market_regime_root()).health()
