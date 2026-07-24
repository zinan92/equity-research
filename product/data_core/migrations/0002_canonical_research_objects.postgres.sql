-- canonical-research-object-v1 · extension of A1/A2, not a parallel authority.
begin;

create table if not exists research.object_revisions (
  object_id text not null,
  object_type text not null check (object_type in ('company','sector_position','evidence','catalyst','roadmap','score_snapshot','falsifier','dossier')),
  revision integer not null check (revision > 0),
  state text not null check (state in ('draft','accepted','superseded','blocked')),
  schema_version text not null,
  source_ref text not null,
  known_at timestamptz not null,
  confidence text not null check (confidence in ('high','medium','low','unknown')),
  evidence_refs jsonb not null,
  facts jsonb not null,
  judgments jsonb not null,
  model_version text,
  revision_of text,
  object_hash text not null unique,
  created_at timestamptz not null default now(),
  primary key (object_id, revision)
);

create or replace function research.reject_object_revision_mutation()
returns trigger language plpgsql as $$ begin
  raise exception 'research object revisions are append-only';
end $$;

drop trigger if exists object_revisions_no_update on research.object_revisions;
create trigger object_revisions_no_update before update or delete on research.object_revisions
for each row execute function research.reject_object_revision_mutation();

commit;
