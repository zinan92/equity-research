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

from data_core.market_regime_data import (
    SCHEMA_VERSION as DATA_SCHEMA_VERSION,
    MarketRegimeDataStore,
)
from data_core.market_regime_intraday_data import (
    INTRADAY_INSTRUMENTS,
    SCHEMA_VERSION as INTRADAY_SCHEMA_VERSION,
    MarketRegimeIntradayDataStore,
)
from data_core.market_regime_intraday_model import (
    COOLDOWN_SECONDS,
    ENTER_SCORE,
    EXIT_SCORE,
    MATERIAL_SCORE_DELTA,
    OVERLAY_MODEL_VERSION,
    OVERLAY_SCHEMA_VERSION,
    PERSISTENCE_OVERLAYS,
    MarketRegimeIntradayOverlayStore,
    validate_overlay,
)
from data_core.market_regime_model import (
    ANALYSIS_SCHEMA_VERSION,
    MODEL_VERSION as STRUCTURAL_MODEL_VERSION,
    MarketRegimeAnalysisStore,
)


API_SCHEMA_VERSION = "market-regime-api-v2"
MATERIAL_RECEIPT_SCHEMA_VERSION = "market-regime-material-change-receipt-v1"
MATERIAL_THRESHOLD_POLICY_VERSION = "market-regime-intraday-thresholds-v1"
HEALTH_SCHEMA_VERSION = "market-regime-health-v2"
SCHEDULER_SCHEMA_VERSION = "market-regime-scheduler-v1"
INTRADAY_SCHEDULER_SCHEMA_VERSION = "market-regime-intraday-scheduler-v1"
PROVIDER_FAILURE_SCHEMA_VERSION = "market-regime-provider-failure-v1"
ALLOWED_INTERVAL_HOURS = (4, 12)
ALLOWED_INTRADAY_INTERVAL_MINUTES = (15,)
INTRADAY_MAX_BACKOFF_SECONDS = 60 * 60
SCHEDULER_LOCK_RETRY_SECONDS = 30
STOP_POLL_SECONDS = 5
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
INTRADAY_KEYS = tuple(item.key for item in INTRADAY_INSTRUMENTS)


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


