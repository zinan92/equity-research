# M3 Moutai generic-model judgment evidence

- Issue: #636
- Official narrative receipt:
  `e4-official-narrative-evidence-v1:a520cc7cd01ddbbdbd721ee689fa31f95936e19c54c210872807f5cc74d8d0da`
- Official document: `1225114741`
- PDF:
  `https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF`
- Raw hash:
  `474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288`
- Narrative coverage: 86 resolved blocks across 34 pages; 202 unresolved
  excerpts retained.
- Model receipt:
  `e4-model-judgments-v1:630a6c847bbbfdae4010c4aed71577c1892ab4d593ef4902f4c70366ab1f8892`
- Model calls: 27 completed `deepseek-v4-pro` calls and 27 response hashes.

## Outcome

- Accepted through the same generic generator:
  `investment_thesis`, `moat_assessment`, `risk_register`,
  `falsification_tests`, `action_triggers`, `accounting_checks`,
  `operating_kpis`, `margin_bridge`.
- Validation-failure MISSING: `monitoring_kpis`.
- Name-swap specificity: 11/11 sentences, 100%.
- Concrete-sentence ratio: 11/11, 100%.
- Numeric traceability: 20/20 tokens, 100%.
- Source scan: zero generator f-strings and zero issuer hardcoding.
- All accepted items remain `ai_generated_judgment_unreviewed`.

## Same-path proof

Both issuers invoke:

```text
scripts/run_e4_model_judgments.py
product/data_core/e4_model_judgments.py
scripts/verify_e4_model_judgments.py
```

There is no Moutai or CATL branch in the generator.  The only issuer-specific
values are frozen identity and official evidence supplied in the receipts.

## Verification

- Full product suite: 622 passed, 1 skipped.
- Baseline: passed with 622 tests.
- Cross-company research verification: passed for five issuers.
- Moutai model verifier: passed; 8 available, 11/11 specific sentences,
  20/20 numeric tokens.
- Gitleaks history and working tree: no leaks.
- High-risk code review: no remaining P0/P1.

## Gotchas

- The narrative extractor retains page-level source text; it does not create
  research judgments.
- The generic capture core requires an official CNINFO URL, document identity,
  frozen raw PDF hash, and upstream financial-receipt SHA before it may emit
  the official truth boundary.
- A model-authored structured MISSING reason remains MISSING.
- Successful generation is not human review and cannot complete a chapter or
  promote Tier.
