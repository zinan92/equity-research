"""Canonical, point-in-time data foundation for the research product."""

from .contracts import SourceManifest
from .store import DataFoundation, QualityGateError, SnapshotReader

__all__ = ["DataFoundation", "QualityGateError", "SnapshotReader", "SourceManifest"]
