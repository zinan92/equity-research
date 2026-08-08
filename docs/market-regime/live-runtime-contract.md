# Market Regime Live v1 · cohesive read-only API contract

Status: S3a local runtime publication contract. API schema:
`market-regime-api-v2`. Material receipt schema:
`market-regime-material-change-receipt-v1`. Story: #722.

This story publishes one hash-verified local bundle. It does not set the
15-minute schedule, redesign the page, contact a provider from HTTP, send a
notification, forecast a market move, or execute an action.

## One identity chain

The API bundle is publishable only when all four verified inputs agree:

1. the completed-daily snapshot `run_id` equals the structural analysis
   `source_run_id`;
2. the overlay structural `analysis_id` equals that verified analysis;
3. the overlay intraday `snapshot_id` equals that verified intraday snapshot;
4. every layer remains read-only, non-publishable and non-actionable.

The bundle keeps two explicit namespaces:

- `structural` contains the completed-daily snapshot identity, full structural
  analysis, nine daily chart projections and three structural probes;
- `intraday` contains the exact 5-minute snapshot identity, coverage/quality,
  and one time/session/freshness projection per frozen intraday asset.

`overlay` remains the complete immutable experimental overlay. It may only
report `confirms`, `diverges`, `insufficient`, or `closed`; it never overwrites
the structural labels. Existing top-level daily fields remain as a temporary
backward-compatible read projection until the S4 page migrates, but their
values are derived from the same `structural` object in the bundle.

## Material-change receipt

Every bundle carries one
`market-regime-material-change-receipt-v1` object. Its content-addressed
identity binds:

- previous and current overlay identities;
- structural analysis and intraday snapshot identities;
- overlay input fingerprint and model version;
- threshold policy version, enter 18, exit 8, persistence 2, cooldown 1,800
  seconds, and material score delta 15;
- stable relation, material flag/reasons and score deltas;
- pending relation/count, cooldown-until and cooldown-blocked state;
- every deterministic contribution's instrument, evidence identity,
  normalized artifact SHA-256, weight and signed contribution.

The receipt calls these rows contribution evidence, not causal drivers. It
contains no news story, predicted return, recommendation or position action.

## Publication order and failure behavior

The writer validates the four inputs, builds the material receipt and bundle,
writes one immutable bundle artifact, reads and verifies that artifact, and
only then atomically replaces `api/latest.json`. The latest pointer binds the
bundle, structural analysis, intraday snapshot, overlay and material receipt
identities.

Any schema, hash, path, identity, truth-boundary, missing-evidence or write
failure before the pointer replacement leaves the previous API pointer
byte-unchanged. Orphaned immutable artifacts are harmless and may be reused
only when their bytes match the same content identity. A valid `partial`,
`closed`, or `insufficient` overlay may become a new honest bundle; a malformed
or incoherent object may not.

The completed-daily 4/12-hour cycle recompiles an overlay against the newest
verified intraday snapshot before publishing, so a new structural analysis can
never be paired with an old overlay identity.

## Two schedulers, one serial publication pipeline

The structural scheduler remains configurable only at 4 or 12 hours.  The
separate intraday scheduler is fixed at a 15-minute target interval.  “Target”
means the next due time is calculated after the previous cycle finishes; it is
not tick data, a WebSocket, an exchange feed, or a promise that the provider
will be fresh every 15 minutes.

Each scheduler has its own non-blocking same-kind lock.  Both also acquire one
shared cohesive-pipeline lock before mutation, so a structural refresh and an
intraday refresh cannot interleave their analysis, overlay, or API identities.
Lock contention is `busy`, leaves status/latest pointers unchanged, and retries
after 30 seconds rather than waiting another 4/12 hours.

Every intraday cycle records and executes these phases in order:

1. `collect` one immutable raw/normalized attempt per configured source;
2. `verify_collected` by reading the hash-bound latest intraday snapshot;
3. `compile` the overlay against the locked structural analysis;
4. `verify_compiled` by reading the overlay/history chain;
5. `publish` and re-read the cohesive API bundle.

A successfully verified partial snapshot is an honest successful pipeline
cycle, not a hidden full cycle.  A rejected asset keeps its original
latest-good provider time, and API health calculates age from that old time.
If a primary request returns 429/5xx/bad data but the frozen fallback succeeds,
the bundle may remain complete while the scheduler still records a degraded-
fallback provider failure.

Provider or cycle failure streaks use a bounded delay of 15, 30, then at most
60 minutes.  There is no rapid retry loop.  Accepted `closed`, `post`,
`lunch_break`, or `maintenance` session evidence is not a provider failure and
does not trigger backoff.  When all A-share dependencies are in known non-open
states, the overlay publishes `closed`; it never changes the label to `live`.

Before overlay compilation, the runtime snapshots the reachable overlay and
API pointers.  A caught compile/publish/verification failure restores those
pointer bytes, so the prior API and hash-linked history heads remain current;
new immutable orphan artifacts may remain as audit evidence.  An interrupted
process is reported as `interrupted` when its last status says `running` but
its lock is free.

The stop switch is
`intraday/scheduler/STOP` under the external runtime root (or
`PARK_MARKET_REGIME_INTRADAY_ENABLED=false`).  It prevents another provider
request immediately between cycles.  An already-running bounded cycle drains
before the in-process loop records `stopped`; the launchd operator command may
instead unload it immediately, in which case a mid-cycle status is honestly
reported as `interrupted`.  Clearing the switch and starting the agent is
reversible and does not delete runtime evidence.

## Read-only HTTP and health

`GET /api/market-regime` and `GET /api/market-regime/health` remain loopback,
authenticated/entitled and `Cache-Control: no-store`. They only read and
verify persisted artifacts. A GET cannot fetch Yahoo/Tencent, refresh data,
compile either model, append overlay history or advance an API pointer.

Health separates the structural and intraday schedulers plus structural,
intraday, overlay and API bundle status. Each
layer exposes its original last-success/evidence time, current age calculated
from that frozen time, quality/partial state, session/freshness counts and the
last scheduler error. Re-serving health may increase age; it never rewrites or
resets provider, observation, receipt, overlay or success timestamps.

## Truth boundary

The bundle is Park-local, read-only and generated from supplementary
local-evaluation sources. `publication_eligible=false` and
`action_eligible=false` are mandatory across the structural snapshot,
intraday snapshot, structural analysis, overlay, material receipt and API
bundle. Fixture replay proves identity and failure behavior only. It does not
prove live-open reliability, latency, redistribution rights or investment
performance.
