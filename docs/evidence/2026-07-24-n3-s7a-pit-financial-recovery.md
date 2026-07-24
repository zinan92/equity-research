# N3-S7a · 20-company PIT financial-delivery recovery

## Result — strict financial-delivery gate met

The unchanged N3-S5 20-company selection now completes with **20/20** real,
publishable four-source PIT financial packets. Each available row has a latest
report period, announcement date and source/raw/manifest/known-at identity for
fundamentals, balance sheet, income statement and cash flow.

| Field | Value |
| --- | --- |
| Runtime receipt | `n3-financial-delivery-e3cd6e06ae0993b7.json` |
| Receipt SHA-256 | `e3cd6e06ae0993b7c864ec0c4094c6e87e2677bbbe06760b778256acd50760d4` |
| Exact N3 selection identity | `397863343d6f6800726f0dfa9e01fd54bf4079b8a14a837ee8f9ba5a8abea75b` |
| Requested / resolved | 20 / 20 |
| Financial delivery available / gaps | 20 / 0 |
| Retry policy | at most 3 isolated current-source attempts per ticker |

## Failure classification and recovery

The original nine gaps were first reproduced under the same A4 source
contract. Eastmoney can include a scheduled disclosure whose `NOTICE_DATE` is
later than the raw capture's `known_at`. Those rows remain in the immutable raw
capture but are now excluded before a PIT record is accepted; their dates are
not rewritten. This restores the latest *already disclosed* period without
allowing future-visible facts.

The next replay exposed a separate wiring error: a Tencent daily-bar timeout
could make the shared market-and-financial packet fail even when all four
financial sources were real and publishable. N3-S7 checks only its declared
four financial sources; the daily-bar gap remains visible to the market path
and is not hidden or converted to a financial fact.

Two fresh 20-company replays reached 19/20 with a different transient source
failure each time. The runner therefore retries only a missing, non-publishable
four-source financial packet, up to three isolated pulls of the exact same A4
adapters. It never reads a prior result, cache, stale period or alternate
provider as a fallback. The final receipt records per-row `collection_attempts`.

## R2 effect

The R2 audit now reports `financial_delivery: 20/20`, alongside `layer: 20/20`.
R2 remains **partial**: moat, market-future and falsifier evidence are each
still 0/20. This recovery creates no valuation, Tier A/B, target-price,
position or action credit.

## Reproduction

```bash
python3 scripts/refresh_n3_financial_delivery.py \
  --runtime-root /Users/wendy/Documents/equity-research-n3-s7d-runtime
python3 scripts/verify_r2_ai_compute_world_model.py \
  /Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json \
  --financial-delivery-receipt /Users/wendy/Documents/equity-research-n3-s7d-runtime/n3-financial-delivery-e3cd6e06ae0993b7.json
```
