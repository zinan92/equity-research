# Market Regime Daily v2 · approved product and visual contract

Status: S0 approved baseline only. Parent tracking issue: #738. Story: #739.
This contract authorizes later scoped stories; it does not change a route,
provider, model, API, scheduler, launch agent or production page by itself.

## User outcome and use moment

Before the A-share open, Park can open one local page and understand within
90 seconds:

1. what the global market is primarily pricing;
2. the current **market posture**;
3. the observable transmission chain behind that synthesis;
4. which assets contradict it; and
5. exactly two observable conditions that would invalidate it.

This is a cross-asset research explanation, not personalized investment
advice. `进攻 / 等待 / 防守 / 未知` describes the market posture. It never tells
the reader to buy, sell, hedge, hold cash, change a position or expect a return.

## Approved information hierarchy

The approved white vertical mockup is the visual and information-architecture
baseline. The page reading order is fixed:

1. one dominant market posture;
2. one synthesis paragraph answering “全球市场当前在定价什么？”;
3. one vertical, evidence-linked transmission chain;
4. one five-session cross-sectional comparison;
5. at least one contradiction;
6. exactly two observable falsifiers; and
7. the completed-daily charts and deeper evidence.

Charts, deterministic scores and intraday state are supporting evidence. They
must not become co-equal headlines or displace the single synthesis above the
fold. Risk On/Off, offense/defense, technology/dividend and leadership remain
useful deterministic dimensions, but the reader sees them reconciled under one
dominant posture instead of four unexplained badges.

The following combination is valid and must not be rendered as a product
contradiction: `risk_on + leaning_defense` means risk appetite is intact while
leadership is defensive. Similar mixed states need an explicit synthesis,
coverage disclosure and contradiction list rather than a forced pure regime.

### Visual tokens

- Default canvas: warm paper white `#f6f5f1`; dark theme remains optional.
- Primary text: `#17191c`; soft primary: `#34383d`; secondary: `#60666d`;
  annotation: `#8b9198`.
- Market posture colors: attack `#17804a`, wait `#a86f0d`, defense `#c94335`.
- Asset return colors are a separate semantic system. Posture color answers
  “what is the market posture”; return color answers “what moved”.
- Chinese serif display type is reserved for the posture and synthesis;
  sans-serif is used for UI; monospaced figures are used for market data.
- Desktop preserves a narrow vertical research-note rhythm. Mobile becomes one
  column with no horizontal overflow; the posture, synthesis and confidence
  remain visible before the evidence chain.

### Approved discovery evidence

The discovery evidence below freezes appearance and hierarchy, not market facts:

| Artifact | SHA-256 | Meaning |
| --- | --- | --- |
| Approved 768 px light/defense capture | `57e5ea474eca1ca534e94ae3822ae806703604b7e27250c34efc8dc98dc0c2ff` | Desktop hierarchy and light tokens |
| Approved 390 px light/current capture | `23c5991aa5bbdf7813fc3f1c40d1163561bd0cc456e78b8b86fd9086ac16aa3c` | Mobile collapse and first-screen order |
| Discovery evidence pack | `6d3638e1fbf4b24f63fe7a711e837ece0851fb9dcf6fb643ea3dd1c428e6a0c0` | Test-only narrative/data shape |

The local prototype and its historical scenario cases are discovery fixtures.
They cannot enter `current`, dated history, API payloads or acceptance as real
market evidence.

## Route and horizon contract

Daily v2 supersedes only the first-screen information architecture in
`web-and-local-service.md`:

- `/market-regime` becomes the completed-daily macro home described here.
- `/market-regime/live` preserves the existing 15-minute-target Live v1 reader.
- A small, honest status entry may link between them, but the values remain
  separate and retain their own time identities.

The existing structural model, `market-regime-api-v2`, intraday collectors,
overlay history, 15-minute scheduler and rollback behavior remain frozen until
their own later story explicitly changes a route projection. Intraday data may
confirm or diverge from structure on `/market-regime/live`; it may never rewrite
the daily headline, evidence pack or history.

## Deterministic semantics

Code remains authoritative for prices, returns, rate changes, trends, coverage,
time skew, contradiction candidates and confidence inputs. The LLM does not
calculate or override them.

### Posture

The narrative layer may select only `attack`, `wait`, `defense` or `unknown`
from frozen deterministic inputs. That output remains
`model_generated_unreviewed`, read-only, non-actionable and non-publishable.
`unknown` is required when the evidence cannot support a coherent posture.

### Confidence

Confidence is code-owned and combines four visible factors:

- accepted evidence coverage;
- cross-asset directional agreement;
- cross-market close skew; and
- the number and materiality of contradictions.

The exact formula and thresholds belong to a later evidence-pack story. The
LLM may explain the result but cannot increase, relabel or hide it. Missing
critical inputs or more than the accepted close-skew threshold must degrade the
state honestly.

## Evidence and unit contract

