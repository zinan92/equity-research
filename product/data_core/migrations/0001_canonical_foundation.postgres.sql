-- data-foundation-v1 · PostgreSQL 15+ / Supabase compatible
-- SQLite uses core_* prefixes; Postgres uses domain schemas.
begin;

create schema if not exists market;
create schema if not exists research;

create table if not exists market.schema_versions (
  version text primary key,
  installed_at timestamptz not null default now()
);

create table if not exists market.source_registry (
  source_key text primary key,
  domain_scope text not null,
  authority_tier text not null check (authority_tier in ('canonical','official','supplementary_only')),
  provider_version text not null,
  schema_version text not null,
  license_status text not null,
  source_url text not null,
  quality_flags jsonb not null default '[]'::jsonb,
  manifest_hash text not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists market.source_manifest_versions (
  manifest_hash text primary key,
  source_key text not null references market.source_registry(source_key),
  provider_version text not null,
  schema_version text not null,
  license_status text not null,
  source_url text not null,
  quality_flags jsonb not null default '[]'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (source_key, manifest_hash)
);

create table if not exists market.instruments (
  instrument_id text primary key,
  ticker text not null unique,
  exchange text not null check (exchange in ('SSE','SZSE','BSE')),
  board text not null,
  name text not null,
  industry text not null,
  listed_at date not null,
  delisted_at date,
  currency text not null default 'CNY',
  lot_size integer not null default 100,
  source_key text not null references market.source_registry(source_key),
  known_at timestamptz not null,
  raw_hash text not null
);

create table if not exists market.trading_calendar (
  exchange text not null,
  trade_date date not null,
  is_open boolean not null,
  previous_open_date date,
  source_key text not null references market.source_registry(source_key),
  known_at timestamptz not null,
  raw_hash text not null,
  primary key (exchange, trade_date)
);

create table if not exists market.ingestion_runs (
  run_id text primary key,
  source_key text not null references market.source_registry(source_key),
  source_manifest_hash text not null references market.source_manifest_versions(manifest_hash),
  data_kind text not null check (data_kind in ('fixture','cached','real')),
  idempotency_key text not null,
  attempt integer not null check (attempt > 0),
  started_at timestamptz not null,
  finished_at timestamptz,
  status text not null check (status in ('running','success','degraded','failed')),
  fetched_count integer not null default 0,
  accepted_count integer not null default 0,
  error_summary text,
  unique (idempotency_key, attempt)
);

create table if not exists market.raw_objects (
  raw_hash text primary key,
  run_id text not null references market.ingestion_runs(run_id),
  source_key text not null references market.source_registry(source_key),
  source_manifest_hash text not null references market.source_manifest_versions(manifest_hash),
  object_kind text not null,
  storage_uri text not null,
  fetched_at timestamptz not null,
  known_at timestamptz not null,
  http_status integer,
  payload_size bigint not null,
  payload jsonb not null,
  provider_version text not null,
  schema_version text not null,
  license_status text not null
);

create table if not exists market.source_observations (
  observation_id text primary key,
  run_id text not null references market.ingestion_runs(run_id),
  source_key text not null references market.source_registry(source_key),
  source_manifest_hash text not null references market.source_manifest_versions(manifest_hash),
  entity_type text not null,
  entity_key text not null,
  canonical_hash text not null,
  raw_hash text not null references market.raw_objects(raw_hash),
  status text not null check (status in ('accepted','rejected')),
  created_at timestamptz not null default now(),
  unique (run_id, entity_type, entity_key)
);

do $migration$
begin
  if not exists (select 1 from pg_constraint where conname = 'instruments_raw_hash_fkey') then
    alter table market.instruments add constraint instruments_raw_hash_fkey
      foreign key (raw_hash) references market.raw_objects(raw_hash);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'trading_calendar_raw_hash_fkey') then
    alter table market.trading_calendar add constraint trading_calendar_raw_hash_fkey
      foreign key (raw_hash) references market.raw_objects(raw_hash);
  end if;
end
$migration$;

create table if not exists market.instrument_status (
  instrument_id text not null references market.instruments(instrument_id),
  trade_date date not null,
  trading_status text not null check (trading_status in ('normal','suspended','delisted','limit_up','limit_down')),
  source_key text not null references market.source_registry(source_key),
  run_id text not null references market.ingestion_runs(run_id),
  known_at timestamptz not null,
  raw_hash text not null references market.raw_objects(raw_hash),
  primary key (instrument_id, trade_date)
);

create table if not exists market.corporate_actions (
  action_id text primary key,
  instrument_id text not null references market.instruments(instrument_id),
  action_type text not null,
  ex_date date not null,
  announced_at timestamptz not null,
  version integer not null check (version > 0),
  details jsonb not null,
  source_key text not null references market.source_registry(source_key),
  run_id text not null references market.ingestion_runs(run_id),
  known_at timestamptz not null,
  raw_hash text not null references market.raw_objects(raw_hash),
  unique (instrument_id, action_type, ex_date, version)
);

create table if not exists market.adjustment_factors (
  instrument_id text not null references market.instruments(instrument_id),
  trade_date date not null,
  factor numeric not null check (factor > 0),
  version integer not null check (version > 0),
  source_key text not null references market.source_registry(source_key),
  run_id text not null references market.ingestion_runs(run_id),
  known_at timestamptz not null,
  raw_hash text not null references market.raw_objects(raw_hash),
  primary key (instrument_id, trade_date, version)
);

