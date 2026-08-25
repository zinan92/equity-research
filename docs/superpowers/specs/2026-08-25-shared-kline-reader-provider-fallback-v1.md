# Shared K-line reader and audited LLM provider fallback v1

## Problem Statement

From the reader's perspective, the Daily K-line Newsletter and Weekly K-line
Newsletter currently look like different products. Weekly renders real static
K-line snapshots with period explanations, while Daily mostly renders status
sentences such as “数据覆盖：日线：可用”. Daily already produces chart snapshot
artifacts, but its projection drops those references before producing Markdown
and HTML. The result hides the actual K-line context that the reader needs.

The explanation layer also depends on DeepSeek. When DeepSeek is unavailable,
the Daily edition must not silently reuse old prose or stop publishing the
verified charts and deterministic readings. It needs an audited, read-only
Codex CLI provider fallback for every model-backed layer, with explicit
disclosure when both providers fail.

## Solution

Build one shared reader projection for Daily and Weekly. The projection keeps
the same asset-card and period-card reading order across Web, Obsidian
Markdown, and the Mini Program article surface:

1. asset identity, ticker and observation time;
2. one period card per eligible period, with the static K-line image above the
   period explanation;
3. position, structure and odds;
4. combined conclusion and market meaning; and
5. a reader-facing source/status area below the analysis.

Daily and Weekly retain different horizon contracts. Daily uses daily data for
all assets and adds only the real 4-hour/30-minute periods declared for that
asset. Weekly uses weekly/daily and eligible 4-hour context. A period outside
the asset contract is omitted; a requested period that fails retains a compact
temporary-unavailable card and its auditable reason.

Introduce one provider adapter contract for all model-backed explanations.
DeepSeek remains primary. After DeepSeek's bounded attempts fail for any
reason, Codex CLI receives the same frozen evidence and structured request in a
read-only, no-tools, no-file-write invocation. Both providers pass the same
schema, evidence-ID, language and numeric validators. The provider, fallback
reason and output receipt are recorded in the status area, not mixed into the
main prose.

If both providers fail, publish a clearly labelled degraded edition containing
the verified K-line snapshots and deterministic readings. The reader must
explicitly see that both DeepSeek and Codex CLI failed, including their short
failure classifications. No previous thesis, old chart, stale cache or
fabricated market data may be reused.

## User Stories

1. As a Daily reader, I want every eligible asset to show its actual K-line
   image, so that I can see the evidence before reading the interpretation.
2. As a Weekly reader, I want the Weekly page to keep its current chart quality
   while using the same reading order as Daily, so that I do not learn two UI
   languages.
3. As a Daily reader, I want the period explanation directly below its chart,
   so that the text has immediate visual context.
4. As a Weekly reader, I want weekly position, daily structure and eligible
   4-hour context to remain distinct, so that horizons are not conflated.
5. As a Daily reader, I want daily direction separated from 4-hour and
   30-minute context, so that short-term rhythm does not overwrite the daily
   view.
6. As a reader, I want the asset ticker and observation time beside the asset
   name, so that a recommendation identifies a searchable tradable instrument.
7. As a reader, I want position, structure and odds in the same place for both
   editions, so that I can compare assets without changing mental models.
8. As a reader, I want one combined conclusion and market-meaning section per
   asset, so that the K-line reading is translated into a useful implication.
9. As a reader, I do not want “数据覆盖：日线：可用” to replace actual analysis,
   so that operational metadata does not masquerade as user value.
10. As a reader, I want source and provider details available below the main
    analysis, so that provenance remains inspectable without dominating the
    first read.
11. As a reader, I want a period that was never part of an asset's contract to
    be omitted, so that unsupported periods do not create a wall of false
    failures.
12. As a reader, I want a requested but failed period to remain visibly marked,
    so that missing evidence is not mistaken for a flat market.
13. As a reader, I want Web HTML to use static PNG snapshots, so that the
    published reader is stable and does not depend on an interactive chart
    runtime.
