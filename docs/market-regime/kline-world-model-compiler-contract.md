# K-line World Model v1 · LLM interpretation and advice contract

Tracking: Issue #763, reliability addendum #767. Parent: #758. Predecessor:
#761 / PR #762.

## Outcome

Compile one immutable, replayable, LLM-authored interpretation from an exact
`market-regime-kline-world-context-v1` artifact. The model may form its own
cross-asset synthesis and give market-level trading advice. Code remains the
authority for data, identities, units, evidence quality and execution limits.

This compiler is a new authority. It does not mutate the historical enum-only
Daily Narrative schema or its artifacts.

## Provider input

The request contains the exact bounded world-context projection:

- 17 completed-daily series, each with 120 OHLC/rate points and deterministic
  multi-horizon features;
- 12 aligned relative-performance histories;
- deterministic agreement, confidence and contradiction inputs;
- exact series, relationship and canonical evidence identities; and
- the local-only, advice-allowed, no-auto-execution truth boundary.

It contains no Finance Daily Newsletter input, storage paths, credentials or
provider exceptions. The request is reconstructible from the context identity,
prompt version and output schema and is bound by its canonical hash.

To keep the complete history inside the provider context budget, repeated point
objects are losslessly encoded as positional arrays. Every series and
relationship declares its own `point_columns`; all 120 observations and every
OHLC, rate or relative-index value remain present. The immutable S1 artifact is
not rewritten or compacted.

## Model authority and output

Successful output contains:

1. an authored headline and concise `world_model`;
2. `regime` posture, risk, style and leadership nuance;
3. two to six `flow_map` edges;
4. three to five observed/inferred `transmission_chain` entries;
5. one to four material contradictions;
6. one to six `trade_plan` recommendations; and
7. exactly two observable falsifiers.

The model is not restricted to fixed prose templates. It may use buy, add,
reduce, avoid, hedge, hold cash, wait and rotate. Each recommendation declares
a target, horizon, observable condition, rationale, citations and one linked
falsifier. This is market-level research; the compiler has no user portfolio or
holdings context and therefore does not produce personalized position sizing.

## Observed, inferred and recommended

- `observed` statements bind a subject reference and a direction derived from
  its deterministic 20-session feature. A direction mismatch fails closed.
- `inferred` statements and every flow rationale must visibly use qualified
  language such as possible, appears, suggests or likely.
- `recommended` content lives in `trade_plan`, carries supporting evidence and
  remains explicitly model-generated and unreviewed.

Every flow edge uses the exact two endpoints of a registered relationship. Its
destination must equal the code-calculated 20-session relative leader, and its
citations must contain that relationship plus at least one explicit endpoint.
The relationship identity itself binds both endpoint series and their aligned
history. This makes the map a disciplined inference from relative repricing,
not a claim that price action directly measured literal fund flow.

## Citation and numeric validation

Accepted citations are only IDs in the exact context: `series_id`,
`relationship_id` or the canonical evidence ID attached to a visible series.
World-model and regime synthesis must be cross-asset. Leadership and trade
targets must cite their own series or defined supporting group. A rotation
recommendation must cite a relationship whose observed leader is its target.

Arabic numeric literals in prose must match a value or deterministic feature
from the same object's cited references within the declared formatting
tolerance. Signed values remain signed and percent-return values cannot be
silently substituted for basis-point changes. Declared window/maturity and
instrument-name labels such as 20-session, US10Y, S&P 500 and STAR 50 are
grammar, not factual numeric claims.

## Code-owned confidence

The provider does not output the visible confidence object. Code projects two
separate measures into every artifact:

- evidence quality from accepted source quality and coverage; and
- directional clarity from the frozen context confidence inputs.

The model may explain those inputs but cannot rewrite their value or promote
its own conviction into evidence quality.

## Advice and execution boundary

Investment advice is allowed. Automatic execution is not.

The validator rejects claims of automatic ordering, completed orders, broker
execution, guaranteed returns and personalized percentage sizing. Artifacts
always bind `automatic_execution_eligible=false`, `broker_access=false` and
`portfolio_mutation=false`. No broker, portfolio or live-money code is called.

## Failure and replay

Missing provider, timeout, truncated response, transport error, malformed
schema, invented ID, wrong direction, unrelated citation, invented number or unsafe semantics
produces a same-context `interpretation_unavailable` artifact. It contains the
failure code and code-owned confidence, but no flow map, transmission chain,
trade advice or falsifier. It never reuses older prose or recommendations.

All provider calls share one hard budget of three attempts over the exact same
frozen context. Timeout or truncated transport may retry the unchanged request.
Schema/citation/numeric/semantic rejection may trigger a complete rewrite; only
fixed, path-scoped validation codes and code-owned correction hints enter that
next request. Rejected prose, raw exceptions, storage paths and credentials do
not. The v2 prompt explicitly requires a literal inference qualifier in the
world synthesis and each flow rationale, and an exact citation for non-mixed
leadership.

The completion receipt binds the ordered outcome of every attempted provider
call, the exact feedback codes actually supplied to later attempts, the final
request hash and the final generation status. A successful receipt must end in
`accepted`; an unavailable receipt must end in the same fixed failure category
stored in the artifact. Missing-provider fallback has zero attempted calls.

Artifacts and completion receipts are immutable and content addressed. The
canonical state advances atomically only after full readback. If the context
advances during provider generation or final commit, the prior state is
restored and the stale advice is not published. Hash/path/identity/source
mismatch fails closed. Hashes prove internal integrity, not authenticity
against a coherent rewrite of every source, artifact, receipt and state object.

## Boundaries

- No HTML/CSS, report page, scheduler, Desktop publication or API change.
- No Finance Daily Newsletter input or comparison.
- No direct ETF/futures/options/custody flow feed in this version.
- No mutation of historical Daily Narrative identities.
- No public redistribution, broker access, order, portfolio mutation or
  live-money execution.
