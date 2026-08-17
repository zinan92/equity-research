# Market Regime K-line Daily Newsletter pilot

Historical note: Issue #759 supersedes this pilot's enum-only/no-advice product
destination for the next version. The current installed pilot remains unchanged
until the versioned cross-asset world-model replacement passes acceptance. See
`kline-world-model-v2-contract.md`.

Tracking: [Issue #754](https://github.com/zinan92/equity-research/issues/754)

## Outcome

At 08:20 Asia/Shanghai, create one local Track 2 Newsletter that lets Park
compare a completed-daily cross-asset interpretation with the already-running
Finance Daily Newsletter.  The two products remain independent: Track 2 never
reads, quotes, scores, schedules, or changes Track 1.

The pilot answers one use moment: within 90 seconds before the A-share open,
what is the completed-daily cross-asset tape pricing, what contradicts that
view, and what two observable changes would make the interpretation stale?

## Fixed observation set

The report contains exactly 15 observations in this order:

1. S&P 500, Nasdaq Composite, Shanghai Composite, STAR 50, Nikkei 225, KOSPI.
2. WTI, gold, silver.
3. Bitcoin.
4. VIX and DXY.
5. U.S. Treasury 2Y, 10Y, and 2s10s.

Price indices, commodities, Bitcoin, VIX, and DXY use completed-daily OHLC.
Treasury yields are rate levels and 2s10s is a spread; their five-session
changes remain basis points and their charts remain lines, never fake returns
or candlesticks.

Bitcoin is a separately frozen human-comparison supplement.  It is shown in
the cross-section and chart wall but is not silently inserted into the
canonical deterministic posture model v1.

## Success criteria

1. All 15 observations show session, quality, value, five-session change, and
   the correct percent-return/basis-point semantics.
2. The frozen S3 Evidence Pack and constrained S4 compiler produce one market
   posture, one synthesis, three to five cited transmission steps,
   contradictions, and exactly two cited falsifiers.
3. Provider absence, timeout, or invalid schema/citation produces a same-pack
   deterministic `unknown` fallback rather than stale or uncited prose.
4. A successful run writes immutable payload/HTML/Markdown artifacts and only
   then atomically advances `latest`; a failed source attempt first exhausts
   the configured same-day source chain. No prior data is promoted as current;
   if every candidate fails, the run stores only fixed, secret-free
   unavailable status fields.
5. One LaunchAgent triggers the Track 2 one-shot runner at 08:20.  It does not
   modify or call the Finance Newsletter job.
6. The white vertical North Star hierarchy works at desktop and 390 px with a
   visibly distinct green/amber/red posture treatment and no overflow.
7. Focused and relevant upstream tests, exact runtime readback, diff checks,
   secret scan, screenshots, and the unchanged Finance plist hash form the
   acceptance receipt.

## Boundaries

- Local evaluation only; `publication_eligible=false` and
  `action_eligible=false`.
- Market posture describes the tape.  It is not personalized advice, a price
  forecast, position sizing, or an order.
- No S5 Daily API, public/member distribution, Feishu delivery, holdings,
  intraday signals, or Live v1 route/cadence changes.
- Put/call, copper, STOXX, and other additions require a later source,
  semantics, and rights contract; they do not block the first comparison run.
- Fixture/demo/mock inputs may exercise isolated tests only and may never be
  published as the current local report.
