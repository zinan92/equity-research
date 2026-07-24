# Canonical Research Objects v1

E1-S2 extends the existing A1/A2 authority path; it does not create a second
company master, source registry, raw store, or ingestion framework.

## Object contract

The eight versioned objects are `Company`, `SectorPosition`, `Evidence`,
`Catalyst`, `Roadmap`, `ScoreSnapshot`, `Falsifier`, and `Dossier`. Each
revision carries a namespaced ID, positive revision number, fixed state,
schema version, `source_ref`, `known_at`, confidence, one or more evidence
references, fact payload, judgment payload, optional model version, prior
revision hash, and deterministic object hash.

`facts` contain only declared fields for the object type and always point to
evidence identities. `judgments` are a separate payload and require a
`model_version`; they cannot be read as sourced facts. Source bytes, raw hash,
document page and provider metadata remain in A1/A2 evidence contracts and are
referenced rather than copied here.

## A2/A5 replay binding

Every stored revision now carries one or more A2 `raw_hashes` and an A5
accepted `snapshot_id`. The writer rejects unknown raw identities, blocked or
unknown snapshots, and raw identities not frozen by that snapshot. The replay
receipt recomputes every object hash, walks the immediate `revision_of` chain,
rechecks raw/snapshot membership, and emits only identities and conflicts—never
source prose.

## Persistence and revision rule

SQLite acceptance uses `core_research_object_revisions`; Supabase/Postgres uses
`research.object_revisions` in migration `0002`. Both are append-only. A first
revision must be `1`; every later revision must be consecutive and bind the
immediately preceding object hash through `revision_of`.

This story defines storage contracts only. Canonical write adapters arrive in
E1-S4, and production API reads arrive in E1-S5.
