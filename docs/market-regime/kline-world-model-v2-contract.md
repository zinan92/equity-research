# Global Market K-line Daily v2 · cross-asset world-model contract

Status: approved S0 direction under Issue #759. Parent program: #758.

This is a documentation and migration contract. It authorizes later scoped
stories; it does not change the installed LaunchAgent, current report, provider,
runtime pointer or Finance Daily Newsletter by itself.

## Product thesis

Park's exact approved product pipeline is:

> 完整 OHLC 日线与跨资产相对关系 → LLM 自主解读 → 资金迁移地图 →
> consistent world model → 可执行交易建议。

The product is an AI cross-asset tape reader, not a chart wall, a deterministic
rule dashboard or an LLM enum selector. Its job is to read completed-daily price
behavior across markets, explain the relative repricing as one internally
consistent world model, infer where capital plausibly appears to be rotating,
and convert that interpretation into an actionable market plan.

Track 1, Finance Daily Newsletter, remains independent. Track 2 neither reads
nor scores it. The two artifacts may be compared by Park only after generation.

## Use moment and reader outcome

Before the A-share open, the reader should be able to answer within 90 seconds:

1. What is the world currently pricing?
2. Which assets are gaining and losing relative leadership?
3. Where does capital plausibly appear to be leaving and entering?
4. Which observations form the dominant transmission chain?
5. What contradicts that chain or makes it conditional?
6. What should the reader prioritize, reduce, avoid or wait for?
7. What observable changes would invalidate the world model and advice?

The report must reconcile dimensions instead of forcing false exclusivity. For
example, `risk_on + leaning_defense + dividend leadership` can mean risk
appetite remains intact while leadership rotates defensively. The world model
has to explain that combination in plain language.

## Frozen context input

The model receives one immutable, size-bounded context object produced from
accepted completed-daily evidence. It contains:

- a bounded OHLC history for every accepted price series;
- the completed session, close time, provider identity, quality and units for
  every series;
- rate-level histories for US2Y and US10Y and a correctly derived 2s10s series;
- code-calculated 5-, 20- and 60-session returns, trend and drawdown features;
- normalized cross-sectional performance and explicit relative-price
  relationships between economically meaningful peers;
- deterministic risk, posture, style and leadership dimensions as supporting
  observations rather than the final answer;
- contradiction candidates, coverage, freshness and cross-market close skew;
  and
- stable evidence IDs resolving every accepted source value and series.

The implementation story freezes the exact lookback, compact serialization and
pair registry. The default target is enough completed daily history to read
medium-term shape without sending an unbounded archive. A chart screenshot may
be a reader artifact, but it is not a substitute for the machine-readable OHLC
and relative context.

Every canonical judgment input must be visible in deeper evidence. If dividend
indices or ETFs influence style and advice, their values and charts must be
available to the reader. Bitcoin may remain a supplement, but the report must
say whether it participated in the canonical judgment rather than implying that
all displayed assets had equal model weight.

## LLM authority and output

The LLM may independently interpret the frozen context and author prose. It is
not limited to selecting enums whose sentences are later filled by templates.
The versioned output contains:

1. `world_model` — one concise, authored synthesis of what is being priced;
2. `regime` — the dominant posture plus supporting risk/style/leadership nuance;
3. `flow_map` — a finite list of `from`, `to`, evidence, confidence and rationale;
4. `transmission_chain` — three to five ordered observations or interpretations;
5. `contradictions` — material evidence that challenges the dominant model;
6. `trade_plan` — market-level recommendations, priorities, avoid/reduce items,
   observable action conditions and intended horizon; and
7. `falsifiers` — exactly two concrete changes that invalidate the model or
   advice.

The LLM may say buy, add, reduce, avoid, hedge, hold cash, wait or rotate when
those recommendations are clearly the output of the cited market interpretation.
It may recommend assets, asset classes or styles and condition the action on
observable market behavior. This product has no portfolio or holdings input, so
personalized position sizing is not implied by the current version.

Automatic order placement, broker access, portfolio mutation and live-money
execution remain out of scope and require a separate explicit authorization and
execution contract.

## Facts, inference and capital-flow language

The report uses three visibly different claim classes:

- **Observed:** exact price, rate, return, trend, relative-strength, quality or
  timing facts from the frozen context.
