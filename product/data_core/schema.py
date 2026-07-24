from __future__ import annotations

from .contracts import SCHEMA_VERSION


SQLITE_DDL = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS core_schema_versions (
    version TEXT PRIMARY KEY,
    installed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_source_registry (
    source_key TEXT PRIMARY KEY,
    domain_scope TEXT NOT NULL,
    authority_tier TEXT NOT NULL CHECK(authority_tier IN ('canonical','official','supplementary_only')),
    provider_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    license_status TEXT NOT NULL,
    source_url TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0,1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_source_manifest_versions (
    manifest_hash TEXT PRIMARY KEY,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    provider_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    license_status TEXT NOT NULL,
    source_url TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE(source_key, manifest_hash)
);

CREATE TABLE IF NOT EXISTS core_instruments (
    instrument_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    exchange TEXT NOT NULL CHECK(exchange IN ('SSE','SZSE','BSE')),
    board TEXT NOT NULL,
    name TEXT NOT NULL,
    industry TEXT NOT NULL,
    listed_at TEXT NOT NULL,
    delisted_at TEXT,
    currency TEXT NOT NULL DEFAULT 'CNY',
    lot_size INTEGER NOT NULL DEFAULT 100,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    known_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash)
);

CREATE TABLE IF NOT EXISTS core_trading_calendar (
    exchange TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    is_open INTEGER NOT NULL CHECK(is_open IN (0,1)),
    previous_open_date TEXT,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    known_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    PRIMARY KEY(exchange, trade_date)
);

CREATE TABLE IF NOT EXISTS core_ingestion_runs (
    run_id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    source_manifest_hash TEXT NOT NULL REFERENCES core_source_manifest_versions(manifest_hash),
    data_kind TEXT NOT NULL CHECK(data_kind IN ('fixture','cached','real')),
    idempotency_key TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt > 0),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','success','degraded','failed')),
    fetched_count INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    UNIQUE(idempotency_key, attempt)
);

