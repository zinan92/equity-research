"""One-shot Weekly Macro K-line runtime.

The runtime is deliberately separate from the existing Daily scheduler.  It
freezes one completed Friday, publishes a source snapshot, calls one isolated
analysis provider per asset, performs the late ranking pass, and only then
advances the reader-facing Weekly pointer.  A failed asset is typed as
``analysis_unavailable``; stale artifacts are never substituted.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from .market_regime_weekly_asset_analysis import (
    SCHEMA_VERSION as ASSET_SCHEMA_VERSION,
    build_asset_analysis_request,
    compile_asset_analysis,
)
from .market_regime_weekly_ranking import (
    SCHEMA_VERSION as RANKING_SCHEMA_VERSION,
    build_ranking_request,
    compile_ranking,
)
from .market_regime_weekly_report import (
    REPORT_ID_PREFIX,
    SCHEMA_VERSION as REPORT_SCHEMA_VERSION,
    build_weekly_report,
    render_weekly_html,
    render_weekly_markdown,
)
from .market_regime_weekly_source import (
    CONTEXT_4H_KEYS,
    SCHEMA_VERSION as SOURCE_SCHEMA_VERSION,
    WEEKLY_KEYS,
    WeeklySourceHistoryStore,
)


RUNTIME_SCHEMA_VERSION = "market-regime-weekly-runtime-v1"
RUNTIME_STATUS_SCHEMA_VERSION = "market-regime-weekly-runtime-status-v1"
SOURCE_ID_PREFIX = "market-regime-weekly-source:"


class WeeklyRuntimeError(RuntimeError):
    """Weekly runtime failed at a public phase boundary."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical(value) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _immutable_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise WeeklyRuntimeError("immutable_artifact_conflict")
        return digest
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


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


def _previous_friday(current: datetime) -> date:
    current_date = current.astimezone(timezone.utc).date()
    days_since_friday = (current_date.weekday() - 4) % 7
    if days_since_friday == 0 and current.astimezone(timezone.utc).time() < time(23, 59, 59):
        days_since_friday = 7
    return current_date - timedelta(days=days_since_friday)


def _failure_code(exc: BaseException, default: str) -> str:
    code = str(exc) if isinstance(exc, WeeklyRuntimeError) else default
    if not code or "/" in code or "\\" in code or len(code) > 96:
        return default
    return code