create table if not exists market.daily_bars (
  instrument_id text not null references market.instruments(instrument_id),
  trade_date date not null,
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  volume numeric not null check (volume >= 0),
  amount numeric not null check (amount >= 0),
  adjustment_version integer not null,
  source_key text not null references market.source_registry(source_key),
  run_id text not null references market.ingestion_runs(run_id),
  known_at timestamptz not null,
  raw_hash text not null references market.raw_objects(raw_hash),
  quality_status text not null check (quality_status in ('accepted','degraded','rejected')),
  primary key (instrument_id, trade_date, adjustment_version),
  foreign key (instrument_id, trade_date, adjustment_version)
    references market.adjustment_factors(instrument_id, trade_date, version)
);

create table if not exists market.financial_facts (
  fact_id text primary key,
  instrument_id text not null references market.instruments(instrument_id),
  report_date date not null,
  announced_at timestamptz not null,
  revision integer not null check (revision > 0),
  metric_key text not null,
  metric_value numeric,
  unit text not null,
  source_key text not null references market.source_registry(source_key),
  run_id text not null references market.ingestion_runs(run_id),
  known_at timestamptz not null,
  raw_hash text not null references market.raw_objects(raw_hash),
  quality_status text not null check (quality_status in ('accepted','degraded','rejected')),
  unique (instrument_id, report_date, revision, metric_key),
  check (announced_at <= known_at)
);

create table if not exists market.quality_results (
  quality_id text primary key,
  evaluation_id text not null,
  run_id text not null references market.ingestion_runs(run_id),
  check_key text not null,
  entity_key text not null,
  status text not null check (status in ('passed','warning','blocked')),
  detail text not null,
  checked_at timestamptz not null,
  unique (evaluation_id, check_key)
);

create table if not exists research.intelligence_items (
  item_id text primary key,
  instrument_id text references market.instruments(instrument_id),
  title text not null,
  published_at timestamptz,
  known_at timestamptz not null,
  evidence jsonb not null,
  inference jsonb,
  is_llm_inferred boolean not null default false,
  source_key text not null references market.source_registry(source_key),
  run_id text not null references market.ingestion_runs(run_id),
  raw_hash text not null references market.raw_objects(raw_hash),
  quality_status text not null check (quality_status in ('accepted','degraded','rejected'))
);

create table if not exists research.dataset_snapshots (
  snapshot_id text primary key,
  snapshot_kind text not null check (snapshot_kind in ('fixture','cached','real')),
  as_of date not null,
  known_at timestamptz not null,
  schema_version text not null,
  model_version text not null,
  dependency_lock_hash text not null,
  random_seed bigint not null,
  quality_status text not null check (quality_status in ('passed','blocked')),
  quality_evaluation_id text not null,
  quality_digest text not null,
  manifest jsonb not null,
  manifest_hash text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists research.dataset_snapshot_items (
  snapshot_id text not null references research.dataset_snapshots(snapshot_id),
  table_name text not null,
  row_key text not null,
  row_hash text not null,
  row_json jsonb not null,
  primary key (snapshot_id, table_name, row_key)
);

create or replace function research.reject_snapshot_mutation()
returns trigger language plpgsql as $$ begin
  raise exception 'dataset snapshots are append-only';
end $$;

drop trigger if exists dataset_snapshots_no_update on research.dataset_snapshots;
create trigger dataset_snapshots_no_update before update or delete on research.dataset_snapshots
for each row execute function research.reject_snapshot_mutation();

drop trigger if exists dataset_snapshot_items_no_update on research.dataset_snapshot_items;
create trigger dataset_snapshot_items_no_update before update or delete on research.dataset_snapshot_items
for each row execute function research.reject_snapshot_mutation();

create or replace function market.reject_quality_result_mutation()
returns trigger language plpgsql as $$ begin
  raise exception 'quality results are append-only';
end $$;

drop trigger if exists quality_results_no_update on market.quality_results;
create trigger quality_results_no_update before update or delete on market.quality_results
for each row execute function market.reject_quality_result_mutation();

create or replace function market.reject_provenance_mutation()
returns trigger language plpgsql as $$ begin
  raise exception 'provenance records are append-only';
end $$;

drop trigger if exists source_registry_no_update on market.source_registry;
create trigger source_registry_no_update before update or delete on market.source_registry
for each row execute function market.reject_provenance_mutation();
drop trigger if exists source_manifest_versions_no_update on market.source_manifest_versions;
create trigger source_manifest_versions_no_update before update or delete on market.source_manifest_versions
for each row execute function market.reject_provenance_mutation();
drop trigger if exists raw_objects_no_update on market.raw_objects;
create trigger raw_objects_no_update before update or delete on market.raw_objects
for each row execute function market.reject_provenance_mutation();
drop trigger if exists source_observations_no_update on market.source_observations;
create trigger source_observations_no_update before update or delete on market.source_observations
for each row execute function market.reject_provenance_mutation();

create or replace function market.guard_ingestion_run_transition()
returns trigger language plpgsql as $$ begin
  if old.status <> 'running'
     or new.run_id <> old.run_id
     or new.source_key <> old.source_key
     or new.source_manifest_hash <> old.source_manifest_hash
     or new.data_kind <> old.data_kind
     or new.idempotency_key <> old.idempotency_key
     or new.attempt <> old.attempt
     or new.started_at <> old.started_at
     or new.status not in ('success','degraded','failed') then
    raise exception 'only running to terminal ingestion transition is allowed';
  end if;
  return new;
end $$;

drop trigger if exists ingestion_runs_terminal_no_update on market.ingestion_runs;
create trigger ingestion_runs_terminal_no_update before update on market.ingestion_runs
for each row execute function market.guard_ingestion_run_transition();
drop trigger if exists ingestion_runs_no_delete on market.ingestion_runs;
create trigger ingestion_runs_no_delete before delete on market.ingestion_runs
for each row execute function market.reject_provenance_mutation();

insert into market.schema_versions(version) values ('data-foundation-v1')
on conflict (version) do nothing;

commit;
