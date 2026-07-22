# Evidence Set, Conflict & Coverage Gate v1

## User outcome

A report can receive research context only when its evidence is complete for the declared policy, existed by the cutoff, is fresh enough, has no unresolved blocking conflict, and is not fixture/sample/lead-only material.

## Position in the stack

The B6 gate sits after A5 snapshots and B1–B5 evidence ingestion, and before the C-series research compiler. It never fetches providers and never writes report prose.

```text
A5 snapshot + B1 filings + B2 sell-side + B3 pages + B4 consensus + B5 events
                                  |
                       EvidenceCandidate.from_record
                                  |
             role / PIT / freshness / conflict / coverage gate
                                  |
                   immutable ResearchContextPack
```

## Role policy

- `primary`: requires canonical or official source authority.
- `independent`: requires subject-independent provenance and cannot use a source family declared subject-controlled by policy.
- `lead`: must remain supplementary-only and is retained in the rejection receipt as `lead_only_not_evidence`; it never enters a Context Pack.

The role is machine-checked against source provenance. A caller cannot promote a supplementary discovery feed to primary simply by changing a label.

## Gate policy

Each versioned policy freezes:

- report cutoff (`as_of`);
- required components and minimum primary/independent/total counts;
- maximum evidence age by role;
- blocking quality flags and conflict severities;
- subject-controlled source families.

The builder rejects future-known, stale, rejected, fixture/mock/sample, role-invalid and lead-only candidates. It then computes component coverage and preserves both required and optional source gaps. Required gaps and blocking conflicts prevent publication; optional gaps stay visible without inventing data.

## Immutable identities

- `policy_hash`: exact quality policy and cutoff.
- `manifest_hash`: ordered accepted evidence plus policy hash.
- `evidence_set_id`: derived from the manifest hash.
- `gate_hash`: accepted IDs, every rejection reason, all conflicts and the complete coverage report.

`verify_evidence_set` rebuilds the set from the original candidates and policies. A publishable `ResearchContextPack` contains only the accepted immutable tuple and a read-only evidence index.

## Deliberately deferred

- Report section schemas and prose generation
- Production Supabase persistence for the new receipt objects
- Per-industry coverage policies and coverage tiers
- UI for evidence browsing and missing-data states
