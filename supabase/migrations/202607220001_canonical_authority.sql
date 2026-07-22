-- canonical-authority-v1 · Supabase PostgreSQL 15+
-- Supabase supplies auth/storage schemas and anon/authenticated/service_role roles.
begin;

create schema if not exists market;
create schema if not exists research;
create schema if not exists control;

create table if not exists control.schema_versions (
  version text primary key,
  installed_at timestamptz not null default now()
);

create table if not exists control.source_manifests (
  manifest_hash text primary key check (manifest_hash ~ '^[0-9a-f]{64}$'),
  source_key text not null,
  domain_scope text[] not null check (
    cardinality(domain_scope) > 0
    and domain_scope <@ array['market','fundamental','document','estimate','event']::text[]
  ),
  authority_tier text not null check (authority_tier in ('canonical','official','supplementary_only')),
  provider_version text not null,
  provider_schema_version text not null,
  license_status text not null,
  source_url text not null,
  quality_flags text[] not null default '{}',
  active boolean not null,
  created_at timestamptz not null default now(),
  check (not active or source_url ~ '^https?://[^[:space:]]+$'),
  unique (source_key, manifest_hash)
);

create table if not exists control.ingestion_runs (
  run_id text primary key,
  manifest_hash text not null references control.source_manifests(manifest_hash),
  idempotency_key text not null,
  attempt integer not null check (attempt > 0),
  data_kind text not null check (data_kind in ('fixture','cached','real')),
  status text not null check (status in ('running','success','degraded','failed')),
  started_at timestamptz not null,
  finished_at timestamptz,
  fetched_count integer not null default 0 check (fetched_count >= 0),
  accepted_count integer not null default 0 check (accepted_count >= 0),
  error_summary text,
  unique (idempotency_key, attempt),
  unique (run_id, manifest_hash)
);

create table if not exists control.raw_objects (
  raw_hash text primary key check (raw_hash ~ '^[0-9a-f]{64}$'),
  storage_bucket text not null check (storage_bucket = 'canonical-raw'),
  storage_path text not null check (
    storage_path ~ '^raw/sha256/[0-9a-f]{2}/[0-9a-f]{64}$'
  ),
  payload_size bigint not null check (payload_size >= 0),
  created_at timestamptz not null default now(),
  unique (storage_bucket, storage_path),
  check (
    storage_path = 'raw/sha256/' || substring(raw_hash from 1 for 2) || '/' || raw_hash
  )
);

create table if not exists control.raw_captures (
  capture_id text primary key,
  raw_hash text not null references control.raw_objects(raw_hash),
  run_id text not null,
  manifest_hash text not null,
  source_url text not null check (source_url ~ '^https?://[^[:space:]]+$'),
  mime_type text not null check (mime_type in ('application/json','text/html','application/pdf')),
  fetched_at timestamptz not null,
  known_at timestamptz not null,
  http_status integer,
  created_at timestamptz not null default now(),
  unique (capture_id, raw_hash, run_id, manifest_hash, known_at),
  foreign key (run_id, manifest_hash)
    references control.ingestion_runs(run_id, manifest_hash)
);

create table if not exists control.record_receipts (
  record_hash text primary key check (record_hash ~ '^[0-9a-f]{64}$'),
  contract_version text not null check (contract_version = 'canonical-data-contract-v1'),
  capture_id text not null,
  run_id text not null,
  raw_hash text not null,
  manifest_hash text not null,
  domain text not null check (domain in ('market','fundamental','document','estimate','event')),
  record_schema_version text not null,
  entity_key text not null,
  payload_json jsonb not null check (jsonb_typeof(payload_json) = 'object'),
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  known_at timestamptz not null,
  status text not null check (status in ('accepted','rejected')),
  quality_flags text[] not null default '{}',
  rejection_reason text,
  violations text[] not null default '{}',
  created_at timestamptz not null default now(),
  check (
    (status = 'accepted' and rejection_reason is null and cardinality(violations) = 0)
    or
    (status = 'rejected' and length(trim(rejection_reason)) > 0 and cardinality(violations) > 0)
  ),
  unique (run_id, domain, entity_key),
  foreign key (capture_id, raw_hash, run_id, manifest_hash, known_at)
    references control.raw_captures(capture_id, raw_hash, run_id, manifest_hash, known_at)
);

