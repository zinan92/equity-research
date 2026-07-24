-- research-object-replay-v1 · binds object revisions to existing A2/A5 lineage.
begin;

alter table research.object_revisions
  add column if not exists raw_hashes jsonb not null default '[]'::jsonb,
  add column if not exists snapshot_id text not null default '';

commit;