CREATE TABLE IF NOT EXISTS core_raw_objects (
    raw_hash TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    source_manifest_hash TEXT NOT NULL REFERENCES core_source_manifest_versions(manifest_hash),
    object_kind TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    known_at TEXT NOT NULL,
    http_status INTEGER,
    payload_size INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    provider_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    license_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_source_observations (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    source_manifest_hash TEXT NOT NULL REFERENCES core_source_manifest_versions(manifest_hash),
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    canonical_hash TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    status TEXT NOT NULL CHECK(status IN ('accepted','rejected')),
    created_at TEXT NOT NULL,
    UNIQUE(run_id, entity_type, entity_key)
);

CREATE TABLE IF NOT EXISTS core_instrument_status (
    instrument_id TEXT NOT NULL REFERENCES core_instruments(instrument_id),
    trade_date TEXT NOT NULL,
    trading_status TEXT NOT NULL CHECK(trading_status IN ('normal','suspended','delisted','limit_up','limit_down')),
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    known_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    PRIMARY KEY(instrument_id, trade_date)
);

CREATE TABLE IF NOT EXISTS core_corporate_actions (
    action_id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES core_instruments(instrument_id),
    action_type TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    announced_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    details_json TEXT NOT NULL,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    known_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    UNIQUE(instrument_id, action_type, ex_date, version)
);

CREATE TABLE IF NOT EXISTS core_adjustment_factors (
    instrument_id TEXT NOT NULL REFERENCES core_instruments(instrument_id),
    trade_date TEXT NOT NULL,
    factor REAL NOT NULL CHECK(factor > 0),
    version INTEGER NOT NULL,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    known_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    PRIMARY KEY(instrument_id, trade_date, version)
);

CREATE TABLE IF NOT EXISTS core_daily_bars (
    instrument_id TEXT NOT NULL REFERENCES core_instruments(instrument_id),
    trade_date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL CHECK(volume >= 0),
    amount REAL NOT NULL CHECK(amount >= 0),
    adjustment_version INTEGER NOT NULL,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    known_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    quality_status TEXT NOT NULL CHECK(quality_status IN ('accepted','degraded','rejected')),
    PRIMARY KEY(instrument_id, trade_date, adjustment_version)
);

CREATE TABLE IF NOT EXISTS core_financial_facts (
    fact_id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL REFERENCES core_instruments(instrument_id),
    report_date TEXT NOT NULL,
    announced_at TEXT NOT NULL,
    revision INTEGER NOT NULL,
    metric_key TEXT NOT NULL,
    metric_value REAL,
    unit TEXT NOT NULL,
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    known_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    quality_status TEXT NOT NULL CHECK(quality_status IN ('accepted','degraded','rejected')),
    UNIQUE(instrument_id, report_date, revision, metric_key)
);

CREATE TABLE IF NOT EXISTS core_intelligence_items (
    item_id TEXT PRIMARY KEY,
    instrument_id TEXT REFERENCES core_instruments(instrument_id),
    title TEXT NOT NULL,
    published_at TEXT,
    known_at TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    inference_json TEXT,
    is_llm_inferred INTEGER NOT NULL DEFAULT 0 CHECK(is_llm_inferred IN (0,1)),
    source_key TEXT NOT NULL REFERENCES core_source_registry(source_key),
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    raw_hash TEXT NOT NULL REFERENCES core_raw_objects(raw_hash),
    quality_status TEXT NOT NULL CHECK(quality_status IN ('accepted','degraded','rejected'))
);

CREATE TABLE IF NOT EXISTS core_research_object_revisions (
    object_id TEXT NOT NULL,
    object_type TEXT NOT NULL CHECK(object_type IN ('thesis','company','sector_position','evidence','catalyst','roadmap','score_snapshot','falsifier','dossier')),
    revision INTEGER NOT NULL CHECK(revision > 0),
    state TEXT NOT NULL CHECK(state IN ('draft','accepted','superseded','blocked')),
    schema_version TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    known_at TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK(confidence IN ('high','medium','low','unknown')),
    evidence_refs_json TEXT NOT NULL,
    raw_hashes_json TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    judgments_json TEXT NOT NULL,
    model_version TEXT,
    revision_of TEXT,
    object_hash TEXT NOT NULL UNIQUE,
    PRIMARY KEY(object_id, revision)
);

CREATE TABLE IF NOT EXISTS core_research_object_receipts (
    receipt_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    object_hash TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    raw_hashes_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('accepted','blocked')),
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(object_id, revision, object_hash)
);

CREATE TABLE IF NOT EXISTS core_quality_results (
    quality_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES core_ingestion_runs(run_id),
    check_key TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('passed','warning','blocked')),
    detail TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    UNIQUE(evaluation_id, check_key)
);

CREATE TABLE IF NOT EXISTS core_snapshot_manifests (
    snapshot_id TEXT PRIMARY KEY,
    snapshot_kind TEXT NOT NULL CHECK(snapshot_kind IN ('fixture','cached','real')),
    as_of TEXT NOT NULL,
    known_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dependency_lock_hash TEXT NOT NULL,
    random_seed INTEGER NOT NULL,
    quality_status TEXT NOT NULL CHECK(quality_status IN ('passed','blocked')),
    quality_evaluation_id TEXT NOT NULL,
    quality_digest TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_snapshot_items (
    snapshot_id TEXT NOT NULL REFERENCES core_snapshot_manifests(snapshot_id),
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    row_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, table_name, row_key)
);