create table if not exists market.market_records (
  record_hash text primary key references control.record_receipts(record_hash),
  instrument_id text not null,
  observed_at timestamptz not null,
  metric text not null,
  value numeric not null,
  unit text not null,
  known_at timestamptz not null,
  check (observed_at <= known_at)
);

create table if not exists market.fundamental_records (
  record_hash text primary key references control.record_receipts(record_hash),
  instrument_id text not null,
  report_period date not null,
  announced_at timestamptz not null,
  metric text not null,
  value numeric not null,
  unit text not null,
  known_at timestamptz not null,
  check (announced_at <= known_at)
);

create table if not exists research.documents (
  record_hash text primary key references control.record_receipts(record_hash),
  document_id text not null unique,
  instrument_id text not null,
  document_type text not null,
  published_at timestamptz not null,
  content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
  storage_bucket text not null check (storage_bucket = 'canonical-raw'),
  storage_path text not null,
  known_at timestamptz not null,
  check (published_at <= known_at),
  foreign key (storage_bucket, storage_path)
    references control.raw_objects(storage_bucket, storage_path)
);

create table if not exists research.estimates (
  record_hash text primary key references control.record_receipts(record_hash),
  estimate_id text not null unique,
  instrument_id text not null,
  broker text not null,
  published_at timestamptz not null,
  fiscal_period date not null,
  metric text not null,
  value numeric not null,
  unit text not null,
  known_at timestamptz not null,
  check (published_at <= known_at)
);

create table if not exists research.events (
  record_hash text primary key references control.record_receipts(record_hash),
  event_id text not null unique,
  instrument_id text not null,
  event_type text not null,
  occurred_at timestamptz not null,
  title text not null,
  evidence_ids text[] not null check (cardinality(evidence_ids) > 0),
  known_at timestamptz not null,
  check (occurred_at <= known_at)
);

create table if not exists control.dataset_snapshots (
  snapshot_id text primary key,
  as_of date not null,
  known_at timestamptz not null,
  contract_version text not null,
  manifest jsonb not null,
  manifest_hash text not null unique check (manifest_hash ~ '^[0-9a-f]{64}$'),
  quality_status text not null check (quality_status in ('passed','blocked')),
  created_at timestamptz not null default now()
);

create table if not exists control.dataset_snapshot_records (
  snapshot_id text not null references control.dataset_snapshots(snapshot_id),
  record_hash text not null references control.record_receipts(record_hash),
  primary key (snapshot_id, record_hash)
);

create or replace function control.validate_record_receipt()
returns trigger language plpgsql as $$
declare
  manifest control.source_manifests%rowtype;
  expected_schema text;
begin
  select * into strict manifest
  from control.source_manifests
  where manifest_hash = new.manifest_hash;

  if not (new.domain = any(manifest.domain_scope)) then
    raise exception 'receipt domain % is outside source manifest scope', new.domain;
  end if;
  if new.status = 'accepted' and not manifest.active then
    raise exception 'accepted receipt requires an active source manifest';
  end if;

  expected_schema := case new.domain
    when 'market' then 'market-record-v1'
    when 'fundamental' then 'fundamental-record-v1'
    when 'document' then 'document-record-v1'
    when 'estimate' then 'estimate-record-v1'
    when 'event' then 'event-record-v1'
  end;
  if new.record_schema_version <> expected_schema then
    raise exception 'record schema % does not match domain %', new.record_schema_version, new.domain;
  end if;
  return new;
end
$$;

drop trigger if exists record_receipts_validate_contract on control.record_receipts;
create trigger record_receipts_validate_contract before insert on control.record_receipts
for each row execute function control.validate_record_receipt();

