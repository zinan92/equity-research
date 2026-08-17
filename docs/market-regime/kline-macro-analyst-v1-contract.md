# K-line Macro Analyst v2 · Addendum 01 and one-AS_OF analysis contract

Tracking: Issue #832. Supersedes closed Issue #829 and the date, history,
parameter-provenance, LONG_GATE, DISPERSION and low-confidence clauses of
Issue #819.

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

The repository also stores the user-supplied
`product/prompts/ADDENDUM-01-macro-analyst.md` byte-for-byte with SHA-256
`ada0fdfe37d87b65877c4fcc62c7065c30b7f1b181ce4b000cd625db16fe9270`.
The effective provider prompt is source prompt + Addendum 01 + versioned JSON
transport appendix. Source, addendum, transport, effective prompt, base request,
final attempt request and output hashes are persisted and replay-validated.

The default provider route is `deepseek-v4-flash` with a declared 1,000,000
token context budget. Each immutable artifact and receipt records the canonical
base/final request byte sizes. A successful provider receipt must also contain
integer `prompt_tokens`, `completion_tokens` and `total_tokens`, bind the exact
requested model, and remain within that declared budget; missing or over-budget
usage fails closed instead of being labelled model-generated. Every attempt's
secret-free provider receipt is retained in order, and the completion receipt
also stores aggregate recorded usage across the entire retry cycle; the
1,000,000-token context limit remains a per-request constraint, not a claim
that cumulative retry cost is below that number.

## Frozen input and date alignment

All 17 exactly-300-session aligned daily histories and 12 aligned relative
histories remain in the request:

- `AS_OF` is the latest date present in every series used by the macro model;
- every number available to prose, tables, charts and relationships is recomputed
  from data ending at that date;
- each series exposes the actual latest source date and discarded-row count, but
  no post-AS_OF row enters a calculation; and
- retained source history is provenance/calibration input only, not a second
  report surface.

## Code-owned data inventory

The request names what is available, partial and missing. At minimum, current
v1 expects completed prices, relative histories, realized volatility, VIX
history, the 2Y/10Y/2s10s curve, rate-futures expectations, implied-volatility
term structure, breakeven inflation, positioning/crowding, event calendar,
equity/industry dispersion, sector breadth, direct fund flows and a 250-session
index percentile.

Coverage is the code-owned available-equivalent weight divided by total
expected weight and rounded to two decimals. Partial inputs receive their
declared fractional weight. The provider must echo the exact value and every
missing row. Because the present
context has no forward-looking expectations, events or positioning, code sets
`all_forward_looking_missing=true`; model confidence is therefore capped at
0.4. Missing event data means `BLACKOUT=[]` is "unknown calendar", not proof
that no event exists. Individual-equity dispersion remains missing and visible
in the ledger; it is not confused with measured cross-market dispersion.

## Code-owned LONG_GATE and cross-market DISPERSION

- `LONG_GATE` uses the Shanghai Composite's final 250 aligned closes:
  `pct250=count(close<=current)/250`; strictly above 0.70 is `CLOSED`, otherwise
  `OPEN`. Confidence never overrides this independent measurement.
- `DISPERSION` uses the 14 price/index series and excludes US2Y, US10Y and
  2s10s. It first computes each market's close-to-previous-local-close return,
  then intersects those return dates across all 14 and computes their population
  standard deviation. The current reading is ranked
  inclusively against the final 252 observations: above 60% is `HIGH`, 40–60%
  inclusive is `MID`, below 40% is `LOW`.
- The report labels this explicitly as cross-market, not individual-equity,
  dispersion.

## Successful output

One successful structured output contains:

1. `headline` and `summary` in Simplified Chinese;
2. `macro_parameters`: exact `AS_OF`, `RISK_BUDGET` in 0–1, `LONG_GATE`,
   `DISPERSION`, optional `SECTOR_PRIOR`, `BLACKOUT`, code-bound `CONFIDENCE`
   and `DATA_COVERAGE`;
3. exactly one code-owned quantitative basis for risk budget, long gate, dispersion,
   sector prior, blackout, confidence and data coverage;
4. zero to three insights, each with evidence, non-restatement explanation,
   historical base-rate status, a numeric falsifier, review date and affected
   parameter;
5. typed `[事实]`, `[推断]` or `[未知]` observations; and
6. the exact missing-data ledger.

Each parameter basis carries `source`, `inputs`, `missing_inputs` and `rule`.
`MEASURED` requires non-empty inputs and no missing inputs; `DEGRADED` requires
both; `DEFAULT_ON_MISSING_DATA` requires empty inputs and non-empty missing
inputs.

With the current inventory, all forward-looking expectation, positioning and
event inputs required by `RISK_BUDGET` are missing. Its code-owned value is
therefore the explicitly non-informational default `0.30`, with
`SOURCE=DEFAULT_ON_MISSING_DATA` and empty inputs; it is not a market reading.

When confidence is at least 0.5, visible posture is code-derived from
`RISK_BUDGET`: 0–0.4 is defense,
above 0.4 through 0.6 is wait, and above 0.6 is attack. The headline must use
the same posture label. If confidence is below 0.5, the posture/headline is the
code-owned exact label `无方向观点 / NO VIEW`, insights are empty and the summary literally states
`本日不提供方向观点`; `LONG_GATE` retains its independently measured value.

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

For the same context, report schema v3 / renderer v6 consumes the exact
one-AS_OF 300-point `charts`, `cross_section` and `relationships` projections.
The candle grammar and registry order remain unchanged. Making actual-latest
metadata and full parameter provenance visibly identical across HTML and
Markdown belongs to follow-up Issue #828.

## Failure, replay and boundaries

A provider or validation failure creates a same-context
`interpretation_unavailable` artifact and never reuses prior parameters or
prose. The report still shows the exact current chart/evidence sections with an
explicit analysis-unavailable notice. Artifact, receipt, source prompt,
effective prompt, request and output identities replay before any pointer
advances.

Every attempt permits only claim-level, current-context recovery: malformed
observations are omitted rather than rewritten, while parameter bases and the
missing-data ledger are regenerated deterministically from that same frozen
request. This avoids repeating the full 300-session provider request merely to
drop an uncited observation. Non-recoverable schema, headline, summary or macro
contract failures still request a full rewrite, up to the bounded attempt cap.
Unknown citations and unverified numbers never survive into the artifact.
Summary and surviving observations remain model-authored. The low-confidence
headline, parameter bases, missing ledger, and deterministic risk-budget/
LONG_GATE/DISPERSION/DATA_COVERAGE values are code-owned; provider copies of
the remaining macro fields must still pass the full contract. Recovery never
reads a prior report and is not a stale-data fallback.

Finance Daily Newsletter is not an input. Data rights remain local-evaluation
only. The macro parameters can inform downstream research, but the system has
no broker access, does not mutate a portfolio and never automatically executes
a trade.