CREATE TRIGGER IF NOT EXISTS core_snapshots_no_update
BEFORE UPDATE ON core_snapshot_manifests BEGIN SELECT RAISE(ABORT, 'core snapshots are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_snapshots_no_delete
BEFORE DELETE ON core_snapshot_manifests BEGIN SELECT RAISE(ABORT, 'core snapshots are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_snapshot_items_no_update
BEFORE UPDATE ON core_snapshot_items BEGIN SELECT RAISE(ABORT, 'core snapshot items are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_snapshot_items_no_delete
BEFORE DELETE ON core_snapshot_items BEGIN SELECT RAISE(ABORT, 'core snapshot items are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_quality_results_no_update
BEFORE UPDATE ON core_quality_results BEGIN SELECT RAISE(ABORT, 'core quality results are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_quality_results_no_delete
BEFORE DELETE ON core_quality_results BEGIN SELECT RAISE(ABORT, 'core quality results are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_source_registry_no_update
BEFORE UPDATE ON core_source_registry BEGIN SELECT RAISE(ABORT, 'source registry is append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_source_registry_no_delete
BEFORE DELETE ON core_source_registry BEGIN SELECT RAISE(ABORT, 'source registry is append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_source_manifest_versions_no_update
BEFORE UPDATE ON core_source_manifest_versions BEGIN SELECT RAISE(ABORT, 'source manifests are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_source_manifest_versions_no_delete
BEFORE DELETE ON core_source_manifest_versions BEGIN SELECT RAISE(ABORT, 'source manifests are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_raw_objects_no_update
BEFORE UPDATE ON core_raw_objects BEGIN SELECT RAISE(ABORT, 'raw objects are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_raw_objects_no_delete
BEFORE DELETE ON core_raw_objects BEGIN SELECT RAISE(ABORT, 'raw objects are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_source_observations_no_update
BEFORE UPDATE ON core_source_observations BEGIN SELECT RAISE(ABORT, 'source observations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_source_observations_no_delete
BEFORE DELETE ON core_source_observations BEGIN SELECT RAISE(ABORT, 'source observations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_research_object_revisions_no_update
BEFORE UPDATE ON core_research_object_revisions BEGIN SELECT RAISE(ABORT, 'research object revisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_research_object_revisions_no_delete
BEFORE DELETE ON core_research_object_revisions BEGIN SELECT RAISE(ABORT, 'research object revisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_research_object_receipts_no_update
BEFORE UPDATE ON core_research_object_receipts BEGIN SELECT RAISE(ABORT, 'research object receipts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_research_object_receipts_no_delete
BEFORE DELETE ON core_research_object_receipts BEGIN SELECT RAISE(ABORT, 'research object receipts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_ingestion_runs_no_delete
BEFORE DELETE ON core_ingestion_runs BEGIN SELECT RAISE(ABORT, 'ingestion runs cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS core_ingestion_runs_terminal_no_update
BEFORE UPDATE ON core_ingestion_runs
WHEN OLD.status != 'running'
  OR NEW.run_id != OLD.run_id
  OR NEW.source_key != OLD.source_key
  OR NEW.source_manifest_hash != OLD.source_manifest_hash
  OR NEW.data_kind != OLD.data_kind
  OR NEW.idempotency_key != OLD.idempotency_key
  OR NEW.attempt != OLD.attempt
  OR NEW.started_at != OLD.started_at
  OR NEW.status NOT IN ('success','degraded','failed')
BEGIN SELECT RAISE(ABORT, 'only running to terminal ingestion transition is allowed'); END;
"""


CORE_TABLES = (
    "core_schema_versions", "core_source_registry", "core_source_manifest_versions",
    "core_ingestion_runs", "core_raw_objects", "core_source_observations",
    "core_instruments", "core_trading_calendar", "core_instrument_status", "core_corporate_actions",
    "core_adjustment_factors", "core_daily_bars", "core_financial_facts", "core_intelligence_items", "core_research_object_revisions", "core_research_object_receipts",
    "core_quality_results", "core_snapshot_manifests", "core_snapshot_items",
)


def schema_version_row(installed_at: str) -> tuple[str, str]:
    return SCHEMA_VERSION, installed_at