create or replace function control.require_accepted_receipt()
returns trigger language plpgsql as $$
declare
  receipt control.record_receipts%rowtype;
  row_data jsonb := to_jsonb(new);
  payload jsonb;
begin
  select * into receipt from control.record_receipts
  where record_hash = new.record_hash
    and status = 'accepted'
    and domain = tg_argv[0];
  if not found then
    raise exception 'canonical row requires an accepted receipt in domain %', tg_argv[0];
  end if;
  if receipt.known_at <> (row_data->>'known_at')::timestamptz then
    raise exception 'canonical row known_at differs from accepted receipt';
  end if;
  payload := receipt.payload_json;
  if tg_argv[0] = 'market' and ((
    payload->>'instrument_id' = row_data->>'instrument_id'
    and (payload->>'observed_at')::timestamptz = (row_data->>'observed_at')::timestamptz
    and payload->>'metric' = row_data->>'metric'
    and (payload->>'value')::numeric = (row_data->>'value')::numeric
    and payload->>'unit' = row_data->>'unit'
  ) is not true) then raise exception 'canonical market row differs from accepted payload';
  elsif tg_argv[0] = 'fundamental' and ((
    payload->>'instrument_id' = row_data->>'instrument_id'
    and (payload->>'report_period')::date = (row_data->>'report_period')::date
    and (payload->>'announced_at')::timestamptz = (row_data->>'announced_at')::timestamptz
    and payload->>'metric' = row_data->>'metric'
    and (payload->>'value')::numeric = (row_data->>'value')::numeric
    and payload->>'unit' = row_data->>'unit'
  ) is not true) then raise exception 'canonical fundamental row differs from accepted payload';
  elsif tg_argv[0] = 'document' and ((
    payload->>'document_id' = row_data->>'document_id'
    and payload->>'instrument_id' = row_data->>'instrument_id'
    and payload->>'document_type' = row_data->>'document_type'
    and (payload->>'published_at')::timestamptz = (row_data->>'published_at')::timestamptz
    and payload->>'content_hash' = row_data->>'content_hash'
    and payload->>'storage_uri' = (row_data->>'storage_bucket') || '/' || (row_data->>'storage_path')
  ) is not true) then raise exception 'canonical document row differs from accepted payload';
  elsif tg_argv[0] = 'estimate' and ((
    payload->>'estimate_id' = row_data->>'estimate_id'
    and payload->>'instrument_id' = row_data->>'instrument_id'
    and payload->>'broker' = row_data->>'broker'
    and (payload->>'published_at')::timestamptz = (row_data->>'published_at')::timestamptz
    and (payload->>'fiscal_period')::date = (row_data->>'fiscal_period')::date
    and payload->>'metric' = row_data->>'metric'
    and (payload->>'value')::numeric = (row_data->>'value')::numeric
    and payload->>'unit' = row_data->>'unit'
  ) is not true) then raise exception 'canonical estimate row differs from accepted payload';
  elsif tg_argv[0] = 'event' and ((
    payload->>'event_id' = row_data->>'event_id'
    and payload->>'instrument_id' = row_data->>'instrument_id'
    and payload->>'event_type' = row_data->>'event_type'
    and (payload->>'occurred_at')::timestamptz = (row_data->>'occurred_at')::timestamptz
    and payload->>'title' = row_data->>'title'
    and payload->'evidence_ids' = row_data->'evidence_ids'
  ) is not true) then raise exception 'canonical event row differs from accepted payload';
  end if;
  return new;
end
$$;