- **Inferred:** the LLM's explanation of likely capital rotation or macro
  transmission, cited to the observations that support it.
- **Recommended:** the action that follows if the inferred model is accepted,
  including its horizon, conditions and falsifiers.

Price action shows relative repricing; it does not directly prove literal fund
flows. Therefore the report says capital *appears to be rotating* unless direct
volume, ETF-flow, futures-positioning, options or custody evidence is separately
contracted and accepted. The model may not upgrade co-movement into proven
causality.

## Evidence and validation

Code remains authoritative for source identity, raw values, OHLC, units,
completed sessions, time skew, coverage and evidence quality. The LLM cannot
alter those values.

- Every numeric statement must match a cited frozen value or deterministic
  calculation within its declared formatting tolerance.
- Every observed statement must cite the series or relationship it describes.
- Every inferred flow edge, causal interpretation and recommendation must cite
  the observations on which it depends.
- Unsupported IDs, invented values, mismatched directions and claims about
  unavailable evidence fail validation.
- AI prose remains `model_generated_unreviewed`; it is an interpretation and
  recommendation, never source evidence.

Advice is allowed and is not rejected merely for using trading language. The
validator instead rejects fabricated facts, uncited assertions, identity/unit
violations, stale-prose reuse, broker actions and claims of automatic execution.

## Confidence semantics

The reader sees at least two separate measures:

1. **Evidence quality** — coverage, freshness, source acceptance, unit validity
   and close-time skew. Code owns this value.
2. **Directional clarity** — cross-asset agreement, relative leadership,
   contradictions and dispersion. Code owns the inputs and bounded score; the
   LLM may explain but not silently increase it.

A report may therefore say “evidence quality high, directional clarity medium”.
The UI must not collapse completeness and conviction into one unexplained high
confidence number.

## Failure and replay

The context, model request, response, validation and rendered report remain
content-addressed and replayable. Missing key, timeout, invalid JSON, unknown
citation, invented number or failed semantic validation produces a same-context
fallback that:

- preserves the last verified market evidence;
- explicitly says interpretation and advice are unavailable;
- never reuses prose or recommendations from an older context; and
- leaves the prior last-good report recoverable without presenting it as current.

## Information hierarchy

The approved white vertical North Star remains the visual baseline. The next
reader surface follows this order:

1. dominant world model and regime nuance;
2. observed-versus-inferred capital migration map;
3. ordered transmission chain;
4. actionable trade plan;
5. cross-sectional data and relative leadership;
6. contradictions and exactly two falsifiers; and
7. all canonical daily charts and deeper evidence.

Posture colors and return colors remain separate. Desktop and 390 px mobile
must preserve one clear first-screen conclusion without horizontal overflow.

## Migration and reuse boundary

Reuse without changing historical identity:

- completed-daily and macro collectors;
- immutable raw/artifact/receipt stores;
- rate and percent-return unit semantics;
- Bitcoin's explicit supplement identity;
- the white vertical reader grammar;
- one-shot 08:20 scheduling and last-good publication mechanics; and
- Track 1 independence.

Version rather than mutate:

- the context/evidence projection that currently exposes only point features;
- the enum-only narrative schema and deterministic prose renderer;
- report identity and rendered sections; and
- confidence projection and visible-input parity.

The installed current runtime remains unchanged until all new stories merge,
the exact merged SHA is deployed, and controlled plus ordinary unattended
acceptance passes. Rollback restores the prior exact app SHA and scheduler
arguments; historical v1 artifacts are not rewritten.

## Program acceptance

The complete program is accepted only when:

- the model demonstrably receives bounded OHLC histories and relative context;
- one real report contains authored, cited world-model prose and a capital-flow
  map that cannot be reproduced by the old fixed templates;
- recommendations are specific enough to act on and carry observable conditions
  and falsifiers;
- every judgment input is visible or explicitly marked supplemental;
- evidence quality and directional clarity render separately;
- provider failure produces no stale world model or advice; and
- an ordinary 08:20 run publishes a replayable Track 2 artifact without reading
  or changing Finance Daily Newsletter.

## Boundaries

- Local/private evaluation remains the only authorized distribution mode until
  data rights change.
- No Finance Daily Newsletter input or fusion.
- No intraday Live v1 redesign in this program.
- No broker, automatic order, portfolio mutation or live-money execution.
- No claim of measured fund flow without separately accepted direct-flow data.
