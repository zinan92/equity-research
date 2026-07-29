# M4 · Real model judgment report recompilation

Issue: #638

## Outcome

The same receipt-bound judgment and report path recompiled both issuers. No
C1 required input, Tier policy, B6 policy, decision-policy threshold or
review state changed.

| Ticker | Before M4 | After M4 | Unreviewed | Tier |
| --- | --- | --- | --- | --- |
| 300750.SZ | 5 FULL / 10 PARTIAL / 3 MISSING | 5 FULL / 10 PARTIAL / 3 MISSING | 7 | B |
| 600519.SH | 4 FULL / 3 PARTIAL / 11 MISSING | 4 FULL / 8 PARTIAL / 6 MISSING | 8 | B |

CATL's counts remain unchanged because two prior invalid judgment inputs were
removed while the seven validator-accepted real model outputs replaced the
valid coverage. Moutai gains five PARTIAL chapters from real, issuer-specific
judgments. No judgment-backed chapter is FULL.

## Eighteen-section terminal state

| Section | CATL | Moutai |
| --- | --- | --- |
| executive_summary | FULL | FULL |
| investment_thesis | PARTIAL · pending_judgment_review | PARTIAL · pending_judgment_review |
| business_model | PARTIAL | MISSING |
| industry_structure | PARTIAL | MISSING |
| competition_and_moat | PARTIAL · pending_judgment_review | PARTIAL · pending_judgment_review |
| management_and_governance | FULL | MISSING |
| revenue_quality_and_kpis | PARTIAL · pending_judgment_review | PARTIAL · pending_judgment_review |
| profitability_and_earnings_quality | PARTIAL | PARTIAL · pending_judgment_review |
| cash_flow_and_balance_sheet | FULL | FULL |
| accounting_quality | PARTIAL · pending_judgment_review | PARTIAL · pending_judgment_review |
| forecasts_and_consensus | MISSING | MISSING |
| valuation | PARTIAL | PARTIAL |
| macro_policy_and_costs | MISSING | MISSING |
| catalysts_and_events | MISSING | MISSING |
| risks_and_falsification | PARTIAL · pending_judgment_review | PARTIAL · pending_judgment_review |
| decision_framework | FULL | FULL |
| monitoring_and_action_triggers | PARTIAL · pending_judgment_review | PARTIAL · pending_judgment_review |
| evidence_and_methodology | FULL | FULL |

Tier reasons for both reports are `partial_or_missing_sections` and
`investment_action_fields_blocked`.

## Receipt and reader evidence

- CATL judgment source:
  `e4-model-judgments-v1:a1398e135d132d6b547f70217fa8026e601a61cac3a800657550b88a6cdd9fb0`.
- Moutai judgment source:
  `e4-model-judgments-v1:630a6c847bbbfdae4010c4aed71577c1892ab4d593ef4902f4c70366ab1f8892`.
- CATL HTML and receipt:
  `artifacts/e4-reports/300750.SZ.html`,
  `artifacts/e4-reports/300750.SZ.receipt.json`.
- Moutai HTML and receipt:
  `artifacts/e4-reports/600519.SH.html`,
  `artifacts/e4-reports/600519.SH.receipt.json`.
- Review queues:
  `artifacts/e4-reports/300750.SZ.judgment-review-queue.json` (7 items) and
  `artifacts/e4-reports/600519.SH.judgment-review-queue.json` (8 items).
- Independent cross-check:
  `artifacts/e4-reports/e4-m4-model-report-verification.json`.

Each queue item contains the complete model body, source receipt, review
writeback shape, and every cited `document_id`, page, anchor and direct PDF
page URL. The report header visibly states the exact unreviewed count.

## Navigation change

CATL already had all five navigation questions at least PARTIAL; no question
newly became answerable, although its judgment content now comes from the real
model receipt. Moutai newly makes “壁垒” and “推翻信号” answerable at PARTIAL.
Its industry-position question remains MISSING.

## Known missing outputs

- Both issuers: `monitoring_kpis` failed strict generation/quote validation.
- CATL: `margin_bridge` failed strict generation validation.
- The other MISSING/PARTIAL inputs shown in the report are independent C1
  coverage gaps and were not replaced with templates, fixtures or proxy facts.

## Validation

- Focused model/wiring/report tests.
- Full product unit-test suite.
- `python3 scripts/verify_baseline.py`.
- `python3 scripts/verify_cross_company_research.py`.
- `gitleaks detect --source . --no-banner --redact`.
- Diff red-line check: no `product/static/**`, C1 required-input definitions,
  Tier policy, B6 policy or decision-policy files changed.