drop trigger if exists market_records_require_receipt on market.market_records;
create trigger market_records_require_receipt before insert or update on market.market_records
for each row execute function control.require_accepted_receipt('market');
drop trigger if exists fundamental_records_require_receipt on market.fundamental_records;
create trigger fundamental_records_require_receipt before insert or update on market.fundamental_records
for each row execute function control.require_accepted_receipt('fundamental');
drop trigger if exists documents_require_receipt on research.documents;
create trigger documents_require_receipt before insert or update on research.documents
for each row execute function control.require_accepted_receipt('document');
drop trigger if exists estimates_require_receipt on research.estimates;
create trigger estimates_require_receipt before insert or update on research.estimates
for each row execute function control.require_accepted_receipt('estimate');
drop trigger if exists events_require_receipt on research.events;
create trigger events_require_receipt before insert or update on research.events
for each row execute function control.require_accepted_receipt('event');

create or replace function control.reject_immutable_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'canonical authority records are append-only';
end
$$;

drop trigger if exists source_manifests_immutable on control.source_manifests;
create trigger source_manifests_immutable before update or delete on control.source_manifests
for each row execute function control.reject_immutable_mutation();
drop trigger if exists raw_objects_immutable on control.raw_objects;
create trigger raw_objects_immutable before update or delete on control.raw_objects
for each row execute function control.reject_immutable_mutation();
drop trigger if exists raw_captures_immutable on control.raw_captures;
create trigger raw_captures_immutable before update or delete on control.raw_captures
for each row execute function control.reject_immutable_mutation();
drop trigger if exists record_receipts_immutable on control.record_receipts;
create trigger record_receipts_immutable before update or delete on control.record_receipts
for each row execute function control.reject_immutable_mutation();
drop trigger if exists dataset_snapshots_immutable on control.dataset_snapshots;
create trigger dataset_snapshots_immutable before update or delete on control.dataset_snapshots
for each row execute function control.reject_immutable_mutation();
drop trigger if exists dataset_snapshot_records_immutable on control.dataset_snapshot_records;
create trigger dataset_snapshot_records_immutable before update or delete on control.dataset_snapshot_records
for each row execute function control.reject_immutable_mutation();
drop trigger if exists market_records_immutable on market.market_records;
create trigger market_records_immutable before update or delete on market.market_records
for each row execute function control.reject_immutable_mutation();
drop trigger if exists fundamental_records_immutable on market.fundamental_records;
create trigger fundamental_records_immutable before update or delete on market.fundamental_records
for each row execute function control.reject_immutable_mutation();
drop trigger if exists documents_immutable on research.documents;
create trigger documents_immutable before update or delete on research.documents
for each row execute function control.reject_immutable_mutation();
drop trigger if exists estimates_immutable on research.estimates;
create trigger estimates_immutable before update or delete on research.estimates
for each row execute function control.reject_immutable_mutation();
drop trigger if exists events_immutable on research.events;
create trigger events_immutable before update or delete on research.events
for each row execute function control.reject_immutable_mutation();

alter table control.schema_versions enable row level security;
alter table control.source_manifests enable row level security;
alter table control.ingestion_runs enable row level security;
alter table control.raw_objects enable row level security;
alter table control.raw_captures enable row level security;
alter table control.record_receipts enable row level security;
alter table control.dataset_snapshots enable row level security;
alter table control.dataset_snapshot_records enable row level security;
alter table market.market_records enable row level security;
alter table market.fundamental_records enable row level security;
alter table research.documents enable row level security;
alter table research.estimates enable row level security;
alter table research.events enable row level security;

revoke all on schema market, research, control from anon, authenticated;
revoke all on all tables in schema market, research, control from anon, authenticated;
revoke all on all sequences in schema market, research, control from anon, authenticated;
grant usage on schema market, research, control to service_role;
grant all on all tables in schema market, research, control to service_role;
grant all on all sequences in schema market, research, control to service_role;

alter default privileges in schema market revoke all on tables from anon, authenticated;
alter default privileges in schema research revoke all on tables from anon, authenticated;
alter default privileges in schema control revoke all on tables from anon, authenticated;
alter default privileges in schema market grant all on tables to service_role;
alter default privileges in schema research grant all on tables to service_role;
alter default privileges in schema control grant all on tables to service_role;

insert into control.schema_versions(version)
values ('canonical-authority-v1')
on conflict (version) do nothing;

commit;
