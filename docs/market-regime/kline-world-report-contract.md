# K-line World Report v1 · approved white North Star surface

Tracking: Issue #765. Parent: #758. Predecessors: #761 and #763.

## Outcome

Render the exact immutable K-line World Context and World Model artifacts as
one local, replayable report whose reading order is the product promise:

> completed OHLC and relative relationships → LLM interpretation → capital
> migration map → consistent world model → actionable trade recommendations.

The approved white vertical prototype is the visual baseline. The report is a
new versioned surface and does not replace the installed legacy newsletter in
this story.

## Information architecture

The page contains, in order:

1. exactly one dominant market posture and one authored synthesis;
2. separate code-owned evidence-quality and directional-clarity measures;
3. the cited capital-migration map;
4. the observed/inferred transmission chain;
5. the model-generated actionable trade plan;
6. all 17 completed-daily series and all 12 relative-leadership relationships;
7. material contradictions and exactly two falsifiers; and
8. all 17 daily charts, with OHLC candles for price series and lines for rates.

Attack, wait and defense are descriptions of the market posture. They use
distinct green, amber and red accents on the same warm-white layout. Historical
scenario controls from the discovery mockup do not ship as current data.

## Evidence and language

All numbers are projected from the exact S1 context. Every world-model claim,
flow edge, chain entry, contradiction, recommendation and falsifier retains its
validated reference IDs and opens a human-readable evidence view. Observed,
inferred and recommended content have distinct visible labels. Relative price
leadership is presented as evidence for possible capital migration, never as a
claim that the system directly measured fund flows.

The report may display explicit trading recommendations because the S2 contract
allows them. Recommendations are model-generated and unreviewed. There is no
personal portfolio context or percentage sizing, and no broker, order or
portfolio mutation.

## Failure and replay

A successful report is a deterministic projection of one exact context ID, one
exact world-model ID, the renderer version and generation time. Its JSON, HTML,
Markdown and completion receipt are immutable and content addressed before the
atomic current pointer advances. Replay revalidates both upstream authorities,
the report identity and every output hash.

If S2 is unavailable, the same-context report still shows all verified data and
charts but contains no stale flow map, transmission chain, trade plan or
falsifier. Fixture contexts are permitted only in explicitly configured visual
and unit tests; the ordinary store rejects them.

## Truth and distribution boundary

- `track=kline_only`; the Finance Daily Newsletter is not an input.
- `investment_advice_allowed=true`.
- `automatic_execution_eligible=false`, `broker_access=false`, and
  `portfolio_mutation=false`.
- `publication_eligible=false`; current provider rights remain local evaluation
  only.
- The visible boundary text says model-generated/unreviewed, local-only, and no
  automatic execution. It does not claim that investment advice is forbidden.

## Acceptance

- Desktop 753/1280 and mobile 390 have zero horizontal overflow.
- Same-state reference/implementation comparisons end with no P0/P1/P2 visual
  defects and `design-qa.md` status `passed`.
- Focused tests cover attack, wait, defense, unavailable, exact upstream replay,
  citation disclosure, coherent projection tamper and output-hash tamper.
- This story does not change the API, scheduler, Desktop output or installed
  LaunchAgent.