def configured_intraday_interval_minutes(value: int | str | None = None) -> int:
    raw = (
        value
        if value is not None
        else os.getenv("PARK_MARKET_REGIME_INTRADAY_INTERVAL_MINUTES", "15")
    )
    try:
        interval = int(raw)
    except (TypeError, ValueError) as exc:
        raise MarketRegimeRuntimeError(
            "market-regime intraday interval must be 15 minutes"
        ) from exc
    if interval not in ALLOWED_INTRADAY_INTERVAL_MINUTES:
        raise MarketRegimeRuntimeError(
            "market-regime intraday interval must be 15 minutes"
        )
    return interval


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise MarketRegimeRuntimeError("scheduler clock must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _instant(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketRegimeRuntimeError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise MarketRegimeRuntimeError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _age_seconds(value: Any, now: datetime, *, field: str) -> int | None:
    if value in {None, ""}:
        return None
    observed = _instant(value, field=field)
    return max(0, int((now.astimezone(timezone.utc) - observed).total_seconds()))


def _content_identity(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_non_actionable(
    payload: Mapping[str, Any],
    *,
    name: str,
    nested: bool = False,
) -> None:
    boundary = payload.get("truth_boundary") if nested else payload
    if not isinstance(boundary, Mapping):
        raise MarketRegimeRuntimeError(f"{name} truth boundary is unavailable")
    if boundary.get("action_eligible") is not False:
        raise MarketRegimeRuntimeError(f"{name} must remain non-actionable")
    if boundary.get("publication_eligible") is not False:
        raise MarketRegimeRuntimeError(f"{name} must remain non-publishable")


def _validate_structural_identity(
    snapshot: Mapping[str, Any], analysis: Mapping[str, Any]
) -> None:
    if snapshot.get("schema_version") != DATA_SCHEMA_VERSION:
        raise MarketRegimeRuntimeError("structural snapshot schema mismatch")
    if (
        analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION
        or analysis.get("model_version") != STRUCTURAL_MODEL_VERSION
    ):
        raise MarketRegimeRuntimeError("structural analysis schema mismatch")
    if analysis.get("source_run_id") != snapshot.get("run_id"):
        raise MarketRegimeRuntimeError("analysis and data snapshot run identities differ")
    fingerprint = str(analysis.get("input_fingerprint") or "")
    expected = sha256(
        f"{STRUCTURAL_MODEL_VERSION}:{fingerprint}".encode("utf-8")
    ).hexdigest()
    if analysis.get("analysis_id") != f"market-regime-analysis:{expected}":
        raise MarketRegimeRuntimeError("structural analysis identity mismatch")
    _require_non_actionable(analysis, name="structural analysis", nested=True)
    snapshot_publication = snapshot.get("publication_eligible")
    snapshot_action = snapshot.get("action_eligible")
    if snapshot_publication is True or snapshot_action is True:
        raise MarketRegimeRuntimeError("structural snapshot truth boundary mismatch")


def _validate_intraday_identity(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("schema_version") != INTRADAY_SCHEMA_VERSION:
        raise MarketRegimeRuntimeError("intraday snapshot schema mismatch")
    core = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    expected = sha256(_json_bytes(core)).hexdigest()
    if snapshot.get("snapshot_id") != f"market-regime-intraday-snapshot:{expected}":
        raise MarketRegimeRuntimeError("intraday snapshot identity mismatch")
    _require_non_actionable(snapshot, name="intraday snapshot")


def _validate_overlay_identity(
    analysis: Mapping[str, Any],
    intraday: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> None:
    try:
        validate_overlay(overlay)
    except Exception as exc:
        raise MarketRegimeRuntimeError(str(exc)) from exc
    if overlay.get("schema_version") != OVERLAY_SCHEMA_VERSION:
        raise MarketRegimeRuntimeError("overlay schema mismatch")
    structural = overlay.get("structural")
    live_input = overlay.get("intraday")
    if (
        not isinstance(structural, Mapping)
        or structural.get("analysis_id") != analysis.get("analysis_id")
    ):
        raise MarketRegimeRuntimeError("overlay and structural analysis identities differ")
    if (
        not isinstance(live_input, Mapping)
        or live_input.get("snapshot_id") != intraday.get("snapshot_id")
    ):
        raise MarketRegimeRuntimeError("overlay and intraday snapshot identities differ")
    material = overlay.get("material_change")
    if (
        not isinstance(material, Mapping)
        or material.get("baseline_overlay_id") != overlay.get("baseline_overlay_id")
    ):
        raise MarketRegimeRuntimeError("overlay material baseline identity mismatch")
    _require_non_actionable(overlay, name="overlay", nested=True)


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


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _optional_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _restore_optional_bytes(path: Path, payload: bytes | None) -> None:
    if payload is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    _write_bytes_atomic(path, payload)


def _try_file_lock(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        return None
    return descriptor


def _unlock_file(descriptor: int) -> None:
    fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)


def _file_lock_busy(path: Path) -> bool:
    try:
        descriptor = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        return True
    _unlock_file(descriptor)
    return False


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


def _intraday_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    instrument = item.get("instrument")
    if not isinstance(instrument, Mapping):
        raise MarketRegimeRuntimeError("intraday instrument identity is invalid")
    reference = item.get("normalized_artifact")
    evidence = None
    if isinstance(reference, Mapping):
        evidence = {
            "path": reference.get("path"),
            "sha256": reference.get("sha256"),
            "schema_version": reference.get("schema_version"),
        }
    projected: dict[str, Any] = {
        "instrument": dict(instrument),
        "provider": item.get("provider"),
        "selected_endpoint": item.get("selected_endpoint"),
        "interval": item.get("interval"),
        "bar_count": item.get("bar_count", 0),
        "provider_timestamp": item.get("provider_timestamp"),
        "last_completed_bar_end_at": item.get("last_completed_bar_end_at"),
        "last_completed_session": item.get("last_completed_session"),
        "observed_at": item.get("observed_at"),
        "received_at": item.get("received_at"),
        "age_seconds": item.get("age_seconds"),
        "current_age_seconds": item.get("current_age_seconds"),
        "session_state": item.get("session_state"),
        "freshness": item.get("freshness"),
        "refresh_status": item.get("refresh_status"),
        "evidence": evidence,
        "publication_eligible": item.get("publication_eligible", False),
        "action_eligible": item.get("action_eligible", False),
    }
    if item.get("refresh_failure"):
        failure = item["refresh_failure"]
        if isinstance(failure, Mapping):
            projected["refresh_failure"] = {
                "reason": failure.get("reason"),
                "source_attempts": failure.get("source_attempts"),
            }
    return projected


def _provider_failure_receipt(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = snapshot.get("instruments")
    if not isinstance(rows, list):
        raise MarketRegimeRuntimeError("intraday snapshot instruments are invalid")
    failures: list[dict[str, Any]] = []
    session_counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise MarketRegimeRuntimeError("intraday snapshot instrument is invalid")
        instrument = row.get("instrument")
        key = str(instrument.get("key") if isinstance(instrument, Mapping) else "")
        session = str(row.get("session_state") or "unknown")
        session_counts[session] = session_counts.get(session, 0) + 1
        rejected = row.get("refresh_status") == "rejected"
        failure = row.get("refresh_failure")
        attempts = (
            failure.get("source_attempts")
            if rejected and isinstance(failure, Mapping)
            else row.get("source_attempts")
        )
        statuses: list[int | None] = []
        endpoints: list[str] = []
        failed_attempts: list[Mapping[str, Any]] = []
        if isinstance(attempts, list):
            for attempt in attempts:
                if not isinstance(attempt, Mapping):
                    continue
                if attempt.get("accepted") is not False:
                    continue
                failed_attempts.append(attempt)
                raw_status = attempt.get("status_code")
                statuses.append(int(raw_status) if isinstance(raw_status, int) else None)
                endpoint = str(attempt.get("endpoint") or "")
                if endpoint:
                    endpoints.append(endpoint)
        if not rejected and not failed_attempts:
            continue
        reason = (
            str(failure.get("reason") or "provider response rejected")
            if rejected and isinstance(failure, Mapping)
            else "; ".join(
                str(attempt.get("reason") or "provider attempt rejected")
                for attempt in failed_attempts
            )
        )
        if 429 in statuses:
            category = "rate_limited"
        elif any(status is not None and status >= 500 for status in statuses):
            category = "provider_server_error"
        else:
            category = "bad_or_unavailable_response"
        failures.append(
            {
                "instrument": key,
                "category": category,
                "reason": reason,
                "status_codes": statuses,
                "endpoints": endpoints,
                "asset_refresh_rejected": rejected,
                "degraded_fallback_succeeded": not rejected,
            }
        )
    return {
        "schema_version": PROVIDER_FAILURE_SCHEMA_VERSION,
        "detected": bool(failures),
        "affected_count": len(failures),
        "rejected_count": sum(
            bool(failure["asset_refresh_rejected"]) for failure in failures
        ),
        "failures": failures,
        "session_counts": dict(sorted(session_counts.items())),
        "closed_or_maintenance_is_failure": False,
    }


def _intraday_backoff_seconds(interval_minutes: int, consecutive_failures: int) -> int:
    base = interval_minutes * 60
    if consecutive_failures <= 0:
        return base
    return min(INTRADAY_MAX_BACKOFF_SECONDS, base * (2 ** (consecutive_failures - 1)))


def build_material_change_receipt(overlay: Mapping[str, Any]) -> dict[str, Any]:
    material = overlay.get("material_change")
    transition = overlay.get("transition")
    contributions = overlay.get("signal_contributions")
    if not isinstance(material, Mapping) or not isinstance(transition, Mapping):
        raise MarketRegimeRuntimeError("overlay change state is incomplete")
    if not isinstance(contributions, list):
        raise MarketRegimeRuntimeError("overlay contribution evidence is incomplete")
    evidence: list[dict[str, Any]] = []
    for row in contributions:
        if not isinstance(row, Mapping):
            raise MarketRegimeRuntimeError("overlay contribution evidence is invalid")
        instrument = str(row.get("instrument") or "")
        evidence_id = str(row.get("evidence_id") or "")
        artifact_sha = str(row.get("normalized_artifact_sha256") or "")
        if instrument not in INTRADAY_KEYS or not evidence_id or len(artifact_sha) != 64:
            raise MarketRegimeRuntimeError("overlay contribution evidence identity is invalid")
        evidence.append(
            {
                "instrument": instrument,
                "evidence_id": evidence_id,
                "normalized_artifact_sha256": artifact_sha,
                "last_completed_bar_end_at": row.get("last_completed_bar_end_at"),
                "signed_weight": row.get("signed_weight"),
                "impulse_score": row.get("impulse_score"),
                "contribution": row.get("contribution"),
            }
        )
    core: dict[str, Any] = {
        "schema_version": MATERIAL_RECEIPT_SCHEMA_VERSION,
        "generated_at": overlay.get("generated_at"),
        "previous_overlay_id": overlay.get("baseline_overlay_id"),
        "current_overlay_id": overlay.get("overlay_id"),
        "structural_analysis_id": (overlay.get("structural") or {}).get("analysis_id"),
        "intraday_snapshot_id": (overlay.get("intraday") or {}).get("snapshot_id"),
        "input_fingerprint": overlay.get("input_fingerprint"),
        "overlay_model_version": overlay.get("model_version"),
        "threshold_policy": {
            "version": MATERIAL_THRESHOLD_POLICY_VERSION,
            "enter_score": ENTER_SCORE,
            "exit_score": EXIT_SCORE,
            "persistence_overlays": PERSISTENCE_OVERLAYS,
            "cooldown_seconds": COOLDOWN_SECONDS,
            "material_score_delta": MATERIAL_SCORE_DELTA,
        },
        "change": {
            "relation": overlay.get("relation"),
            "is_material": material.get("is_material"),
            "reasons": material.get("reasons"),
            "relation_from": material.get("relation_from"),
            "relation_to": material.get("relation_to"),
            "a_share_score_delta": material.get("a_share_score_delta"),
            "cross_asset_score_delta": material.get("cross_asset_score_delta"),
        },
        "cooldown": {
            "pending_relation": transition.get("pending_relation"),
            "pending_count": transition.get("pending_count"),
            "persistence_required": transition.get("persistence_required"),
            "cooldown_until": transition.get("cooldown_until"),
            "blocked_by_cooldown": transition.get("blocked_by_cooldown"),
            "transitioned": transition.get("transitioned"),
        },
        "contribution_evidence": evidence,
        "truth_boundary": {
            "read_only": True,
            "drivers_are_causal_claims": False,
            "forecast": False,
            "publication_eligible": False,
            "action_eligible": False,
        },
    }
    identity = _content_identity(core)
    return {
        **core,
        "receipt_id": f"market-regime-material-change:{identity}",
    }


def build_market_regime_api_payload(
    snapshot: Mapping[str, Any],
    analysis: Mapping[str, Any],
    intraday: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_structural_identity(snapshot, analysis)
    _validate_intraday_identity(intraday)
    _validate_overlay_identity(analysis, intraday, overlay)
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
    intraday_items = intraday.get("instruments") or []
    if not isinstance(intraday_items, list):
        raise MarketRegimeRuntimeError("intraday snapshot instruments are invalid")
    intraday_by_key: dict[str, Mapping[str, Any]] = {}
    for item in intraday_items:
        if not isinstance(item, Mapping):
            raise MarketRegimeRuntimeError("intraday snapshot instrument is invalid")
        instrument = item.get("instrument")
        key = str(instrument.get("key") if isinstance(instrument, Mapping) else "")
        if key not in INTRADAY_KEYS or key in intraday_by_key:
            raise MarketRegimeRuntimeError("intraday snapshot instrument identity is invalid")
        if item.get("publication_eligible") is True or item.get("action_eligible") is True:
            raise MarketRegimeRuntimeError("intraday instrument truth boundary mismatch")
        intraday_by_key[key] = item
    intraday_missing = [key for key in INTRADAY_KEYS if key not in intraday_by_key]
    if intraday_missing:
        raise MarketRegimeRuntimeError(
            f"market-regime API intraday snapshot is missing: {', '.join(intraday_missing)}"
        )
    material_receipt = build_material_change_receipt(overlay)
    structural_projection = {
        "source_run_id": snapshot.get("run_id"),
        "analysis_id": analysis.get("analysis_id"),
        "snapshot_generated_at": snapshot.get("generated_at"),
        "analysis_generated_at": analysis.get("generated_at"),
        "verdict_as_of": analysis.get("verdict_as_of"),
        "latest_evidence_at": analysis.get("latest_evidence_at"),
        "data_quality": snapshot.get("quality"),
        "analysis_status": analysis.get("status"),
        "data_kind": analysis.get("data_kind"),
        "license": snapshot.get("license"),
        "analysis": analysis,
        "charts": [_instrument_projection(by_key[key]) for key in PRIMARY_CHART_KEYS],
        "probes": [_instrument_projection(by_key[key]) for key in PROBE_KEYS],
    }
    intraday_projection = {
        "snapshot_id": intraday.get("snapshot_id"),
        "run_id": intraday.get("run_id"),
        "generated_at": intraday.get("generated_at"),
        "quality": intraday.get("quality"),
        "data_kind": intraday.get("data_kind"),
        "accepted_count": intraday.get("accepted_count"),
        "rejected_count": intraday.get("rejected_count"),
        "license": intraday.get("license"),
        "assets": [
            _intraday_projection(intraday_by_key[key])
            for key in INTRADAY_KEYS
        ],
    }
    data_kinds = {
        str(structural_projection.get("data_kind") or "unknown"),
        str(intraday_projection.get("data_kind") or "unknown"),
    }
    payload = {
        "schema_version": API_SCHEMA_VERSION,
        "generated_at": overlay.get("generated_at"),
        "structural": structural_projection,
        "intraday": intraday_projection,
        "overlay": overlay,
        "material_change_receipt": material_receipt,
        "data_kind": next(iter(data_kinds)) if len(data_kinds) == 1 else "mixed",
        "truth_boundary": {
            "judgment_state": "model_generated_unreviewed",
            "read_only": True,
            "structural_labels_overwritten": False,
            "drivers_are_causal_claims": False,
            "forecast": False,
            "investment_advice": False,
            "not_investment_advice": True,
            "publication_eligible": False,
            "action_eligible": False,
        },
        # Backward-compatible daily projection for the pre-S4 local page.
        "source_run_id": structural_projection["source_run_id"],
        "analysis_id": structural_projection["analysis_id"],
        "intraday_snapshot_id": intraday_projection["snapshot_id"],
        "overlay_id": overlay.get("overlay_id"),
        "material_change_receipt_id": material_receipt["receipt_id"],
        "verdict_as_of": structural_projection["verdict_as_of"],
        "latest_evidence_at": structural_projection["latest_evidence_at"],
        "data_quality": structural_projection["data_quality"],
        "analysis_status": structural_projection["analysis_status"],
        "license": structural_projection["license"],
        "analysis": analysis,
        "charts": structural_projection["charts"],
        "probes": structural_projection["probes"],
    }
    identity = _content_identity(payload)
    return {**payload, "bundle_id": f"market-regime-api:{identity}"}


class MarketRegimeApiStore:
    """Publish and verify one cohesive, last-successful API bundle."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def publish(
        self,
        snapshot: Mapping[str, Any],
        analysis: Mapping[str, Any],
        intraday: Mapping[str, Any],
        overlay: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = build_market_regime_api_payload(
            snapshot,
            analysis,
            intraday,
            overlay,
        )
        identity = payload["bundle_id"].split(":", 1)[1]
        relative = f"api/artifacts/{identity}.json"
        artifact_hash = _write_immutable(self.root / relative, payload)
        encoded = (self.root / relative).read_bytes()
        if sha256(encoded).hexdigest() != artifact_hash:
            raise MarketRegimeRuntimeError("market-regime API staged artifact hash mismatch")
        pointer = {
            "schema_version": API_SCHEMA_VERSION,
            "bundle_id": payload["bundle_id"],
            "source_run_id": payload["source_run_id"],
            "analysis_id": payload["analysis_id"],
            "intraday_snapshot_id": payload["intraday_snapshot_id"],
            "overlay_id": payload["overlay_id"],
            "material_change_receipt_id": payload["material_change_receipt_id"],
            "artifact": {"path": relative, "sha256": artifact_hash},
        }
        _write_atomic(self.root / "api" / "latest.json", pointer)
        return payload

    def publish_latest(self) -> dict[str, Any]:
        snapshot = MarketRegimeDataStore(self.root).latest()
        analysis = MarketRegimeAnalysisStore(self.root).latest()
        intraday = MarketRegimeIntradayDataStore(self.root).latest()
        overlay = MarketRegimeIntradayOverlayStore(self.root).latest()
        return self.publish(snapshot, analysis, intraday, overlay)

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
        identity = _content_identity(identity_payload)
        structural = payload.get("structural")
        intraday = payload.get("intraday")
        overlay = payload.get("overlay")
        material = payload.get("material_change_receipt")
        if not all(isinstance(value, Mapping) for value in (structural, intraday, overlay, material)):
            raise MarketRegimeRuntimeError("market-regime API cohesive layers are incomplete")
        assert isinstance(structural, Mapping)
        assert isinstance(intraday, Mapping)
        assert isinstance(overlay, Mapping)
        assert isinstance(material, Mapping)
        try:
            validate_overlay(overlay)
        except Exception as exc:
            raise MarketRegimeRuntimeError(str(exc)) from exc
        material_core = {key: value for key, value in material.items() if key != "receipt_id"}
        material_identity = _content_identity(material_core)
        assets = intraday.get("assets")
        asset_keys = {
            str((row.get("instrument") or {}).get("key") or "")
            for row in assets
            if isinstance(row, Mapping)
        } if isinstance(assets, list) else set()
        _require_non_actionable(payload, name="API bundle", nested=True)
        if (
            payload.get("bundle_id") != f"market-regime-api:{identity}"
            or pointer.get("bundle_id") != payload.get("bundle_id")
            or pointer.get("source_run_id") != payload.get("source_run_id")
            or pointer.get("analysis_id") != payload.get("analysis_id")
            or pointer.get("intraday_snapshot_id") != payload.get("intraday_snapshot_id")
            or pointer.get("overlay_id") != payload.get("overlay_id")
            or pointer.get("material_change_receipt_id")
            != payload.get("material_change_receipt_id")
            or structural.get("analysis_id") != payload.get("analysis_id")
            or intraday.get("snapshot_id") != payload.get("intraday_snapshot_id")
            or overlay.get("overlay_id") != payload.get("overlay_id")
            or (overlay.get("structural") or {}).get("analysis_id")
            != structural.get("analysis_id")
            or (overlay.get("intraday") or {}).get("snapshot_id")
            != intraday.get("snapshot_id")
            or material.get("receipt_id")
            != f"market-regime-material-change:{material_identity}"
            or material.get("receipt_id") != payload.get("material_change_receipt_id")
            or material.get("current_overlay_id") != overlay.get("overlay_id")
            or material.get("structural_analysis_id") != structural.get("analysis_id")
            or material.get("intraday_snapshot_id") != intraday.get("snapshot_id")
            or asset_keys != set(INTRADAY_KEYS)
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
        intraday_store_factory: Callable[[Path], Any] = MarketRegimeIntradayDataStore,
        overlay_store_factory: Callable[[Path], Any] = MarketRegimeIntradayOverlayStore,
        api_store_factory: Callable[[Path], Any] = MarketRegimeApiStore,
    ) -> None:
        self.root = Path(root or market_regime_root()).expanduser().resolve()
        self.interval_hours = configured_interval_hours(interval_hours)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or time.sleep
        self.data_store_factory = data_store_factory
        self.analysis_store_factory = analysis_store_factory
        self.intraday_store_factory = intraday_store_factory
        self.overlay_store_factory = overlay_store_factory
        self.api_store_factory = api_store_factory
        self.status_path = self.root / "scheduler" / "status.json"
        self.lock_path = self.root / "scheduler" / "refresh.lock"
        self.pipeline_lock_path = self.root / "scheduler" / "pipeline.lock"

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
        return _try_file_lock(self.lock_path)

    def _try_pipeline_lock(self) -> int | None:
        return _try_file_lock(self.pipeline_lock_path)

    @staticmethod
    def _unlock(descriptor: int) -> None:
        _unlock_file(descriptor)

    def _lock_busy(self) -> bool:
        return _file_lock_busy(self.lock_path)

    def cycle(self) -> dict[str, Any]:
        descriptor = self._try_lock()
        if descriptor is None:
            return {
                "schema_version": SCHEDULER_SCHEMA_VERSION,
                "state": "busy",
                "busy": True,
                "interval_hours": self.interval_hours,
                "retry_in_seconds": SCHEDULER_LOCK_RETRY_SECONDS,
            }
        pipeline_descriptor = self._try_pipeline_lock()
        if pipeline_descriptor is None:
            self._unlock(descriptor)
            return {
                "schema_version": SCHEDULER_SCHEMA_VERSION,
                "state": "busy",
                "busy": True,
                "contention": "cohesive_pipeline",
                "interval_hours": self.interval_hours,
                "retry_in_seconds": SCHEDULER_LOCK_RETRY_SECONDS,
            }
        try:
            previous = self._read_status() or {}
            started = self.clock().astimezone(timezone.utc)
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
                "intraday_run_id": previous.get("intraday_run_id"),
                "intraday_snapshot_id": previous.get("intraday_snapshot_id"),
                "overlay_id": previous.get("overlay_id"),
                "material_change_receipt_id": previous.get("material_change_receipt_id"),
                "bundle_id": previous.get("bundle_id"),
                "data_quality": previous.get("data_quality"),
                "analysis_status": previous.get("analysis_status"),
                "intraday_quality": previous.get("intraday_quality"),
                "overlay_relation": previous.get("overlay_relation"),
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
                intraday_store = self.intraday_store_factory(self.root)
                intraday = intraday_store.latest()
                overlay_store = self.overlay_store_factory(self.root)
                compiled_overlay = overlay_store.compile_latest()
                overlay = overlay_store.latest()
                compiled_payload = compiled_overlay.get("overlay") or {}
                if compiled_payload.get("overlay_id") != overlay.get("overlay_id"):
                    raise MarketRegimeRuntimeError(
                        "compiled result differs from verified latest overlay"
                    )
                api_store = self.api_store_factory(self.root)
                published = api_store.publish(snapshot, analysis, intraday, overlay)
                bundle = api_store.latest()
                if published.get("bundle_id") != bundle.get("bundle_id"):
                    raise MarketRegimeRuntimeError(
                        "published result differs from verified latest API bundle"
                    )
                finished = self.clock().astimezone(timezone.utc)
                result = {
                    **running,
                    "state": "idle",
                    "busy": False,
                    "last_success_at": _iso(finished),
                    "next_due_at": _iso(finished + timedelta(hours=self.interval_hours)),
                    "source_run_id": snapshot.get("run_id"),
                    "analysis_id": analysis.get("analysis_id"),
                    "intraday_run_id": intraday.get("run_id"),
                    "intraday_snapshot_id": intraday.get("snapshot_id"),
                    "overlay_id": overlay.get("overlay_id"),
                    "material_change_receipt_id": bundle.get(
                        "material_change_receipt_id"
                    ),
                    "bundle_id": bundle.get("bundle_id"),
                    "data_quality": snapshot.get("quality"),
                    "analysis_status": analysis.get("status"),
                    "intraday_quality": intraday.get("quality"),
                    "overlay_relation": overlay.get("relation"),
                    "last_error": None,
                }
            except Exception as exc:
                finished = self.clock().astimezone(timezone.utc)
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
            self._unlock(pipeline_descriptor)
            self._unlock(descriptor)

    def health(self) -> dict[str, Any]:
        busy = self._lock_busy()
        status = self._read_status()
        now = self.clock().astimezone(timezone.utc)
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
            latest = {
                "status": "unavailable",
                "detail": str(exc),
                "layers": {
                    key: {"status": "unavailable"}
                    for key in ("structural", "intraday", "overlay", "bundle")
                },
            }
        else:
            structural = bundle["structural"]
            intraday = bundle["intraday"]
            overlay = bundle["overlay"]
            assets = intraday.get("assets") or []
            session_counts: dict[str, int] = {}
            freshness_counts: dict[str, int] = {}
            provider_ages: list[int] = []
            asset_errors: list[dict[str, Any]] = []
            for row in assets:
                if not isinstance(row, Mapping):
                    continue
                session = str(row.get("session_state") or "unknown")
                freshness = str(row.get("freshness") or "unavailable")
                session_counts[session] = session_counts.get(session, 0) + 1
                freshness_counts[freshness] = freshness_counts.get(freshness, 0) + 1
                age = _age_seconds(
                    row.get("provider_timestamp"),
                    now,
                    field=f"health.{(row.get('instrument') or {}).get('key')}.provider_timestamp",
                )
                if age is not None:
                    provider_ages.append(age)
                if row.get("refresh_failure"):
                    asset_errors.append(
                        {
                            "instrument": (row.get("instrument") or {}).get("key"),
                            "reason": (row.get("refresh_failure") or {}).get("reason"),
                        }
                    )
            structural_reference = (
                structural.get("latest_evidence_at")
                or structural.get("analysis_generated_at")
            )
            overlay_generated = overlay.get("generated_at")
            bundle_generated = bundle.get("generated_at")
            latest = {
                "status": "available",
                "bundle_id": bundle.get("bundle_id"),
                "source_run_id": bundle.get("source_run_id"),
                "analysis_id": bundle.get("analysis_id"),
                "data_quality": bundle.get("data_quality"),
                "analysis_status": bundle.get("analysis_status"),
                "verdict_as_of": bundle.get("verdict_as_of"),
                "intraday_snapshot_id": bundle.get("intraday_snapshot_id"),
                "overlay_id": bundle.get("overlay_id"),
                "material_change_receipt_id": bundle.get(
                    "material_change_receipt_id"
                ),
                "layers": {
                    "structural": {
                        "status": structural.get("analysis_status"),
                        "quality": structural.get("data_quality"),
                        "partial": structural.get("analysis_status") != "full"
                        or structural.get("data_quality") != "fresh",
                        "last_success_at": structural.get("analysis_generated_at"),
                        "evidence_at": structural_reference,
                        "age_seconds": _age_seconds(
                            structural_reference,
                            now,
                            field="health.structural.evidence_at",
                        ),
                        "analysis_id": structural.get("analysis_id"),
                        "errors": (structural.get("analysis") or {}).get(
                            "rejected_inputs", []
                        ),
                    },
                    "intraday": {
                        "status": "available",
                        "quality": intraday.get("quality"),
                        "partial": intraday.get("quality") != "complete",
                        "last_success_at": intraday.get("generated_at"),
                        "age_seconds": _age_seconds(
                            intraday.get("generated_at"),
                            now,
                            field="health.intraday.generated_at",
                        ),
                        "newest_provider_age_seconds": min(provider_ages)
                        if provider_ages
                        else None,
                        "oldest_provider_age_seconds": max(provider_ages)
                        if provider_ages
                        else None,
                        "session_counts": dict(sorted(session_counts.items())),
                        "freshness_counts": dict(sorted(freshness_counts.items())),
                        "accepted_count": intraday.get("accepted_count"),
                        "rejected_count": intraday.get("rejected_count"),
                        "snapshot_id": intraday.get("snapshot_id"),
                        "errors": asset_errors,
                    },
                    "overlay": {
                        "status": "available",
                        "partial": overlay.get("relation") == "insufficient",
                        "last_success_at": overlay_generated,
                        "age_seconds": _age_seconds(
                            overlay_generated,
                            now,
                            field="health.overlay.generated_at",
                        ),
                        "overlay_id": overlay.get("overlay_id"),
                        "relation": overlay.get("relation"),
                        "material": (overlay.get("material_change") or {}).get(
                            "is_material"
                        ),
                        "cooldown_until": (overlay.get("transition") or {}).get(
                            "cooldown_until"
                        ),
                        "blocked_by_cooldown": (overlay.get("transition") or {}).get(
                            "blocked_by_cooldown"
                        ),
                        "errors": overlay.get("excluded_signals") or [],
                    },
                    "bundle": {
                        "status": "available",
                        "partial": structural.get("analysis_status") != "full"
                        or structural.get("data_quality") != "fresh"
                        or intraday.get("quality") != "complete"
                        or overlay.get("relation") == "insufficient",
                        "last_success_at": bundle_generated,
                        "age_seconds": _age_seconds(
                            bundle_generated,
                            now,
                            field="health.bundle.generated_at",
                        ),
                        "bundle_id": bundle.get("bundle_id"),
                        "errors": asset_errors,
                    },
                },
            }
        intraday_scheduler = MarketRegimeIntradayRuntime(
            self.root, interval_minutes=15
        ).status()
        return {
            "schema_version": HEALTH_SCHEMA_VERSION,
            "observed_at": _iso(now),
            "scheduler": scheduler,
            "intraday_scheduler": intraday_scheduler,
            "latest": latest,
            "last_error": scheduler.get("last_error")
            or scheduler.get("last_failure")
            or intraday_scheduler.get("last_error")
            or intraday_scheduler.get("last_failure"),
        }

    def run_forever(self) -> None:
        while True:
            result = self.cycle()
            delay = (
                SCHEDULER_LOCK_RETRY_SECONDS
                if result.get("state") == "busy"
                else self.interval_hours * 3600
            )
            self.sleeper(delay)


class MarketRegimeIntradayRuntime:
    """Serial 15-minute target loop for the verified intraday pipeline."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        interval_minutes: int | str | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        data_store_factory: Callable[[Path], Any] = MarketRegimeDataStore,
        analysis_store_factory: Callable[[Path], Any] = MarketRegimeAnalysisStore,
        intraday_store_factory: Callable[[Path], Any] = MarketRegimeIntradayDataStore,
        overlay_store_factory: Callable[[Path], Any] = MarketRegimeIntradayOverlayStore,
        api_store_factory: Callable[[Path], Any] = MarketRegimeApiStore,
    ) -> None:
        self.root = Path(root or market_regime_root()).expanduser().resolve()
        self.interval_minutes = configured_intraday_interval_minutes(interval_minutes)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or time.sleep
        self.data_store_factory = data_store_factory
        self.analysis_store_factory = analysis_store_factory
        self.intraday_store_factory = intraday_store_factory
        self.overlay_store_factory = overlay_store_factory
        self.api_store_factory = api_store_factory
        self.status_path = self.root / "intraday" / "scheduler" / "status.json"
        self.lock_path = self.root / "intraday" / "scheduler" / "refresh.lock"
        self.stop_path = self.root / "intraday" / "scheduler" / "STOP"
        self.pipeline_lock_path = self.root / "scheduler" / "pipeline.lock"
        self.overlay_pointer_path = self.root / "intraday" / "overlay" / "latest.json"
        self.api_pointer_path = self.root / "api" / "latest.json"

    def _read_status(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise MarketRegimeRuntimeError(
                "market-regime intraday scheduler status is not JSON"
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != INTRADAY_SCHEDULER_SCHEMA_VERSION
        ):
            raise MarketRegimeRuntimeError(
                "market-regime intraday scheduler status schema mismatch"
            )
        return payload

    def stop_requested(self) -> bool:
        raw = os.getenv("PARK_MARKET_REGIME_INTRADAY_ENABLED", "1").strip().lower()
        if raw not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            raise MarketRegimeRuntimeError(
                "PARK_MARKET_REGIME_INTRADAY_ENABLED must be true or false"
            )
        return raw in {"0", "false", "no", "off"} or self.stop_path.exists()

    def request_stop(self, *, reason: str = "operator_requested") -> dict[str, Any]:
        requested = self.clock().astimezone(timezone.utc)
        marker = {
            "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
            "requested_at": _iso(requested),
            "reason": reason,
        }
        _write_atomic(self.stop_path, marker)
        return marker

    def clear_stop(self) -> None:
        try:
            self.stop_path.unlink()
        except FileNotFoundError:
            pass

    def _try_lock(self) -> int | None:
        return _try_file_lock(self.lock_path)

    def _try_pipeline_lock(self) -> int | None:
        return _try_file_lock(self.pipeline_lock_path)

    @staticmethod
    def _unlock(descriptor: int) -> None:
        _unlock_file(descriptor)

    def _lock_busy(self) -> bool:
        return _file_lock_busy(self.lock_path)

    def status(self) -> dict[str, Any]:
        busy = self._lock_busy()
        try:
            stopped = self.stop_requested()
            payload = self._read_status()
        except MarketRegimeRuntimeError as exc:
            return {
                "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
                "state": "unavailable",
                "busy": busy,
                "stop_requested": False,
                "interval_minutes": self.interval_minutes,
                "detail": str(exc),
            }
        if payload is None:
            return {
                "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
                "state": "stopped" if stopped else "unavailable",
                "busy": busy,
                "stop_requested": stopped,
                "interval_minutes": self.interval_minutes,
            }
        result = {**payload, "busy": busy, "stop_requested": stopped}
        if stopped and not busy:
            result["state"] = "stopped"
        elif payload.get("state") == "running" and not busy:
            result["state"] = "interrupted"
        return result

    def _record_stopped(self) -> dict[str, Any]:
        previous = self._read_status() or {}
        observed = self.clock().astimezone(timezone.utc)
        result = {
            **previous,
            "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
            "state": "stopped",
            "phase": None,
            "busy": False,
            "stop_requested": True,
            "interval_minutes": self.interval_minutes,
            "observed_at": _iso(observed),
            "next_due_at": None,
            "wait_seconds": None,
        }
        _write_atomic(self.status_path, result)
        return result

    def _write_phase(self, running: Mapping[str, Any], phase: str) -> dict[str, Any]:
        payload = {**running, "phase": phase}
        _write_atomic(self.status_path, payload)
        return payload

    def cycle(self) -> dict[str, Any]:
        if self.stop_requested():
            if self._lock_busy():
                return {
                    "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
                    "state": "stopped",
                    "busy": True,
                    "stop_requested": True,
                    "interval_minutes": self.interval_minutes,
                    "detail": "active cycle is finishing without starting another request",
                }
            return self._record_stopped()
        descriptor = self._try_lock()
        if descriptor is None:
            return {
                "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
                "state": "busy",
                "busy": True,
                "stop_requested": False,
                "interval_minutes": self.interval_minutes,
                "wait_seconds": SCHEDULER_LOCK_RETRY_SECONDS,
            }
        pipeline_descriptor = self._try_pipeline_lock()
        if pipeline_descriptor is None:
            self._unlock(descriptor)
            return {
                "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
                "state": "busy",
                "busy": True,
                "contention": "cohesive_pipeline",
                "stop_requested": False,
                "interval_minutes": self.interval_minutes,
                "wait_seconds": SCHEDULER_LOCK_RETRY_SECONDS,
            }
        try:
            previous = self._read_status() or {}
            started = self.clock().astimezone(timezone.utc)
            running: dict[str, Any] = {
                "schema_version": INTRADAY_SCHEDULER_SCHEMA_VERSION,
                "state": "running",
                "phase": "collect",
                "busy": True,
                "stop_requested": False,
                "pid": os.getpid(),
                "interval_minutes": self.interval_minutes,
                "last_attempt_at": _iso(started),
                "last_success_at": previous.get("last_success_at"),
                "last_full_success_at": previous.get("last_full_success_at"),
                "last_failure": previous.get("last_failure"),
                "last_provider_failure": previous.get("last_provider_failure"),
                "next_due_at": None,
                "wait_seconds": None,
                "provider_failure_streak": int(
                    previous.get("provider_failure_streak") or 0
                ),
                "cycle_failure_streak": int(previous.get("cycle_failure_streak") or 0),
                "source_run_id": previous.get("source_run_id"),
                "analysis_id": previous.get("analysis_id"),
                "intraday_run_id": previous.get("intraday_run_id"),
                "intraday_snapshot_id": previous.get("intraday_snapshot_id"),
                "overlay_id": previous.get("overlay_id"),
                "material_change_receipt_id": previous.get(
                    "material_change_receipt_id"
                ),
                "bundle_id": previous.get("bundle_id"),
                "intraday_quality": previous.get("intraday_quality"),
                "overlay_relation": previous.get("overlay_relation"),
            }
            _write_atomic(self.status_path, running)
            overlay_pointer_before = _optional_bytes(self.overlay_pointer_path)
            api_pointer_before = _optional_bytes(self.api_pointer_path)
            overlay_attempted = False
            api_attempted = False
            try:
                intraday_store = self.intraday_store_factory(self.root)
                collected = intraday_store.refresh()
                running = self._write_phase(running, "verify_collected")
                intraday = intraday_store.latest()
                if collected.get("snapshot_id") != intraday.get("snapshot_id"):
                    raise MarketRegimeRuntimeError(
                        "collected result differs from verified latest intraday snapshot"
                    )
                provider_failure = _provider_failure_receipt(intraday)

                running = self._write_phase(running, "compile")
                overlay_store = self.overlay_store_factory(self.root)
                overlay_attempted = True
                compiled = overlay_store.compile_latest()
                running = self._write_phase(running, "verify_compiled")
                overlay = overlay_store.latest()
                compiled_overlay = compiled.get("overlay") or {}
                if compiled_overlay.get("overlay_id") != overlay.get("overlay_id"):
                    raise MarketRegimeRuntimeError(
                        "compiled result differs from verified latest overlay"
                    )
                if (overlay.get("intraday") or {}).get("snapshot_id") != intraday.get(
                    "snapshot_id"
                ):
                    raise MarketRegimeRuntimeError(
                        "verified overlay differs from collected intraday snapshot"
                    )

                running = self._write_phase(running, "publish")
                structural = self.data_store_factory(self.root).latest()
                analysis = self.analysis_store_factory(self.root).latest()
                api_store = self.api_store_factory(self.root)
                api_attempted = True
                published = api_store.publish(structural, analysis, intraday, overlay)
                bundle = api_store.latest()
                if published.get("bundle_id") != bundle.get("bundle_id"):
                    raise MarketRegimeRuntimeError(
                        "published result differs from verified latest API bundle"
                    )

                finished = self.clock().astimezone(timezone.utc)
                provider_failed = bool(provider_failure["detected"])
                provider_streak = (
                    int(previous.get("provider_failure_streak") or 0) + 1
                    if provider_failed
                    else 0
                )
                wait_seconds = _intraday_backoff_seconds(
                    self.interval_minutes, provider_streak
                )
                provider_failure = {
                    **provider_failure,
                    "at": _iso(finished),
                    "consecutive_failures": provider_streak,
                    "backoff_seconds": wait_seconds if provider_failed else 0,
                }
                result = {
                    **running,
                    "state": "idle",
                    "phase": None,
                    "busy": False,
                    "last_success_at": _iso(finished),
                    "last_full_success_at": (
                        previous.get("last_full_success_at")
                        if provider_failed
                        else _iso(finished)
                    ),
                    "next_due_at": _iso(finished + timedelta(seconds=wait_seconds)),
                    "wait_seconds": wait_seconds,
                    "provider_failure_streak": provider_streak,
                    "cycle_failure_streak": 0,
                    "source_run_id": structural.get("run_id"),
                    "analysis_id": analysis.get("analysis_id"),
                    "intraday_run_id": intraday.get("run_id"),
                    "intraday_snapshot_id": intraday.get("snapshot_id"),
                    "overlay_id": overlay.get("overlay_id"),
                    "material_change_receipt_id": bundle.get(
                        "material_change_receipt_id"
                    ),
                    "bundle_id": bundle.get("bundle_id"),
                    "intraday_quality": intraday.get("quality"),
                    "overlay_relation": overlay.get("relation"),
                    "last_provider_failure": (
                        provider_failure
                        if provider_failed
                        else previous.get("last_provider_failure")
                    ),
                    "last_error": provider_failure if provider_failed else None,
                }
            except Exception as exc:
                rollback_errors: list[str] = []
                if api_attempted:
                    try:
                        _restore_optional_bytes(self.api_pointer_path, api_pointer_before)
                    except OSError as rollback_exc:
                        rollback_errors.append(f"api pointer rollback: {rollback_exc}")
                if overlay_attempted:
                    try:
                        _restore_optional_bytes(
                            self.overlay_pointer_path, overlay_pointer_before
                        )
                    except OSError as rollback_exc:
                        rollback_errors.append(f"overlay pointer rollback: {rollback_exc}")
                finished = self.clock().astimezone(timezone.utc)
                cycle_streak = int(previous.get("cycle_failure_streak") or 0) + 1
                wait_seconds = _intraday_backoff_seconds(
                    self.interval_minutes, cycle_streak
                )
                failure = {
                    "at": _iso(finished),
                    "phase": running.get("phase"),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "rollback_errors": rollback_errors,
                }
                result = {
                    **running,
                    "state": "failed",
                    "phase": None,
                    "failed_phase": failure["phase"],
                    "busy": False,
                    "last_failure": failure,
                    "last_error": failure,
                    "cycle_failure_streak": cycle_streak,
                    "next_due_at": _iso(finished + timedelta(seconds=wait_seconds)),
                    "wait_seconds": wait_seconds,
                }
            _write_atomic(self.status_path, result)
            return result
        finally:
            self._unlock(pipeline_descriptor)
            self._unlock(descriptor)

    def run_forever(self) -> None:
        while True:
            result = self.cycle()
            if result.get("state") == "stopped":
                return
            remaining = float(
                result.get("wait_seconds") or self.interval_minutes * 60
            )
            while remaining > 0:
                if self.stop_requested():
                    self._record_stopped()
                    return
                step = min(float(STOP_POLL_SECONDS), remaining)
                self.sleeper(step)
                remaining -= step


def market_regime_payload(root: Path | str | None = None) -> dict[str, Any]:
    return MarketRegimeApiStore(root or market_regime_root()).latest()


def market_regime_health_payload(root: Path | str | None = None) -> dict[str, Any]:
    return MarketRegimeRuntime(root or market_regime_root()).health()
