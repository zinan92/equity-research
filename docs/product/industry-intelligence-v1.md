# Industry Intelligence v1

## Outcome

The private research site exposes a code-gated industry-intelligence library with three source-backed views:

1. 38 archived industry-segment three-high nodes.
2. 94 archived semiconductor-material company nodes.
3. 489 complete company dossiers, loaded on demand.

## Access contract

- A one-time access code is a 32-character, high-entropy secret created from the existing invite store.
- The raw code is shown only when it is created and only its hash is stored.
- Redemption is atomic and limited to an invite whose `max_uses` is exactly one.
- Redemption creates an internal guest identity; no visitor email, name, or password is collected.
- Existing owner and member email/password login remains available.
- Industry endpoints require the existing `dashboard` entitlement and are closed to anonymous requests.

## Data contract

The packaged snapshot is `product/data/industry-intelligence-v1.json` with schema
`industry-intelligence-snapshot-v1`. It is deterministically built from the archived browser payload by
`scripts/build_industry_intelligence.py` and carries the source SHA-256, capture date, archive date, and truth boundary.

The overview endpoint omits dossier Markdown so the 489-document corpus is not transferred on initial load. A dossier body is returned only from its code-specific endpoint.

## Truth boundary

- The data is a captured public-web snapshot archived around 2026-07-02, not live market data.
- Three-high coordinates and labels reproduce the archived source methodology; this product does not independently recompute them.
- The 38 segment nodes are not automatically mapped to the 489 dossiers because their taxonomies do not have an exact reviewed crosswalk.
- A dossier link from the 94-company materials map appears only when the source explicitly marks that dossier as present.
- The archived narratives have not passed this repository's canonical evidence gate and are not investment advice.

## Read APIs

- `GET /api/industry-intelligence`
- `GET /api/industry-intelligence/dossiers/{code}`

## Verification

```bash
python3 -m unittest product.tests.test_industry_intelligence product.tests.test_dashboard product.tests.test_private_beta_http
python3 -m unittest discover -s product/tests -q
node --check product/static/app.js
```
