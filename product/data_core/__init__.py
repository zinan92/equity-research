"""Canonical, point-in-time data foundation for the research product."""

from .contracts import (
    CONTRACT_VERSION,
    RECORD_SCHEMAS,
    Provenance,
    RawCapture,
    RecordDomain,
    RecordEnvelope,
    RecordSchema,
    RecordStatus,
    SourceManifest,
    contract_descriptor,
    validate_adapter_output,
)
from .authority_sink import AuthoritySinkError, ObjectStore, SupabaseAuthoritySink
from .ingestion import (
    AdapterContractError,
    AdapterRegistry,
    AuthoritySink,
    BatchQuality,
    FetchedPayload,
    FetchCache,
    FetchRequest,
    IngestionAttempt,
    IngestionOutcome,
    IngestionRuntime,
    QualityPolicy,
    SourceAdapter,
    SourceChoice,
    ValidatedFetch,
    build_raw_capture,
    evaluate_records,
    validate_fetched_payload,
)
from .local_cache import SQLiteFetchCache
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
from .storage_layout import RAW_BUCKET, StorageObjectKey, raw_storage_key

__all__ = [
    "CanonicalComponent", "CanonicalPublicationError", "CanonicalResearchRefresh",
    "canonical_active_report", "canonical_active_summary",
    "CollectedBundle", "DataFoundation", "InjectedInterruption",
    "FileBundleFallbackAdapter", "LegacyCollectorAdapter", "QualityGateError", "RefreshInProgressError", "SnapshotReader",
    "CONTRACT_VERSION", "RECORD_SCHEMAS", "Provenance", "RawCapture",
    "RecordDomain", "RecordEnvelope", "RecordSchema", "RecordStatus",
    "SourceManifest", "contract_descriptor", "validate_adapter_output",
    "RAW_BUCKET", "StorageObjectKey", "raw_storage_key",
    "AdapterContractError", "AdapterRegistry", "AuthoritySink", "AuthoritySinkError",
    "BatchQuality", "FetchedPayload", "FetchCache", "FetchRequest", "IngestionAttempt",
    "IngestionOutcome", "IngestionRuntime", "ObjectStore", "QualityPolicy", "SourceAdapter",
    "SourceChoice", "SQLiteFetchCache", "SupabaseAuthoritySink", "ValidatedFetch",
    "build_raw_capture", "evaluate_records", "validate_fetched_payload",
]
