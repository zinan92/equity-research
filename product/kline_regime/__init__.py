"""Deterministic, research-only K-line regime contract v1."""

from .contract import (
    CONTRACT_VERSION,
    MIN_BARS_4H,
    MIN_BARS_1D,
    build_regime,
    validate_contract,
)

__all__ = [
    "CONTRACT_VERSION",
    "MIN_BARS_4H",
    "MIN_BARS_1D",
    "build_regime",
    "validate_contract",
]
