# N3-S5 · 20-company dossier batch baseline

## Result — strict threshold not met

The real, sequential CNINFO filing replay completed with **19/20** compiled
evidence-bound dossiers and one typed transport failure. The N3-S5 requirement
is at least 20 compiled dossiers, so this run is an explicit failed acceptance
baseline — not a completed 20-company milestone.

| Field | Value |
| --- | --- |
| Runtime receipt | `n3-dossier-batch-0bedbe4c38e01339.json` |
| Receipt SHA-256 | `0bedbe4c38e01339539fa516ea308f5835185c0d63264c725a0e45ff45cf05c4` |
| Exact selection identity | `397863343d6f6800726f0dfa9e01fd54bf4079b8a14a837ee8f9ba5a8abea75b` |
| Known at | `2026-07-24T15:19:53.979595Z` |
| Requested / resolved | 20 / 20 |
| Compiled / `no_action` | 19 / 19 |
| Failed | 1 |

## Failure taxonomy

| Ticker | Failure type | Detail |
| --- | --- | --- |
| `601138.SH` 工业富联 | `TimeoutError` | `The read operation timed out` while reading its already-cited official CNINFO PDF |

No alternate source was used. The batch did not treat the existing citation as
fresh proof after the refetch failed, and it did not emit a dossier, report,
rating, target, position, or tier credit for the failed row.

## What the 19 compiled rows prove

Each successful row re-fetched the exact existing official PDF URL and verified
its SHA-256 against the E3-S3 page citation before compiling:

```text
official PDF URL/page/raw hash
  → accepted filing Context Pack
  → deterministic dossier
  → offline report contract
  → decision-policy receipt (`no_action`)
```

All 19 retain the same explicit gaps: `market_price`, `valuation`,
`quality_risk_liquidity`, `sell_side`, and `catalyst_profile`. Thus this is
partial evidence-bound coverage only; it is not 19 complete reports or 19
investment recommendations.

## Checkpoint and replay boundary

The runtime-only runner writes a receipt after each terminal row. Resume is
allowed only when the full deterministic selection identity — ticker, URL,
page, and expected raw hash for all 20 positions — matches exactly. Compiled
rows with matching cited raw hash are reused; failed rows are retried. A changed
selection fails closed instead of combining two different batches.

The next source-recovery ticket must resolve `601138.SH` from the same official
CNINFO citation or record a new official, page-cited source under a new input
identity. It must not relax the 20-company threshold.
