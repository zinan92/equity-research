# Research Section Contract v3

## Decision

Park accepted `docs/dossier-production/samples/300750.SZ-v1.md` as the exact
reader structure. C1 therefore uses its nine numbered chapters verbatim. The
previously merged “产业坐标 / 创始人与团队 / 发展时间线 / 大白话点评”
taxonomy was a redesign and is retired.

The accepted CATL sample contains 3,443 characters inside the nine chapter
bodies and 4,249 characters for the full Markdown artifact. The section
contract therefore targets 3,080–4,620 chapter-body characters; headings,
front matter and Sources are outside that sum. `Sources` remains the publication
appendix. `生产记录` is the ninth canonical chapter.

## Completion semantics

- `MISSING`: no required or optional input exists.
- `PARTIAL`: some material exists but a required input is absent.
- `PARTIAL / pending_judgment_review`: a supplied chapter draft contains
  `ai_generated_judgment_unreviewed`.
- `FULL`: every required input exists and no research judgment is unreviewed.

Chapters 1–8 require a complete `chapter_draft` with non-empty text,
`document_id + page_number + quoted_anchor` bindings and explicit review
identity. Only `human_reviewed_judgment + review_status=approved` is eligible
for FULL. Chapter 9 is deterministic production metadata: it requires the
actual run receipt and source manifest rather than an AI judgment.

Live assessment still requires a B6-passed evidence set. The existing
`assess_any_ticker` ladder is unchanged: all nine FULL may reach Tier A;
otherwise a live-eligible report stays Tier B and target price, position range
and action remain blocked.

## Canonical sections

| order | title / section_id | target | required inputs |
|---:|---|---:|---|
| 1 | 一句话定位 / `one_line_positioning` | 140–240 | `issuer_identity`, `positioning_evidence`, `chapter_draft` |
| 2 | 身份、创始人与治理 / `identity_founder_and_governance` | 220–360 | `issuer_identity`, `management_evidence`, `governance_evidence`, `chapter_draft` |
| 3 | 技术来源与发展史 / `technology_origin_and_development_history` | 380–550 | `timeline_evidence`, `chapter_draft` |
| 4 | 商业模式与业务线 / `business_model_and_business_lines` | 520–750 | `business_evidence`, `operating_evidence`, `chapter_draft` |
| 5 | 财务与经营时间序列 / `financial_and_operating_time_series` | 450–650 | `financial_evidence`, `operating_evidence`, `chapter_draft` |
| 6 | 护城河的证据链 / `moat_evidence_chain` | 420–620 | `moat_evidence`, `falsification_evidence`, `chapter_draft` |
| 7 | 风险、反题材与观察触发器 / `risks_counter_thesis_and_triggers` | 450–650 | `risk_evidence`, `trigger_evidence`, `chapter_draft` |
| 8 | 研究结论与待补问题 / `research_conclusion_and_open_questions` | 200–350 | `synthesis_evidence`, `decision_policy_output`, `chapter_draft` |
| 9 | 生产记录 / `production_record` | 300–450 | `run_receipt`, `source_manifest` |

## Direct consumers

The contract builder, degradation compiler, industry and judgment adapters,
review queue, migration scripts, report compiler, verifiers and
their focused tests all use the corrected IDs. R2 industry material is optional
context inside `business_model_and_business_lines`; it is not promoted into a
new canonical chapter.

`product/research_reports.py` and `product/company_research.py` remain the
separate report-v1 surface until the publication cutover milestone.

## Frozen safety boundary

This correction does not change:

- `product/data_core/research_degradation.py`
- `product/data_core/evidence_gate.py`
- `product/data_core/decision_policy.py`
- `_TIER_ALLOWED`
- `_BLOCKED_FIELDS`

Their byte hashes remain checked by the north-star and section-contract
verifiers.
