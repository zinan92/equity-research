"""One-shot local runtime for the K-line World Report Track 2 product.

The runtime composes the already-versioned daily, context, model and report
authorities.  It does not own recurrence and it never reads Track 1.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping

from .market_regime_data import HttpCapture, MarketRegimeDataStore, http_get_capture
from .market_regime_daily_evidence import MarketRegimeDailyEvidenceStore
from .market_regime_kline_newsletter import BitcoinDailyStore
from .market_regime_kline_world_context import (
    KlineWorldContextStore,
    build_kline_world_context,
    load_context_source_snapshots,
)
from .market_regime_kline_world_model import (
    DeepSeekWorldModelProvider,
    KlineWorldModelStore,
    WorldModelProvider,
)
from .market_regime_kline_world_report import KlineWorldReportStore
from .market_regime_macro_data import MarketRegimeMacroDataStore


SCHEMA_VERSION = "market-regime-kline-world-runtime-v1"
DELIVERY_ID_PREFIX = "market-regime-kline-world-delivery:"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_CODE_RE = re.compile(r"^[a-z0-9_:-]{1,80}$")
ISO_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
PHASES = {
    "daily_validate",
    "bitcoin_refresh",
    "macro_refresh",
    "evidence_compile",
    "context_compile",
    "model_compile",
    "report_compile",
    "report_verify",
    "desktop_promote",
    "status_publish",
    "track2_run",
}
_AUTO_PROVIDER = object()


class KlineWorldRuntimeError(RuntimeError):
    """A Track 2 orchestration, delivery or status invariant failed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_bytes(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_bytes(path, _json_bytes(value))


def _immutable_bytes(path: Path, encoded: bytes) -> str:
    digest = sha256(encoded).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise KlineWorldRuntimeError("immutable_delivery_collision")
        return digest
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return digest


def _truth_boundary(generation_status: str) -> dict[str, Any]:
    success = generation_status == "model_generated_unreviewed"
    return {
        "track": "kline_only",
        "finance_newsletter_input": False,
        "local_evaluation_only": True,
        "contains_investment_advice": success,
        "automatic_execution_eligible": False,
        "broker_access": False,
        "portfolio_mutation": False,
        "publication_eligible": False,
    }


def _safe_failure_code(exc: BaseException) -> str:
    value = str(exc)
    return value if SAFE_CODE_RE.fullmatch(value) else "run_failed"


def _safe_ref(value: Any, *, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise KlineWorldRuntimeError(f"{field}_reference_invalid")
    path = str(value.get("path") or "")
    digest = str(value.get("sha256") or "")
    if not path or path.startswith("/") or ".." in Path(path).parts or not SHA256_RE.fullmatch(digest):
        raise KlineWorldRuntimeError(f"{field}_reference_invalid")
    return {"path": path, "sha256": digest}


def _read_ref(base: Path, reference: Mapping[str, Any], *, field: str) -> bytes:
    safe = _safe_ref(dict(reference), field=field)
    target = (base / safe["path"]).resolve()
    if base not in target.parents:
        raise KlineWorldRuntimeError(f"{field}_path_escape")
    try:
        encoded = target.read_bytes()
    except FileNotFoundError as exc:
        raise KlineWorldRuntimeError(f"{field}_unavailable") from exc
    if sha256(encoded).hexdigest() != safe["sha256"]:
        raise KlineWorldRuntimeError(f"{field}_hash_mismatch")
    return encoded


def _validate_report_summary(report: Mapping[str, Any], *, allow_fixture: bool) -> dict[str, Any]:
    if report.get("data_kind") != "real" and not allow_fixture:
        raise KlineWorldRuntimeError("fixture_report_delivery_forbidden")
    generation_status = str(report.get("generation_status") or "")
    if generation_status not in {"model_generated_unreviewed", "interpretation_unavailable"}:
        raise KlineWorldRuntimeError("report_generation_status_invalid")
    chart_count = len(report.get("charts") or [])
    relationship_count = len(report.get("relationships") or [])
    flow_count = len(report.get("flow_map") or [])
    trade_count = len(report.get("trade_plan") or [])
    falsifier_count = len(report.get("falsifiers") or [])
    if chart_count != 17 or relationship_count != 12:
        raise KlineWorldRuntimeError("report_visible_input_count_invalid")
    if generation_status == "interpretation_unavailable" and any(
        value != 0 for value in (flow_count, trade_count, falsifier_count)
    ):
        raise KlineWorldRuntimeError("fallback_contains_stale_interpretation")
    if generation_status == "model_generated_unreviewed" and falsifier_count != 2:
        raise KlineWorldRuntimeError("report_falsifier_count_invalid")
    boundary = report.get("truth_boundary") or {}
    expected_boundary = _truth_boundary(generation_status)
    for key, expected in expected_boundary.items():
        if boundary.get(key) != expected:
            raise KlineWorldRuntimeError("report_truth_boundary_invalid")
    return {
        "report_id": str(report.get("report_id") or ""),
        "context_id": str(report.get("context_id") or ""),
        "world_model_id": str(report.get("world_model_id") or ""),
        "report_date": str(report.get("report_date") or ""),
        "generated_at": str(report.get("generated_at") or ""),
        "data_kind": str(report.get("data_kind") or ""),
        "generation_status": generation_status,
        "posture": str(report.get("posture") or "unknown"),
        "chart_count": chart_count,
        "relationship_count": relationship_count,
        "flow_count": flow_count,
        "trade_count": trade_count,
        "falsifier_count": falsifier_count,
        "truth_boundary": expected_boundary,
    }


def _validate_delivery_summary(core: Mapping[str, Any], *, allow_fixture: bool) -> dict[str, Any]:
    summary_keys = {
        "report_id",
        "context_id",
        "world_model_id",
        "report_date",
        "generated_at",
        "data_kind",
        "generation_status",
        "posture",
        "chart_count",
        "relationship_count",
        "flow_count",
        "trade_count",
        "falsifier_count",
        "truth_boundary",
    }
    if set(core) != {"schema_version", *summary_keys, "source_report", "aliases"}:
        raise KlineWorldRuntimeError("delivery_identity_core_invalid")
    data_kind = str(core.get("data_kind") or "")
    if data_kind != "real" and not (allow_fixture and data_kind == "fixture"):
        raise KlineWorldRuntimeError("fixture_report_delivery_forbidden")
    generation_status = str(core.get("generation_status") or "")
    if generation_status not in {"model_generated_unreviewed", "interpretation_unavailable"}:
        raise KlineWorldRuntimeError("report_generation_status_invalid")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(core.get("report_date") or "")):
        raise KlineWorldRuntimeError("delivery_report_date_invalid")
    if not ISO_RE.fullmatch(str(core.get("generated_at") or "")):
        raise KlineWorldRuntimeError("delivery_generated_at_invalid")
    for key in ("report_id", "context_id", "world_model_id"):
        if not str(core.get(key) or "") or len(str(core.get(key))) > 180:
            raise KlineWorldRuntimeError("delivery_source_identity_invalid")
    counts = {
        key: core.get(key)
        for key in (
            "chart_count",
            "relationship_count",
            "flow_count",
            "trade_count",
            "falsifier_count",
        )
    }
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts.values()):
        raise KlineWorldRuntimeError("delivery_count_invalid")
    if counts["chart_count"] != 17 or counts["relationship_count"] != 12:
        raise KlineWorldRuntimeError("report_visible_input_count_invalid")
    if generation_status == "interpretation_unavailable" and any(
        counts[key] != 0 for key in ("flow_count", "trade_count", "falsifier_count")
    ):
        raise KlineWorldRuntimeError("fallback_contains_stale_interpretation")
    if generation_status == "model_generated_unreviewed" and counts["falsifier_count"] != 2:
        raise KlineWorldRuntimeError("report_falsifier_count_invalid")
    expected_boundary = _truth_boundary(generation_status)
    if core.get("truth_boundary") != expected_boundary:
        raise KlineWorldRuntimeError("delivery_truth_boundary_mismatch")
    return {key: core.get(key) for key in summary_keys}


