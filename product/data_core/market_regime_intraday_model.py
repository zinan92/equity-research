"""Deterministic, evidence-bound intraday overlay for the structural regime."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any, Mapping

from .market_regime_intraday_data import (
    INSTRUMENT_BY_KEY as INTRADAY_INSTRUMENT_BY_KEY,
    SCHEMA_VERSION as INTRADAY_SCHEMA_VERSION,
    MarketRegimeIntradayDataError,
    MarketRegimeIntradayDataStore,
)
from .market_regime_model import (
    ANALYSIS_SCHEMA_VERSION,
    MODEL_VERSION as STRUCTURAL_MODEL_VERSION,
    MarketRegimeAnalysisStore,
    MarketRegimeModelError,
)


OVERLAY_SCHEMA_VERSION = "market-regime-intraday-overlay-v1"
OVERLAY_MODEL_VERSION = "market-regime-intraday-model-v1"
POINTER_SCHEMA_VERSION = "market-regime-intraday-overlay-pointer-v1"
HISTORY_SCHEMA_VERSION = "market-regime-intraday-overlay-history-v1"

ENTER_SCORE = 18.0
EXIT_SCORE = 8.0
STRUCTURAL_DIRECTION_SCORE = 10.0
MATERIAL_SCORE_DELTA = 15.0
PERSISTENCE_OVERLAYS = 2
COOLDOWN_SECONDS = 30 * 60
MIN_CONTIGUOUS_BARS = 4
MAX_IMPULSE_BARS = 13
MIN_NOISE_RETURNS = 10
NOISE_FLOOR = 0.0005

RELATIONS = frozenset({"confirms", "diverges", "insufficient", "closed"})
DIRECTIONAL_RELATIONS = frozenset({"confirms", "diverges"})
KNOWN_A_NON_OPEN = frozenset({"pre", "lunch_break", "post", "closed"})
A_SHARE_KEYS = ("shanghai", "star50", "china_dividend")
A_SHARE_WEIGHTS = {"shanghai": 0.50, "star50": 0.30, "china_dividend": 0.20}

# Fixed group weights sum to one. Cash and futures in one group divide, rather
# than duplicate, that group's explanatory weight when both are eligible.
SIGNAL_GROUPS: dict[str, dict[str, Any]] = {
    "us_large_cap": {
        "weight": 0.16,
        "sign": 1.0,
        "role": "US large-cap risk appetite",
        "members": ("sp500_cash", "sp500_futures_proxy"),
    },
    "us_growth": {
        "weight": 0.18,
        "sign": 1.0,
        "role": "US growth risk appetite",
        "members": ("nasdaq_cash", "nasdaq100_futures_proxy"),
    },
    "a_broad": {
        "weight": 0.12,
        "sign": 1.0,
        "role": "A-share broad tape",
        "members": ("shanghai",),
    },
    "a_technology": {
        "weight": 0.12,
        "sign": 1.0,
        "role": "A-share technology tape",
        "members": ("star50",),
    },
    "a_dividend": {
        "weight": 0.04,
        "sign": 1.0,
        "role": "A-share dividend tape",
        "members": ("china_dividend",),
    },
    "korea": {
        "weight": 0.07,
        "sign": 1.0,
        "role": "Korea cash risk appetite",
        "members": ("kospi",),
    },
    "japan": {
        "weight": 0.07,
        "sign": 1.0,
        "role": "Japan cash risk appetite",
        "members": ("nikkei",),
    },
    "volatility": {
        "weight": 0.08,
        "sign": -1.0,
        "role": "cash volatility defense",
        "members": ("vix",),
    },
    "us_dividend": {
        "weight": 0.04,
        "sign": 1.0,
        "role": "US dividend tape",
        "members": ("us_dividend",),
    },
    "energy": {
        "weight": 0.04,
        "sign": 1.0,
        "role": "energy/reflation context",
        "members": ("wti",),
    },
    "gold": {
        "weight": 0.04,
        "sign": -1.0,
        "role": "gold defense context",
        "members": ("gold",),
    },
    "silver": {
        "weight": 0.04,
        "sign": -1.0,
        "role": "silver defense context",
        "members": ("silver",),
    },
}
if not math.isclose(
    sum(float(spec["weight"]) for spec in SIGNAL_GROUPS.values()),
    1.0,
    abs_tol=1e-12,
):  # pragma: no cover - import-time contract invariant
    raise RuntimeError("intraday signal group weights must sum to one")
_SIGNAL_MEMBERS = [key for spec in SIGNAL_GROUPS.values() for key in spec["members"]]
if len(_SIGNAL_MEMBERS) != len(set(_SIGNAL_MEMBERS)):  # pragma: no cover
    raise RuntimeError("intraday signal identities must belong to one group")


class MarketRegimeIntradayModelError(RuntimeError):
    """A frozen overlay input, transition, or history contract is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _round(value: float, digits: int = 6) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == -0.0 else rounded


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _instant(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketRegimeIntradayModelError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise MarketRegimeIntradayModelError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha_core(value: Mapping[str, Any]) -> str:
    return sha256(_json_bytes(value)).hexdigest()


def _validate_structural(analysis: Mapping[str, Any]) -> None:
    if (
        analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION
        or analysis.get("model_version") != STRUCTURAL_MODEL_VERSION
    ):
        raise MarketRegimeIntradayModelError("structural analysis contract mismatch")
    fingerprint = str(analysis.get("input_fingerprint") or "")
    expected = sha256(
        f"{STRUCTURAL_MODEL_VERSION}:{fingerprint}".encode("utf-8")
    ).hexdigest()
    if analysis.get("analysis_id") != f"market-regime-analysis:{expected}":
        raise MarketRegimeIntradayModelError("structural analysis identity mismatch")
    dimensions = analysis.get("dimensions")
    if not isinstance(dimensions, Mapping):
        raise MarketRegimeIntradayModelError("structural dimensions are unavailable")
    for key in ("risk", "posture", "style", "leadership"):
        if not isinstance(dimensions.get(key), Mapping):
            raise MarketRegimeIntradayModelError(f"structural {key} dimension is unavailable")
    if not isinstance(analysis.get("asset_features"), list):
        raise MarketRegimeIntradayModelError("structural asset features are unavailable")


def _validate_intraday_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("schema_version") != INTRADAY_SCHEMA_VERSION:
        raise MarketRegimeIntradayModelError("intraday snapshot contract mismatch")
    core = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    expected = _sha_core(core)
    if snapshot.get("snapshot_id") != f"market-regime-intraday-snapshot:{expected}":
        raise MarketRegimeIntradayModelError("intraday snapshot identity mismatch")
    if not isinstance(snapshot.get("instruments"), list):
        raise MarketRegimeIntradayModelError("intraday instruments must be a list")
    _instant(snapshot.get("generated_at"), field="intraday.generated_at")


def _overlay_core(overlay: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in overlay.items() if key != "overlay_id"}


def validate_overlay(overlay: Mapping[str, Any]) -> None:
    if (
        overlay.get("schema_version") != OVERLAY_SCHEMA_VERSION
        or overlay.get("model_version") != OVERLAY_MODEL_VERSION
    ):
        raise MarketRegimeIntradayModelError("overlay contract mismatch")
    if overlay.get("relation") not in RELATIONS:
        raise MarketRegimeIntradayModelError("overlay relation mismatch")
    a_share = overlay.get("a_share_tape")
    if not isinstance(a_share, Mapping) or a_share.get("relation") != overlay.get("relation"):
        raise MarketRegimeIntradayModelError("overlay A-share relation mismatch")
    watch = overlay.get("watch_conditions")
    if not isinstance(watch, list) or len(watch) != 2:
        raise MarketRegimeIntradayModelError("overlay watch-condition contract mismatch")
    boundary = overlay.get("truth_boundary")
    if (
        not isinstance(boundary, Mapping)
        or boundary.get("experimental") is not True
        or boundary.get("forecast") is not False
        or boundary.get("action_eligible") is not False
        or boundary.get("publication_eligible") is not False
    ):
        raise MarketRegimeIntradayModelError("overlay truth boundary mismatch")
    expected = _sha_core(_overlay_core(overlay))
    if overlay.get("overlay_id") != f"market-regime-intraday-overlay:{expected}":
        raise MarketRegimeIntradayModelError("overlay identity mismatch")
    _instant(overlay.get("generated_at"), field="overlay.generated_at")


def _instrument_map(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for raw in snapshot.get("instruments") or []:
        if not isinstance(raw, Mapping):
            raise MarketRegimeIntradayModelError("intraday instrument must be an object")
        instrument = raw.get("instrument")
        key = str(instrument.get("key") if isinstance(instrument, Mapping) else "")
        if key not in INTRADAY_INSTRUMENT_BY_KEY:
            raise MarketRegimeIntradayModelError(f"unknown intraday instrument: {key or 'missing'}")
        if key in result:
            raise MarketRegimeIntradayModelError(f"duplicate intraday instrument: {key}")
        result[key] = raw
    return result


def build_asset_impulse(item: Mapping[str, Any]) -> dict[str, Any]:
    """Build one bounded impulse from an already eligible normalized item."""
    instrument = item.get("instrument")
    key = str(instrument.get("key") if isinstance(instrument, Mapping) else "")
    if key not in INTRADAY_INSTRUMENT_BY_KEY:
        raise MarketRegimeIntradayModelError(f"unknown intraday instrument: {key or 'missing'}")
    reference = item.get("normalized_artifact")
    artifact_sha = str(reference.get("sha256") if isinstance(reference, Mapping) else "")
    if len(artifact_sha) != 64:
        raise MarketRegimeIntradayModelError(f"{key} normalized artifact identity is unavailable")
    rows = item.get("bars")
    if not isinstance(rows, list):
        raise MarketRegimeIntradayModelError(f"{key} bars must be a list")
    parsed: list[tuple[datetime, float]] = []
    previous: datetime | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MarketRegimeIntradayModelError(f"{key} bar {index} must be an object")
        ended = _instant(row.get("ended_at"), field=f"{key}.bar[{index}].ended_at")
        try:
            close = float(row["close"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketRegimeIntradayModelError(f"{key} bar {index} close is invalid") from exc
        if not math.isfinite(close) or close <= 0:
            raise MarketRegimeIntradayModelError(f"{key} bar {index} close is invalid")
        if previous is not None and ended <= previous:
            raise MarketRegimeIntradayModelError(f"{key} bar times are not strictly ascending")
        parsed.append((ended, close))
        previous = ended
    adjacent_returns = [
        math.log(parsed[index][1] / parsed[index - 1][1])
        for index in range(1, len(parsed))
        if int((parsed[index][0] - parsed[index - 1][0]).total_seconds()) == 300
    ]
    if len(adjacent_returns) < MIN_NOISE_RETURNS:
        raise MarketRegimeIntradayModelError(f"{key} has insufficient adjacent noise history")
    tail = [parsed[-1]] if parsed else []
    for index in range(len(parsed) - 2, -1, -1):
        if int((tail[0][0] - parsed[index][0]).total_seconds()) != 300:
            break
        tail.insert(0, parsed[index])
        if len(tail) == MAX_IMPULSE_BARS:
            break
    if len(tail) < MIN_CONTIGUOUS_BARS:
        raise MarketRegimeIntradayModelError(f"{key} has insufficient contiguous completed bars")
    intervals = len(tail) - 1
    trailing_log_return = math.log(tail[-1][1] / tail[0][1])
    observed_noise = statistics.pstdev(adjacent_returns)
    noise = max(observed_noise, NOISE_FLOOR)
    z_score = trailing_log_return / (noise * math.sqrt(intervals))
    impulse = 50.0 * math.tanh(z_score / 2.0)
    last_completed = str(item.get("last_completed_bar_end_at") or _iso(tail[-1][0]))
    return {
        "instrument": key,
        "impulse_score": _round(_clamp(impulse, -50.0, 50.0), 3),
        "trailing_return_pct": _round((math.exp(trailing_log_return) - 1.0) * 100, 6),
        "standardized_move": _round(z_score, 4),
        "noise_5m": _round(noise, 8),
        "noise_floor_applied": observed_noise < NOISE_FLOOR,
        "interval_count": intervals,
        "last_completed_bar_end_at": last_completed,
        "provider_timestamp": item.get("provider_timestamp"),
        "session_state": item.get("session_state"),
        "freshness": item.get("freshness"),
        "evidence_id": f"intraday:{key}:{last_completed}:{artifact_sha[:16]}",
        "normalized_artifact_sha256": artifact_sha,
    }


def _eligible_signals(
    instruments: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    signals: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, str]] = []
    for key in sorted(instruments):
        item = instruments[key]
        reason: str | None = None
        if item.get("refresh_status") != "accepted":
            reason = "current refresh was not accepted"
        elif item.get("session_state") != "open":
            reason = f"session is {item.get('session_state') or 'unknown'}"
        elif item.get("freshness") != "live_candidate":
            reason = f"freshness is {item.get('freshness') or 'unavailable'}"
        if reason is None:
            try:
                signals[key] = build_asset_impulse(item)
            except MarketRegimeIntradayModelError as exc:
                reason = str(exc)
        if reason is not None:
            excluded.append({"instrument": key, "reason": reason})
    return signals, excluded


def _cross_asset_contributions(signals: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    pending: list[dict[str, Any]] = []
    active_weight = 0.0
    for group, spec in SIGNAL_GROUPS.items():
        members = [key for key in spec["members"] if key in signals]
        if not members:
            continue
        active_weight += float(spec["weight"])
        allocated = float(spec["weight"]) / len(members)
        for key in members:
            signed_weight = allocated * float(spec["sign"])
            pending.append(
                {
                    **signals[key],
                    "group": group,
                    "role": spec["role"],
                    "signed_weight": signed_weight,
                    "raw_contribution": float(signals[key]["impulse_score"]) * signed_weight,
                }
            )
    contributions: list[dict[str, Any]] = []
    if active_weight > 0:
        for row in pending:
            contribution = row.pop("raw_contribution") / active_weight
            row["signed_weight"] = _round(row["signed_weight"], 6)
            row["contribution"] = _round(contribution, 3)
            contributions.append(row)
    contributions.sort(key=lambda row: (-abs(float(row["contribution"])), row["instrument"]))
    score = sum(float(row["contribution"]) for row in contributions)
    return {
        "status": "full" if active_weight >= 0.50 else "partial" if contributions else "insufficient",
        "score": _round(_clamp(score, -50.0, 50.0), 3) if contributions else None,
        "active_group_weight": _round(active_weight, 3),
        "active_group_count": len({row["group"] for row in contributions}),
        "contributions": contributions,
        "top_drivers": contributions[:5],
    }


def _structural_a_score(analysis: Mapping[str, Any]) -> tuple[float | None, list[str]]:
    features: dict[str, Mapping[str, Any]] = {}
    for row in analysis.get("asset_features") or []:
        if isinstance(row, Mapping):
            key = str(row.get("key") or "")
            if key in A_SHARE_WEIGHTS:
                if key in features:
                    raise MarketRegimeIntradayModelError(f"duplicate structural feature: {key}")
                features[key] = row
    missing = [key for key in A_SHARE_KEYS if key not in features]
    if "shanghai" not in features or not ({"star50", "china_dividend"} & set(features)):
        return None, missing
    denominator = sum(A_SHARE_WEIGHTS[key] for key in features)
    try:
        values = {key: float(features[key]["trend_score"]) for key in features}
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketRegimeIntradayModelError("structural A-share score is invalid") from exc
    if any(not math.isfinite(value) for value in values.values()):
        raise MarketRegimeIntradayModelError("structural A-share score is invalid")
    score = sum(values[key] * A_SHARE_WEIGHTS[key] for key in features) / denominator
    return _round(_clamp(score, -100.0, 100.0), 3), missing


def _live_a_score(signals: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, list[str]]:
    available = {key: signals[key] for key in A_SHARE_KEYS if key in signals}
    missing = [key for key in A_SHARE_KEYS if key not in available]
    if "shanghai" not in available or not ({"star50", "china_dividend"} & set(available)):
        return None, missing
    denominator = sum(A_SHARE_WEIGHTS[key] for key in available)
    score = sum(
        float(available[key]["impulse_score"]) * A_SHARE_WEIGHTS[key]
        for key in available
    ) / denominator
    return _round(_clamp(score, -50.0, 50.0), 3), missing


def _structural_direction(score: float) -> str:
    if score >= STRUCTURAL_DIRECTION_SCORE:
        return "positive"
    if score <= -STRUCTURAL_DIRECTION_SCORE:
        return "negative"
    return "neutral"


def classify_relation_candidate(
    structural_direction: str,
    impulse_score: float,
    *,
    previous_relation: str | None = None,
) -> str:
    """Classify with enter/exit hysteresis but without persistence/cooldown."""
    score = float(impulse_score)
    if structural_direction == "positive":
        if previous_relation == "confirms" and score >= EXIT_SCORE:
            return "confirms"
        if previous_relation == "diverges" and score <= -EXIT_SCORE:
            return "diverges"
        if score >= ENTER_SCORE:
            return "confirms"
        if score <= -ENTER_SCORE:
            return "diverges"
        return "insufficient"
    if structural_direction == "negative":
        if previous_relation == "confirms" and score <= -EXIT_SCORE:
            return "confirms"
        if previous_relation == "diverges" and score >= EXIT_SCORE:
            return "diverges"
        if score <= -ENTER_SCORE:
            return "confirms"
        if score >= ENTER_SCORE:
            return "diverges"
        return "insufficient"
    if structural_direction != "neutral":
        raise MarketRegimeIntradayModelError("structural direction is invalid")
    magnitude = abs(score)
    if previous_relation == "confirms" and magnitude <= ENTER_SCORE:
        return "confirms"
    if previous_relation == "diverges" and magnitude >= EXIT_SCORE:
        return "diverges"
    if magnitude <= EXIT_SCORE:
        return "confirms"
    if magnitude >= ENTER_SCORE:
        return "diverges"
    return "insufficient"


def _transition(
    candidate: str,
    *,
    generated_at: datetime,
    structural_analysis_id: str,
    previous: Mapping[str, Any] | None,
    immediate: bool,
) -> tuple[str, dict[str, Any]]:
    if candidate not in RELATIONS:
        raise MarketRegimeIntradayModelError("transition candidate is invalid")
    if immediate:
        return candidate, {
            "raw_relation": candidate,
            "pending_relation": None,
            "pending_count": 0,
            "persistence_required": PERSISTENCE_OVERLAYS,
            "cooldown_until": None,
            "blocked_by_cooldown": False,
            "transitioned": previous is not None and previous.get("relation") != candidate,
            "immediate_evidence_state": True,
        }
    compatible = bool(
        previous
        and isinstance(previous.get("structural"), Mapping)
        and previous["structural"].get("analysis_id") == structural_analysis_id
    )
    previous_relation = str(previous.get("relation")) if compatible else "insufficient"
    previous_transition = previous.get("transition") if compatible else None
    if not isinstance(previous_transition, Mapping):
        previous_transition = {}
    cooldown_until_raw = previous_transition.get("cooldown_until")
    cooldown_until = (
        _instant(cooldown_until_raw, field="previous.transition.cooldown_until")
        if cooldown_until_raw
        else None
    )
    if candidate == previous_relation:
        return candidate, {
            "raw_relation": candidate,
            "pending_relation": None,
            "pending_count": 0,
            "persistence_required": PERSISTENCE_OVERLAYS,
            "cooldown_until": _iso(cooldown_until) if cooldown_until and cooldown_until > generated_at else None,
            "blocked_by_cooldown": False,
            "transitioned": False,
            "immediate_evidence_state": False,
        }
    prior_pending = previous_transition.get("pending_relation")
    prior_count = int(previous_transition.get("pending_count") or 0)
    pending_count = prior_count + 1 if prior_pending == candidate else 1
    opposite_directional = (
        previous_relation in DIRECTIONAL_RELATIONS
        and candidate in DIRECTIONAL_RELATIONS
        and candidate != previous_relation
    )
    blocked = bool(opposite_directional and cooldown_until and generated_at < cooldown_until)
    can_transition = pending_count >= PERSISTENCE_OVERLAYS and not blocked
    if can_transition:
        next_cooldown = (
            generated_at + timedelta(seconds=COOLDOWN_SECONDS)
            if candidate in DIRECTIONAL_RELATIONS
            else None
        )
        return candidate, {
            "raw_relation": candidate,
            "pending_relation": None,
            "pending_count": 0,
            "persistence_required": PERSISTENCE_OVERLAYS,
            "cooldown_until": _iso(next_cooldown) if next_cooldown else None,
            "blocked_by_cooldown": False,
            "transitioned": True,
            "immediate_evidence_state": False,
        }
    stable = previous_relation if previous_relation in DIRECTIONAL_RELATIONS else "insufficient"
    return stable, {
        "raw_relation": candidate,
        "pending_relation": candidate,
        "pending_count": pending_count,
        "persistence_required": PERSISTENCE_OVERLAYS,
        "cooldown_until": _iso(cooldown_until) if cooldown_until and cooldown_until > generated_at else None,
        "blocked_by_cooldown": blocked,
        "transitioned": False,
        "immediate_evidence_state": False,
    }


def _score_band(value: float | None) -> str:
    if value is None:
        return "unavailable"
    if value >= ENTER_SCORE:
        return "positive"
    if value <= -ENTER_SCORE:
        return "negative"
    if abs(value) <= EXIT_SCORE:
        return "neutral"
    return "transition"


def _material_change(
    *,
    relation: str,
    structural_analysis_id: str,
    a_score: float | None,
    cross_score: float | None,
    previous: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if previous is None:
        return {
            "baseline_overlay_id": None,
            "is_material": False,
            "reasons": ["baseline_not_available"],
            "relation_from": None,
            "relation_to": relation,
            "a_share_score_delta": None,
            "cross_asset_score_delta": None,
        }
    reasons: list[str] = []
    previous_relation = str(previous.get("relation"))
    if previous_relation != relation:
        reasons.append("stable_relation_changed")
    previous_structural = previous.get("structural") or {}
    if previous_structural.get("analysis_id") != structural_analysis_id:
        reasons.append("structural_analysis_changed")
    previous_a = (previous.get("a_share_tape") or {}).get("impulse_score")
    previous_cross = (previous.get("cross_asset") or {}).get("score")
    a_delta = float(a_score) - float(previous_a) if a_score is not None and previous_a is not None else None
    cross_delta = (
        float(cross_score) - float(previous_cross)
        if cross_score is not None and previous_cross is not None
        else None
    )
    if cross_delta is not None and abs(cross_delta) >= MATERIAL_SCORE_DELTA:
        reasons.append("cross_asset_score_delta")
    if _score_band(a_score) != _score_band(float(previous_a) if previous_a is not None else None):
        reasons.append("a_share_score_band_changed")
    return {
        "baseline_overlay_id": previous.get("overlay_id"),
        "is_material": bool(reasons),
        "reasons": reasons,
        "relation_from": previous_relation,
        "relation_to": relation,
        "a_share_score_delta": _round(a_delta, 3) if a_delta is not None else None,
        "cross_asset_score_delta": _round(cross_delta, 3) if cross_delta is not None else None,
    }


def _watch_conditions(
    relation: str,
    *,
    structural_direction: str | None,
    a_score: float | None,
    cross_score: float | None,
    missing: list[str],
) -> list[dict[str, Any]]:
    if relation == "closed":
        return [
            {
                "code": "a_share_session_reopens",
                "condition": "Shanghai session is open with live_candidate completed bars",
                "current": "closed",
                "threshold": "session_state=open and freshness=live_candidate",
            },
            {
                "code": "directional_persistence",
                "condition": "eligible A-share relation persists across unique verified overlays",
                "current": 0,
                "threshold": PERSISTENCE_OVERLAYS,
            },
        ]
    if relation == "insufficient":
        return [
            {
                "code": "a_share_evidence_recovers",
                "condition": "Shanghai plus STAR 50 or SSE Dividend become eligible",
                "current": sorted(missing),
                "threshold": "shanghai + one style index",
            },
            {
                "code": "directional_enter",
                "condition": "A-share impulse reaches a frozen relation-enter threshold",
                "current": a_score,
                "threshold": {"positive": ENTER_SCORE, "negative": -ENTER_SCORE},
            },
        ]
    if structural_direction == "positive":
        flip = -ENTER_SCORE if relation == "confirms" else ENTER_SCORE
        operator = "<=" if relation == "confirms" else ">="
    elif structural_direction == "negative":
        flip = ENTER_SCORE if relation == "confirms" else -ENTER_SCORE
        operator = ">=" if relation == "confirms" else "<="
    else:
        flip = ENTER_SCORE if relation == "confirms" else EXIT_SCORE
        operator = "abs >=" if relation == "confirms" else "abs <="
    return [
        {
            "code": "relation_flip",
            "condition": f"A-share impulse {operator} {flip} for consecutive verified overlays",
            "current": a_score,
            "threshold": flip,
            "persistence_required": PERSISTENCE_OVERLAYS,
        },
        {
            "code": "material_cross_asset_delta",
            "condition": "absolute cross-asset score move from this verified baseline",
            "current": cross_score,
            "threshold": MATERIAL_SCORE_DELTA,
        },
    ]


def compile_intraday_overlay(
    structural: Mapping[str, Any],
    intraday: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile one deterministic overlay without performing I/O."""
    _validate_structural(structural)
    _validate_intraday_snapshot(intraday)
    if previous is not None:
        validate_overlay(previous)
    input_identity = {
        "structural_analysis_id": structural["analysis_id"],
        "intraday_snapshot_id": intraday["snapshot_id"],
    }
    input_fingerprint = _sha_core(input_identity)
    if previous is not None and previous.get("input_fingerprint") == input_fingerprint:
        return dict(previous)
    generated_at = _instant(intraday.get("generated_at"), field="intraday.generated_at")
    if previous is not None:
        previous_at = _instant(previous.get("generated_at"), field="previous.generated_at")
        if generated_at <= previous_at:
            raise MarketRegimeIntradayModelError(
                "new intraday snapshot must be later than the previous successful overlay"
            )
    instruments = _instrument_map(intraday)
    signals, excluded = _eligible_signals(instruments)
    cross_asset = _cross_asset_contributions(signals)
    structural_a, structural_missing = _structural_a_score(structural)
    live_a, live_missing = _live_a_score(signals)
    a_states = {
        key: str(instruments[key].get("session_state") or "unknown")
        if key in instruments
        else "unavailable"
        for key in A_SHARE_KEYS
    }
    all_current_a_sessions = all(
        key in instruments and instruments[key].get("refresh_status") == "accepted"
        for key in A_SHARE_KEYS
    )
    all_known_non_open = all_current_a_sessions and all(
        state in KNOWN_A_NON_OPEN for state in a_states.values()
    )
    missing = sorted(set(structural_missing + live_missing))
    direction: str | None = None
    if all_known_non_open:
        candidate = "closed"
        immediate = True
        relation_reason = "all A-share dependencies are in known non-open sessions"
    elif not any(state == "open" for state in a_states.values()):
        candidate = "insufficient"
        immediate = True
        relation_reason = "A-share session evidence is unavailable or conflicting"
    elif structural_a is None or live_a is None:
        candidate = "insufficient"
        immediate = True
        relation_reason = "required A-share structural or intraday evidence is missing"
    else:
        direction = _structural_direction(structural_a)
        prior_relation = None
        if (
            previous is not None
            and isinstance(previous.get("structural"), Mapping)
            and previous["structural"].get("analysis_id") == structural["analysis_id"]
        ):
            prior_relation = str(previous.get("relation"))
        candidate = classify_relation_candidate(
            direction,
            live_a,
            previous_relation=prior_relation,
        )
        immediate = False
        relation_reason = "eligible A-share impulse compared with frozen daily structure"
    relation, transition = _transition(
        candidate,
        generated_at=generated_at,
        structural_analysis_id=str(structural["analysis_id"]),
        previous=previous,
        immediate=immediate,
    )
    style_score = None
    if "star50" in signals and "china_dividend" in signals:
        style_score = _round(
            float(signals["star50"]["impulse_score"])
            - float(signals["china_dividend"]["impulse_score"]),
            3,
        )
    material = _material_change(
        relation=relation,
        structural_analysis_id=str(structural["analysis_id"]),
        a_score=live_a,
        cross_score=cross_asset["score"],
        previous=previous,
    )
    dimensions = structural["dimensions"]
    leadership = dimensions["leadership"]
    scenario = structural.get("scenario") or {}
    core: dict[str, Any] = {
        "schema_version": OVERLAY_SCHEMA_VERSION,
        "model_version": OVERLAY_MODEL_VERSION,
        "generated_at": _iso(generated_at),
        "input_fingerprint": input_fingerprint,
        "baseline_overlay_id": previous.get("overlay_id") if previous else None,
        "relation": relation,
        "structural": {
            "analysis_id": structural["analysis_id"],
            "status": structural.get("status"),
            "verdict_as_of": structural.get("verdict_as_of"),
            "risk": dimensions["risk"].get("label"),
            "posture": dimensions["posture"].get("label"),
            "style": dimensions["style"].get("label"),
            "leader": leadership.get("leader"),
            "scenario": scenario.get("code"),
            "immutable": True,
        },
        "intraday": {
            "snapshot_id": intraday["snapshot_id"],
            "run_id": intraday.get("run_id"),
            "quality": intraday.get("quality"),
            "data_kind": intraday.get("data_kind"),
        },
        "a_share_tape": {
            "relation": relation,
            "reason": relation_reason,
            "session_states": a_states,
            "structural_score": structural_a,
            "structural_direction": direction,
            "impulse_score": live_a,
            "score_band": _score_band(live_a),
            "missing_dependencies": missing,
            "style_relative_score": style_score,
            "eligible_signals": [signals[key] for key in A_SHARE_KEYS if key in signals],
        },
        "cross_asset": {
            key: value
            for key, value in cross_asset.items()
            if key not in {"contributions", "top_drivers"}
        },
        "signal_contributions": cross_asset["contributions"],
        "top_drivers": cross_asset["top_drivers"],
        "excluded_signals": excluded,
        "transition": transition,
        "material_change": material,
        "watch_conditions": _watch_conditions(
            relation,
            structural_direction=direction,
            a_score=live_a,
            cross_score=cross_asset["score"],
            missing=missing,
        ),
        "truth_boundary": {
            "judgment_state": "model_generated_unreviewed",
            "experimental": True,
            "read_only": True,
            "structural_labels_overwritten": False,
            "drivers_are_causal_claims": False,
            "forecast": False,
            "investment_advice": False,
            "not_investment_advice": True,
            "action_eligible": False,
            "publication_eligible": False,
        },
    }
    identity = _sha_core(core)
    return {**core, "overlay_id": f"market-regime-intraday-overlay:{identity}"}


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
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
            raise MarketRegimeIntradayModelError(f"immutable identity collision: {path.name}")
        return sha256(existing).hexdigest()
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return sha256(encoded).hexdigest()


class MarketRegimeIntradayOverlayStore:
    """Compile and persist immutable overlays with a hash-linked history."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    @property
    def _pointer_path(self) -> Path:
        return self.root / "intraday" / "overlay" / "latest.json"

    def _pointer(self, *, allow_missing: bool = False) -> dict[str, Any] | None:
        try:
            value = json.loads(self._pointer_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if allow_missing:
                return None
            raise MarketRegimeIntradayModelError("intraday overlay is unavailable")
        except json.JSONDecodeError as exc:
            raise MarketRegimeIntradayModelError("intraday overlay pointer is not JSON") from exc
        if not isinstance(value, dict) or value.get("schema_version") != POINTER_SCHEMA_VERSION:
            raise MarketRegimeIntradayModelError("intraday overlay pointer contract mismatch")
        return value

    def _read_reference(self, reference: Mapping[str, Any], *, prefix: str) -> dict[str, Any]:
        relative = str(reference.get("path") or "")
        expected_hash = str(reference.get("sha256") or "")
        if not relative.startswith(prefix) or len(expected_hash) != 64:
            raise MarketRegimeIntradayModelError("overlay artifact reference is incomplete")
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise MarketRegimeIntradayModelError("overlay artifact path escapes runtime root")
        try:
            encoded = target.read_bytes()
        except FileNotFoundError as exc:
            raise MarketRegimeIntradayModelError("overlay artifact is missing") from exc
        if sha256(encoded).hexdigest() != expected_hash:
            raise MarketRegimeIntradayModelError("overlay artifact hash mismatch")
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise MarketRegimeIntradayModelError("overlay artifact is not JSON") from exc
        if not isinstance(value, dict):
            raise MarketRegimeIntradayModelError("overlay artifact must be an object")
        return value

    def _read_overlay(self, reference: Mapping[str, Any]) -> dict[str, Any]:
        overlay = self._read_reference(
            reference, prefix="intraday/overlay/artifacts/"
        )
        validate_overlay(overlay)
        if overlay.get("overlay_id") != reference.get("overlay_id"):
            raise MarketRegimeIntradayModelError("overlay reference identity mismatch")
        return overlay

    def verify_history(self) -> list[dict[str, Any]]:
        pointer = self._pointer()
        assert pointer is not None
        current = pointer.get("history")
        if not isinstance(current, Mapping):
            raise MarketRegimeIntradayModelError("overlay history pointer is incomplete")
        expected_sequence = int(pointer.get("sequence") or 0)
        if expected_sequence < 1:
            raise MarketRegimeIntradayModelError("overlay history sequence is invalid")
        seen: set[str] = set()
        reversed_entries: list[dict[str, Any]] = []
        while current is not None:
            path = str(current.get("path") or "")
            if path in seen:
                raise MarketRegimeIntradayModelError("overlay history contains a cycle")
            seen.add(path)
            entry = self._read_reference(
                current, prefix="intraday/overlay/history/"
            )
            if entry.get("schema_version") != HISTORY_SCHEMA_VERSION:
                raise MarketRegimeIntradayModelError("overlay history contract mismatch")
            entry_core = {key: value for key, value in entry.items() if key != "history_id"}
            expected_id = f"market-regime-intraday-history:{_sha_core(entry_core)}"
            if entry.get("history_id") != expected_id or current.get("history_id") != expected_id:
                raise MarketRegimeIntradayModelError("overlay history identity mismatch")
            if int(entry.get("sequence") or 0) != expected_sequence:
                raise MarketRegimeIntradayModelError("overlay history sequence gap")
            overlay_reference = entry.get("overlay")
            if not isinstance(overlay_reference, Mapping):
                raise MarketRegimeIntradayModelError("history overlay reference is incomplete")
            overlay = self._read_overlay(overlay_reference)
            if overlay.get("overlay_id") != entry.get("overlay_id"):
                raise MarketRegimeIntradayModelError("history overlay identity mismatch")
            reversed_entries.append(entry)
            previous = entry.get("previous")
            if expected_sequence == 1:
                if previous is not None:
                    raise MarketRegimeIntradayModelError("history genesis has a predecessor")
                current = None
            else:
                if not isinstance(previous, Mapping):
                    raise MarketRegimeIntradayModelError("overlay history chain is broken")
                current = previous
            expected_sequence -= 1
        if expected_sequence != 0:
            raise MarketRegimeIntradayModelError("overlay history chain is truncated")
        entries = list(reversed(reversed_entries))
        latest_overlay = entries[-1]["overlay"]
        pointer_overlay = pointer.get("overlay")
        if (
            not isinstance(pointer_overlay, Mapping)
            or pointer_overlay.get("overlay_id") != latest_overlay.get("overlay_id")
            or pointer_overlay.get("sha256") != latest_overlay.get("sha256")
        ):
            raise MarketRegimeIntradayModelError("latest overlay/history pointer mismatch")
        return entries

    def latest(self) -> dict[str, Any]:
        pointer = self._pointer()
        assert pointer is not None
        self.verify_history()
        reference = pointer.get("overlay")
        if not isinstance(reference, Mapping):
            raise MarketRegimeIntradayModelError("latest overlay reference is incomplete")
        overlay = self._read_overlay(reference)
        if overlay.get("input_fingerprint") != pointer.get("input_fingerprint"):
            raise MarketRegimeIntradayModelError("latest overlay input identity mismatch")
        return overlay

    def compile_latest(self) -> dict[str, Any]:
        try:
            structural = MarketRegimeAnalysisStore(self.root).latest()
            intraday = MarketRegimeIntradayDataStore(self.root).latest()
        except (MarketRegimeModelError, MarketRegimeIntradayDataError) as exc:
            raise MarketRegimeIntradayModelError(str(exc)) from exc
        pointer = self._pointer(allow_missing=True)
        previous = self.latest() if pointer is not None else None
        overlay = compile_intraday_overlay(structural, intraday, previous)
        if previous is not None and overlay["overlay_id"] == previous["overlay_id"]:
            return {
                "overlay": previous,
                "history_appended": False,
                "sequence": pointer["sequence"],
                "history_id": (pointer.get("history") or {}).get("history_id"),
            }
        digest = overlay["overlay_id"].split(":", 1)[1]
        overlay_relative = f"intraday/overlay/artifacts/{digest}.json"
        overlay_hash = _write_immutable(self.root / overlay_relative, overlay)
        sequence = int(pointer.get("sequence") or 0) + 1 if pointer else 1
        previous_reference = dict(pointer["history"]) if pointer else None
        entry_core: dict[str, Any] = {
            "schema_version": HISTORY_SCHEMA_VERSION,
            "sequence": sequence,
            "overlay_id": overlay["overlay_id"],
            "overlay": {
                "path": overlay_relative,
                "sha256": overlay_hash,
                "overlay_id": overlay["overlay_id"],
            },
            "previous": previous_reference,
        }
        history_identity = _sha_core(entry_core)
        history_id = f"market-regime-intraday-history:{history_identity}"
        entry = {**entry_core, "history_id": history_id}
        history_relative = (
            f"intraday/overlay/history/{sequence:08d}-{history_identity}.json"
        )
        history_hash = _write_immutable(self.root / history_relative, entry)
        # Read both new immutable objects before the only mutable pointer moves.
        overlay_reference = entry_core["overlay"]
        self._read_overlay(overlay_reference)
        self._read_reference(
            {
                "path": history_relative,
                "sha256": history_hash,
                "history_id": history_id,
            },
            prefix="intraday/overlay/history/",
        )
        latest_pointer = {
            "schema_version": POINTER_SCHEMA_VERSION,
            "sequence": sequence,
            "input_fingerprint": overlay["input_fingerprint"],
            "overlay": overlay_reference,
            "history": {
                "path": history_relative,
                "sha256": history_hash,
                "history_id": history_id,
            },
        }
        _write_atomic(self._pointer_path, latest_pointer)
        return {
            "overlay": overlay,
            "history_appended": True,
            "sequence": sequence,
            "history_id": history_id,
        }
