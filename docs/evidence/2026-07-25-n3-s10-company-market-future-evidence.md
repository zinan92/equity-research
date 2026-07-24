# N3-S10 · 20-company company market-future evidence

## Result — final five-question gate met

The unchanged N3 20-company selection completed with **20/20** accepted,
page-bound issuer-disclosed forward market-driver observations. Each row binds
the original official CNINFO URL, full-document SHA-256, a one-based page,
known-at timestamp, observation type and deterministic evidence ID.

| Field | Value |
| --- | --- |
| Runtime receipt | `n3-market-future-evidence-1dd226f975205c35.json` |
| Receipt SHA-256 | `235d7e2acf2d2dd47939f255cc6ce4fba3055a1cb4440b3483bfa449cdfdcc76` |
| Exact N3 selection identity | `397863343d6f6800726f0dfa9e01fd54bf4079b8a14a837ee8f9ba5a8abea75b` |
| Requested / resolved | 20 / 20 |
| Accepted / gaps | 20 / 0 |

## Collection boundary

The collector re-fetches only the cited official CNINFO filing and accepts a
native-text passage only when it combines a forward-looking marker with an
industry, market, demand, customer, downstream, application or supply-chain
context. Generic management aspirations are a gap. Each assembled large PDF
must equal its cited SHA-256; no mirror, benchmark archive, market-consensus
feed, model forecast or whole-document OCR is used.

The resulting observation type is `issuer_disclosed_market_outlook`. It is not
sell-side consensus and does not state a target price, valuation, position,
Tier or action.

## R2 effect

R2 now reports all five company questions at **20/20** and returns `passed`:
layer, moat, financial delivery, market future and falsifier. This is a
research-evidence gate only; its 20 dossier outputs remain `no_action`.

## Reproduction

```bash
python3 scripts/refresh_n3_market_future_evidence.py \
  --runtime-root /Users/wendy/Documents/equity-research-n3-s10b-runtime
python3 scripts/verify_r2_ai_compute_world_model.py \
  /Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json \
  --financial-delivery-receipt /Users/wendy/Documents/equity-research-n3-s7d-runtime/n3-financial-delivery-e3cd6e06ae0993b7.json \
  --falsifier-evidence-receipt /Users/wendy/Documents/equity-research-n3-s8d-runtime/n3-falsifier-evidence-0ef0c3c1052ccc7e.json \
  --moat-evidence-receipt /Users/wendy/Documents/equity-research-n3-s9b-runtime/n3-moat-evidence-3e3be84f79f76c9d.json \
  --market-future-evidence-receipt /Users/wendy/Documents/equity-research-n3-s10b-runtime/n3-market-future-evidence-1dd226f975205c35.json
```
