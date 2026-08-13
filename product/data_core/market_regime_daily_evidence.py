"""Immutable, citation-resolvable Evidence Pack v1 for Market Regime Daily v2."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .market_regime_data import (
    INSTRUMENTS,
    INSTRUMENT_BY_KEY,
    SCHEMA_VERSION as DATA_SCHEMA_VERSION,
    MarketRegimeDataError,
    MarketRegimeDataStore,
    instrument_registry_payload,
)
from .market_regime_macro_data import (
    MACRO_FACTORS,
    MACRO_FACTOR_BY_KEY,
    MarketRegimeMacroDataError,
    MarketRegimeMacroDataStore,
    SCHEMA_VERSION as MACRO_SCHEMA_VERSION,
)
from .market_regime_model import (
    ANALYSIS_SCHEMA_VERSION,
    MAX_FULL_CLOSE_SKEW_HOURS,
    MarketRegimeAnalysisStore,
    MarketRegimeModelError,
    compile_market_regime,
)


SCHEMA_VERSION = "market-regime-daily-evidence-v1"
PACK_ID_PREFIX = "market-regime-daily-evidence:"
SLOT_KEYS = tuple(item.key for item in INSTRUMENTS) + tuple(
    item.key for item in MACRO_FACTORS
)
CRITICAL_KEYS = frozenset(
    {"sp500", "nasdaq", "shanghai", "star50", "vix", "dxy", "us2y", "us10y"}
)
if len(SLOT_KEYS) != 16 or len(set(SLOT_KEYS)) != 16:  # pragma: no cover
    raise RuntimeError("daily evidence contract must contain 16 unique slots")


class MarketRegimeDailyEvidenceError(RuntimeError):
    """A frozen input, unit, citation or immutable-pack contract failed."""


def _truth_boundary() -> dict[str, bool]:
    # Return a fresh value so callers cannot mutate the validator's expected
    # process-wide contract through a previously returned pack.
    return {
        "read_only": True,
        "causal_claims": False,
        "forecast": False,
        "investment_advice": False,
        "publication_eligible": False,
        "action_eligible": False,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _identity(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _instant(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise MarketRegimeDailyEvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise MarketRegimeDailyEvidenceError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _finite(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MarketRegimeDailyEvidenceError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise MarketRegimeDailyEvidenceError(f"{field} must be finite")
    return round(number, 6)


def _source_tier(provider: str) -> str:
    sources = instrument_registry_payload().get("sources") or {}
    source = sources.get(provider) if isinstance(sources, dict) else None
    tier = str((source or {}).get("authority_tier") or "")
    if not tier:
        raise MarketRegimeDailyEvidenceError(
            f"daily provider lacks source tier: {provider}"
        )
    return tier


def _state(item: Mapping[str, Any]) -> str:
    refresh = str(item.get("refresh_status") or "accepted")
    if refresh == "rejected":
        return "last_good"
    if refresh in {"not_requested", "not_refreshed"}:
        return refresh
    return "accepted"


def _capture_failure_identity(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key)
        for key in (
            "method",
            "requested_url",
            "final_url",
            "status_code",
            "content_type",
            "raw_sha256",
            "raw_bytes",
            "error",
        )
    }


def _failure_identity(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    sources = value.get("sources")
    return {
        "reason": value.get("reason"),
        "bounded_raw_excerpt": value.get("bounded_raw_excerpt"),
        "source": _capture_failure_identity(value.get("source")),
        "sources": (
            [_capture_failure_identity(item) for item in sources]
            if isinstance(sources, list)
            else None
        ),
    }


def _evidence_id(*, key: str, identity_core: Mapping[str, Any]) -> str:
    return f"{SCHEMA_VERSION}:{key}:{_identity(identity_core)}"


def _slot_identity_core(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in slot.items() if key != "evidence_id"}


def _daily_slot(
    *, key: str, item: Mapping[str, Any] | None, feature: Mapping[str, Any] | None
) -> dict[str, Any]:
    spec = INSTRUMENT_BY_KEY[key]
    if item is None or item.get("quality") not in {"fresh", "partial", "stale"}:
        return {
            "key": key,
            "display_name": spec.display_name,
            "kind": "completed_daily_price",
            "status": "unavailable",
            "quality": "unavailable",
            "level_unit": spec.unit,
            "change_5d_unit": "percent_return",
            "publication_eligible": False,
            "action_eligible": False,
        }
    if feature is None:
        raise MarketRegimeDailyEvidenceError(f"{key} is absent from current analysis")
    if _canonical_json(item.get("instrument")) != _canonical_json(asdict(spec)):
        raise MarketRegimeDailyEvidenceError(f"{key} instrument registry mismatch")
    reference = item.get("normalized_artifact") or {}
    artifact_sha = str(reference.get("sha256") or "")
    if len(artifact_sha) != 64:
        raise MarketRegimeDailyEvidenceError(f"{key} lacks normalized artifact identity")
    if feature.get("normalized_artifact_sha256") != artifact_sha:
        raise MarketRegimeDailyEvidenceError(f"{key} analysis artifact identity mismatch")
    session = str(item.get("last_completed_session") or "")
    close_at = str(item.get("last_completed_close_at") or "")
    _instant(close_at, field=f"{key}.close_at")
    if feature.get("session") != session:
        raise MarketRegimeDailyEvidenceError(f"{key} analysis session mismatch")
    source = item.get("source") or {}
    provider = str((item.get("instrument") or {}).get("provider") or "")
    source_identity = {
        "normalized_artifact_sha256": artifact_sha,
        "raw_sha256": source.get("raw_sha256"),
    }
    identity_core = {
        "key": key,
        "source_identity": source_identity,
        "session": session,
        "close_at": close_at,
        "value": _finite(feature.get("close"), field=f"{key}.close"),
        "change_5d": _finite(
            (feature.get("returns") or {}).get("5d"), field=f"{key}.return_5d_pct"
        ),
        "level_unit": spec.unit,
        "change_5d_unit": "percent_return",
        "display_name": spec.display_name,
        "kind": "completed_daily_price",
        "status": _state(item),
        "quality": item.get("quality"),
        "source_tier": _source_tier(provider),
        "source_provider": provider,
        "trend_score": _finite(
            feature.get("trend_score"), field=f"{key}.trend_score"
        ),
        "refresh_failure": _failure_identity(item.get("refresh_failure")),
        "publication_eligible": False,
        "action_eligible": False,
    }
    return {
        **identity_core,
        "evidence_id": _evidence_id(
            key=key, identity_core=_slot_identity_core(identity_core)
        ),
    }


def _macro_slot(*, key: str, item: Mapping[str, Any] | None) -> dict[str, Any]:
    spec = MACRO_FACTOR_BY_KEY[key]
    if item is None or item.get("quality") not in {"fresh", "partial", "stale"}:
        return {
            "key": key,
            "display_name": spec.display_name,
            "kind": spec.kind,
            "status": "unavailable",
            "quality": "unavailable",
            "level_unit": spec.level_unit,
            "change_5d_unit": spec.change_unit,
            "publication_eligible": False,
            "action_eligible": False,
        }
    reference = item.get("artifact") or {}
    artifact_sha = str(reference.get("sha256") or "")
    factor_id = str(item.get("factor_id") or "")
    if len(artifact_sha) != 64 or not factor_id.startswith(
        "market-regime-macro-data-v1:"
    ):
        raise MarketRegimeDailyEvidenceError(f"{key} lacks factor artifact identity")
    factor = item.get("factor") or {}
    if _canonical_json(factor) != _canonical_json(asdict(spec)):
        raise MarketRegimeDailyEvidenceError(f"{key} factor registry mismatch")
    session = str(item.get("last_completed_session") or "")
    close_at = str(item.get("last_completed_close_at") or "")
    _instant(close_at, field=f"{key}.close_at")
    if key == "dxy":
        change = (item.get("changes") or {}).get("5d_pct")
        change_unit = "percent_return"
    else:
        change = (item.get("changes") or {}).get("5d_bp")
        change_unit = "basis_points"
    if change_unit != spec.change_unit:
        raise MarketRegimeDailyEvidenceError(f"{key} change unit contract mismatch")
    source_identity = {
        "factor_id": factor_id,
        "artifact_sha256": artifact_sha,
    }
    identity_core = {
        "key": key,
        "source_identity": source_identity,
        "session": session,
        "close_at": close_at,
        "value": _finite(item.get("value"), field=f"{key}.value"),
        "change_5d": _finite(change, field=f"{key}.change_5d"),
        "level_unit": spec.level_unit,
        "change_5d_unit": change_unit,
        "display_name": spec.display_name,
        "kind": spec.kind,
        "status": _state(item),
        "quality": item.get("quality"),
        "source_tier": spec.source_tier,
        "source_provider": spec.provider,
        "refresh_failure": _failure_identity(item.get("refresh_failure")),
        "publication_eligible": False,
        "action_eligible": False,
    }
    return {
        **identity_core,
        "evidence_id": _evidence_id(
            key=key, identity_core=_slot_identity_core(identity_core)
        ),
    }


def _unique_by_key(
    values: Any, *, field: str, key_path: tuple[str, ...]
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(values, list):
        raise MarketRegimeDailyEvidenceError(f"{field} must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise MarketRegimeDailyEvidenceError(f"{field} item must be an object")
        current: Any = value
        for part in key_path:
            current = current.get(part) if isinstance(current, dict) else None
        key = str(current or "")
        if not key or key in result:
            raise MarketRegimeDailyEvidenceError(f"{field} has missing/duplicate key")
        result[key] = value
    return result


def _contradictions(
    analysis: Mapping[str, Any], slots: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    dimensions = analysis.get("dimensions") or {}
    for dimension in ("risk", "posture", "style"):
        value = dimensions.get(dimension) or {}
        rows = value.get("contradictions") or []
        if not isinstance(rows, list):
            raise MarketRegimeDailyEvidenceError(
                f"analysis {dimension} contradictions must be a list"
            )
        for row in rows:
            if not isinstance(row, dict):
                raise MarketRegimeDailyEvidenceError("contradiction must be an object")
            instrument = str(row.get("instrument") or "")
            pair = str(row.get("pair") or "")
            pair_members = {
                "US_vs_A_tech": ("nasdaq", "sp500", "star50", "shanghai"),
                "US_vs_A_dividend": (
                    "us_dividend",
                    "sp500",
                    "china_dividend",
                    "shanghai",
                ),
            }
            if instrument:
                keys = (instrument,)
            elif pair in pair_members:
                keys = pair_members[pair]
            else:
                raise MarketRegimeDailyEvidenceError(
                    "contradiction lacks a known instrument or pair"
                )
            evidence_ids = [slots.get(key, {}).get("evidence_id") for key in keys]
            if any(not evidence_id for evidence_id in evidence_ids):
                raise MarketRegimeDailyEvidenceError(
                    f"contradiction references unavailable evidence: {', '.join(keys)}"
                )
            core = {
                "dimension": dimension,
                "keys": list(keys),
                "evidence_ids": evidence_ids,
                "pair": pair or None,
                "reason": str(row.get("reason") or "deterministic dimension divergence"),
                "signed_contribution": row.get("signed_contribution"),
                "trend_score": row.get("trend_score"),
            }
            candidates.append(
                {
                    "candidate_id": f"contradiction:{_identity(core)}",
                    **core,
                    "causal_status": "observable_noncausal",
                }
            )
    return candidates


def compile_daily_evidence_pack(
    daily: Mapping[str, Any], analysis: Mapping[str, Any], macro: Mapping[str, Any]
) -> dict[str, Any]:
    if daily.get("schema_version") != DATA_SCHEMA_VERSION:
        raise MarketRegimeDailyEvidenceError("daily evidence schema mismatch")
    if analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise MarketRegimeDailyEvidenceError("analysis schema mismatch")
    if macro.get("schema_version") != MACRO_SCHEMA_VERSION:
        raise MarketRegimeDailyEvidenceError("macro evidence schema mismatch")
    if analysis.get("source_run_id") != daily.get("run_id"):
        raise MarketRegimeDailyEvidenceError("analysis does not bind current daily run")
    try:
        expected_analysis = compile_market_regime(daily)
    except MarketRegimeModelError as exc:
        raise MarketRegimeDailyEvidenceError(str(exc)) from exc
    if _canonical_json(analysis) != _canonical_json(expected_analysis):
        raise MarketRegimeDailyEvidenceError("analysis identity does not match daily evidence")

    daily_items = _unique_by_key(
        daily.get("instruments"), field="daily instruments", key_path=("instrument", "key")
    )
    feature_items = _unique_by_key(
        analysis.get("asset_features"), field="analysis asset_features", key_path=("key",)
    )
    macro_items = _unique_by_key(
        macro.get("factors"), field="macro factors", key_path=("factor", "key")
    )
    unknown_daily = set(daily_items) - set(INSTRUMENT_BY_KEY)
    unknown_macro = set(macro_items) - set(MACRO_FACTOR_BY_KEY)
    if unknown_daily or unknown_macro:
        raise MarketRegimeDailyEvidenceError("input contains unknown evidence keys")

    slots: dict[str, dict[str, Any]] = {}
    for spec in INSTRUMENTS:
        slots[spec.key] = _daily_slot(
            key=spec.key,
            item=daily_items.get(spec.key),
            feature=feature_items.get(spec.key),
        )
    for spec in MACRO_FACTORS:
        slots[spec.key] = _macro_slot(key=spec.key, item=macro_items.get(spec.key))

    evidence_ids = [slot.get("evidence_id") for slot in slots.values() if slot.get("evidence_id")]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise MarketRegimeDailyEvidenceError("evidence IDs must be unique")
    accepted = [slot for slot in slots.values() if slot.get("evidence_id")]
    close_times = [
        _instant(slot["close_at"], field=f"{slot['key']}.close_at") for slot in accepted
    ]
    if close_times:
        earliest, latest = min(close_times), max(close_times)
        skew = round((latest - earliest).total_seconds() / 3600, 3)
        joint_time = earliest.isoformat().replace("+00:00", "Z")
        latest_time = latest.isoformat().replace("+00:00", "Z")
    else:
        skew, joint_time, latest_time = None, None, None
    unavailable = [key for key, slot in slots.items() if not slot.get("evidence_id")]
    stale = [key for key, slot in slots.items() if slot.get("quality") == "stale"]
    fallback = [
        key
        for key, slot in slots.items()
        if slot.get("status") in {"last_good", "not_refreshed", "not_requested"}
    ]
    critical_missing = sorted(CRITICAL_KEYS.intersection(unavailable))
    contradiction_candidates = _contradictions(analysis, slots)
    coverage = round(len(accepted) / len(SLOT_KEYS), 3)
    degraded = (
        coverage < 1
        or bool(stale)
        or bool(fallback)
        or bool(critical_missing)
        or skew is None
        or skew > MAX_FULL_CLOSE_SKEW_HOURS
        or analysis.get("status") != "full"
    )
    quality = "unavailable" if not accepted else "partial" if degraded else "fresh"

    analysis_confidence = (analysis.get("confidence") or {}).get("score")
    base_confidence = _finite(
        analysis_confidence if analysis_confidence is not None else 0,
        field="analysis.confidence.score",
    )
    skew_factor = (
        0.0
        if skew is None
        else 0.75
        if skew > MAX_FULL_CLOSE_SKEW_HOURS
        else 1.0
    )
    freshness_factor = 0.8 if stale else 1.0
    fallback_factor = 0.8 if fallback else 1.0
    critical_factor = 0.0 if critical_missing else 1.0
    contradiction_factor = max(0.6, 1.0 - 0.05 * len(contradiction_candidates))
    confidence_score = round(
        base_confidence
        * coverage
        * skew_factor
        * freshness_factor
        * fallback_factor
        * critical_factor
        * contradiction_factor,
        3,
    )
    confidence_level = (
        "high" if confidence_score >= 0.8 else "medium" if confidence_score >= 0.6 else "low"
    )
    confidence_inputs = {
        "score": confidence_score,
        "level": confidence_level,
        "base_analysis_confidence": base_confidence,
        "coverage_factor": coverage,
        "skew_factor": skew_factor,
        "freshness_factor": freshness_factor,
        "fallback_factor": fallback_factor,
        "critical_factor": critical_factor,
        "contradiction_factor": round(contradiction_factor, 3),
        "formula": "base*coverage*skew*freshness*fallback*critical*contradiction",
    }

    dimensions = analysis.get("dimensions") or {}
    agreement_inputs = {
        "analysis_status": analysis.get("status"),
        "analysis_confidence": analysis.get("confidence"),
        "risk": {
            key: (dimensions.get("risk") or {}).get(key)
            for key in ("score", "label", "status", "confidence")
        },
        "posture": {
            key: (dimensions.get("posture") or {}).get(key)
            for key in ("score", "label", "status", "confidence")
        },
        "style": {
            key: (dimensions.get("style") or {}).get(key)
            for key in ("score", "label", "status", "confidence")
        },
        "leadership": {
            key: (dimensions.get("leadership") or {}).get(key)
            for key in ("status", "state", "leader", "confidence")
        },
    }
    identity_core = {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "daily_run_id": daily.get("run_id"),
            "analysis_id": analysis.get("analysis_id"),
            "analysis_input_fingerprint": analysis.get("input_fingerprint"),
            "macro_run_id": macro.get("run_id"),
        },
        "quality": quality,
        "coverage": {
            "accepted": len(accepted),
            "total": len(SLOT_KEYS),
            "ratio": coverage,
            "unavailable_keys": unavailable,
            "critical_missing_keys": critical_missing,
            "stale_keys": stale,
            "fallback_keys": fallback,
        },
        "time": {
            "joint_judgment_time": joint_time,
            "latest_evidence_time": latest_time,
            "cross_market_close_skew_hours": skew,
            "full_quality_skew_limit_hours": MAX_FULL_CLOSE_SKEW_HOURS,
        },
        "agreement_inputs": agreement_inputs,
        "confidence_inputs": confidence_inputs,
        "contradiction_candidates": contradiction_candidates,
        "slots": [slots[key] for key in SLOT_KEYS],
        "truth_boundary": _truth_boundary(),
    }
    pack_id = f"{PACK_ID_PREFIX}{_identity(identity_core)}"
    return {
        "schema_version": SCHEMA_VERSION,
        "pack_id": pack_id,
        "identity_core": identity_core,
        **{key: value for key, value in identity_core.items() if key != "schema_version"},
        "evidence_index": {
            slot["evidence_id"]: slot["key"]
            for slot in identity_core["slots"]
            if slot.get("evidence_id")
        },
    }


def resolve_evidence(pack: Mapping[str, Any], evidence_id: str) -> Mapping[str, Any]:
    key = (pack.get("evidence_index") or {}).get(evidence_id)
    for slot in pack.get("slots") or []:
        if isinstance(slot, dict) and slot.get("key") == key and slot.get("evidence_id") == evidence_id:
            return slot
    raise MarketRegimeDailyEvidenceError(f"unknown evidence ID: {evidence_id}")


def _validate_slot_contract(slots: Any) -> None:
    if (
        not isinstance(slots, list)
        or len(slots) != len(SLOT_KEYS)
        or [slot.get("key") if isinstance(slot, dict) else None for slot in slots]
        != list(SLOT_KEYS)
    ):
        raise MarketRegimeDailyEvidenceError("daily evidence slot contract is invalid")
    unavailable_forbidden = {
        "evidence_id",
        "source_identity",
        "session",
        "close_at",
        "value",
        "change_5d",
        "source_provider",
        "source_tier",
    }
    for slot in slots:
        evidence_id = slot.get("evidence_id")
        if slot.get("status") == "unavailable":
            if evidence_id or unavailable_forbidden.intersection(slot):
                raise MarketRegimeDailyEvidenceError(
                    "unavailable daily evidence slot cannot carry a citation"
                )
            continue
        if not evidence_id:
            raise MarketRegimeDailyEvidenceError(
                "non-unavailable daily evidence slot lacks identity"
            )
        expected_evidence_id = _evidence_id(
            key=str(slot.get("key") or ""),
            identity_core=_slot_identity_core(slot),
        )
        if evidence_id != expected_evidence_id:
            raise MarketRegimeDailyEvidenceError("daily evidence slot identity mismatch")


def _write_immutable(path: Path, payload: Mapping[str, Any]) -> str:
    encoded = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != encoded:
            raise MarketRegimeDailyEvidenceError(
                f"evidence artifact identity collision: {path.name}"
            )
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


class MarketRegimeDailyEvidenceStore:
    """Compile verified latest inputs into an independent immutable pack."""

    def __init__(
        self,
        daily_root: Path | str,
        macro_root: Path | str,
        output_root: Path | str,
    ) -> None:
        self.daily_root = Path(daily_root).expanduser().resolve()
        self.macro_root = Path(macro_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    def compile_latest(self) -> dict[str, Any]:
        try:
            daily = MarketRegimeDataStore(self.daily_root).latest()
            analysis = MarketRegimeAnalysisStore(self.daily_root).latest()
            macro = MarketRegimeMacroDataStore(self.macro_root).latest()
        except (MarketRegimeDataError, MarketRegimeModelError, MarketRegimeMacroDataError) as exc:
            raise MarketRegimeDailyEvidenceError(str(exc)) from exc
        pack = compile_daily_evidence_pack(daily, analysis, macro)
        digest = pack["pack_id"].removeprefix(PACK_ID_PREFIX)
        relative = f"artifacts/{digest}.json"
        artifact_sha = _write_immutable(self.output_root / relative, pack)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "event": "completed",
            "pack_id": pack["pack_id"],
            "inputs": pack["inputs"],
            "artifact": {"path": relative, "sha256": artifact_sha},
            "publication_eligible": False,
            "action_eligible": False,
        }
        receipt_relative = f"receipts/{digest}.json"
        receipt_sha = _write_immutable(self.output_root / receipt_relative, receipt)
        pointer = {
            "schema_version": SCHEMA_VERSION,
            "pack_id": pack["pack_id"],
            "artifact": {"path": relative, "sha256": artifact_sha},
            "receipt": {"path": receipt_relative, "sha256": receipt_sha},
        }
        _write_atomic(self.output_root / "latest.json", pointer)
        return pack

    def latest(self) -> dict[str, Any]:
        pointer_path = self.output_root / "latest.json"
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MarketRegimeDailyEvidenceError("daily evidence pack is unavailable") from exc
        except json.JSONDecodeError as exc:
            raise MarketRegimeDailyEvidenceError("daily evidence pointer is not JSON") from exc
        if not isinstance(pointer, dict) or pointer.get("schema_version") != SCHEMA_VERSION:
            raise MarketRegimeDailyEvidenceError("daily evidence pointer schema mismatch")
        pointer_id = str(pointer.get("pack_id") or "")
        if not pointer_id.startswith(PACK_ID_PREFIX):
            raise MarketRegimeDailyEvidenceError("daily evidence pointer identity is invalid")
        pointer_digest = pointer_id.removeprefix(PACK_ID_PREFIX)
        canonical_paths = {
            "artifact": f"artifacts/{pointer_digest}.json",
            "receipt": f"receipts/{pointer_digest}.json",
        }
        for name in ("artifact", "receipt"):
            reference = pointer.get(name) or {}
            relative = str(reference.get("path") or "")
            expected = str(reference.get("sha256") or "")
            target = (self.output_root / relative).resolve()
            if relative != canonical_paths[name] or len(expected) != 64 or self.output_root not in target.parents:
                raise MarketRegimeDailyEvidenceError(f"daily evidence {name} reference is invalid")
            try:
                encoded = target.read_bytes()
            except FileNotFoundError as exc:
                raise MarketRegimeDailyEvidenceError(f"daily evidence {name} is missing") from exc
            if sha256(encoded).hexdigest() != expected:
                raise MarketRegimeDailyEvidenceError(f"daily evidence {name} hash mismatch")
            try:
                payload = json.loads(encoded)
            except json.JSONDecodeError as exc:
                raise MarketRegimeDailyEvidenceError(f"daily evidence {name} is not JSON") from exc
            if name == "artifact":
                pack = payload
            else:
                receipt = payload
        if not isinstance(pack, dict) or not isinstance(receipt, dict):
            raise MarketRegimeDailyEvidenceError("daily evidence payload is invalid")
        identity_core = pack.get("identity_core")
        if not isinstance(identity_core, dict):
            raise MarketRegimeDailyEvidenceError("daily evidence identity core is missing")
        expected_id = f"{PACK_ID_PREFIX}{_identity(identity_core)}"
        if (
            pack.get("schema_version") != SCHEMA_VERSION
            or pack.get("pack_id") != expected_id
            or pointer.get("pack_id") != expected_id
            or receipt.get("pack_id") != expected_id
            or receipt.get("inputs") != pack.get("inputs")
            or receipt.get("schema_version") != SCHEMA_VERSION
            or receipt.get("event") != "completed"
            or receipt.get("artifact") != pointer.get("artifact")
            or receipt.get("publication_eligible") is not False
            or receipt.get("action_eligible") is not False
            or identity_core.get("truth_boundary") != _truth_boundary()
            or pack.get("truth_boundary") != _truth_boundary()
        ):
            raise MarketRegimeDailyEvidenceError("daily evidence identity mismatch")
        projected = {
            key: value for key, value in identity_core.items() if key != "schema_version"
        }
        if any(pack.get(key) != value for key, value in projected.items()):
            raise MarketRegimeDailyEvidenceError("daily evidence projection mismatch")
        expected_index = {
            slot["evidence_id"]: slot["key"]
            for slot in identity_core.get("slots") or []
            if isinstance(slot, dict) and slot.get("evidence_id")
        }
        index = pack.get("evidence_index")
        if not isinstance(index, dict) or index != expected_index:
            raise MarketRegimeDailyEvidenceError("daily evidence index is invalid")
        slots = identity_core.get("slots")
        _validate_slot_contract(slots)
        for evidence_id in index:
            resolve_evidence(pack, evidence_id)
        return pack
