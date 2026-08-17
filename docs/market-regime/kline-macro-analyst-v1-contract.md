# K-line Macro Analyst v1 · parameter-first analysis contract

Tracking: Issue #819. Supersedes the analysis/output portions of Issues #763,
#765 and #797. The completed-daily context, chart renderer and evidence surfaces
remain authoritative and unchanged.

## Outcome

Turn the same frozen 17-series and 12-relationship K-line context into one
machine-consumable macro-layer decision record. The analytical discipline is
the exact user-supplied `SYSTEM-PROMPT-macro-analyst.md`: parameters first,
zero-to-three falsifiable insights, typed observations and a complete
missing-data ledger. It does not emit the former inferred fund-flow map,
transmission narrative or asset-level trade plan.

## Prompt identity

The repository stores the supplied prompt byte-for-byte at
`product/prompts/SYSTEM-PROMPT-macro-analyst.md`. Its SHA-256 is
`81b5d8bcf46c71dc1ebc124fb93949b4c7a10196dd326828c8fae21cb9f1d63d`.

The provider system prompt is that exact text followed by one versioned
transport appendix. The appendix does not add a market view. It only requires
JSON equivalent to the prompt's YAML block, exact context IDs, the explicit
`UNKNOWN` dispersion state when the required cross-sectional metric is absent,
and the no-instruction/no-secret boundary. Both the source-prompt hash and the
effective-prompt hash are persisted and replay-validated.

## Frozen input and date alignment

All existing 17 complete daily histories and 12 relative histories remain in
the request. Code additionally derives one analysis-only aligned snapshot:

- `AS_OF` is the latest date present in every series used by the macro model;
- 5/20/60-session features are recomputed from each series at or before that
  common date rather than comparing independently moving latest closes;
- each series still exposes its actual completed session, making later closes
  visible without treating them as comparable on `AS_OF`; and
- chart/evidence projections continue to show the full latest completed data
  and are not truncated or rewritten by alignment.

## Code-owned data inventory

The request names what is available, partial and missing. At minimum, current
v1 expects completed prices, relative histories, realized volatility, VIX
history, the 2Y/10Y/2s10s curve, rate-futures expectations, implied-volatility
term structure, breakeven inflation, positioning/crowding, event calendar,
equity/industry dispersion, sector breadth, direct fund flows and a 250-session
index percentile.

Coverage is the code-owned available-equivalent weight divided by total
expected weight. Partial inputs receive their declared fractional weight. The
provider must echo the exact value and every missing row. Because the present
context has no forward-looking expectations, events or positioning, code sets
`all_forward_looking_missing=true`; model confidence is therefore capped at
0.4. Missing event data means `BLACKOUT=[]` is "unknown calendar", not proof
that no event exists. Missing equity dispersion is `DISPERSION=UNKNOWN`, never
an invented HIGH/MID/LOW reading.

## Successful output

One successful structured output contains:

1. `headline` and `summary` in Simplified Chinese;
2. `macro_parameters`: exact `AS_OF`, `RISK_BUDGET` in 0–1, `LONG_GATE`,
   `DISPERSION`, optional `SECTOR_PRIOR`, `BLACKOUT`, code-bound `CONFIDENCE`
   and `DATA_COVERAGE`;
3. exactly one quantitative basis for risk budget, long gate, dispersion,
   sector prior, blackout, confidence and data coverage;
4. zero to three insights, each with evidence, non-restatement explanation,
   historical base-rate status, a numeric falsifier, review date and affected
   parameter;
5. typed `[事实]`, `[推断]` or `[未知]` observations; and
6. the exact missing-data ledger.

The visible posture is code-derived from `RISK_BUDGET`: 0–0.4 is defense,
above 0.4 through 0.6 is wait, and above 0.6 is attack. The headline must use
the same posture label. If confidence is below 0.5, `LONG_GATE=CLOSED`, insights
are empty and the summary literally states `本日不提供方向观点`.

## Insight and semantic validation

- Relative price or return evidence may be described only as relative
  performance/leadership. Without a direct-flow reference, text claiming money
  or capital flowed from A to B is rejected.
- Every insight falsifier names a real series/relationship subject, metric,
  operator, numeric threshold and matching unit. The threshold may be a model
  decision boundary, but current observations and historical statistics may
  not be invented.
- `base_rate.status=not_backtested` is honest and forces that insight's
  confidence at least 0.2 below overall confidence. Measured base rates require
  a separately bound historical-analogue input; v1 has none.
- Every parameter basis and observation cites exact context references and/or
  exact missing-data IDs. Factual numeric prose reuses only cited values.
- Individual stocks, personal position sizes, broker/order claims, guaranteed
  returns and unbound event claims fail closed.
- Hedge words are counted across generated prose, limited to three, and are
  forbidden in insight conclusions.

## Report surface

The hero shows the code-consistent posture, headline, summary, risk budget,
long gate, confidence and data coverage. After it, the report preserves:

1. the exact existing 17-chart section;
2. the macro parameter board and quantitative bases;
3. insights (or the explicit empty state) plus typed observations;
4. the complete missing-data ledger; and
5. the exact existing 17-market cross-section and 12 relative-history section.

For the same context, `charts`, `cross_section` and `relationships` JSON
projections are byte-identical to renderer v3. Their HTML builders, canvas
attributes, point payloads, candle colors, order and evidence-dialog rows are
unchanged. Only the old analysis sections are replaced.

## Failure, replay and boundaries

A provider or validation failure creates a same-context
`interpretation_unavailable` artifact and never reuses prior parameters or
prose. The report still shows the exact current chart/evidence sections with an
explicit analysis-unavailable notice. Artifact, receipt, source prompt,
effective prompt, request and output identities replay before any pointer
advances.

The compiler requests a full rewrite on the first three model-validation
failures. On the fourth and final attempt it may perform only claim-level,
current-context recovery: malformed observations are omitted rather than
rewritten, while parameter bases and the missing-data ledger are regenerated
deterministically from that same frozen request. Unknown citations and
unverified numbers never survive into the artifact. Headline, summary and macro
parameter values remain model-authored and must still pass the full contract;
if they do not, the analysis is unavailable. This recovery never reads a prior
report and is not a stale-data fallback.

Finance Daily Newsletter is not an input. Data rights remain local-evaluation
only. The macro parameters can inform downstream research, but the system has
no broker access, does not mutate a portfolio and never automatically executes
a trade.
