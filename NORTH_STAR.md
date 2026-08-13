# North Star — equity-research

> Stable intent. Change this only when Park explicitly changes the product
> destination, approved baseline, or success definition.

## What we are building

A private-beta A-share investment-research product for long-term capital. A
user can enter a ticker and receive a concise decision summary plus a
standardized research report whose claims remain tied to verifiable,
point-in-time evidence.

## Approved product North Star — Market Regime Daily v2

Within the Market Regime product, the reader-facing North Star is the
**Macro World Model · pre-open 90-second judgment** experience represented by
the approved 8898 discovery page. It is not a chart wall and it is not a set
of co-equal labels. Before the A-share open, one local page should let the
reader understand:

1. what global markets are primarily pricing;
2. the single current market posture;
3. the observable transmission chain behind that synthesis;
4. which assets contradict the dominant story; and
5. exactly two observable conditions that would falsify it.

The approved reading order is fixed:

`posture → synthesis → evidence chain → five-session cross-section →
contradictions → two falsifiers → completed-daily charts and deeper evidence`.

The visual baseline is a white, narrow vertical research note: one dominant
headline, clear Chinese serif hierarchy, separate posture/return color
semantics, visible confidence and no mobile horizontal overflow. `进攻 / 等待 /
防守 / 未知` describes market posture only; it never instructs a user to buy,
sell, hedge, change a position or expect a return.

The daily page is an explanation of a frozen completed-daily cross-asset model.
Deterministic code owns facts, units, confidence, time identity and evidence
links. LLM output is downstream explanation only and must fall back honestly
when unavailable. `/market-regime` is the future daily macro home;
`/market-regime/live` remains the separate 15-minute reader and cannot rewrite
the daily judgment.

The 8898 page, its scenario tabs and its example numbers are discovery
references for hierarchy and visual language, not current market evidence or
dated history. The executable details live in
[`docs/market-regime/daily-v2-contract.md`](docs/market-regime/daily-v2-contract.md).

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

- AI-generated prose is never a source of fact; it may only explain frozen
  evidence while retaining its identity.
- Unavailable, stale, fixture, cached, or conflicting inputs remain visibly
  unavailable; they cannot become investment conclusions.
- Existing approved product and UX foundations are changed only through a new,
  recorded approval; do not replace them with a new framework.
- Documentation work does not trigger data refresh, publication, payment,
  production deployment, or a scheduler change.

## Change control

`REGISTRY.md` may report progress through these milestones but cannot redefine
them. Record the rationale for a North Star change in `decision-log.md` and
link the approving decision.
