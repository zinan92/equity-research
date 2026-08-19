"""Deterministic, evidence-bound market-level payoff-versus-risk setup."""

from __future__ import annotations

import math
from typing import Any, Mapping


ODDS_SCHEMA_VERSION = "market-regime-weekly-odds-v1"
ODDS_FORMULA_VERSION = "entry-close-boundary-v1"
ODDS_STATES = frozenset({"favorable", "marginal", "unfavorable", "not_ready"})
DIRECTIONS = frozenset({"long", "short", "none"})
LEVEL_WINDOW = 20


class WeeklyOddsError(ValueError):
    """Odds setup failed closed or violated its arithmetic contract."""


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _value(point: Mapping[str, Any]) -> float | None:
    return _finite(point.get("close", point.get("value")))


def _level_points(points: list[Mapping[str, Any]]) -> tuple[float | None, float | None]:
    lows: list[float] = []
    highs: list[float] = []
    for point in points[-LEVEL_WINDOW:]:
        value = _value(point)
        if value is None:
            continue
        lows.append(_finite(point.get("low")) if _finite(point.get("low")) is not None else value)
        highs.append(_finite(point.get("high")) if _finite(point.get("high")) is not None else value)
    return (min(lows) if lows else None, max(highs) if highs else None)


def _not_ready(*, timeframe: str | None, evidence_ids: list[str], reason_code: str, text: str) -> dict[str, Any]:
    return {
        "schema_version": ODDS_SCHEMA_VERSION,
        "formula_version": ODDS_FORMULA_VERSION,
        "state": "not_ready",
        "direction": "none",
        "timeframe": timeframe,
        "evidence_ids": list(evidence_ids),
        "reason_code": reason_code,
        "text": text,
    }


def _bound_feature_ids(frame: Mapping[str, Any]) -> list[str]:
    features = frame.get("features")
    identity = str(features.get("feature_identity") or "") if isinstance(features, Mapping) else ""
    expected = f"feature:{identity}" if identity else ""
    frame_ids = {str(item) for item in frame.get("evidence_ids") or []}
    return [expected] if expected and expected in frame_ids else []


def build_odds(request: Mapping[str, Any], structure: Mapping[str, Any]) -> dict[str, Any]:
    """Build one setup from the latest verified close and observed boundaries.

    The current close is the entry reference and trigger level. Support and
    resistance are the min/max of the latest 20 verified points in the chosen
    daily (then weekly) frame. No model-selected price is accepted.
    """

    bias = str(structure.get("bias") or "")
    direction = "long" if bias == "bullish" else ("short" if bias == "bearish" else "none")
    timeframes = request.get("timeframes")
    if not isinstance(timeframes, Mapping):
        return _not_ready(timeframe=None, evidence_ids=[], reason_code="timeframes_unavailable", text="赔率尚未形成：没有可用的周期证据。")
    selected: tuple[str, Mapping[str, Any]] | None = None
    first_frame: tuple[str, Mapping[str, Any]] | None = None
    for timeframe in ("daily", "weekly"):
        frame = timeframes.get(timeframe)
        if isinstance(frame, Mapping):
            first_frame = first_frame or (timeframe, frame)
            features = frame.get("features")
            if isinstance(features, Mapping) and features.get("status") == "complete" and len(list(features.get("points") or [])) >= 2:
                selected = (timeframe, frame)
                break
    if selected is None:
        if first_frame is None:
            return _not_ready(timeframe=None, evidence_ids=[], reason_code="timeframe_unavailable", text="赔率尚未形成：没有可用的日线或周线边界。")
        first_timeframe, first = first_frame
        return _not_ready(timeframe=first_timeframe, evidence_ids=_bound_feature_ids(first), reason_code="insufficient_boundary_history", text="赔率尚未形成：边界历史不足。")
    timeframe, frame = selected
    evidence_ids = _bound_feature_ids(frame)
    features = frame.get("features")
    points = list(features.get("points") or []) if isinstance(features, Mapping) else []
    feature_identity = str(features.get("feature_identity") or "") if isinstance(features, Mapping) else ""
    expected_feature_id = f"feature:{feature_identity}" if feature_identity else ""
    if not expected_feature_id or expected_feature_id not in evidence_ids:
        return _not_ready(timeframe=timeframe, evidence_ids=evidence_ids, reason_code="feature_evidence_mismatch", text="赔率尚未形成：边界特征与证据身份不一致。")
    if len(points) < 2:
        return _not_ready(timeframe=timeframe, evidence_ids=evidence_ids, reason_code="insufficient_boundary_history", text="赔率尚未形成：边界历史不足。")
    entry = _value(points[-1])
    support, resistance = _level_points(points)
    if entry is None or support is None or resistance is None:
        return _not_ready(timeframe=timeframe, evidence_ids=evidence_ids, reason_code="boundary_unavailable", text="赔率尚未形成：触发、止损或目标边界不可用。")
    if direction == "none":
        return _not_ready(timeframe=timeframe, evidence_ids=evidence_ids, reason_code="direction_unavailable", text="赔率尚未形成：多周期没有单一方向。")
    if direction == "long":
        stop, target = support, resistance
        risk, reward = entry - stop, target - entry
        trigger_rule = "下一根同周期收盘仍站在当前参考位上方"
    else:
        stop, target = resistance, support
        risk, reward = stop - entry, entry - target
        trigger_rule = "下一根同周期收盘仍处于当前参考位下方"
    if not (risk > 0 and reward > 0):
        return _not_ready(timeframe=timeframe, evidence_ids=evidence_ids, reason_code="level_order_invalid", text="赔率尚未形成：止损与目标的顺序无效。")
    risk_reward = reward / risk
    state = "favorable" if risk_reward >= 2 else ("marginal" if risk_reward >= 1 else "unfavorable")
    state_text = {"favorable": "赔率有利", "marginal": "赔率一般", "unfavorable": "赔率不利"}[state]
    direction_text = {"long": "做多", "short": "做空"}[direction]
    return {
        "schema_version": ODDS_SCHEMA_VERSION,
        "formula_version": ODDS_FORMULA_VERSION,
        "state": state,
        "direction": direction,
        "timeframe": timeframe,
        "trigger": entry,
        "trigger_rule": trigger_rule,
        "entry_reference": entry,
        "stop": stop,
        "target": target,
        "risk": risk,
        "reward": reward,
        "risk_reward": risk_reward,
        "boundary_window": LEVEL_WINDOW,
        "sample_count": len(points[-LEVEL_WINDOW:]),
        "evidence_ids": list(evidence_ids),
        "text": f"{state_text}：{direction_text}方向，风险约{risk:.4g}，潜在收益约{reward:.4g}，R≈{risk_reward:.2f}。",
    }


