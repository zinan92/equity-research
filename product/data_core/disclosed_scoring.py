"""Deterministic replication of the publicly disclosed scoring formulas.

These functions reproduce disclosed arithmetic only. They neither carry over an
archived company score nor infer the separate research-grade judgement.
"""
from __future__ import annotations

from typing import Any


COMPOSITE_WEIGHTS = {"growth": 0.28, "quality": 0.12, "value": 0.13, "attention": 0.08}
OPPORTUNITY_WEIGHTS = {"growth": 0.45, "quality": 0.20, "value": 0.35}
QUANTIFIABLE_WEIGHT = sum(COMPOSITE_WEIGHTS.values())


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _round_to_archive_integer(value: float) -> int:
    """Use the majority-observed nearest-integer serialization.

    A small residual set includes apparent per-company overrides, including
    inconsistent half-ties. Validation reports those rows instead of changing
    the arithmetic globally to fit them.
    """
    return int(round(value))


def composite_score(*, growth: Any, quality: Any, value: Any, attention: Any) -> int:
    """Normalize four disclosed factors from their 61% weight to a 0–100 score."""
    inputs = {"growth": growth, "quality": quality, "value": value, "attention": attention}
    weighted = sum(COMPOSITE_WEIGHTS[field] * _number(raw, field) for field, raw in inputs.items())
    return _round_to_archive_integer(weighted / QUANTIFIABLE_WEIGHT)


def opportunity_score(*, growth: Any, quality: Any, value: Any) -> int:
    """Compute the disclosed 45/20/35 opportunity score."""
    inputs = {"growth": growth, "quality": quality, "value": value}
    return _round_to_archive_integer(sum(OPPORTUNITY_WEIGHTS[field] * _number(raw, field) for field, raw in inputs.items()))


def peg_grade(peg: Any) -> str | None:
    """Classify PEG according to the disclosed 1 / 2 / 4 thresholds."""
    if peg is None:
        return None
    value = _number(peg, "peg")
    if value < 1:
        return "便宜"
    if value < 2:
        return "合理"
    if value <= 4:
        return "偏贵"
    return "极贵"
