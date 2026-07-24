# N3-S7 · 20-company PIT financial-delivery baseline

## Result — strict 20-company financial gate not met

The real A4-backed PIT financial batch completed all 20 N3-S5 identities, but
only **11/20** rows supplied a real, publishable four-source financial packet
with a latest report period and known-at identity. Nine rows were explicitly
rejected as `packet_validation_failed`; the R2 financial-delivery gate is
therefore 11/20 and remains below its unchanged 20-company threshold.

| Field | Value |
| --- | --- |
| Runtime receipt | `n3-financial-delivery-4dd8be33a7d924cf.json` |
| Receipt SHA-256 | `4dd8be33a7d924cf3f584f81f2660ca1f31c42534ef6a6c83c4a1225b3f8ca48` |
| Exact N3 selection identity | `397863343d6f6800726f0dfa9e01fd54bf4079b8a14a837ee8f9ba5a8abea75b` |
| Requested / resolved | 20 / 20 |
| Financial delivery available / gaps | 11 / 9 |

Every available row records its `report_period`, `announced_at`, plus real
source key, raw hash, manifest hash and known-at timestamp for fundamentals,
balance sheet, income statement and cash flow. These are PIT input receipts,
not valuation results.

## Typed gaps

The following tickers were not promoted: `000063.SZ`, `000977.SZ`,
`002050.SZ`, `300054.SZ`, `300308.SZ`, `300346.SZ`, `300502.SZ`,
`300750.SZ`, and `603228.SH`. Each has
`packet_validation_failed` and `missing_latest_financial_period`; none receives
financial-delivery coverage from a filing, a cached value, or another ticker.

## R2 effect

The R2 audit now reports `financial_delivery: 11/20` with source
`n3_pit_financial_delivery`. It remains `partial`: financial coverage does not
repair the missing moat, market-future or falsifier evidence, and it does not
produce a target price, position, Tier A/B or action.

## Reproduction

```bash
python3 scripts/refresh_n3_financial_delivery.py \
  --runtime-root /Users/wendy/Documents/equity-research-n3-s7-runtime
python3 scripts/verify_r2_ai_compute_world_model.py \
  /Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json \
  --financial-delivery-receipt /Users/wendy/Documents/equity-research-n3-s7-runtime/n3-financial-delivery-4dd8be33a7d924cf.json
```

The next recovery must fix the same A4/PIT source contract or leave the nine
rows as gaps. It may not lower the 20-company requirement.
