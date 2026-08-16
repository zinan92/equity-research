# K-line World Runtime v1 Contract

Issue: #769

## Outcome

Replace only Track 2's local scheduled execution path with the merged S1 to S3
chain. At 08:20 Asia/Shanghai the one existing LaunchAgent validates completed
daily authorities, refreshes Bitcoin and macro data, freezes the 17-series and
12-relationship world context, asks the LLM for a cited world model and
market-level trade plan, renders the approved white vertical report, and only
then promotes verified bytes to the Desktop aliases.

Finance Daily Newsletter remains an independent Track 1 product and is never
read, modified or used as fallback content.

## Success criteria

1. One serial runtime executes Daily validation, Bitcoin/macro refresh, S3
   evidence, S1 context, S2 world model, S3 report, full replay verification,
   Desktop promotion and safe status publication in that order.
2. `com.park.market-regime.kline-newsletter` at 08:20 remains the only Track 2
   scheduler. No second LaunchAgent, API or intraday dependency is introduced.
3. Desktop `latest.html`, `latest.md` and dated aliases contain the exact bytes
   of the verified immutable S3 artifacts. Any failure before a successful
   promotion preserves the prior last-good aliases and delivery state.
4. A missing key or exhausted provider publishes only the current-context
   `interpretation_unavailable` report: zero flow edges, advice or stale prose.
   Success status exposes posture, generation state, 17 charts, 12 relative
   relationships, and flow/advice counts.
5. Focused tests cover full ordering, Track 1/intraday independence, no-key
   behavior, rollback, status replay/tamper, lock contention and the unchanged
   single-job plist. All Market Regime tests remain green.
6. Deployment uses the exact merged main SHA in the existing detached app
   worktree, records the prior SHA, re-bootstraps the existing LaunchAgent and
   performs one controlled real run with Desktop, browser, runtime and
   `launchctl` evidence.
7. A controlled run is not described as ordinary 08:20 acceptance. Product
   utility remains unproven until later calendar-triggered Track 2 outputs are
   manually compared with the already-running Track 1 newsletter.

## In scope

- A new versioned runtime and delivery-state authority.
- Migration of the existing runner and status projection.
- Reuse of the existing LaunchAgent label, schedule, roots and one-shot lock.
- Focused tests, exact-SHA controlled deployment evidence and `REGISTRY.md`.

## Out of scope

- Finance Daily Newsletter changes or fusion.
- APIs, routes, intraday surfaces or a second scheduler.
- S1/S2/S3 identity, semantics or visual changes.
- Public hosting, data redistribution, broker access or automatic execution.
- A claim that the product has already proved useful.

## Forbidden

- Reading Track 1 as an input or fallback.
- Publishing fixtures, stale prose or an unverified report as current.
- Overwriting last-good Desktop aliases from a failed promotion.
- Persisting provider exceptions, paths or secrets in status or receipts.
- Weakening any completed-daily, context, model or report validator.

## Runtime and failure semantics

The runtime is one-shot; recurrence belongs only to the existing LaunchAgent.
It uses the existing `run.lock` so old and new invocations cannot overlap. A
model-unavailable S2 artifact is a valid current-context result, but its status
must remain `interpretation_unavailable` and its report must contain no flow or
trade plan. Collection, evidence, context, report-replay or promotion failures
leave the prior delivery available and update only a fixed-code failure status.

Desktop aliases are a local convenience projection, not a new evidence source.
Immutable report artifacts are written first. Aliases are replaced atomically
per file, delivery state advances last, and caught failures restore the exact
prior alias and state bytes. This does not claim cryptographic authenticity or
perfect multi-file crash transactions against an actor able to rewrite all
local files.