def validate_odds(
    value: Any,
    *,
    allowed_feature_ids: set[str] | None = None,
    allowed_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WeeklyOddsError("odds_invalid")
    if value.get("schema_version") != ODDS_SCHEMA_VERSION or value.get("formula_version") != ODDS_FORMULA_VERSION:
        raise WeeklyOddsError("odds_version_invalid")
    state = str(value.get("state") or "")
    direction = str(value.get("direction") or "")
    if state not in ODDS_STATES or direction not in DIRECTIONS:
        raise WeeklyOddsError("odds_state_invalid")
    ids = value.get("evidence_ids")
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        raise WeeklyOddsError("odds_evidence_invalid")
    if len(set(ids)) != len(ids):
        raise WeeklyOddsError("odds_evidence_duplicate")
    if allowed_evidence_ids is not None and not set(ids).issubset(allowed_evidence_ids):
        raise WeeklyOddsError("odds_evidence_mismatch")
    if not any(item.startswith("feature:") for item in ids):
        raise WeeklyOddsError("odds_feature_evidence_missing")
    if allowed_feature_ids is not None and not any(item in allowed_feature_ids for item in ids):
        raise WeeklyOddsError("odds_feature_evidence_mismatch")
    if state == "not_ready":
        if direction != "none" or "risk_reward" in value:
            raise WeeklyOddsError("odds_not_ready_payload_invalid")
        if any(name in value for name in ("trigger", "entry_reference", "stop", "target", "risk", "reward")):
            raise WeeklyOddsError("odds_not_ready_levels_present")
        return dict(value)
    if value.get("timeframe") not in {"daily", "weekly"}:
        raise WeeklyOddsError("odds_timeframe_invalid")
    if direction not in {"long", "short"}:
        raise WeeklyOddsError("odds_ready_direction_invalid")
    numbers = {name: _finite(value.get(name)) for name in ("trigger", "entry_reference", "stop", "target", "risk", "reward", "risk_reward")}
    if any(number is None for number in numbers.values()):
        raise WeeklyOddsError("odds_level_missing")
    if numbers["trigger"] != numbers["entry_reference"]:
        raise WeeklyOddsError("odds_trigger_entry_mismatch")
    if not isinstance(value.get("trigger_rule"), str) or not value["trigger_rule"].strip():
        raise WeeklyOddsError("odds_trigger_rule_missing")
    if direction == "long":
        if not (numbers["stop"] < numbers["entry_reference"] < numbers["target"]):
            raise WeeklyOddsError("odds_long_order_invalid")
    else:
        if not (numbers["target"] < numbers["entry_reference"] < numbers["stop"]):
            raise WeeklyOddsError("odds_short_order_invalid")
    expected_risk = abs(numbers["entry_reference"] - numbers["stop"])
    expected_reward = abs(numbers["target"] - numbers["entry_reference"])
    expected_rr = expected_reward / expected_risk
    if abs(numbers["risk"] - expected_risk) > 1e-9 or abs(numbers["reward"] - expected_reward) > 1e-9 or abs(numbers["risk_reward"] - expected_rr) > 1e-9:
        raise WeeklyOddsError("odds_formula_mismatch")
    expected_state = "favorable" if expected_rr >= 2 else ("marginal" if expected_rr >= 1 else "unfavorable")
    if state != expected_state:
        raise WeeklyOddsError("odds_threshold_mismatch")
    return dict(value)