14. As an Obsidian reader, I want the same chart images referenced in Markdown,
    so that the archive is self-contained and readable outside the Web page.
15. As a Mini Program reader, I want the chart image included as article media,
    so that a snapshot ID alone is never presented as a chart.
16. As a reader, I want image and text order to stay identical across Web,
    Obsidian and Mini Program output, so that the same report is recognizable
    everywhere.
17. As a model-backed reader, I want DeepSeek to remain the primary explanation
    provider, so that the existing analysis path remains stable when healthy.
18. As a model-backed reader, I want every DeepSeek-backed layer to have the
    same Codex CLI fallback, so that a DeepSeek outage does not selectively
    remove asset or market explanations.
19. As a reader, I want a DeepSeek schema or evidence failure to trigger the
    fallback after bounded retries, so that an unusable response cannot block
    the entire edition.
20. As a reader, I want a provider fallback to use the same frozen evidence,
    so that changing models cannot change the observed market facts.
21. As a safety reviewer, I want Codex CLI to run read-only with no tools and no
    file writes, so that fallback cannot mutate data, code or runtime state.
22. As a safety reviewer, I want Codex CLI forbidden from fetching markets,
    reading old newsletters or using external news, so that the evidence
    boundary is identical between providers.
23. As a reader, I want the fallback provider and reason recorded in the status
    area, so that I know which model generated the explanation.
24. As a reader, I want no technical fallback details inserted into the main
    thesis prose, so that transparency does not ruin readability.
25. As a reader, I want both model failures explicitly named, so that “thesis
    unavailable” cannot conceal whether one or two providers failed.
26. As a reader, I want the edition to publish charts and deterministic readings
    even when both models fail, so that a model outage does not erase verified
    market evidence.
27. As a reader, I want a degraded edition clearly labelled as deterministic
    only, so that I do not confuse code readings with an LLM world model.
28. As an operator, I want each provider response to carry a receipt and output
    hash, so that the chosen explanation can be replayed and audited.
29. As an operator, I want DeepSeek and Codex CLI attempts bounded, so that the
    08:20 job cannot wait indefinitely.
30. As an operator, I want one run lock and a hard total runtime limit, so that
    overlapping editions cannot overwrite or mix artifacts.
31. As an operator, I want source failure and model failure represented as
    separate states, so that a provider outage cannot be misdiagnosed as bad
    market data.
32. As a maintainer, I want Daily and Weekly projection logic to share one
    reader seam, so that a visual fix does not need two divergent implementations.
33. As a maintainer, I want provider selection to share one adapter seam, so that
    future providers can be added without copying the analysis pipeline.
34. As a maintainer, I want the current 31-slot Daily source capability matrix
    preserved, so that this reader work does not widen or weaken data contracts.
35. As a maintainer, I want Finance Daily Newsletter and Weekly/Daily K-line
    tracks to remain separate, so that the comparison experiment stays valid.

## Implementation Decisions

- Use the existing Weekly static reader as the visual control. Daily and Weekly
  project into the same reader contract; they do not receive separate layout
  systems.
- Keep the existing standard-kline snapshot pipeline. The projection consumes
  immutable PNG references; it does not mount an interactive chart in the
  reader.
- Add one shared report projection seam that accepts report data, eligible
  period cards, snapshot references and provider/status metadata, then emits
  HTML, Markdown and Mini Program article representations.
- The projection must consume the Daily snapshot references already produced by
  the runtime. It must never regenerate charts from stale or undeclared data at
  render time.
- Keep the current per-asset capability matrix. Unrequested periods are
  omitted; requested failures are explicit cards; ready periods show image and
  explanation.
- Keep OPS/source/provenance fields out of the main reader narrative. Expose
  them in a compact, visible status area.
- Add one LLM provider adapter seam shared by per-asset analysis and cross-asset
  thesis compilation. The adapter returns structured JSON plus a receipt.
