"""Canonical, point-in-time data foundation for the research product."""

from .contracts import SourceManifest
from .research_refresh import (
    CanonicalComponent,
    CanonicalResearchRefresh,
    CanonicalPublicationError,
    canonical_active_report,
    canonical_active_summary,
    CollectedBundle,
    FileBundleFallbackAdapter,
    InjectedInterruption,
    LegacyCollectorAdapter,
    RefreshInProgressError,
)
from .store import DataFoundation, QualityGateError, SnapshotReader

__all__ = [
    "CanonicalComponent", "CanonicalPublicationError", "CanonicalResearchRefresh",
    "canonical_active_report", "canonical_active_summary",
    "CollectedBundle", "DataFoundation", "InjectedInterruption",
    "FileBundleFallbackAdapter", "LegacyCollectorAdapter", "QualityGateError", "RefreshInProgressError", "SnapshotReader",
    "SourceManifest",
]