class WeeklyReportStore:
    """Content-addressed Weekly report/artifact store with a verified pointer."""

    def __init__(self, runtime_root: Path | str, output_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    def publish(self, report: Mapping[str, Any]) -> dict[str, Any]:
        report_id = str(report.get("report_id") or "")
        core = report.get("identity_core")
        boundary = report.get("truth_boundary")
        if not report_id.startswith(REPORT_ID_PREFIX) or not isinstance(core, Mapping):
            raise WeeklyRuntimeError("report_identity_invalid")
        if report_id != f"{REPORT_ID_PREFIX}{_digest(core)}":
            raise WeeklyRuntimeError("report_identity_mismatch")
        if not isinstance(boundary, Mapping) or boundary.get("publication_eligible") is not False:
            raise WeeklyRuntimeError("report_publication_boundary_invalid")

        digest = report_id.removeprefix(REPORT_ID_PREFIX)
        artifact_relative = f"reports/artifacts/{digest}.json"
        receipt_relative = f"reports/receipts/{digest}.json"
        artifact_hash = _immutable_bytes(self.runtime_root / artifact_relative, _json_bytes(dict(report)))
        receipt = {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "event": "completed",
            "report_id": report_id,
            "artifact": {"path": artifact_relative, "sha256": artifact_hash},
        }
        receipt_hash = _immutable_bytes(self.runtime_root / receipt_relative, _json_bytes(receipt))
        week_end = str(report.get("week_end") or "unknown")
        html_relative = f"archive/{week_end}/{digest}.html"
        markdown_relative = f"archive/{week_end}/{digest}.md"
        html_hash = _immutable_bytes(self.output_root / html_relative, render_weekly_html(report).encode("utf-8"))
        markdown_hash = _immutable_bytes(self.output_root / markdown_relative, render_weekly_markdown(report).encode("utf-8"))
        pointer = {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "report_id": report_id,
            "week_end": week_end,
            "artifact": {"path": artifact_relative, "sha256": artifact_hash},
            "receipt": {"path": receipt_relative, "sha256": receipt_hash},
            "html": {"path": html_relative, "sha256": html_hash},
            "markdown": {"path": markdown_relative, "sha256": markdown_hash},
            "publication_eligible": False,
            "action_eligible": False,
        }
        _atomic_bytes(self.runtime_root / "latest.json", _json_bytes(pointer))
        _atomic_bytes(self.output_root / "latest.html", render_weekly_html(report).encode("utf-8"))
        _atomic_bytes(self.output_root / "latest.md", render_weekly_markdown(report).encode("utf-8"))
        self.latest()
        return pointer

    def latest(self) -> dict[str, Any]:
        try:
            pointer = json.loads((self.runtime_root / "latest.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise WeeklyRuntimeError("weekly_report_latest_unavailable") from exc
        required = {"schema_version", "report_id", "week_end", "artifact", "receipt", "html", "markdown", "publication_eligible", "action_eligible"}
        if not isinstance(pointer, dict) or set(pointer) != required or pointer.get("schema_version") != RUNTIME_SCHEMA_VERSION:
            raise WeeklyRuntimeError("weekly_report_pointer_invalid")
        if pointer.get("publication_eligible") is not False or pointer.get("action_eligible") is not False:
            raise WeeklyRuntimeError("weekly_report_boundary_invalid")
        report_id = str(pointer.get("report_id") or "")
        digest = report_id.removeprefix(REPORT_ID_PREFIX)
        if not report_id.startswith(REPORT_ID_PREFIX) or len(digest) != 64:
            raise WeeklyRuntimeError("weekly_report_pointer_identity_invalid")

        def read_ref(name: str, expected_relative: str) -> bytes:
            reference = pointer.get(name)
            if not isinstance(reference, Mapping) or reference.get("path") != expected_relative:
                raise WeeklyRuntimeError(f"weekly_report_{name}_reference_invalid")
            target = (self.runtime_root / expected_relative).resolve() if name in {"artifact", "receipt"} else (self.output_root / expected_relative).resolve()
            root = self.runtime_root if name in {"artifact", "receipt"} else self.output_root
            if root not in target.parents:
                raise WeeklyRuntimeError(f"weekly_report_{name}_path_escape")
            try:
                payload = target.read_bytes()
            except FileNotFoundError as exc:
                raise WeeklyRuntimeError(f"weekly_report_{name}_unavailable") from exc
            if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
                raise WeeklyRuntimeError(f"weekly_report_{name}_hash_mismatch")
            return payload

        artifact_relative = f"reports/artifacts/{digest}.json"
        receipt_relative = f"reports/receipts/{digest}.json"
        artifact_bytes = read_ref("artifact", artifact_relative)
        receipt_bytes = read_ref("receipt", receipt_relative)
        html_bytes = read_ref("html", str(pointer["html"].get("path") or ""))
        markdown_bytes = read_ref("markdown", str(pointer["markdown"].get("path") or ""))
        try:
            report = json.loads(artifact_bytes)
            receipt = json.loads(receipt_bytes)
        except json.JSONDecodeError as exc:
            raise WeeklyRuntimeError("weekly_report_json_invalid") from exc
        if not isinstance(report, dict) or report.get("report_id") != report_id:
            raise WeeklyRuntimeError("weekly_report_artifact_identity_invalid")
        if report_id != f"{REPORT_ID_PREFIX}{_digest(report.get('identity_core'))}":
            raise WeeklyRuntimeError("weekly_report_artifact_identity_mismatch")
        expected_receipt = {"schema_version": RUNTIME_SCHEMA_VERSION, "event": "completed", "report_id": report_id, "artifact": {"path": artifact_relative, "sha256": pointer["artifact"]["sha256"]}}
        if receipt != expected_receipt:
            raise WeeklyRuntimeError("weekly_report_receipt_identity_mismatch")
        if not html_bytes or not markdown_bytes:
            raise WeeklyRuntimeError("weekly_report_output_empty")
        return report


def _evidence_id(source_id: str, key: str, timeframe: str) -> str:
    return f"{source_id}:{key}:{timeframe}"


def _asset_snapshot(source: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    series = source.get("series", {}).get(key)
    if not isinstance(series, Mapping):
        return None
    # Charts retain the full captured history, while each isolated LLM call
    # receives a bounded recent context so one asset cannot monopolize the
    # provider request.  The bound is explicit and does not alter evidence.
    weekly = list(series.get("points") or [])[-156:]
    daily = list(series.get("daily_points") or [])[-300:]
    if not weekly or not daily or series.get("status") == "unavailable":
        return None
    source_id = str(source.get("snapshot_id") or f"source:{_digest(source)}")
    result: dict[str, Any] = {
        "key": key,
        "canonical_symbol": series.get("canonical_symbol"),
        "series_kind": series.get("series_kind"),
        "price_basis": series.get("price_basis"),
        "week_end": source.get("week_end"),
        "weekly": {"points": weekly, "status": series.get("status", "complete"), "unit": series.get("unit"), "evidence_ids": [_evidence_id(source_id, key, "weekly")]},
        "daily": {"points": daily, "status": series.get("status", "complete"), "unit": series.get("unit"), "evidence_ids": [_evidence_id(source_id, key, "daily")]},
    }
    context = series.get("context_4h")
    if key in CONTEXT_4H_KEYS and isinstance(context, Mapping) and context.get("status") == "complete" and context.get("points"):
        result["four_hour"] = {"points": list(context.get("points") or [])[-120:], "status": "complete", "unit": series.get("unit"), "evidence_ids": [_evidence_id(source_id, key, "four_hour")]}
    return result


class WeeklyMacroRuntime:
    """Run one Weekly edition; scheduling is intentionally outside this class."""

    def __init__(
        self,
        *,
        source_loader: Callable[..., Mapping[str, Any]],
        asset_provider: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
        ranking_provider: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
        runtime_root: Path | str,
        output_root: Path | str,
        allow_fixture: bool = False,
        phase_observer: Callable[[str], None] | None = None,
    ) -> None:
        self.source_loader = source_loader
        self.asset_provider = asset_provider
        self.ranking_provider = ranking_provider
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.allow_fixture = allow_fixture
        self.phase_observer = phase_observer
        self.source_store = WeeklySourceHistoryStore(self.runtime_root / "source")
        self.report_store = WeeklyReportStore(self.runtime_root, self.output_root)

    def _phase(self, phase: str) -> None:
        if self.phase_observer is not None:
            self.phase_observer(phase)

    def _status(self, *, state: str, success: Mapping[str, Any] | None = None, failure: Mapping[str, Any] | None = None) -> dict[str, Any]:
        status = {"schema_version": RUNTIME_STATUS_SCHEMA_VERSION, "state": state, "last_success": success, "last_failure": failure}
        _atomic_bytes(self.runtime_root / "status.json", _json_bytes(status))
        return status

    def run_once(self, *, now: datetime | None = None, week_end: date | None = None) -> dict[str, Any]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        frozen_week_end = week_end or _previous_friday(current)
        cutoff_at = datetime.combine(frozen_week_end, time(23, 59, 59), tzinfo=timezone.utc)
        phase = "source"
        try:
            self._phase(phase)
            raw_source = self.source_loader(week_end=frozen_week_end, cutoff_at=cutoff_at)
            if not isinstance(raw_source, Mapping) or raw_source.get("schema_version") != SOURCE_SCHEMA_VERSION:
                raise WeeklyRuntimeError("source_schema_invalid")
            if not self.allow_fixture:
                kinds = {str(raw_source.get("data_kind") or "")}
                kinds.update(str(item.get("data_kind") or "") for item in (raw_source.get("series") or {}).values() if isinstance(item, Mapping))
                if "fixture" in kinds:
                    raise WeeklyRuntimeError("fixture_source_not_publishable")
            source_state = self.source_store.publish(raw_source)
            source = self.source_store.latest()

            phase = "asset_analysis"
            self._phase(phase)
            analyses: dict[str, dict[str, Any]] = {}
            for key in WEEKLY_KEYS:
                snapshot = _asset_snapshot(source, key)
                if snapshot is None:
                    analyses[key] = {"asset_key": key, "generation_status": "analysis_unavailable", "failure_code": "source_unavailable"}
                    continue
                request = build_asset_analysis_request(snapshot)
                if self.asset_provider is None:
                    analyses[key] = {"asset_key": key, "generation_status": "analysis_unavailable", "failure_code": "provider_unavailable"}
                else:
                    analyses[key] = compile_asset_analysis(request, self.asset_provider)

            from .market_regime_weekly_asset_analysis import build_terminal_vector

            vector = build_terminal_vector(analyses)
            phase = "ranking"
            self._phase(phase)
            ranking_request = build_ranking_request(vector)
            ranking = compile_ranking(ranking_request, self.ranking_provider) if self.ranking_provider is not None else {"generation_status": "ranking_unavailable", "failure_code": "provider_unavailable", "ordered_assets": [], "important_changes": []}

            phase = "report"
            self._phase(phase)
            report = build_weekly_report(source, analyses, ranking)
            phase = "publish"
            self._phase(phase)
            pointer = self.report_store.publish(report)
            replay = self.report_store.latest()
            if replay.get("report_id") != report.get("report_id"):
                raise WeeklyRuntimeError("report_replay_identity_mismatch")
            success = {"at": current.isoformat().replace("+00:00", "Z"), "week_end": frozen_week_end.isoformat(), "report_id": pointer["report_id"], "source_id": source_state.get("snapshot_id"), "generation_status": "completed"}
            status = self._status(state="idle", success=success)
            return {"source": source, "analyses": analyses, "ranking": ranking, "report": report, "pointer": pointer, "status": status}
        except Exception as exc:
            failure = {"at": current.isoformat().replace("+00:00", "Z"), "code": _failure_code(exc, "weekly_run_failed"), "phase": phase}
            self._status(state="failed", failure=failure)
            if isinstance(exc, WeeklyRuntimeError):
                raise
            raise WeeklyRuntimeError("weekly_run_failed") from exc
