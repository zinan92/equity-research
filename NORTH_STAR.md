# North Star — equity-research

> Stable intent. Change this only when Park explicitly changes the product
> destination, approved baseline, or success definition.

## What we are building

A private-beta A-share investment-research product for long-term capital. A
user can enter a ticker and receive a concise decision summary plus a
standardized research report whose claims remain tied to verifiable,
point-in-time evidence.

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
