"""One-shot Daily K-line runtime and auditable status store."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from .market_regime_daily_analysis import (
    DailyAnalysisError,
    DailyAnalysisStore,
    DeepSeekDailyAssetProvider,
    build_daily_analysis_bundle,
)
from .market_regime_daily_snapshots import DailyChartSnapshotPort
from .market_regime_daily_source import DailyDatafeedClient, DailySourceError, DailySourceStore, build_daily_source_bundle
from .market_regime_daily_thesis import (
    DailyThesisDeliveryStore,
    DeepSeekDailyThesisProvider,
    DailyThesisError,
    compile_daily_thesis,
)


SCHEMA_VERSION = "market-regime-daily-runtime-v1"
STATUS_SCHEMA_VERSION = "market-regime-daily-runtime-status-v1"


class DailyRuntimeError(RuntimeError):
    """A public Daily runtime phase failed."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class DailyRuntimeStatusStore:
    """Secret-free status and last-failure state."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()

    def latest(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema_version": STATUS_SCHEMA_VERSION, "state": "idle", "last_success": None, "last_failure": None}
        except json.JSONDecodeError as exc:
            raise DailyRuntimeError("status_json_invalid") from exc
        if value.get("schema_version") != STATUS_SCHEMA_VERSION:
            raise DailyRuntimeError("status_schema_invalid")
        return value

    def success(self, *, at: str, source: Mapping[str, Any], analysis: Mapping[str, Any], thesis: Mapping[str, Any], delivery: Mapping[str, Any], service_health: Mapping[str, Any] | None = None) -> dict[str, Any]:
        core = {
            "schema_version": STATUS_SCHEMA_VERSION,
            "state": "completed",
            "completed_at": at,
            "source_bundle_id": source.get("bundle_id"),
            "analysis_bundle_id": analysis.get("bundle_id"),
            "thesis_id": thesis.get("thesis_id"),
            "delivery_id": delivery.get("delivery_id"),
            "source_status": source.get("source_status"),
            "analysis_status": analysis.get("analysis_status"),
            "thesis_status": thesis.get("generation_status"),
            "datafeed_health": dict(service_health or {}),
        }
        value = {
            **core,
            "status_id": f"daily-status:{_digest(core)}",
            "last_success": {
                "at": at,
                "source_bundle_id": source.get("bundle_id"),
                "analysis_bundle_id": analysis.get("bundle_id"),
                "thesis_id": thesis.get("thesis_id"),
                "delivery_id": delivery.get("delivery_id"),
                "source_status": source.get("source_status"),
                "analysis_status": analysis.get("analysis_status"),
                "thesis_status": thesis.get("generation_status"),
                "datafeed_health": dict(service_health or {}),
            },
            "last_failure": None,
            "publication_eligible": False,
            "automatic_execution_eligible": False,
        }
        _atomic_bytes(self.path, (_canonical(value) + "\n").encode("utf-8"))
        return value

    def failure(self, *, at: str, phase: str, code: str) -> dict[str, Any]:
        prior = self.latest()
        value = {
            **prior,
            "schema_version": STATUS_SCHEMA_VERSION,
            "state": "failed",
            "last_failure": {"at": at, "phase": phase, "code": code[:200]},
            "publication_eligible": False,
            "automatic_execution_eligible": False,
        }
        _atomic_bytes(self.path, (_canonical(value) + "\n").encode("utf-8"))
        return value


class DailyKlineRuntime:
    """Acquire, analyze, synthesize and deliver one Daily edition."""

    def __init__(
        self,
        *,
        runtime_root: Path | str,
        output_root: Path | str,
        archive_root: Path | str,
        key_file: Path | str | None,
        datafeed_url: str = "http://127.0.0.1:8100",
        no_llm: bool = False,
        no_snapshots: bool = False,
        source_builder: Callable[[DailyDatafeedClient], Mapping[str, Any]] | None = None,
        analysis_builder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        thesis_builder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.archive_root = Path(archive_root).expanduser().resolve()
        self.key_file = Path(key_file).expanduser().resolve() if key_file else None
        self.datafeed_url = datafeed_url
        self.no_llm = no_llm
        self.no_snapshots = no_snapshots
        self.source_builder = source_builder
        self.analysis_builder = analysis_builder
        self.thesis_builder = thesis_builder
        self.status_store = DailyRuntimeStatusStore(self.runtime_root / "status.json")

    def status(self) -> dict[str, Any]:
        return self.status_store.latest()

    def _asset_provider_factory(self):
        if self.no_llm or self.key_file is None or not self.key_file.is_file():
            return None
        provider = DeepSeekDailyAssetProvider(self.key_file)
        return lambda _request: provider

    def _thesis_provider(self):
        if self.no_llm or self.key_file is None or not self.key_file.is_file():
            return None
        return DeepSeekDailyThesisProvider(self.key_file)

    def run_once(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
        cutoff = current.isoformat().replace("+00:00", "Z")
        phase = "source_refresh"
        lock_path = self.runtime_root / "run.lock"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DailyRuntimeError("run_lock_busy") from exc
            try:
                client = DailyDatafeedClient(base_url=self.datafeed_url)
                service_health = client.health()
                source_store = DailySourceStore(self.runtime_root / "source")
                source = dict(self.source_builder(client) if self.source_builder else build_daily_source_bundle(client, generated_at=current))
                source_store.publish(source)

                phase = "analysis_compile"
                analysis_store = DailyAnalysisStore(self.runtime_root / "analysis")
                if self.analysis_builder:
                    analysis = dict(self.analysis_builder(source))
                else:
                    snapshot_port = None if self.no_snapshots else DailyChartSnapshotPort(runtime_root=self.runtime_root, output_root=self.output_root)
                    analysis = build_daily_analysis_bundle(source, provider_factory=self._asset_provider_factory(), cutoff_at=cutoff, snapshot_port=snapshot_port)
                analysis_store.publish(analysis)

                phase = "thesis_compile"
                thesis = dict(self.thesis_builder(analysis) if self.thesis_builder else compile_daily_thesis(analysis, self._thesis_provider()))
                phase = "delivery_publish"
                delivery = DailyThesisDeliveryStore(runtime_root=self.runtime_root, output_root=self.output_root, archive_root=self.archive_root).publish(thesis, analysis)
                status = self.status_store.success(at=cutoff, source=source, analysis=analysis, thesis=thesis, delivery=delivery, service_health=service_health)
                return {"schema_version": SCHEMA_VERSION, "state": "completed", "service_health": service_health, "source": source, "analysis": analysis, "thesis": thesis, "delivery": delivery, "status": status}
            except (DailySourceError, DailyAnalysisError, DailyThesisError, DailyRuntimeError) as exc:
                code = str(exc)[:200] or type(exc).__name__
                status = self.status_store.failure(at=cutoff, phase=phase, code=code)
                raise DailyRuntimeError(code) from exc
            except Exception as exc:
                code = f"{type(exc).__name__}:{exc}"[:200]
                status = self.status_store.failure(at=cutoff, phase=phase, code=code)
                raise DailyRuntimeError(code) from exc


__all__ = ["DailyKlineRuntime", "DailyRuntimeError", "DailyRuntimeStatusStore", "SCHEMA_VERSION", "STATUS_SCHEMA_VERSION"]
