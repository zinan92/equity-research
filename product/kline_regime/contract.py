"""The kline-regime-v1 schema and deterministic calculation.

This module deliberately has no product runtime, broker, strategy, risk, or
control imports.  It consumes already-closed OHLC bars and returns a
research-only artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_VERSION = "kline-regime-v1"
MIN_BARS_1D = 20
MIN_BARS_4H = 30


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(daily: Sequence[Mapping[str, Any]], four_hour: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(_canonical({"1d": list(daily), "4h": list(four_hour)})).hexdigest()


def _is_forming(bar: Mapping[str, Any]) -> bool:
    flags = {str(flag).lower() for flag in bar.get("quality_flags", [])}
    return bool(
        bar.get("is_forming") is True
        or bar.get("forming") is True
        or str(bar.get("status", "")).lower() in {"forming", "open"}
        or "forming" in flags
    )


def _number(bar: Mapping[str, Any], key: str) -> float:
    value = float(bar[key])
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"invalid {key}")
    return value


def _slope_score(bars: Sequence[Mapping[str, Any]]) -> float:
    closes = [_number(bar, "close") for bar in bars]
    logs = [math.log(value) for value in closes]
    x_mean = (len(logs) - 1) / 2
    numerator = sum((index - x_mean) * (value - sum(logs) / len(logs)) for index, value in enumerate(logs))
    denominator = sum((index - x_mean) ** 2 for index in range(len(logs)))
    slope = numerator / denominator

    true_ranges = []
    previous_close = None
    for bar in bars:
        high = _number(bar, "high")
        low = _number(bar, "low")
        close = _number(bar, "close")
        if low > high:
            raise ValueError("low exceeds high")
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)) if previous_close is not None else high - low)
        previous_close = close
    atr_window = true_ranges[-14:]
    atr = sum(atr_window) / len(atr_window)
    average_close = sum(closes[-14:]) / min(14, len(closes))
    atr_pct = atr / average_close
    return slope * len(logs) / max(atr_pct, 1e-12)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _unavailable(asset: str, reason: str, digest: str, as_of: str | None = None) -> dict[str, Any]:
    return {
        "regime": "unavailable",
        "range_low": None,
        "range_high": None,
        "confidence": 0.0,
        "as_of": as_of,
        "inputs_digest": digest,
        "action_eligible": False,
        "version": CONTRACT_VERSION,
        "reason": reason,
        "asset": asset,
    }


def build_regime(asset: str, daily: Sequence[Mapping[str, Any]], four_hour: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a byte-stable regime result from two closed bar series."""
    digest = _digest(daily, four_hour)
    if len(daily) < MIN_BARS_1D or len(four_hour) < MIN_BARS_4H:
        return _unavailable(asset, f"insufficient bars: need {MIN_BARS_1D} 1d and {MIN_BARS_4H} 4h", digest)
    if any(_is_forming(bar) for bar in [*daily, *four_hour]):
        return _unavailable(asset, "forming bar present", digest)
    try:
        daily_used = list(daily[-MIN_BARS_1D:])
        four_hour_used = list(four_hour[-MIN_BARS_4H:])
        score = 0.7 * _slope_score(daily_used) + 0.3 * _slope_score(four_hour_used)
        highs = [_number(bar, "high") for bar in daily_used]
        lows = [_number(bar, "low") for bar in daily_used]
        range_low = _percentile(lows, 0.2)
        range_high = _percentile(highs, 0.8)
        if score >= 0.35:
            regime = "trend_up"
            confidence = min(1.0, score / 1.5)
        elif score <= -0.35:
            regime = "trend_down"
            confidence = min(1.0, abs(score) / 1.5)
        else:
            regime = "range"
            confidence = min(1.0, 1.0 - abs(score) / 0.35)
        timestamps = [str(bar["timestamp"]) for bar in [*daily_used, *four_hour_used]]
        return {
            "regime": regime,
            "range_low": range_low,
            "range_high": range_high,
            "confidence": round(max(0.0, min(1.0, confidence)), 12),
            "as_of": max(timestamps),
            "inputs_digest": digest,
            "action_eligible": False,
            "version": CONTRACT_VERSION,
            "asset": asset,
        }
    except (KeyError, TypeError, ValueError) as exc:
        return _unavailable(asset, f"invalid bar: {exc}", digest)


def validate_contract(payload: Mapping[str, Any]) -> None:
    """Raise jsonschema.ValidationError when a result violates v1."""
    schema = json.loads((Path(__file__).parent / "kline-regime-v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