class KlineWorldDeliveryStore:
    """Promote only replay-verified report bytes to the local Desktop aliases."""

    def __init__(
        self,
        report_store: KlineWorldReportStore,
        root: Path | str,
        output_root: Path | str,
        *,
        allow_fixture: bool = False,
    ) -> None:
        self.report_store = report_store
        self.root = Path(root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.allow_fixture = allow_fixture

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    def promote(self) -> tuple[dict[str, Any], dict[str, Any]]:
        report_state, report = self.report_store.latest()
        summary = _validate_report_summary(report, allow_fixture=self.allow_fixture)
        html_ref = _safe_ref(report_state.get("html"), field="source_html")
        markdown_ref = _safe_ref(report_state.get("markdown"), field="source_markdown")
        report_ref = _safe_ref(report_state.get("report"), field="source_report")
        receipt_ref = _safe_ref(report_state.get("receipt"), field="source_report_receipt")
        html = _read_ref(self.report_store.output_root, html_ref, field="source_html")
        markdown = _read_ref(
            self.report_store.output_root, markdown_ref, field="source_markdown"
        )
        _read_ref(self.report_store.root, report_ref, field="source_report")
        _read_ref(
            self.report_store.root, receipt_ref, field="source_report_receipt"
        )
        dated_base = f"{summary['report_date']}-kline-daily"
        aliases = {
            "latest_html": {"path": "latest.html", "sha256": sha256(html).hexdigest()},
            "latest_markdown": {"path": "latest.md", "sha256": sha256(markdown).hexdigest()},
            "dated_html": {"path": f"{dated_base}.html", "sha256": sha256(html).hexdigest()},
            "dated_markdown": {"path": f"{dated_base}.md", "sha256": sha256(markdown).hexdigest()},
        }
        core = {
            "schema_version": SCHEMA_VERSION,
            **summary,
            "source_report": {
                "report": report_ref,
                "html": html_ref,
                "markdown": markdown_ref,
                "receipt": receipt_ref,
            },
            "aliases": aliases,
        }
        delivery_id = f"{DELIVERY_ID_PREFIX}{_digest(core)}"
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "delivery_id": delivery_id,
            "identity_core": core,
        }
        digest = delivery_id.removeprefix(DELIVERY_ID_PREFIX)
        receipt_ref_out = {"path": f"receipts/{digest}.json"}
        receipt_ref_out["sha256"] = _immutable_bytes(
            self.root / receipt_ref_out["path"], _json_bytes(receipt)
        )
        state = {
            "schema_version": SCHEMA_VERSION,
            "delivery_id": delivery_id,
            "receipt": receipt_ref_out,
        }

        payloads = {
            "latest.html": html,
            "latest.md": markdown,
            f"{dated_base}.html": html,
            f"{dated_base}.md": markdown,
        }
        prior_aliases = {
            name: (self.output_root / name).read_bytes()
            if (self.output_root / name).exists()
            else None
            for name in payloads
        }
        prior_state = self.state_path.read_bytes() if self.state_path.exists() else None
        try:
            for name, encoded in payloads.items():
                _atomic_bytes(self.output_root / name, encoded)
            _atomic_json(self.state_path, state)
            replay_state, replay = self.latest()
            if replay_state != state or replay != core:
                raise KlineWorldRuntimeError("delivery_final_readback_mismatch")
        except Exception:
            for name, prior in prior_aliases.items():
                target = self.output_root / name
                if prior is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_bytes(target, prior)
            if prior_state is None:
                self.state_path.unlink(missing_ok=True)
            else:
                _atomic_bytes(self.state_path, prior_state)
            raise
        return state, core

    def latest(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineWorldRuntimeError("delivery_state_unavailable") from exc
        if not isinstance(state, dict) or set(state) != {"schema_version", "delivery_id", "receipt"}:
            raise KlineWorldRuntimeError("delivery_state_invalid")
        if state.get("schema_version") != SCHEMA_VERSION:
            raise KlineWorldRuntimeError("delivery_state_invalid")
        delivery_id = str(state.get("delivery_id") or "")
        if not delivery_id.startswith(DELIVERY_ID_PREFIX):
            raise KlineWorldRuntimeError("delivery_identity_invalid")
        digest = delivery_id.removeprefix(DELIVERY_ID_PREFIX)
        receipt_ref = _safe_ref(state.get("receipt"), field="delivery_receipt")
        if receipt_ref["path"] != f"receipts/{digest}.json":
            raise KlineWorldRuntimeError("delivery_receipt_reference_invalid")
        receipt_bytes = _read_ref(self.root, receipt_ref, field="delivery_receipt")
        try:
            receipt = json.loads(receipt_bytes)
        except json.JSONDecodeError as exc:
            raise KlineWorldRuntimeError("delivery_receipt_invalid") from exc
        if not isinstance(receipt, dict) or set(receipt) != {
            "schema_version",
            "event",
            "delivery_id",
            "identity_core",
        }:
            raise KlineWorldRuntimeError("delivery_receipt_invalid")
        core = receipt.get("identity_core")
        if (
            not isinstance(core, dict)
            or receipt.get("schema_version") != SCHEMA_VERSION
            or receipt.get("event") != "completed"
            or receipt.get("delivery_id") != delivery_id
            or core.get("schema_version") != SCHEMA_VERSION
            or delivery_id != f"{DELIVERY_ID_PREFIX}{_digest(core)}"
        ):
            raise KlineWorldRuntimeError("delivery_receipt_identity_mismatch")
        summary = _validate_delivery_summary(core, allow_fixture=self.allow_fixture)
        source = core.get("source_report")
        aliases = core.get("aliases")
        if not isinstance(source, dict) or set(source) != {"report", "html", "markdown", "receipt"}:
            raise KlineWorldRuntimeError("delivery_source_invalid")
        if not isinstance(aliases, dict) or set(aliases) != {
            "latest_html",
            "latest_markdown",
            "dated_html",
            "dated_markdown",
        }:
            raise KlineWorldRuntimeError("delivery_aliases_invalid")
        source_html = _read_ref(
            self.report_store.output_root, source["html"], field="source_html"
        )
        source_markdown = _read_ref(
            self.report_store.output_root,
            source["markdown"],
            field="source_markdown",
        )
        report_bytes = _read_ref(
            self.report_store.root, source["report"], field="source_report"
        )
        _read_ref(
            self.report_store.root,
            source["receipt"],
            field="source_report_receipt",
        )
        try:
            report = json.loads(report_bytes)
        except json.JSONDecodeError as exc:
            raise KlineWorldRuntimeError("source_report_invalid") from exc
        source_summary = _validate_report_summary(report, allow_fixture=self.allow_fixture)
        if any(core.get(key) != value for key, value in source_summary.items()):
            raise KlineWorldRuntimeError("delivery_source_projection_mismatch")
        expected_aliases = {
            "latest_html": ("latest.html", source_html),
            "latest_markdown": ("latest.md", source_markdown),
            "dated_html": (f"{summary['report_date']}-kline-daily.html", source_html),
            "dated_markdown": (f"{summary['report_date']}-kline-daily.md", source_markdown),
        }
        for key, (expected_path, source_bytes) in expected_aliases.items():
            reference = _safe_ref(aliases.get(key), field=f"delivery_{key}")
            if reference["path"] != expected_path:
                raise KlineWorldRuntimeError(f"delivery_{key}_path_invalid")
            alias_bytes = _read_ref(self.output_root, reference, field=f"delivery_{key}")
            if alias_bytes != source_bytes:
                raise KlineWorldRuntimeError(f"delivery_{key}_replay_mismatch")
        if core.get("truth_boundary") != _truth_boundary(summary["generation_status"]):
            raise KlineWorldRuntimeError("delivery_truth_boundary_mismatch")
        return state, dict(core)


class KlineWorldStatusStore:
    """Expose a strict, secret-free status projection over the last delivery."""

    def __init__(self, path: Path | str, delivery_store: KlineWorldDeliveryStore) -> None:
        self.path = Path(path).expanduser().resolve()
        self.delivery_store = delivery_store

    @staticmethod
    def _success(core: Mapping[str, Any], *, at: str) -> dict[str, Any]:
        return {
            "at": at,
            "delivery_id": f"{DELIVERY_ID_PREFIX}{_digest(core)}",
            **{
                key: core.get(key)
                for key in (
                    "report_id",
                    "context_id",
                    "world_model_id",
                    "report_date",
                    "generation_status",
                    "posture",
                    "chart_count",
                    "relationship_count",
                    "flow_count",
                    "trade_count",
                )
            },
        }

    def record_success(self, core: Mapping[str, Any], *, at: datetime) -> dict[str, Any]:
        status = {
            "schema_version": SCHEMA_VERSION,
            "state": "idle",
            "last_success": self._success(core, at=_iso(at)),
            "last_failure": None,
        }
        _atomic_json(self.path, status)
        return self.latest()

    def record_failure(self, *, code: str, phase: str, at: datetime) -> dict[str, Any]:
        if not SAFE_CODE_RE.fullmatch(code):
            code = "run_failed"
        if phase not in PHASES:
            phase = "track2_run"
        last_success = None
        try:
            prior = self.latest()
            last_success = prior.get("last_success")
        except KlineWorldRuntimeError:
            try:
                _, core = self.delivery_store.latest()
                last_success = self._success(
                    core, at=str(core.get("generated_at") or _iso(at))
                )
            except KlineWorldRuntimeError:
                pass
        status = {
            "schema_version": SCHEMA_VERSION,
            "state": "failed",
            "last_success": last_success,
            "last_failure": {"at": _iso(at), "code": code, "phase": phase},
        }
        _atomic_json(self.path, status)
        return self.latest()

    def latest(self) -> dict[str, Any]:
        try:
            status = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KlineWorldRuntimeError("runtime_status_unavailable") from exc
        if not isinstance(status, dict) or set(status) != {
            "schema_version",
            "state",
            "last_success",
            "last_failure",
        }:
            raise KlineWorldRuntimeError("runtime_status_invalid")
        if status.get("schema_version") != SCHEMA_VERSION or status.get("state") not in {"idle", "failed"}:
            raise KlineWorldRuntimeError("runtime_status_invalid")
        success = status.get("last_success")
        failure = status.get("last_failure")
        if success is not None:
            required = {
                "at",
                "delivery_id",
                "report_id",
                "context_id",
                "world_model_id",
                "report_date",
                "generation_status",
                "posture",
                "chart_count",
                "relationship_count",
                "flow_count",
                "trade_count",
            }
            if not isinstance(success, dict) or set(success) != required or not ISO_RE.fullmatch(str(success.get("at") or "")):
                raise KlineWorldRuntimeError("runtime_success_status_invalid")
            _, core = self.delivery_store.latest()
            expected = self._success(core, at=str(success["at"]))
            if success != expected:
                raise KlineWorldRuntimeError("runtime_success_status_mismatch")
        if failure is not None:
            if (
                not isinstance(failure, dict)
                or set(failure) != {"at", "code", "phase"}
                or not ISO_RE.fullmatch(str(failure.get("at") or ""))
                or not SAFE_CODE_RE.fullmatch(str(failure.get("code") or ""))
                or failure.get("phase") not in PHASES
            ):
                raise KlineWorldRuntimeError("runtime_failure_status_invalid")
        if status["state"] == "idle" and (success is None or failure is not None):
            raise KlineWorldRuntimeError("runtime_status_state_mismatch")
        if status["state"] == "failed" and failure is None:
            raise KlineWorldRuntimeError("runtime_status_state_mismatch")
        return status


class KlineWorldRuntime:
    """Execute one complete Track 2 cycle; the LaunchAgent owns recurrence."""

    def __init__(
        self,
        *,
        daily_root: Path | str,
        runtime_root: Path | str,
        output_root: Path | str,
        key_file: Path | str | None,
        bitcoin_http_get: Callable[[str], HttpCapture] = http_get_capture,
        macro_http_get: Callable[[str], HttpCapture] | None = None,
        world_model_provider: WorldModelProvider | None | object = _AUTO_PROVIDER,
        allow_fixture: bool = False,
        phase_observer: Callable[[str], None] | None = None,
    ) -> None:
        self.daily_root = Path(daily_root).expanduser().resolve()
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.key_file = Path(key_file).expanduser().resolve() if key_file else None
        self.allow_fixture = allow_fixture
        self.phase_observer = phase_observer
        self.world_model_provider = world_model_provider
        self.bitcoin_store = BitcoinDailyStore(
            self.runtime_root / "bitcoin", http_get=bitcoin_http_get
        )
        self.macro_store = MarketRegimeMacroDataStore(
            self.runtime_root / "macro",
            **({"http_get": macro_http_get} if macro_http_get is not None else {}),
        )
        self.evidence_store = MarketRegimeDailyEvidenceStore(
            self.daily_root,
            self.runtime_root / "macro",
            self.runtime_root / "evidence",
        )
        self.context_store = KlineWorldContextStore(
            self.runtime_root / "world-context", allow_fixture=allow_fixture
        )
        self.model_store = KlineWorldModelStore(
            self.context_store, self.runtime_root / "world-model"
        )
        self.report_store = KlineWorldReportStore(
            self.context_store,
            self.model_store,
            self.runtime_root / "world-report",
            self.output_root,
            allow_fixture=allow_fixture,
        )
        self.delivery_store = KlineWorldDeliveryStore(
            self.report_store,
            self.runtime_root / "world-delivery",
            self.output_root,
            allow_fixture=allow_fixture,
        )
        self.status_store = KlineWorldStatusStore(
            self.runtime_root / "world-status.json", self.delivery_store
        )

    def _phase(self, value: str) -> None:
        if self.phase_observer is not None:
            self.phase_observer(value)

    def _provider(self) -> WorldModelProvider | None:
        if self.world_model_provider is not _AUTO_PROVIDER:
            return self.world_model_provider  # type: ignore[return-value]
        if self.key_file is None or not self.key_file.is_file():
            return None
        return DeepSeekWorldModelProvider(self.key_file)

    def run_once(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        phase = "daily_validate"
        try:
            self._phase(phase)
            MarketRegimeDataStore(self.daily_root).latest()

            phase = "bitcoin_refresh"
            self._phase(phase)
            self.bitcoin_store.refresh(**({"now": current} if now is not None else {}))

            phase = "macro_refresh"
            self._phase(phase)
            self.macro_store.refresh(
                **({"now": current} if now is not None else {}),
                deployment_mode="local_prototype",
                license_status="local_evaluation_only",
            )

            phase = "evidence_compile"
            self._phase(phase)
            self.evidence_store.compile_latest()
            pack = self.evidence_store.latest()

            phase = "context_compile"
            self._phase(phase)
            bitcoin = self.bitcoin_store.latest()
            daily, macro = load_context_source_snapshots(
                daily_root=self.daily_root,
                macro_root=self.runtime_root / "macro",
                pack=pack,
            )
            context = build_kline_world_context(
                daily=daily,
                macro=macro,
                pack=pack,
                bitcoin=bitcoin,
                allow_fixture=self.allow_fixture,
            )
            self.context_store.publish(context)

            phase = "model_compile"
            self._phase(phase)
            model = self.model_store.compile_latest(self._provider())

            phase = "report_compile"
            self._phase(phase)
            self.report_store.compile_latest(generated_at=current)

            phase = "report_verify"
            self._phase(phase)
            report_state, report = self.report_store.latest()
            if (
                report.get("context_id") != context.get("context_id")
                or report.get("world_model_id") != model.get("world_model_id")
            ):
                raise KlineWorldRuntimeError("report_runtime_identity_mismatch")

            phase = "desktop_promote"
            self._phase(phase)
            delivery_state, delivery = self.delivery_store.promote()

            phase = "status_publish"
            self._phase(phase)
            status = self.status_store.record_success(
                delivery, at=datetime.now(timezone.utc) if now is None else current
            )
            return {
                "delivery_state": delivery_state,
                "delivery": delivery,
                "report_state": report_state,
                "report": report,
                "status": status,
            }
        except Exception as exc:
            code = _safe_failure_code(exc)
            try:
                self.status_store.record_failure(
                    code=code,
                    phase=phase,
                    at=datetime.now(timezone.utc) if now is None else current,
                )
            except Exception:
                pass
            raise KlineWorldRuntimeError(code) from exc

    def status(self) -> dict[str, Any]:
        """Read status and delivery only; this method creates no files."""
        return self.status_store.latest()
