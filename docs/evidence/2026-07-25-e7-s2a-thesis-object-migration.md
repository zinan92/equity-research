# E7-S2a thesis object migration evidence

## Contract

`thesis` is a first-class append-only research object. It requires
`company_id`, `statement`, `scope`, and `time_horizon`; optional valuation and
forecast references may point to evidence frozen in the same snapshot. It is
research context, not a rating, target price, or action.

## Migration paths

- Fresh SQLite installations receive the updated `object_type` check from the
  canonical schema.
- Existing SQLite stores whose check predates `thesis` are rebuilt explicitly:
  all rows are copied to the replacement table, then append-only triggers are
  reinstalled.
- PostgreSQL receives `0004_research_thesis_object.postgres.sql`, which
  replaces only the `object_type` check constraint.

## Verification

The focused contract test degrades a populated SQLite table to the old shape,
runs `DataFoundation.initialize()`, and proves the `thesis` check exists, the
existing object hash survives, and updates remain rejected by append-only
triggers.
