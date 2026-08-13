# Market Regime Daily S5 · bundle/API/health runtime contract

Status: approved execution contract for Issue #750. This story connects the
already merged S3 Evidence Pack and S4 Narrative Compiler. It does not change
their contracts or the existing Live v1 route.

## Outcome

Turn a verified S3 Evidence Pack and the S4 narrative generated from that same
pack into one local/private, read-only, replayable Daily bundle for the
approved white North Star page. Existing Live v1 API semantics and the
15-minute intraday cadence remain unchanged.

S5 is a downstream phase of the existing 4h/12h structural cycle, not a third
market-regime scheduler:

```text
verified structural data/analysis + macro
  -> S3 Evidence Pack
  -> S4 Narrative
  -> S5 Daily bundle
```

The controlled local scheduler may invoke S3/S4 compilers and their provider
through the existing runtime boundary. HTTP GET never collects, compiles,
calls a provider, or advances a pointer.

## Success criteria

1. **Dedicated bundle and identity.** Publish `market-regime-daily-bundle-v1`.
   The immutable bundle artifact contains only the stable
   `publication_identity` and its deterministic projection: pack/narrative
   identities, S3/S4 artifact hashes, output/schema/compiler versions,
   generation status, truth boundary, and the North Star read projection. It
   does not contain S3/S4 receipt paths, receipt hashes, run IDs, attempt
   timestamps, or compatibility mirrors. `bundle_id` is content-addressed from
   `publication_identity`. The first S5 completion receipt binds that bundle to
   the S3/S4 receipt references observed at publication; later immutable check
   receipts bind the same candidate to newly observed receipt references but do
   not change the bundle artifact, bundle history, or served pointer. Every
   receipt is still strictly verified for schema/hash/path/identity/truth
   consistency and fails closed on mismatch.
2. **North Star projection.** `GET /api/market-regime/daily` returns one
   posture, synthesis, transmission chain, contradictions, exactly two
   falsifiers, the 16-slot evidence/citation projection, coverage/quality/
   confidence, joint judgment time, close skew, and rights boundary. Factual
   fields resolve to S3/S4 evidence IDs. Partial, fallback, and unavailable
   states are explicit.
3. **Health and last-good.** `GET /api/market-regime/daily/health` returns
   last attempt ID/time/status, last successful bundle ID/time, current
   candidate pack/narrative IDs, served bundle ID, fixed failure code and
   phase, next due, lock/interrupted state, quality, and age. With no verified
   success, `/daily` returns HTTP 503 and `unavailable`. If a current attempt
   fails while a verified last-good exists, `/daily` returns the unchanged
   last-good bundle; health marks the runtime `degraded` and exposes the fixed
   failure code. Corrupt state/artifact/receipt/hash is never treated as
   last-good. Health reads only the S5 atomic state/status; it does not
   assemble a mixed view by independently reading S3/S4 latest pointers.
   Persisted errors are fixed `code`/`phase` values only, never provider
   exception text, request bodies, response bodies, or credentials.
4. **Identity-triggered publication.** Advance only for a new verified
   candidate `publication_identity` (`pack_id`, `narrative_id`, artifact/output
   hashes, compiler/schema versions, generation status, truth boundary), not
   merely a changed `pack_id` or a new receipt/run ID. The S3/S4 receipt
   path/hash is stored in the completion/check receipt and verified as
   provenance for that candidate, but a receipt-only change is an idempotent
   check and cannot create history. Canonical state keeps the served bundle's
   original completion receipt separate from the most recent check receipt.
   The tuple uses fixed field names and ordering; attempt timestamps, temporary
   paths, and compatibility mirrors are excluded. Re-running the same
   candidate is an idempotent check receipt. A same-pack deterministic
   fallback can later be upgraded to a model narrative and a new bundle. S5
   invokes the S4 runner/store and never constructs its own fallback or handles
   provider credentials.
