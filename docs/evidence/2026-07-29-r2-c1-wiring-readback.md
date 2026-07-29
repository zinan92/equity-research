# R2 → C1 wiring readback

## Real-run sources

The R2 acceptance rerun passed with receipt
`r2-ai-compute-world-model-acceptance-v1:8d0b6122b8ce78edca201ce6299590f27c6b2ef6b12ecef7848758e3c8323989`.
Its N3 dossier source is
`n3-dossier-batch-v1:10dd875e32907e146963ff7161fe5fef9539b9fd3f60f39d67e823aec95c4d21`.

The rerun verifies 12 industry nodes, 108 segments, 30 accepted/page-cited
company positions, and 20 compiled no-action dossiers.  Its runtime artifact
is intentionally outside Git; the C1 wiring records both receipt identities.

## CATL (`300750.SZ`)

- `business_model.company_profile` is supplied by the compiled R2 dossier and
  the accepted CATL position: energy supplier in
  `ai-compute/energy-supply-chain/battery`.
- `industry_structure.industry_profile` is supplied by that issuer-position
  bridge plus the R2 node/segment taxonomy.
- The issuer citation is CNINFO
  [1222806982 PDF, p.2](https://static.cninfo.com.cn/finalpage/2025-03-15/1222806982.PDF),
  raw hash `b4f1713d7b821eb076c102711d177fe942ccc2bc8dd171ae5d7a95799a65b0ad`.

Both sections remain `PARTIAL`: `segment_financials` and `market_size` were
not produced by R2.

## Explicit non-wiring

- `catalyst_calendar` remains missing. R2 contains segment-level catalyst
  profile state, but no issuer-specific future date and mechanism object.
- `600519.SH` and `000001.SZ` remain missing for both R2 profile inputs: they
  have no accepted issuer-specific R2 position/dossier bridge.
