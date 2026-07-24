# E4-S4f · 100 ticker official-evidence baseline

## Result

The 2026-07-24 runtime-only corpus resolved all 100 real security-master identities.
It captured 40 current official primary filings and recorded 60 issuer-level failures.
The subsequent partial-model compilation produced 40 real, evidence-bound Report
Models. All 40 remain Tier C / `no_action`; no Tier A/B or numeric/page-audit
credit was created.

| Gate | Threshold | Observed | Result |
| --- | ---: | ---: | --- |
| real identities | 100 | 100 | pass |
| real Report Models | 95 | 40 | fail |
| Tier A/B | 80 | 0 | fail |
| numeric + page audits | 20 | 0 | fail |

## Runtime receipts

- Official-evidence batch: `115bdd8d6ac1f5c5` (40 captured, 60 failed).
- Partial-model batch: `b27d7e8c8cc752a1` (40 compiled, 60 blocked).
- Strict acceptance receipt: `b24009621a40897fc0336b86ef0a4fa55a70967158d1f4626159666c7ab76609`.

Receipts, PDFs and per-ticker detail remain in ignored `product/runtime/`; this
document intentionally records hashes and aggregate counts only.

## Interpretation and next gate

This is a failed acceptance baseline, not an accepted R3 release. The 40 model
rows are blocked by missing market/fundamentals, valuation, sell-side and
industry-position inputs; the 60 others retain their source-specific official
discovery or document-capture failures. The next implementation story must
expand real official-source coverage and bind the remaining required components
without treating this baseline, cached data, or fixtures as evidence credit.
