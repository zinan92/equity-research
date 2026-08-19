"""Isolated per-asset Weekly Macro analysis contract."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping

from .market_regime_weekly_source import CANONICAL_REGISTRY, CONTEXT_4H_KEYS, WEEKLY_KEYS
from .market_regime_weekly_position_structure import WeeklyPositionStructureError, build_position_structure
from .market_regime_weekly_mechanisms import mechanism_for_asset, validate_theoretical_statement
from .market_regime_weekly_odds import WeeklyOddsError, build_odds, validate_odds


SCHEMA_VERSION = "market-regime-weekly-asset-analysis-v4"
ANALYSIS_ID_PREFIX = "market-regime-weekly-asset-analysis:"
AGREEMENT_STATES = frozenset({"aligned_bullish", "aligned_bearish", "mixed", "neutral"})
OPPORTUNITY_STATES = frozenset({"participate", "wait", "avoid"})
ALLOWED_LATIN_WORDS = frozenset({"Nasdaq", "Bitcoin", "Nikkei", "KOSPI", "SCHD", "OHLC", "MACD", "EMA", "DXY", "VIX", "WTI", "ETF"})


class WeeklyAssetAnalysisError(ValueError):
    """Asset request/output violated the isolated compiler contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_asset_analysis_request(asset_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build one isolated provider request from one asset only."""

    key = str(asset_snapshot.get("key") or "")
    registry = CANONICAL_REGISTRY.get(key)
    if registry is None:
        raise WeeklyAssetAnalysisError(f"unknown_asset_key:{key}")
    for field in ("canonical_symbol", "series_kind", "price_basis"):
        supplied = asset_snapshot.get(field)
        if supplied is not None and str(supplied) != str(registry[field]):
            raise WeeklyAssetAnalysisError(f"asset_registry_mismatch:{key}:{field}")
    timeframes: dict[str, dict[str, Any]] = {}
    for source_key, request_key in (("weekly", "weekly"), ("daily", "daily"), ("four_hour", "four_hour")):
        frame = asset_snapshot.get(source_key)
        if frame is None:
            if source_key == "four_hour" and key not in CONTEXT_4H_KEYS:
                continue
            if source_key == "four_hour":
                continue
            raise WeeklyAssetAnalysisError(f"asset_timeframe_missing:{key}:{source_key}")
        if not isinstance(frame, Mapping):
            raise WeeklyAssetAnalysisError(f"asset_timeframe_invalid:{key}:{source_key}")
        evidence_ids = list(frame.get("evidence_ids") or [])
        if not evidence_ids or any(not isinstance(item, str) or not item for item in evidence_ids):
            raise WeeklyAssetAnalysisError(f"asset_evidence_missing:{key}:{source_key}")
        timeframes[request_key] = {
            "points": frame.get("points") or [],
            "evidence_ids": evidence_ids,
            "status": frame.get("status", "complete"),
            "unit": frame.get("unit", registry["unit"]),
            "features": frame.get("features"),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "asset_key": key,
        "canonical_symbol": registry["canonical_symbol"],
        "series_kind": registry["series_kind"],
        "price_basis": registry["price_basis"],
        "week_end": str(asset_snapshot.get("week_end") or ""),
        "timeframes": timeframes,
        "mechanism": mechanism_for_asset(key),
        "truth_boundary": {
            "local_evaluation_only": True,
            "model_generated_unreviewed": True,
            "automatic_execution_eligible": False,
            "broker_access": False,
            "portfolio_mutation": False,
        },
    }


def _validate_statement(value: Any, *, known_ids: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise WeeklyAssetAnalysisError(f"statement_invalid:{field}")
    ids = value.get("evidence_ids")
    if not isinstance(ids, list) or not ids:
        raise WeeklyAssetAnalysisError(f"evidence_ids_missing:{field}")
    if any(item not in known_ids for item in ids):
        raise WeeklyAssetAnalysisError(f"evidence_id_unknown:{field}")
    return {"text": value["text"], "evidence_ids": list(ids)}


def _has_forbidden_english(text: str) -> bool:
    words = re.findall(r"[A-Za-z]{4,}", text)
    return any(word not in ALLOWED_LATIN_WORDS for word in words)


def validate_asset_analysis(output: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one provider response against its isolated request."""

    if not isinstance(output, Mapping):
        raise WeeklyAssetAnalysisError("analysis_output_invalid")
    key = str(request.get("asset_key") or "")
    if output.get("asset_key") != key:
        raise WeeklyAssetAnalysisError("analysis_asset_identity_mismatch")
    status = str(output.get("generation_status") or "")
    if status == "analysis_unavailable":
        if not isinstance(output.get("failure_code"), str) or not output["failure_code"]:
            raise WeeklyAssetAnalysisError("analysis_failure_code_missing")
        return {"asset_key": key, "generation_status": status, "failure_code": output["failure_code"]}
    if status != "model_generated_unreviewed":
        raise WeeklyAssetAnalysisError("analysis_generation_status_invalid")
    if output.get("odds") is not None:
        raise WeeklyAssetAnalysisError("analysis_odds_must_be_code_owned")
    timeframes = request.get("timeframes")
    if not isinstance(timeframes, Mapping):
        raise WeeklyAssetAnalysisError("analysis_request_timeframes_invalid")
    known_ids = {item for frame in timeframes.values() for item in frame.get("evidence_ids", [])}
    mechanism = request.get("mechanism")
    if not isinstance(mechanism, Mapping) or mechanism.get("asset_key") != key:
        raise WeeklyAssetAnalysisError("analysis_mechanism_invalid")
    mechanism_ids = {str(item) for item in mechanism.get("mechanism_ids") or []}
    if not mechanism_ids:
        raise WeeklyAssetAnalysisError("analysis_mechanism_ids_missing")
    result: dict[str, Any] = {"asset_key": key, "generation_status": status}
    result["weekly"] = _validate_statement(output.get("weekly"), known_ids=known_ids, field="weekly")
    result["daily"] = _validate_statement(output.get("daily"), known_ids=known_ids, field="daily")
    if "four_hour" in timeframes:
        result["four_hour"] = _validate_statement(output.get("four_hour"), known_ids=known_ids, field="four_hour")
    elif output.get("four_hour") is not None:
        raise WeeklyAssetAnalysisError("analysis_timeframe_not_in_request:four_hour")
    result["synthesis"] = _validate_statement(output.get("synthesis"), known_ids=known_ids, field="synthesis")
    agreement = str(output.get("agreement") or "")
    opportunity = str(output.get("opportunity_state") or "")
    if agreement not in AGREEMENT_STATES:
        raise WeeklyAssetAnalysisError("analysis_agreement_invalid")
    if opportunity not in OPPORTUNITY_STATES:
        raise WeeklyAssetAnalysisError("analysis_opportunity_invalid")
    result["agreement"] = agreement
    result["confirmation"] = _validate_statement(output.get("confirmation"), known_ids=known_ids, field="confirmation")
    result["invalidation"] = _validate_statement(output.get("invalidation"), known_ids=known_ids, field="invalidation")
    result["opportunity_state"] = opportunity
    result["rationale"] = _validate_statement(output.get("rationale"), known_ids=known_ids, field="rationale")
    try:
        result["theoretical_implication"] = validate_theoretical_statement(
            output.get("theoretical_implication"), mechanism_ids
        )
    except ValueError as exc:
        raise WeeklyAssetAnalysisError(str(exc)) from exc
    if "four_hour" not in timeframes:
        all_text = " ".join(
            str(result.get(field, {}).get("text", ""))
            for field in ("weekly", "daily", "synthesis", "confirmation", "invalidation", "rationale", "theoretical_implication")
        )
        if any(token in all_text.lower() for token in ("4h", "4小时", "小时")):
            raise WeeklyAssetAnalysisError("analysis_forbidden_timeframe")
    if any(_has_forbidden_english(str(result.get(field, {}).get("text", ""))) for field in ("weekly", "daily", "synthesis", "confirmation", "invalidation", "rationale") if isinstance(result.get(field), Mapping)):
        raise WeeklyAssetAnalysisError("analysis_language_not_chinese")
    if isinstance(result.get("four_hour"), Mapping) and _has_forbidden_english(str(result["four_hour"].get("text", ""))):
        raise WeeklyAssetAnalysisError("analysis_language_not_chinese")
    return result


def compile_asset_analysis(
    request: Mapping[str, Any],
    provider: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Call an injected provider and return a typed terminal artifact."""

    key = str(request.get("asset_key") or "")
    request_hash = _digest(request)
    try:
        raw = provider(request)
        output = validate_asset_analysis(raw, request)
    except (WeeklyAssetAnalysisError, WeeklyPositionStructureError):
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_key": key,
            "request_hash": request_hash,
            "generation_status": "analysis_unavailable",
            "failure_code": "output_schema_invalid",
        }
    except Exception:
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_key": key,
            "request_hash": request_hash,
            "generation_status": "analysis_unavailable",
            "failure_code": "provider_error",
        }
    try:
        derived = build_position_structure(request)
    except WeeklyPositionStructureError:
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_key": key,
            "request_hash": request_hash,
            "generation_status": "analysis_unavailable",
            "failure_code": "derived_feature_invalid",
        }
    try:
        odds = build_odds(request, derived["structure"])
        selected_frame = request.get("timeframes", {}).get(odds.get("timeframe")) if isinstance(request.get("timeframes"), Mapping) else None
        selected_features = selected_frame.get("features") if isinstance(selected_frame, Mapping) else None
        feature_identity = str(selected_features.get("feature_identity") or "") if isinstance(selected_features, Mapping) else ""
        allowed_evidence_ids = {str(item) for item in selected_frame.get("evidence_ids") or []} if isinstance(selected_frame, Mapping) else set()
        odds = validate_odds(
            odds,
            allowed_feature_ids={f"feature:{feature_identity}"} if feature_identity else set(),
            allowed_evidence_ids=allowed_evidence_ids,
        )
    except WeeklyOddsError:
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_key": key,
            "request_hash": request_hash,
            "generation_status": "analysis_unavailable",
            "failure_code": "derived_odds_invalid",
        }
    output = {**output, **derived, "odds": odds}
    core = {
        "schema_version": SCHEMA_VERSION,
        "asset_key": key,
        "request_hash": request_hash,
        "generation_status": output["generation_status"],
        "output": output,
    }
    output_hash = _digest(output)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "event": "completed",
        "asset_key": key,
        "request_hash": request_hash,
        "output_hash": output_hash,
    }
    return {
        "analysis_id": f"{ANALYSIS_ID_PREFIX}{_digest(core)}",
        "identity_core": core,
        "receipt": receipt,
        "output_hash": output_hash,
        "request_asset_key": key,
        **output,
    }


def build_terminal_vector(analyses: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project every registry key into a terminal validated/unavailable slot."""

    vector: list[dict[str, Any]] = []
    for key in WEEKLY_KEYS:
        artifact = analyses.get(key)
        if not isinstance(artifact, Mapping) or artifact.get("generation_status") != "model_generated_unreviewed":
            vector.append({"asset_key": key, "status": "analysis_unavailable", "reason_code": (artifact or {}).get("failure_code", "analysis_missing")})
            continue
        if not isinstance(artifact.get("analysis_id"), str) or not artifact["analysis_id"].startswith(ANALYSIS_ID_PREFIX):
            vector.append({"asset_key": key, "status": "analysis_unavailable", "reason_code": "analysis_identity_invalid"})
            continue
        vector.append({
            "asset_key": key,
            "status": "validated",
            "analysis_id": artifact.get("analysis_id"),
            "generation_status": artifact.get("generation_status"),
            "output": artifact,
        })
    return vector
