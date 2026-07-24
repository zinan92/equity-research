-- Extend the existing append-only research object contract; no second store.
begin;

alter table research.object_revisions
  drop constraint if exists object_revisions_object_type_check;
alter table research.object_revisions
  add constraint object_revisions_object_type_check
  check (object_type in ('thesis','company','sector_position','evidence','catalyst','roadmap','score_snapshot','falsifier','dossier'));

commit;
