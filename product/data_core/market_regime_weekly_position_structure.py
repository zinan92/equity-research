"""Code-owned Position and Structure dimensions for one Weekly asset."""

from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "market-regime-weekly-position-structure-v1"
POSITION_STATES = frozenset({"low", "middle", "high", "unavailable", "unknown"})
STRUCTURE_STATES = frozenset({"continuation", "weakening", "reversal", "range", "mixed", "unknown"})
TIMEFRAME_LABELS = {"weekly": "周线", "daily": "日线", "four_hour": "4小时", "thirty_minute": "30分钟"}


class WeeklyPositionStructureError(ValueError):
    """Position/Structure derivation failed closed."""


def _values(frame: Mapping[str, Any]) -> list[float]:
    result: list[float] = []
    for point in frame.get("points") or []:
        raw = point.get("close", point.get("value")) if isinstance(point, Mapping) else None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value == value and abs(value) != float("inf"):
            result.append(value)
    return result


def _position_for_frame(frame: Mapping[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    features = frame.get("features") or {}
    values = _values({"points": features.get("points") or []})
    sample_count = len(values)
    window = int(features.get("source_point_count") or sample_count)
    if features.get("status") in {"short_history", "unavailable"}:
        timeframe = TIMEFRAME_LABELS.get(str(frame.get("timeframe")), str(frame.get("timeframe") or "当前周期"))
        return {"state": "unavailable", "percentile": None, "timeframe": frame.get("timeframe"), "window": window, "sample_count": sample_count, "evidence_ids": list(evidence_ids), "text": f"位置：{timeframe}历史不足，无法判断。"}
    if not values:
        return {"state": "unknown", "percentile": None, "timeframe": frame.get("timeframe"), "window": window, "sample_count": sample_count, "evidence_ids": list(evidence_ids), "text": "位置：不可用。"}
    current = values[-1]
    percentile = sum(value <= current for value in values) / len(values)
    state = "high" if percentile > 0.7 else ("low" if percentile < 0.3 else "middle")
    label = {"high": "高位", "middle": "中位", "low": "低位"}[state]
    timeframe = TIMEFRAME_LABELS.get(str(frame.get("timeframe")), str(frame.get("timeframe") or "当前周期"))
    return {
        "state": state,
        "percentile": round(percentile, 6),
        "timeframe": frame.get("timeframe"),
        "window": window,
        "sample_count": sample_count,
        "evidence_ids": list(evidence_ids),
        "text": f"位置：{timeframe}处于{label}，当前收盘位于该周期样本的约{percentile:.0%}分位。",
    }


def _orientation(close: float, ema: float | None, macd: float | None) -> str:
    if ema is None or macd is None:
        return "unknown"
    if close > ema and macd >= 0:
        return "bullish"
    if close < ema and macd <= 0:
        return "bearish"
    return "neutral"


def _structure_for_frame(frame: Mapping[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    features = frame.get("features") or {}
    points = list(features.get("points") or [])
    if len(points) < 2:
        return {"state": "unknown", "bias": "unknown", "timeframe": frame.get("timeframe"), "evidence_ids": list(evidence_ids), "text": "结构：证据不足。"}
    last, previous = points[-1], points[-2]
    try:
        close = float(last.get("close", last.get("value")))
        prev_close = float(previous.get("close", previous.get("value")))
    except (TypeError, ValueError) as exc:
        raise WeeklyPositionStructureError("feature_point_invalid") from exc
    if close != close or prev_close != prev_close:
        raise WeeklyPositionStructureError("feature_point_invalid")
    current_orientation = _orientation(close, last.get("ema50"), last.get("macd"))
    previous_orientation = _orientation(prev_close, previous.get("ema50"), previous.get("macd"))
    if current_orientation == "unknown":
        state, bias = "unknown", "unknown"
    elif current_orientation == "neutral":
        state, bias = "range", "neutral"
    elif previous_orientation not in {"unknown", "neutral", current_orientation}:
        state, bias = "reversal", current_orientation
    else:
        histogram = last.get("macd_histogram")
        previous_histogram = previous.get("macd_histogram")
        weakening = (
            isinstance(histogram, (int, float))
            and isinstance(previous_histogram, (int, float))
            and abs(float(histogram)) < abs(float(previous_histogram))
        )
        state, bias = ("weakening", current_orientation) if weakening else ("continuation", current_orientation)
    state_label = {"continuation": "趋势延续", "weakening": "趋势减弱", "reversal": "趋势反转", "range": "区间震荡", "mixed": "周期分歧", "unknown": "未知"}[state]
    bias_label = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性", "unknown": "未知"}[bias]
    timeframe = TIMEFRAME_LABELS.get(str(frame.get("timeframe")), str(frame.get("timeframe") or "当前周期"))
    return {"state": state, "bias": bias, "timeframe": frame.get("timeframe"), "evidence_ids": list(evidence_ids), "text": f"结构：{timeframe}{state_label}，方向{bias_label}。"}


def build_position_structure(request: Mapping[str, Any]) -> dict[str, Any]:
    """Derive reader-facing Position/Structure without model judgment."""

    timeframes = request.get("timeframes")
    if not isinstance(timeframes, Mapping):
        raise WeeklyPositionStructureError("position_structure_timeframes_invalid")
    position_by_timeframe: dict[str, dict[str, Any]] = {}
    structure_by_timeframe: dict[str, dict[str, Any]] = {}
    for timeframe, raw in timeframes.items():
        if not isinstance(raw, Mapping):
            continue
        frame = {**raw, "timeframe": timeframe}
        evidence_ids = [str(item) for item in raw.get("evidence_ids") or []]
        features = raw.get("features")
        if not isinstance(features, Mapping):
            raise WeeklyPositionStructureError(f"feature_payload_missing:{timeframe}")
        feature_identity = str(features.get("feature_identity") or "")
        feature_evidence_id = f"feature:{feature_identity}" if feature_identity else ""
        if not feature_evidence_id or feature_evidence_id not in evidence_ids:
            raise WeeklyPositionStructureError(f"feature_evidence_missing:{timeframe}")
        position_by_timeframe[str(timeframe)] = _position_for_frame(frame, evidence_ids)
        structure_by_timeframe[str(timeframe)] = _structure_for_frame(frame, evidence_ids)

    usable_positions = [row for row in (position_by_timeframe.get("weekly"), position_by_timeframe.get("daily"), position_by_timeframe.get("four_hour"), position_by_timeframe.get("thirty_minute")) if isinstance(row, Mapping) and row.get("state") not in {"unavailable", "unknown"}]
    position_source = usable_positions[0] if usable_positions else next(iter(position_by_timeframe.values()), None)
    if position_source is None:
        position = {"state": "unknown", "percentile": None, "timeframe": None, "window": 0, "sample_count": 0, "evidence_ids": [], "timeframes": {}, "text": "位置：不可用。"}
    else:
        position = {**position_source, "timeframes": position_by_timeframe}

    structures = list(structure_by_timeframe.values())
    evidence_ids = sorted({item for row in structures for item in row.get("evidence_ids", [])})
    biases = {row.get("bias") for row in structures if row.get("bias") not in {"unknown", "neutral"}}
    states = {row.get("state") for row in structures if row.get("state") != "unknown"}
    if not structures or not states:
        state, bias, text = "unknown", "unknown", "结构：不可用。"
    elif len(biases) > 1:
        state, bias, text = "mixed", "mixed", "结构：不同周期存在分歧，需要等待确认。"
    elif len(structures) == 1:
        state, bias, text = structures[0]["state"], structures[0]["bias"], structures[0]["text"]
    elif len(states) == 1:
        state, bias = next(iter(states)), next(iter(biases), "neutral")
        text = f"结构：各周期均显示{ {'continuation': '趋势延续', 'weakening': '趋势减弱', 'reversal': '趋势反转', 'range': '区间震荡'}.get(state, '方向不明')}，方向{ {'bullish': '偏多', 'bearish': '偏空', 'neutral': '中性'}.get(bias, '不明')}。"
    else:
        state, bias, text = "mixed", "mixed", "结构：不同周期状态不完全一致，需要等待确认。"
    structure = {"state": state, "bias": bias, "evidence_ids": evidence_ids, "timeframes": structure_by_timeframe, "text": text}
    return {"schema_version": SCHEMA_VERSION, "position": position, "structure": structure}
