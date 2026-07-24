# N3-S8 · 20-company company-falsifier evidence

## Result — strict falsifier gate met

The unchanged N3-S5 20-company selection completed with **20/20** accepted,
page-bound issuer-disclosed risk conditions. Each accepted row binds one
official CNINFO URL, full-document SHA-256, one-based page locator, known-at
timestamp and deterministic evidence ID. Generic risk headings without an
observable weakening condition are rejected as gaps.

| Field | Value |
| --- | --- |
| Runtime receipt | `n3-falsifier-evidence-0ef0c3c1052ccc7e.json` |
| Receipt SHA-256 | `0ef0c3c1052ccc7e2aa633ff1e0f7d1de17271200ce75bc2e20ad59880d8e032` |
| Exact N3 selection identity | `397863343d6f6800726f0dfa9e01fd54bf4079b8a14a837ee8f9ba5a8abea75b` |
| Requested / resolved | 20 / 20 |
| Accepted / gaps | 20 / 0 |

## Collection boundary

CNINFO's large PDFs intermittently terminate long single-stream downloads.
The collector therefore uses bounded standard HTTP Range reads against the
same allowlisted official URL and assembles bytes only after the completed PDF
matches the pre-existing cited SHA-256. It does not use a mirror, cached prior
file, alternative provider or benchmark text. Pages without native readable
text remain unavailable: this task does not OCR a whole annual report merely
to fabricate a risk condition.

## R2 effect

R2 now reports `falsifier: 20/20`, `financial_delivery: 20/20`, and `layer:
20/20`. R2 is still **partial** because company moat and market-future
evidence remain 0/20. Issuer-disclosed risks are not valuation, Tier A/B,
target-price, position or action evidence.

## Reproduction

```bash
python3 scripts/refresh_n3_falsifier_evidence.py \
  --runtime-root /Users/wendy/Documents/equity-research-n3-s8d-runtime
python3 scripts/verify_r2_ai_compute_world_model.py \
  /Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json \
  --financial-delivery-receipt /Users/wendy/Documents/equity-research-n3-s7d-runtime/n3-financial-delivery-e3cd6e06ae0993b7.json \
  --falsifier-evidence-receipt /Users/wendy/Documents/equity-research-n3-s8d-runtime/n3-falsifier-evidence-0ef0c3c1052ccc7e.json
```
