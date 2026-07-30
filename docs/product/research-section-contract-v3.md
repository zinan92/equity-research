# Research Section Contract v3

## Decision

Park accepted Round 7 as the product's definition of a good research dossier.
C1 therefore uses the nine reader units from
`product/data_core/round7_north_star.py`, rather than mapping them back into the
retired 18-section taxonomy.

The target is 4,200–5,500 Chinese characters across the nine reader sections.
Production record and Sources remain required publication appendices, but they
are not research sections and do not receive Tier credit.

## Completion semantics

- `MISSING`: no required or optional input exists.
- `PARTIAL`: some material exists but a required input is absent.
- `PARTIAL / pending_judgment_review`: any supplied required or optional input
  contains `ai_generated_judgment_unreviewed`.
- `FULL`: every required input exists and none contains an unreviewed judgment.

Every section requires a complete `chapter_draft`. The object must carry
non-empty chapter text, at least one `document_id + page_number + quoted_anchor`
evidence binding, and an explicit review identity. Only
`human_reviewed_judgment + review_status=approved` is eligible for FULL;
`ai_generated_judgment_unreviewed` is PARTIAL, and an absent or unknown status
is rejected. A field-oriented judgment is only transitional
`legacy_judgment_materials`; it can make the material visible but can never
complete a chapter.

Live assessment still requires a B6-passed evidence set. The existing
`assess_any_ticker` policy consumes the resulting nine statuses without a
threshold change: all nine FULL may reach Tier A; otherwise a live-eligible
report remains Tier B and target price, position range, and action stay blocked.

## Canonical sections

| order | section_id | target chars | required inputs | primary annual-report origins |
|---:|---|---:|---|---|
| 1 | `one_line_positioning` | 300–450 | `issuer_identity`, `positioning_evidence`, `chapter_draft` | company profile |
| 2 | `industry_coordinates` | 500–700 | `industry_evidence`, `company_position`, `chapter_draft` | business review |
| 3 | `founder_and_team` | 400–550 | `management_evidence`, `governance_evidence`, `chapter_draft` | directors, supervisors, management; governance |
| 4 | `development_timeline` | 450–600 | `timeline_evidence`, `chapter_draft` | company history; business review |
| 5 | `technology_products_and_business_model` | 650–800 | `business_evidence`, `operating_evidence`, `chapter_draft` | principal business; MD&A |
| 6 | `financials_and_valuation` | 650–800 | `financial_evidence`, `valuation_evidence`, `chapter_draft` | financial statements; official market snapshot |
| 7 | `why_it_can_win` | 450–600 | `moat_evidence`, `falsification_evidence`, `chapter_draft` | competitive advantages |
| 8 | `core_risks` | 450–600 | `risk_evidence`, `trigger_evidence`, `chapter_draft` | risk factors |
| 9 | `plain_language_verdict` | 350–400 | `synthesis_evidence`, `decision_policy_output`, `chapter_draft` | prior chapters; decision policy |

## Migrated direct consumers

| consumer | migration |
|---|---|
| `product/report_contract.py` | v3 schema, nine specs, character targets and status evaluation |
| `product/data_core/e4_vertical_degradation.py` | official page facts feed `financials_and_valuation.financial_evidence` |
| `product/data_core/e4_r2_industry_wiring.py` | accepted issuer-linked R2 material feeds industry coordinates and business evidence |
| `product/data_core/e4_judgment_wiring.py` | old field judgments become optional legacy materials, never chapter drafts |
| `product/data_core/e4_judgment_review_queue.py` | old field approval no longer claims it can promote a Round 7 chapter |
| `scripts/run_e4_m2_research_wiring.py` | market, decision, financial, industry and governance receipts use v3 input keys |
| `scripts/build_e4_l1_m5_reassessment.py` | governance overlay uses `founder_and_team` and v3 builder |
| `scripts/inventory_e4_section_completion.py` | inventories nine sections and shared `chapter_draft` leverage |
| `scripts/compile_e4_m4_report.py` | renders nine-section states and Round 7 navigation |
| `scripts/verify_e4_wired_reports.py` | requires exactly nine sections and binds report, wiring, judgment, queue and HTML identities |
| `product/data_core/research_degradation.py` | interface unchanged; consumes the v3 section tuple generically |
| contract, degradation, wiring, renderer and inventory tests | assert v3 IDs and reject old IDs |

`product/research_reports.py` and `product/company_research.py` belong to the
separate public report-v1 surface. They are not direct C1 section-contract
consumers in M2; M6 owns their publication cutover. Keeping that boundary
explicit prevents a silent claim that the public API already serves Round 7.

## Frozen safety boundary

This migration does not change:

- `product/data_core/research_degradation.py`
- `product/data_core/evidence_gate.py`
- `product/data_core/decision_policy.py`
- `_TIER_ALLOWED`
- `_BLOCKED_FIELDS`

Their byte hashes are verified against
`artifacts/evidence/round7-north-star-baseline.json`.