5. **Atomic publication and race safety.** Build may occur from immutable
   references outside the publication lock. Before commit, acquire the same
   shared daily publication lock used by S3/S4; while holding it, re-read and
   verify the complete current S3 and S4 identities, require the same
   `pack_id`, write the immutable S5 artifact and completion receipt, then
   atomically replace the canonical S5 state without releasing the lock.
   Read back the state before releasing it. If identity changed, validation or
   readback fails, preserve the exact prior served-state bytes and leave only
   orphan immutable artifacts. A crash may leave orphans but never a partial
   canonical state. This prevents torn writes, misbinding, and concurrent
   overwrite; it is not an authenticated anti-rollback guarantee against an
   attacker who coherently replaces every artifact, receipt, and state file.
   A receipt-only check uses the same lock: while holding it, re-read the
   served `publication_identity`; write an immutable check receipt first, then
   atomically update only `latest_check_receipt` while leaving served and
   completion fields byte-for-byte unchanged. If the served identity has
   advanced, the check receipt remains an orphan and state is not changed.
6. **Routes and rights.** Both routes are exact-match `dashboard` entitlement
   allowlist entries, loopback-only, GET-only, `Cache-Control: no-store`, and
   have zero side effects. They never return absolute paths, raw provider
   exceptions, prompts, secrets, or source-rights upgrades. Existing
   `/api/market-regime` and `/api/market-regime/health` retain their current
   bytes, semantics, permissions, and cadence.
7. **Runtime integration and verification.** S5 is a downstream phase of the
   existing structural 4h/12h cycle under the shared cohesive-pipeline lock.
   It does not collect intraday data, change the 15-minute scheduler, modify
   Live v1 state, or require intraday availability. Focused S5 tests, relevant
   product tests, baseline,
   gitleaks, and readback runtime evidence pass. Tests cover fallback-to-model
   upgrade, S3/S4 advancement during compile, lock/CAS/readback rollback,
   crash/interrupted/orphan artifact, corrupt state/receipt/artifact,
   partial/degraded/unavailable states, GET zero side effect, route
   allowlist/entitlement/non-loopback/no-store, fixture exclusion, and old
   Live API/scheduler regression. Include real lock contention and injected
   crashes after artifact write, receipt write, final validation, and before
   state replacement; check(A) racing publish(B); check-receipt write/state
   update crashes; same canonical candidates must not create history; a
   fallback must bind the same pack; and provider-shaped secrets must not leak
   through state, receipts, logs, or API responses.

## In scope

- Daily bundle compiler/store and immutable artifact/receipt/state contract.
- Downstream integration into the existing structural runtime cycle.
- Exact GET routes `/api/market-regime/daily` and
  `/api/market-regime/daily/health`.
- Daily health/status and CLI/runtime verification.
- Focused/upstream tests, docs, `REGISTRY.md`, `decision-log.md`, and runtime
  evidence.

## Out of scope

- North Star UI implementation or `/market-regime` route migration (S6).
- New providers, DRAM, or news/event-source integration.
- Changes to S3 Evidence Pack or S4 Narrative contracts.
- Public/member distribution, remote hosting, alerts, notifications,
  payments, or personalized advice.
- Holdings, position sizing, orders, or live trading.
- Changes to existing Live v1 API schema, cadence, data sources, or route
  semantics.

## Forbidden

- GET may not fetch upstream, call an LLM/provider, compile S3/S4, refresh data,
  or advance a pointer.
- Fixture/demo/mock scenario values may not be published as current or history.
- Yahoo/Tencent rights/status may not be upgraded or implied publishable.
- A narrative from another pack may not be served.
- Existing immutable artifacts/receipts may not be overwritten or mutated.
- Absolute local paths, raw captures, prompts, credentials, and provider error
  bodies may not be exposed.
- Do not bind public interfaces, bypass auth/entitlement, or touch真钱/live
  paths.

## Reuse and verification

Reuse the S3 store/compiler in
`product/data_core/market_regime_daily_evidence.py`, the S4 store/compiler in
`product/data_core/market_regime_daily_narrative.py`, the existing structural
runtime/lock in `product/market_regime_runtime.py`, and the exact local route
guard in `product/server.py`. Add glue around those canonical contracts; do
not copy them wholesale.

Expected checks:

```bash
python3 -m unittest product.tests.test_market_regime_daily_bundle product.tests.test_market_regime_runtime product.tests.test_market_regime_web -q
python3 scripts/verify_baseline.py
git diff --check
gitleaks protect --staged --no-banner --redact
```
