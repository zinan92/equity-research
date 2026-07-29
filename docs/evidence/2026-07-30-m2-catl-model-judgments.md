# M2 CATL real-model judgment evidence

- Issue: #634
- Generator receipt:
  `e4-model-judgments-v1:a1398e135d132d6b547f70217fa8026e601a61cac3a800657550b88a6cdd9fb0`
- Model: `deepseek-v4-pro`
- Model calls: 45 completed calls; 45 response hashes
- Frozen financial input SHA-256:
  `c34ab2e4e4177fd90e0a5806814cbfaa325ed85f7b668b125f5fd7815faa8145`
- Frozen narrative receipt:
  `e4-official-narrative-evidence-v1:ad4aecf4459d0e2f7b5aebe19f4d8f28a2d7f4d63995de1934daf4be47c9501e`

## Outcome

- 7/9 runnable judgments accepted:
  `investment_thesis`, `moat_assessment`, `risk_register`,
  `falsification_tests`, `action_triggers`, `accounting_checks`,
  `operating_kpis`.
- `monitoring_kpis` and `margin_bridge` remain MISSING with their exact
  validation errors in the receipt.
- Name-swap specificity: 11/11 sentences, 100%.
- Concrete-sentence ratio: 11/11, 100%.
- Numeric traceability: 12/12 tokens, 100%.
- Source scan: zero generator f-strings and zero issuer hardcoding.
- Every accepted output remains `ai_generated_judgment_unreviewed`.

## Verification

```text
python3 -m unittest discover -s product/tests -q
Ran 619 tests ... OK (skipped=1)

python3 scripts/verify_baseline.py
status=passed; test_count=619

python3 scripts/verify_cross_company_research.py
status=passed

python3 scripts/verify_e4_model_judgments.py \
  artifacts/e4-reports/300750.SZ.judgments.json \
  --out artifacts/e4-reports/300750.SZ.judgments.m2.verification.json
status=passed; available=7; rename=11/11; numeric=12/12

gitleaks detect --source . --no-banner --redact --log-opts=--all
no leaks found

gitleaks detect --source . --no-banner --redact --no-git
no leaks found
```

## Gotchas

- Resume checkpoints are accepted only when outer receipt hash, source
  lineage, content hash, prompt/input/version hashes, model-call fields, and
  call/response cardinality all match.  The final receipt records three prior
  checkpoint identities.
- A single-period absolute value cannot support an unquoted growth or trend
  claim.
- A falsification test must target a future/next formal disclosure; the
  accepted CATL test uses `下一份正式披露` against the frozen `2026Q1`
  baseline.
- Model retry is not human review, and it never changes chapter completion or
  Tier policy.
