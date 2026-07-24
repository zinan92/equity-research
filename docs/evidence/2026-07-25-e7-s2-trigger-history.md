# E7-S2 trigger history evidence

## Reused contracts

- B5 supplies immutable `IntelligenceEvent` identities and evidence IDs.
- E1 supplies append-only `ResearchObject` revisions and authority checks.
- E3 catalyst/falsifier objects now include a thesis reference, direction,
  threshold, time window, and explicit trigger status.

## Transition rule

`propose_event_match()` accepts only an explicit `fulfilled`, `delayed`, or
`broken` interpretation whose evidence references include an evidence ID from
the selected B5 event. It returns an audit proposal only.

`propose_trigger_revision()` creates the next `ResearchObject` revision but
does not persist it. The existing `ResearchObjectStore.append()` remains the
only persistence path, preserving revision history and raw/snapshot authority
checks. There is no action, target, position, or order output in either step.

## Verification

`product/tests/test_research_trigger_history.py` proves a fulfilled catalyst
event leaves revision 1 unchanged, binds revision 2 to the immediately prior
hash and event evidence, and rejects unmatched event evidence and invalid
directions.
