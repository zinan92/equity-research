# North Star — equity-research

> Stable intent. Change this only when Park explicitly changes the product
> destination, approved baseline, or success definition.

## What we are building

A private-beta A-share investment-research product for long-term capital. A
user can enter a ticker and receive a concise decision summary plus a
standardized research report whose claims remain tied to verifiable,
point-in-time evidence.

## Approved product North Star — Cross-asset K-line World Model

Within the Market Regime product, the reader-facing North Star is an AI
cross-asset tape reader delivered as the **Global Market K-line Daily**. Park's
exact approved product pipeline is:

> 完整 OHLC 日线与跨资产相对关系 → LLM 自主解读 → 资金迁移地图 →
> consistent world model → 可执行交易建议。

The approved 8898 white vertical discovery page remains the attention and
visual baseline, but the product is not a chart wall, a deterministic label
selector or a template-filled scorecard. Before the A-share open, one local
page should let the reader understand:

1. what global markets are primarily pricing;
2. which assets are being repriced up and down relative to one another;
3. where capital plausibly appears to be leaving and entering;
4. the consistent world model that reconciles risk, posture, style and
   leadership, including apparent contradictions;
5. what market-level trading action follows; and
6. which observable conditions would falsify the interpretation and advice.

The approved reading order is:

`world model → capital-migration map → transmission chain → actionable plan →
cross-section → contradictions → two falsifiers → all canonical daily charts
and deeper evidence`.

The visual baseline is a white, narrow vertical research note: one dominant
headline, clear Chinese serif hierarchy, separate posture/return color
semantics, visible confidence and no mobile horizontal overflow. `进攻 / 等待 /
防守 / 未知` remains a description of the tape. A separate advice section may
recommend attack, wait or defend; prioritize, reduce or avoid assets and
styles; and name observable entry, exit and invalidation conditions. Advice is
an intended output. Automatic execution, broker mutation and live-money action
are not.

The daily page gives the LLM bounded, frozen completed-daily OHLC sequences and
code-derived cross-asset relative relationships, not only point features or
chart screenshots. Deterministic code owns source facts, units, time identity,
evidence quality and evidence links. The LLM independently authors the world
model, inferred migration map and advice while citing that frozen context.
Observed repricing and inferred capital migration remain visibly distinct;
price action alone is not presented as literal fund-flow measurement. Provider
failure falls back honestly to evidence without stale interpretation or advice.
`/market-regime` is the future daily macro home; `/market-regime/live` remains
the separate 15-minute reader and cannot rewrite the daily judgment.

The 8898 page, its scenario tabs and its example numbers are discovery
references for hierarchy and visual language, not current market evidence or
dated history. The executable details for the approved next version live in
[`docs/market-regime/kline-world-model-v2-contract.md`](docs/market-regime/kline-world-model-v2-contract.md).
The earlier Daily v2 and K-line pilot contracts remain historical runtime
baselines until the versioned replacement passes acceptance.

## Done looks like

The product can serve its approved research universe with evidence-bound report
models, clear coverage and uncertainty states, and a human-verifiable report
surface. It never presents fixtures, cached data, or AI prose as verified
research. Product completion is measured by the active coverage and release
gates in `REGISTRY.md`, not by the existence of a polished mockup or generated
report alone.

## Approved foundations

| Item | Canonical artifact / reference | Decision date | Do not reinvent |
| --- | --- | --- | --- |
| Product and evidence boundary | `AGENTS.md` | rolling | yes |
| Current state and active release gates | `REGISTRY.md` | rolling | yes |
| Durable decisions and known traps | `decision-log.md` | rolling | yes |
| Canonical product surface | `product/` and its verified artifacts | rolling | yes |

## Milestones to the intent

| # | Milestone | Evidence that it is complete | Status |
| --- | --- | --- | --- |
| 1 | Preserve a canonical, evidence-bound research contract | Product verification commands pass; unavailable inputs remain explicit gaps | complete |
| 2 | Build real, replayable coverage across the approved universe | The current `REGISTRY.md` coverage gate has a source-backed receipt | in progress |
| 3 | Deliver a private-beta research experience on that evidence | Release, access, and research-quality gates pass without fixture or mock claims | not started |

## Non-negotiables

- AI-generated prose is never a source of fact. It may interpret frozen
  evidence and make market-level trading recommendations, but observed facts,
  inferred flows and advice must remain distinguishable and cited.
- Unavailable, stale, fixture, cached, or conflicting inputs remain visibly
  unavailable; they cannot become investment conclusions.
- Existing approved product and UX foundations are changed only through a new,
  recorded approval; do not replace them with a new framework.
- Trading advice does not authorize automatic orders, broker access, portfolio
  mutation or live-money execution.
- Documentation work does not trigger data refresh, publication, payment,
  production deployment, or a scheduler change.

## Change control

`REGISTRY.md` may report progress through these milestones but cannot redefine
them. Record the rationale for a North Star change in `decision-log.md` and
link the approving decision.
