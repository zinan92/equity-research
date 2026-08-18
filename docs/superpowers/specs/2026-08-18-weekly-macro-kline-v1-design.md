# Weekly Macro K-line v1 design

Status: **approved in conversation; awaiting Park's written-spec review**

Tracking: [Issue #837](https://github.com/zinan92/equity-research/issues/837)

Design date: 2026-08-18
Complexity: **L** for the eventual feature; this issue is documentation only.

## 1. Executive decision

Replace the destination of the current K-line Daily experiment with an
independent **Weekly Macro K-line v1**, but do not modify the running Daily
product during design or prototype work.

The first version answers a narrower question:

> What does each of the 17 macro market tapes say on its own, across the honest
> timeframes available for that market, and which tapes deserve attention next
> week after every asset has been inspected?

It does **not** yet claim a single attack/defense posture, infer cross-asset
capital migration, calculate correlations, incorporate new macro expectation
feeds, or prescribe 15-minute/30-minute execution.

## 2. Why the current surface is not the destination

The current report mixes three products on one page:

1. a reader newsletter: conclusion, explanation and action;
2. an evidence notebook: charts, cross-section and relative histories; and
3. an Ops console: source classes, inputs, missing inputs, rules and receipts.

Its parameter surface is useful for replay but not for a reader. Its
Observations section restates numbers already visible in the chart wall and
cross-section. The later 17-market table then repeats those facts again. The
result is complete engineering evidence but weak attention design.

Weekly v1 separates the layers:

- the default page contains only reader content and the charts that support it;
- exact evidence IDs, source identities, validation and failure receipts remain
  in immutable machine artifacts; and
- provider exceptions, hashes, request metrics and retry details remain Ops
  data and never enter the reading hierarchy.

## 3. Product outcome and use moment

Every Monday at 08:20 Asia/Shanghai, Park should be able to inspect one local
weekly report and, without consulting another charting product, answer:

- Where is each market on its long-horizon weekly structure?
- What path is its daily tape taking over recent weeks?
- Where an honest intraday context exists, does that context confirm or weaken
  the daily structure?
- Which markets are worth participating in, waiting for, or avoiding next week?
- What completed-bar observation would confirm or invalidate each conclusion?

The report remains independent from Finance Daily Newsletter. The two products
may be compared by a human but never read or score one another.

## 4. Fixed universe and reading order

The universe remains exactly 17 series. No new instrument enters v1. These keys,
symbols and price bases bind the versioned Weekly registry; a fallback may
change an endpoint but may not change this identity.

| Chapter | Key | Canonical identity | Series semantics | Weekly | Daily | Context |
| --- | --- | --- | --- | --- | --- | --- |
| Money price | `dxy` | `DX-Y.NYB` | unadjusted price index | candle | candle | 4H candle |
| Money price | `us2y` | Treasury `2 Yr` | official par-yield level | line | line | none |
| Money price | `us10y` | Treasury `10 Yr` | official par-yield level | line | line | none |
| Money price | `us2s10s` | `us10y-us2y` same-date | derived spread in bp | line | line | none |
| Risk assets | `sp500` | `^GSPC` | unadjusted cash index | candle | candle | none |
| Risk assets | `nasdaq` | `^IXIC` | unadjusted cash index | candle | candle | none |
| Risk assets | `us_dividend` | `SCHD` | unadjusted ETF/style proxy | candle | candle | none |
| Risk assets | `vix` | `^VIX` | unadjusted cash volatility index | candle | candle | none |
| Risk assets | `bitcoin` | `BTC-USD` | unadjusted continuous price | candle | candle | 4H candle |
| Asia and A shares | `shanghai` | `000001.SH` | unadjusted cash index | candle | candle | none |
| Asia and A shares | `star50` | `000688.SH` | unadjusted cash index | candle | candle | none |
| Asia and A shares | `china_dividend` | `000015.SH` | unadjusted cash style index | candle | candle | none |
| Asia and A shares | `nikkei` | `^N225` | unadjusted cash index | candle | candle | none |
| Asia and A shares | `kospi` | `^KS11` | unadjusted cash index | candle | candle | none |
| Real assets | `wti` | `CL=F` | provider continuous front month, unadjusted | candle | candle | 4H candle |
| Real assets | `gold` | `GC=F` | provider continuous front month, unadjusted | candle | candle | 4H candle |
| Real assets | `silver` | `SI=F` | provider continuous front month, unadjusted | candle | candle | 4H candle |

This produces exactly **39 fixed reader chart slots**:

- 17 completed weekly charts;
- 17 completed daily charts; and
- five completed 4H chart slots for DXY, Bitcoin, WTI, gold and silver.

A full edition plots all 39 slots. A degraded edition retains the same 39
positions and renders an explicit unavailable placeholder wherever a current
plot cannot be verified. Only a plotted slot counts as a chart.

The earlier 51-chart idea is explicitly superseded. A literal A-share 4H bar
nearly duplicates its full daily session, while official Treasury yields are
daily. V1 does not invent intraday resolution or silently replace rates with
futures proxies.

## 5. Reader information architecture

The page reads in this order:

1. report week and plain-language data cutoff;
2. Money price chapter;
3. Risk assets chapter;
4. Asia and A shares chapter;
5. Real assets chapter; and
6. the complete Stage B surface—important changes and opportunity ordering—
   after all 17 asset cards.

V1 does not show a global `attack | wait | defense` posture. It does not show
macro parameters, the old Observations list, a repeated 17-row return table, a
missing-data ledger, cross-asset relative histories or a capital-migration map.

### 5.1 Asset card

Every asset card has one stable reading grammar:

1. instrument name and one multi-timeframe conclusion;
2. weekly chart immediately followed by weekly analysis;
3. daily chart immediately followed by daily analysis;
4. a 4H chart immediately followed by 4H analysis only for the five approved
   4H markets;
5. agreement state: `aligned_bullish | aligned_bearish | mixed | neutral`;
6. one observable confirmation level/condition;
7. one observable invalidation level/condition; and
8. preliminary state: `participate | wait | avoid`.

Text never floats away from the timeframe that supports it. Desktop may place
weekly and daily views side by side, with weekly receiving more space. Mobile
must stack chart then analysis in chronological reading order. A rate line is
never rendered as a candlestick.

### 5.2 Timeframe writing roles

- **Weekly price series**: long-horizon location, trend, range, previous
  completed weekly candle in context, and what the weekly tape can and cannot
  establish.
- **Weekly rate series**: end-of-week level/spread, weekly direction and change
  in basis points. Rate lines have no candle body, wick or OHLC language.
- **Daily**: recent multi-week path, higher-high/lower-low structure, breakout,
  pullback, compression, momentum change and key daily levels.
- **4H**: intermediate context for the coming week, local support/resistance,
  confirmation and failure. It is not the execution timeframe.
- **Synthesis**: only whether the available timeframes confirm or contradict
  one another. It does not repeat all numbers.

The color of one candle is never sufficient evidence. Body, wicks, range,
location and surrounding structure must be interpreted together.

## 6. Data and completion contract

### 6.1 Separate Weekly source-history authority

The deployed World Context's 520 retained daily observations are not enough to
prove three full years for every series, especially seven-day Bitcoin. Weekly
v1 therefore requires a new immutable **Weekly source-history authority**; it
does not extend or rewrite the deployed Daily context identity.

The authority:

- binds the exact 17-key registry, provider/canonical symbols, units,
  timezones, price basis, raw-capture hashes and rights;
- requests a five-calendar-year target window so provider holidays and missing
  sessions do not silently shorten the analysis surface;
- stores enough completed source observations to derive 156 consecutive,
  non-empty weekly bins ending at `WEEK_END` for a full slot;
- separately retains the nine-calendar-month daily display window and the
  eight-calendar-week hourly source window for approved 4H keys; and
- labels a shorter result `short_history` with its actual first/last session
  and bin count. It never pads, backfills or carries a prior value forward.

The full-edition gate is `weekly_bin_count=156` for every weekly slot. Bitcoin
will normally require at least 1,095 completed daily observations to satisfy
that gate; cash-market row counts vary, so the weekly-bin test—not one generic
daily-row count—is authoritative.

### 6.2 Windows and weekly aggregation

- weekly: exactly 156 completed weekly bins for a full slot;
- daily: the completed observations whose exchange-local session dates fall in
  the final nine calendar months through `WEEK_END`; and
- 4H: the final eight calendar weeks through `WEEK_END` for the five approved
  4H markets.

For a price series, one weekly candle uses the first completed daily open,
maximum high, minimum low and last completed close from the exchange-local
Monday-through-Friday bin. Optional volume is summed only from accepted source
rows. A holiday-shortened week uses its actual rows and records
`actual_last_session`; no synthetic Friday row is created. A whole week with no
accepted row is `unavailable`, not carried forward.

For `us2y` and `us10y`, the weekly line value is the last accepted official
yield level in that Monday-through-Friday bin. `us2s10s` is first derived on
each common official date as `(10Y-2Y)*100 bp`, then its last accepted same-date
spread becomes the weekly line value. Weekly rate change is end-level minus
prior end-level in basis points; rate series never receive OHLC fields.

### 6.3 WEEK_END and completion identity

`WEEK_END` is the ISO date of the latest Friday strictly before the Monday
08:20 Asia/Shanghai edition. `cutoff_at` is that Friday at `23:59:59 UTC`.
Each source maps observations to its declared exchange-local session date, then
admits only dates from the Monday-through-Friday calendar bin ending on
`WEEK_END`.

Every slot stores:

- `week_end` and `cutoff_at`;
- source timezone and local session-date rule;
- actual first and last admitted sessions;
- expected/accepted/missing observation counts;
- quality and any holiday/short-history reason; and
- the exact completed point IDs used by the weekly/daily/4H projection.

Weekly, daily and 4H analysis excludes observations after `cutoff_at`. Bitcoin
uses UTC session dates and is truncated at Friday 23:59:59 UTC. Its weekend
move may appear as an “after WEEK_END / not analyzed” overlay. Any current quote
uses the same label and never becomes a candle or model input.

### 6.4 Exact 4H bins and futures basis

Four-hour bars derive only from accepted, completed 60-minute rows. The v1
anchors are:

| Key | Timezone | Anchor | Price basis |
| --- | --- | --- | --- |
| `dxy` | America/New_York | 20:00 | `DX-Y.NYB` unadjusted index |
| `bitcoin` | UTC | 00:00 | `BTC-USD` unadjusted trade price |
| `wti` | America/New_York | 18:00 | `CL=F` continuous front month, unadjusted |
| `gold` | America/New_York | 18:00 | `GC=F` continuous front month, unadjusted |
| `silver` | America/New_York | 18:00 | `SI=F` continuous front month, unadjusted |

A valid 4H bar contains four consecutive provider-declared completed hourly
rows in the same anchored bucket. A bucket intersecting a maintenance break,
missing hour or terminal three-hour session remainder is omitted and disclosed;
hours are never compressed into a fake 4H bar. DST uses the named timezone, not
a fixed UTC offset.

WTI/gold/silver weekly, daily and 4H slots retain the same existing
`provider_continuous_front_month_unadjusted` basis. The source artifact records
roll methodology and `roll_boundary_status=known|unknown`; no back adjustment
or cross-symbol splice is permitted. Unknown roll boundaries degrade quality,
and the LLM may not call an isolated roll gap organic price momentum.

### 6.5 Source and rights boundary

Same-window source fallback is allowed: an alternate endpoint may provide the
same current completed period for the same canonical key, units, timezone and
price basis. Stale data is never relabelled current. Every source change binds
its own immutable capture, provider identity, session rules and rights.

Hourly/4H production rights are not inferred from daily rights. Current
research-only Yahoo-style intraday access can support a local prototype but
cannot unlock public or member redistribution. If no accepted intraday source
exists for one of the five keys, its 4H slot is explicitly unavailable.

Every chart exposes a reader-friendly completion time. Provider identity,
hashes, inputs and receipt paths remain in machine evidence only.

## 7. Two-stage LLM contract

### 7.1 Stage A: 17 isolated asset analyses

Run one provider request per asset. A request receives only that asset's exact
weekly/daily/optional-4H frozen projection, code-derived features, evidence IDs,
units and completion metadata. It receives no other asset, no Finance Daily
Newsletter content and no prior prose.

The constrained output contains:

- weekly analysis;
- daily analysis;
- optional 4H analysis;
- multi-timeframe synthesis;
- agreement state;
- confirmation predicate and evidence IDs;
- invalidation predicate and evidence IDs; and
- preliminary opportunity state and rationale.

Every observed statement, synthesis claim, confirmation, invalidation and
opportunity rationale carries one or more evidence IDs from that exact request.
The validator rejects unknown IDs, unavailable evidence, uncited assertions,
direction/structure mismatch and a claim cited only to another timeframe.
Numeric claims additionally resolve to values from their cited rows within a
declared formatting tolerance. Weekly prose cannot cite a 4H-only value; 4H
prose cannot invent an unfinished bar. Natural paragraphs are rendered for
readers, while the structured statements and IDs remain identity-bound.

### 7.2 Stage B: ordering after full coverage

Stage A always produces an ordered 17-slot terminal vector. Each slot is one of:

- `validated`, carrying its analysis ID, exact conclusion artifact/receipt
  references and underlying evidence IDs; or
- `analysis_unavailable`, carrying only a fixed reason code and available chart
  slot IDs.

After all 17 slots become terminal, run one ranking request over that exact
vector. It may:

- identify the three most important weekly changes;
- order all assets into `participate | wait | avoid`; and
- explain why higher-ranked setups have clearer confirmation and invalidation.

It cannot modify Stage A facts, introduce a new price, hide an asset, perform
cross-asset causal attribution or claim direct capital flow. It ranks only
`validated` slots; unavailable assets remain visibly `unavailable` and may not
be converted to `wait` or `avoid`. The ranking receipt records validated and
unavailable counts and the exact 17-slot input identity.

Every Stage B statement cites one or more Stage A analysis IDs plus the
underlying evidence IDs admitted by those analyses. Unknown, unavailable or
uncited evidence fails validation. All Stage B output—including important
changes—appears only after the full asset wall, so it cannot become an early
information filter.

The provider may rank zero assets as `participate`. It must not manufacture a
trade to fill a quota.

## 8. Failure and replay semantics

- Collection exhausts same-window alternate sources before declaring a period
  unavailable; it never substitutes an earlier week.
- One asset or timeframe failure does not block the other assets.
- A missing timeframe retains its exact card position and a concise reader
  status. It is not synthesized from another timeframe.
- Each Stage A request has `max_attempts=3` over the exact frozen evidence for
  transport or whole-output schema repair. Rejected prose is never patched into
  acceptance, and receipts preserve each bounded attempt outcome.
- If one Stage A analysis remains unavailable, verified plots still render and
  its terminal vector slot is `analysis_unavailable`. Stage B may rank the
  remaining validated slots but cannot classify or hide the unavailable asset.
- If Stage B fails, the 17 individual analyses still publish and the ordering
  section is explicitly unavailable.
- No failure path reuses last week's analysis text.
- Context identity binds source-history IDs, all timeframe slot IDs,
  `WEEK_END`, cutoff, registry version and quality. Analysis identity binds the
  exact context and 17-slot terminal vector; report identity additionally binds
  Stage B (or its typed unavailable status), renderer version and generation
  time.
- Immutable context, Stage A, Stage B, report and delivery artifacts precede
  any current pointer or Desktop alias update. Same-week editions use distinct
  time/digest identities. `load(report_id)` replays immutable references without
  collectors or LLM calls, even after current advances.
- A partial current-week edition may become current with visible slot/status
  disclosure. Total collection failure publishes a data-free current-week
  unavailable surface. Prior successful editions remain history only and are
  never relabelled current.

Reader copy contains only bounded statuses. Provider exceptions, local paths,
request IDs and retry details remain secret-safe Ops receipts.

## 9. Prototype contract

The next artifact is a throwaway, local-only prototype whose only question is:

> Can a reader navigate all 39 honest charts and adjacent analyses without the
> page becoming another unprioritized wall?

The prototype must:

- use the fixed four-chapter and 17-asset order;
- render all 39 actual fixture/snapshot plots before any opportunity ordering;
- keep every timeframe's prose adjacent to its chart;
- include one multi-timeframe summary per asset;
- omit Ops fields and all superseded report sections;
- expose machine-checkable DOM counts/order, work at 1280 px and 390 px without
  horizontal overflow, and preserve screenshots at both widths; and
- leave the installed Daily app, Desktop aliases, runtime and LaunchAgent byte
  unchanged.

The prototype may use a clearly dated, local-evaluation real snapshot or an
explicit fixture. It must never present fixture values as the current week.
Park will use the rendered artifact to choose one explicit prototype receipt:
`expanded_approved | folding_required | rework_required`. No content is
filtered before that decision, and implementation planning cannot begin while
the receipt is absent or not approved.

## 10. Runtime and migration boundary

Design and prototype phases do not change recurrence. The current Daily
LaunchAgent remains installed and continues its existing contract.

Only after the prototype and later implementation stories pass acceptance may
a separate migration story reuse the existing
`com.park.market-regime.kline-newsletter` label and its existing
`runtime/run.lock`:

1. preserve the prior Daily app, plist and Desktop artifacts;
2. boot out that one label, atomically replace its plist with
   `StartCalendarInterval={Weekday=2,Hour=8,Minute=20}`, then bootstrap the same
   label—never loading old and new Track 2 jobs together;
3. keep manual one-shot execution;
4. prove one controlled exact-main run;
5. make same-`WEEK_END` reruns idempotent so a wake/manual catch-up cannot create
   a false new week, then observe one ordinary calendar-triggered Monday run;
6. if plist/bootstrap, controlled readback or current-week publication fails,
   boot out the candidate, restore the exact prior app SHA/plist bytes and
   bootstrap the prior label; and
7. publish the prior/new hashes and rollback result in the migration receipt.

There is never a second permanent Track 2 scheduler.

## 11. Advice and safety boundary

The system may state market-level weekly opportunity, confirmation and
invalidation. It has no holdings, cost basis or personal risk tolerance. V1
does not produce 15m/30m entries, personalized sizing, broker orders or claims
of completed execution.

Always bind:

- `track=kline_only`;
- `finance_newsletter_input=false`;
- `local_evaluation_only=true`;
- `publication_eligible=false` as an immutable v1 contract value; a later
  versioned rights contract is required to change it;
- `automatic_execution_eligible=false`;
- `broker_access=false`; and
- `portfolio_mutation=false`.

Every reader edition visibly states “model generated, unreviewed”, “local
evaluation only” and “no automatic execution”. These disclosures are not hidden
inside an evidence dialog or machine receipt.

## 12. Eventual implementation sequence

The eventual feature is L-sized and must be split into sequential issues/PRs:

1. **Prototype** — render the approved 39-chart information architecture with
   clearly typed data and no runtime mutation.
2. **Multi-timeframe authority** — weekly aggregation for 17 assets and
   session-anchored hourly-to-4H aggregation for the five approved markets.
3. **Per-asset compiler** — one strict independent schema, validator and
   immutable receipt applied across 17 calls.
4. **Ranking compiler** — read only validated Stage A summaries and produce the
   late-page opportunity ordering.
5. **Weekly report store and surface** — 39 fixed chart slots, full/degraded
   reader page, Markdown, replay and partial-state behavior.
6. **Weekly runtime migration** — one Monday scheduler, controlled deployment,
   rollback and ordinary-trigger acceptance.

Each issue must freeze its own Outcome, three-to-seven reproducible success
criteria, In/Out scope and forbidden actions. Stories merge sequentially from
the latest main; no stacked production PRs.

## 13. Acceptance checklist for the eventual v1

- Exactly 17 assets appear in fixed chapter order.
- Exactly 39 fixed chart slots render in every edition. A full edition contains
  39 plots—17 weekly, 17 daily and five approved 4H—while a degraded edition
  keeps typed unavailable placeholders in the same positions.
- Every chart is followed by its timeframe-specific analysis.
- Every asset has one non-repetitive multi-timeframe synthesis, one confirmation
  and one invalidation.
- All assets are visible before the ordering section.
- No old posture, parameter surface, Observations list, repeated cross-section,
  data ledger or relationship wall appears.
- Incomplete bars and post-WEEK_END values never enter analysis.
- Partial data/model/ranking states fail honestly without stale prose.
- Desktop/mobile, identity replay, secret scan and relevant upstream tests pass.
- Finance Daily Newsletter, broker state and public distribution remain outside
  the feature.

## 14. Deferred work

The following require later independent contracts and must not leak into v1:

- rate-futures implied paths;
- breakeven inflation;
- implied-volatility term structure;
- positioning and crowding;
- macro event calendar integration;
- cross-asset pairs, rolling correlations and capital-migration synthesis;
- individual-stock/industry dispersion, breadth and direct flow; and
- 30m/15m execution for assets selected after weekly analysis.

## 15. Supersession and proof boundary

This document is a proposed reader/product destination. It does not mutate or
invalidate existing Daily artifacts. Once Park approves this written spec and
the design PR merges, a later explicit North Star update may mark Weekly v1 as
the approved next destination while preserving the Daily contracts as deployed
history and rollback evidence.

Design approval does not prove data availability, model quality, trade
accuracy, weekly automation or user value. Those claims require the prototype,
implementation receipts, ordinary scheduler evidence and repeated human use.