- DeepSeek is primary. Each DeepSeek-backed call gets bounded same-provider
  attempts; any final failure, including balance, transport, timeout, schema or
  citation failure, selects Codex CLI.
- Codex CLI runs ephemerally, read-only, without tools, without file writes and
  without external data fetching. It receives only the frozen request object.
- Both providers use the same validator. Provider switching cannot loosen
  evidence binding, numeric binding, language rules or trading-safety bounds.
- The provider receipt records provider, model, CLI/API version where relevant,
  fallback reason, attempt count, request hash, output hash and validation
  result.
- If both providers fail, publish a degraded deterministic edition and name
  both failed providers and their failure categories in the status area.
- Set a hard 20-minute run ceiling. On timeout, publish the latest valid source,
  deterministic analysis and whatever validated model output exists; never
  reuse old prose to fill the missing part.
- Keep the source/data fallback policy unchanged: no stale promotion, no
  implicit source switch and no synthetic candles.
- Keep Finance Daily Newsletter, Weekly runtime, broker paths and execution
  authorization outside this feature.

## Testing Decisions

- Test external reader behavior, not CSS implementation details: a Daily and a
  Weekly fixture must produce the same semantic section order and a period card
  must contain its snapshot image before its explanation.
- Test that Daily Markdown contains real image references and not only snapshot
  IDs; test that HTML contains the corresponding image elements.
- Test unrequested periods are omitted and requested failed periods render a
  compact explicit failure card with no stale image.
- Test that OPS phrases such as “数据覆盖：日线：可用” do not appear as the
  primary asset narrative when a ready snapshot and analysis exist.
- Test responsive reader projection at desktop and mobile viewports, including
  no horizontal overflow, all images readable, and stable source/status footer.
- Test the Mini Program article projection with the same semantic order and
  image attachments.
- Test the provider adapter with a successful DeepSeek response, a DeepSeek
  final failure followed by valid Codex JSON, invalid Codex JSON, and both
  providers failing.
- Test that every fallback request has the same evidence hash and that Codex
  cannot be accepted if it cites unknown IDs or unbound numbers.
- Test explicit user-facing dual-failure wording and deterministic-only status.
- Test provider receipts, fallback reason, attempt counts and output hashes are
  immutable and bound to the delivery.
- Test the 20-minute timeout and run lock behavior without sleeping for the
  full duration in unit tests.
- Run an attended real-data acceptance against the current 31-slot Daily
  source, the Weekly reader, the Daily reader and the 08:20 LaunchAgent. The
  acceptance must distinguish source readiness, asset-model coverage,
  cross-asset thesis status and delivery/archive status.
- Reuse existing Weekly snapshot, report projection, Daily source/analysis,
  provider validation and runtime readback tests as prior art.

## Out of Scope

- New market data sources, new fallback data providers, stale-cache promotion,
  synthetic candles or changes to the 31-slot capability matrix.
- Any change to Finance Daily Newsletter or its data sources.
- Any change to Weekly source semantics, provisional-bar rules or datafeed
  ownership.
- Interactive charts, client-side chart fetching or a new charting library.
- Trading execution, broker integration, live orders, portfolio changes or
  personalized investment advice.
- Public deployment, domain routing, authentication, payments or commercial
  publication rights.
- Adding news, macro event calendars, direct fund flows or non-K-line data to
  this reader.

## Further Notes

- The current production Daily source run is real and has reached 31/31 ready;
  the remaining problem is projection and model-provider resilience, not a
  missing chart-data acquisition path.
- The current DeepSeek account has returned HTTP 402 `Insufficient Balance`.
  Codex CLI is available locally and authenticated, but its non-interactive
  LaunchAgent invocation must be tested before it becomes an automatic
  fallback.
- The accepted domain decisions are recorded in `CONTEXT.md` and ADR 0001.
- This spec is a build contract. Any change to the reader contract, provider
  fallback boundary or dual-failure behavior must return to the spec stage.