Every displayed number and factual narrative claim resolves to an evidence ID
that carries source identity, immutable content hash, session, provider/source
timestamp, observation/receipt time where applicable, quality and unit.

There is no claim that “全部市场同为某日完成日线”. The homepage instead shows:

- one joint judgment time derived from the frozen bundle;
- each asset's latest completed session and close time; and
- the measured cross-market close skew.

### Instruments and explanatory factors

| Key | Role | Display semantics | Required behavior |
| --- | --- | --- | --- |
| S&P 500, Nasdaq, Shanghai, STAR 50, WTI, Gold, Silver, KOSPI, Nikkei | Existing primary charts | Completed-daily OHLC and returns | Reuse the verified nine-chart authority; no demo bars |
| VIX | Existing risk probe | Level, completed-daily change and evidence | Reuse the verified probe authority |
| DXY | New macro factor | Index level and completed-daily return | Requires a new provider/source contract or `unavailable` |
| US2Y, US10Y | New macro factors | Yield level in percent; five-session change in **basis points** | Requires a new authoritative rates contract or `unavailable`; never label the change as a price return |
| 2s10s | Derived macro factor | `US10Y - US2Y`, level and change in basis points | Must bind the exact two source rows and derivation receipt; no independent guessed value |

Treasury yields and the curve are rate levels, not price-return instruments.
They use a line/sparkline or compact factor row, not a candlestick price chart.

DRAM is deferred. It cannot block Daily v2 and cannot be added until a separate
issue freezes its canonical identity, source stability, unit and rights scope.

## News and causal language

Price/rates evidence may ship without news. An event candidate may enter a
later evidence pack only when it preserves the original article/event identity,
source, URL, publication time, capture time, source tier, health and content
hash. A prior newsletter or LLM-written 财经日报 is not source evidence.

News can support only a `plausible` driver unless an independent contract proves
more. The UI and narrative must distinguish:

- `supported`: directly supported by frozen market or source facts;
- `plausible`: a candidate explanation with citations but unproven causality;
- `contradiction`: observable evidence inconsistent with the dominant story;
- `unavailable`: required evidence could not be accepted.

No page or prompt may turn co-movement, a headline or generated prose into
price-proven causality.

## LLM narrative contract

The LLM is a separate compiler after deterministic evidence. It receives only a
frozen, size-bounded evidence pack plus untrusted candidate text isolated as
data. It must return a strict schema containing:

- one posture enum and one synthesis;
- a finite transmission chain with evidence IDs and status per step;
- at least one contradiction with evidence IDs;
- exactly two falsifiers using observable frozen fields;
- a prose explanation of the code-owned confidence; and
- a source-boundary disclosure.

Every numeric claim must match a frozen field and unit. Every factual claim must
cite known evidence IDs. Unknown IDs, altered numbers, unsupported thresholds,
causal upgrades, prompt instructions inside source text and trading language
fail validation.

Provider metadata, model, prompt/schema version, evidence-pack hash, output
hash, validation result and generation time are persisted in an immutable
receipt. On missing key, timeout, provider error, invalid schema, citation
failure or unsafe output, the same evidence identity publishes a conservative
**deterministic fallback**. It discloses that the LLM explanation is unavailable
and never reuses stale prose from an older pack.

## Runtime and history

- The existing 4h/12h structural scheduler remains a check cadence.
- A new daily judgment is compiled and published only when the accepted
  completed-daily evidence identity changes.
- Daily artifacts, latest pointer, API/health and failure receipts use a
  separate namespace and rollback boundary from `market-regime-api-v2`.
- A daily failure cannot delete, mutate or roll back the existing Live v1 API.
- History contains real dated, verified daily bundles only. Mock scenario tabs,
  fixtures and duplicated polls never become history entries.

## Truth, rights and release boundary

Daily v2 remains local/private evaluation. Yahoo/Tencent evidence stays
`supplementary_only`, `publication_eligible=false` and `action_eligible=false`.
An attractive page, HTTP success or LLM output does not prove data rights,
reliability, publication permission or investment-advice compliance.

No member distribution, public/team-hosted link, commercial deployment,
personalized holdings, alert, payment, order, position or broker surface is
authorized by this contract. A separate, provider/scope/deployment-bound rights
receipt and product approval is required before any of those claims can change.

## Sequential delivery gates

Issue #738 owns the program. Stories execute in this order with one issue,
branch and PR each:

1. S0 contract/baseline (this document);
2. macro data authority;
3. optional event-candidate source boundary;
4. Evidence Pack v1;
5. narrative compiler;
6. daily bundle/API/runtime;
7. approved product surface and route migration; and
8. exact-main deployment plus five completed trading-day receipts.

The optional event-candidate integration may be deferred without blocking a
price-and-rates Daily v2. Deployment cannot claim private-beta reliability
until desktop/mobile/light/dark/no-data/no-key/error acceptance passes and five
consecutive completed trading days have auditable receipts.
