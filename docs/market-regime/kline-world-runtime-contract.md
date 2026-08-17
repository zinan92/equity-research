# K-line World Runtime v2 Contract

Issue: #769; same-day source fallback: #783; Addendum 01 surface/history:
#828; one-AS_OF context/model predecessor: #832 (supersedes closed #829).

## Issue #828 superseding addendum

The serial 08:20 runtime, one LaunchAgent, source fallback order and stale-data
failure rules below remain authoritative. Issue #828 additionally requires:

- the report store to bind and replay immutable historical context/model
  artifacts and receipts instead of consulting their current pointers;
- one canonical eight-row parameter surface to drive both HTML and Markdown;
- every visible market value to end at the context's single `AS_OF`, while each
  market exposes its actual latest date and discarded post-AS_OF count;
- every successful edition to contain 17 histories of exactly 300 aligned
  sessions and 12 aligned relative histories;
- multiple editions on one date to use distinct time/digest history paths, with
  no overwrite of an earlier dated edition;
- Desktop promotion to preserve the previous edition before atomically
  replacing `latest.html` and `latest.md`; and
- runtime status to expose the report ID and parameter-surface count without
  recomputing analysis or reading Finance Daily Newsletter.

The runtime schema is v3, the report schema is v4, and the renderer is v7.
The controlled real run and browser acceptance must be performed from the exact
merged `main` SHA. A controlled run proves delivery plumbing, not the product's
predictive value or the later ordinary 08:20 trigger.

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
3. Each refreshed factor exhausts its ordered same-day source/endpoint chain
   before the runtime treats that factor as unavailable. A successful
   alternate source produces a current accepted artifact and does not block the
   report. Desktop `latest.html` and `latest.md` contain either the exact bytes
   of the verified immutable S3 artifacts or an explicit current `今日数据不可用`
   surface. Dated aliases contain only verified historical reports. A failed
   run never labels a prior report as the current result and preserves the
   prior immutable delivery/history state.
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
- Overwriting dated historical aliases from a failed run, or leaving a prior
  report under the current `latest` label after a source failure.
- Persisting provider exceptions, paths or secrets in status or receipts.
- Weakening any completed-daily, context, model or report validator.

## Runtime and failure semantics

The runtime is one-shot; recurrence belongs only to the existing LaunchAgent.
It uses the existing `run.lock` so old and new invocations cannot overlap. A
model-unavailable S2 artifact is a valid current-context result, but its status
must remain `interpretation_unavailable` and its report must contain no flow or
trade plan. Collection first retries the configured same-day source chain. If a
required factor still has no accepted current source, evidence/context/report
failures produce the explicit data-free unavailable latest surface and a
fixed-code failure status; prior dated artifacts and delivery receipts remain
historical and are never relabelled as current.

Desktop aliases are a local convenience projection, not a new evidence source.
Immutable report artifacts are written first. A successful run atomically
replaces the aliases and advances the served delivery state. A failed run
atomically replaces only `latest.html`/`latest.md` with a data-free unavailable
surface; dated aliases and the prior delivery receipt remain historical. The
unavailable surface contains no charts, generated prose, advice or previous
source values. This does not claim cryptographic authenticity or perfect
multi-file crash transactions against an actor able to rewrite all local files.
