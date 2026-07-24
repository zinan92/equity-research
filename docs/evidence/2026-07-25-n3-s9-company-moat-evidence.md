# N3-S9 · 20-company company-moat evidence

## Result — strict moat gate met

The unchanged N3-S5 20-company selection completed with **20/20** accepted,
page-bound issuer-disclosed capability observations. Each accepted row binds an
official CNINFO URL, full-document SHA-256, one-based page locator, known-at
timestamp and deterministic evidence ID. Generic claims without a concrete
capability marker are a gap rather than a moat claim.

| Field | Value |
| --- | --- |
| Runtime receipt | `n3-moat-evidence-3e3be84f79f76c9d.json` |
| Receipt SHA-256 | `6eef6ee0511273ed05dbe49c932e03322ea538404755162ed3ca0421bcd75d07` |
| Exact N3 selection identity | `397863343d6f6800726f0dfa9e01fd54bf4079b8a14a837ee8f9ba5a8abea75b` |
| Requested / resolved | 20 / 20 |
| Accepted / gaps | 20 / 0 |

## Collection boundary

The collector reuses the same official-CNINFO PDF Range downloader as N3-S8.
It accepts only native-text passages containing an issuer-described competitive
or technical advantage and a concrete capability marker. Every completed PDF
must match its cited raw SHA-256. It does not use a mirror, benchmark archive,
alternative provider, whole-document OCR or model inference to create a moat.

## R2 effect

R2 now reports `layer`, `financial_delivery`, `falsifier`, and `moat` at
**20/20**. It remains **partial** because `market_future` is 0/20. A disclosed
capability is not a valuation, Tier, target price, position or action signal.

## Reproduction

```bash
python3 scripts/refresh_n3_moat_evidence.py \
  --runtime-root /Users/wendy/Documents/equity-research-n3-s9b-runtime
python3 scripts/verify_r2_ai_compute_world_model.py \
  /Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json \
  --financial-delivery-receipt /Users/wendy/Documents/equity-research-n3-s7d-runtime/n3-financial-delivery-e3cd6e06ae0993b7.json \
  --falsifier-evidence-receipt /Users/wendy/Documents/equity-research-n3-s8d-runtime/n3-falsifier-evidence-0ef0c3c1052ccc7e.json \
  --moat-evidence-receipt /Users/wendy/Documents/equity-research-n3-s9b-runtime/n3-moat-evidence-3e3be84f79f76c9d.json
```
