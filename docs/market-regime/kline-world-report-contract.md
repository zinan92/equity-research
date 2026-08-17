# K-line World Report v4 · Addendum 01 parameter-first surface

Tracking: Issue #828. Parent: #827. Data/analysis predecessor: Issue #832
(which supersedes the closed Issue #829). This contract supersedes the report
surface and replay clauses from Issue #765; the approved warm-white visual
grammar, hollow-green/filled-red candles, local-only rights boundary and
no-automatic-execution boundary remain unchanged.

## Outcome

Render one local, replayable K-line Daily where every visible market value ends
at one report-wide `AS_OF`, HTML and Markdown expose the same complete parameter
record, and the low-confidence state cannot masquerade as a directional view.

The input-to-product chain remains:

> 17 completed OHLC/rate histories + 12 relative relationships → frozen
> Addendum 01 request → LLM interpretation → code-owned parameter controls →
> one inspectable local report.

## Information architecture

The page contains, in order:

1. one posture hero; confidence below 0.5 is always `无方向观点 / NO VIEW`;
2. all 17 completed-daily charts, with price OHLC candles and rate lines;
3. one canonical eight-row macro parameter surface;
4. gated insights plus cited observations;
5. the complete missing-data ledger; and
6. the 17-market cross-section plus all 12 relative-leadership histories.

The approved white vertical layout remains the North Star. The report does not
reintroduce historical discovery tabs or fixture values as current data.

## One-AS_OF truth contract

`AS_OF` is the latest completed session shared by all 17 aligned series. Every
number in prose, cards, tables, citations, charts and relative relationships
ends on that date. Each market separately exposes `actual_latest_session`,
`at_as_of | ahead_of_as_of`, and the number of post-AS_OF rows discarded. An
ahead market is never simply labelled fresh, and its newer value never enters
the report calculation or LLM-visible aligned tape.

Every successful chart contains exactly 300 aligned sessions. The 12 relative
histories are derived only from those aligned series. U.S. Treasury changes use
basis points; the 2s10s spread is a rate relationship, not a price return.

## Canonical parameter surface

One identity-bound `parameter_surface` drives HTML and Markdown. It contains,
in this exact order:

1. `AS_OF`;
2. `RISK_BUDGET`;
3. `LONG_GATE`;
4. `DISPERSION`;
5. `SECTOR_PRIOR`;
6. `BLACKOUT`;
7. `CONFIDENCE`; and
8. `DATA_COVERAGE`.

Every row carries the exact value, `MEASURED | DEGRADED |
DEFAULT_ON_MISSING_DATA` source, inputs, missing inputs, rule and plain-language
statement. `DATA_COVERAGE` is stored and rendered to two decimals.
`BLACKOUT=[]` means the event calendar is unknown, never that no events exist.
When confidence is below 0.5, insights stay empty; a default risk budget remains
supporting context and cannot become the headline.

## Evidence and language

All displayed facts and model-authored claims retain validated evidence IDs.
Relative leadership is evidence about repricing, not direct proof of fund flow.
The ledger is code-owned and keeps each unavailable input's exact
“本期不回答什么问题” boundary. Missing forward-looking data is not synthesized from
historical prices.

The model may produce market-level interpretation and recommendations when its
output passes the frozen contract. It receives no personal holdings and cannot
place orders, access a broker or mutate a portfolio.

## Identity, history and replay

A report identity binds the exact context ID, world-model ID, report/renderer
versions, generation time and canonical parameter surface. The completion
receipt additionally binds immutable context and world-model artifact/receipt
paths and hashes. `load(report_id)` replays those historical authorities even
after either upstream latest pointer advances.

JSON, HTML and Markdown artifacts are immutable and content addressed. Multiple
successful editions on one date use digest/time-bearing history aliases; they
never overwrite one dated filename. `latest.html` and `latest.md` are atomic
Desktop convenience aliases, not evidence authorities.

## Failure semantics

No stale report is relabelled as current. If current market data cannot produce
a verified context, the runtime publishes an explicit data-unavailable surface
without old values. If the current context is valid but the LLM is unavailable,
the report is `interpretation_unavailable` and contains no old prose, flow map,
insight or recommendation. Prior immutable editions remain loadable history.

## Truth and distribution boundary

- `track=kline_only`; Finance Daily Newsletter is not an input or fallback.
- `investment_advice_allowed=true` at the market level.
- `automatic_execution_eligible=false`, `broker_access=false`, and
  `portfolio_mutation=false`.
- `publication_eligible=false`; accepted sources remain local-evaluation-only.
- Visible copy says model-generated/unreviewed and local-only.

## Acceptance

- Desktop 1280 and mobile 390 have zero horizontal overflow.
- Exactly 17 chart canvases, 12 relative canvases and eight parameter records
  render from the same report identity.
- HTML and Markdown parameter values/source/inputs/missing-inputs are identical.
- Historical load survives upstream latest advancement; same-day histories are
  unique and immutable.
- Focused/upstream tests, identity replay, `git diff --check` and gitleaks pass.
- The deployed exact-main run preserves the previous Desktop edition and emits
  machine-readable parity, source, AS_OF and provider-usage evidence.
