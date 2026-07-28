# Six-milestone official-fact handoff

## Result

The six-milestone batch is complete as an evidence-and-decision pipeline. It
does **not** complete #218, create a Tier A/B report, create a target price or
position, or turn any audit assignment into a completed human audit.

| Milestone | Delivered result | Boundary |
| --- | --- | --- |
| M1 | Dual-column facts, retained source instances, column/unit context and cross-year classification are available. | Inconsistent source pairs are `disputed`, not silently reconciled. |
| M2 | The 20-ticker receipt records official-PDF facts, coverage and explicit gaps; local recovery added native-layout and English-report support. | Missing periods/metrics remain missing; no aggregator replacement. |
| M3 | `/tmp/e4-m3-vertical-batch-v2.json`: 20 decision receipts, all `no_action`. | Banks are `not_applicable`; other names remain blocked by missing market/quality/risk/liquidity evidence. |
| M4 | `/tmp/e4-m4-complete-assignments-v5.json`: 20 distinct pending-human-review assignments, 5 `cross_verified`, 15 `unverified`, 0 selected `disputed`. | Assignments are not completed audits and earn no #218, Tier or action credit. |
| M5 | `docs/specifications/valuation-profiles-v1.md` defines manufacturing, consumer and bank input/model differences. | It is design-only; no bank valuation model was introduced. |
| M6 | This handoff, the decision log and REGISTRY record the real output and next decision. | No next implementation is started by this handoff. |

## Five inspectable samples

1. **Cross-verified fact — CATL 2021FY revenue.** `13,035,579.64 万元`,
   consolidated, appears as current period in [2022 annual report p113](https://static.cninfo.com.cn/finalpage/2022-04-22/1213027750.PDF)
   (`1213027750`) and as prior period in [2023 annual report p105](https://static.cninfo.com.cn/finalpage/2023-03-10/1216084559.PDF)
   (`1216084559`).
2. **Disputed fact — CSCEC 2021FY operating cash flow.** Current-period
   `3,902,084,385 元` at [2022 annual report p86](https://static.cninfo.com.cn/finalpage/2022-04-25/1213059469.PDF)
   (`1213059469`) conflicts with prior-period `3,899,648,030 元` at [2023
   annual report p88](https://static.cninfo.com.cn/finalpage/2023-04-26/1216593484.PDF)
   (`1216593484`). It is marked `disputed`, excluded from M4 and requires a
   later restatement/explanation check.
3. **Share-count disclosure — CATL 2025FY.** [2025 annual report p6](https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF)
   (`1225002214`) states total shares `4,563,868,956`; its distribution base
   is `4,531,886,650` after excluding `31,982,306` repurchased A shares. This
   is a share count, not the balance-sheet share-capital amount, and its
   disclosure is for the report's 2025FY proposal context.
4. **Provisional valuation assumption — CATL.** The existing partial-C2
   receipt uses WACC `9%`, terminal growth `3%` and a five-year horizon, all
   labelled `provisional_unreviewed`; no target/position is released from it.
5. **Decision receipt — 000002.SZ.** The M3 receipt is `no_action`,
   `target_range=null`, `position_range=null`, with
   `insufficient_evidence_coverage`, `missing_market_price` and
   `missing_quality_risk_or_liquidity`; `valuation_completeness=missing`.

## Analyst review priority

1. WACC, terminal growth and forecast horizon: highest sensitivity to a future
   valuation conclusion.
2. Bank credit cost, capital, payout and the residual-income/DDM model choice:
   manufacturing FCF DCF remains inapplicable.
3. Cross-year disputed facts: determine whether each is a real restatement or
   an extraction/layout defect before it can become a research input.
4. Market price, liquidity, quality and risk inputs: required before an honest
   decision policy can leave `no_action`.

## Next decision

Do not invite a reviewer until Park decides whether the 20 pending assignments
should enter the existing owner-only audit workstation. A reviewer should first
open the five samples above; any disagreement with a `cross_verified` pair is
evidence against the parser, not a reason to relax the audit standard.
