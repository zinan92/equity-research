# Retired Industry Intelligence Snapshot

## Outcome

The former code-gated industry-intelligence library has been retired from product-serving paths. Its historical segment, materials and dossier views are benchmark-only research artifacts, not product data.

## Retired access contract

- A one-time access code is a 32-character, high-entropy secret created from the existing invite store.
- The raw code is shown only when it is created and only its hash is stored.
- Redemption is atomic and limited to an invite whose `max_uses` is exactly one.
- Redemption creates an internal guest identity; no visitor email, name, or password is collected.
- Existing owner and member email/password login remains available.
- The historical endpoints remain entitlement-gated and now return `410 industry_intelligence_unavailable`.

## Archived data boundary

`product/data/industry-intelligence-v1.json` was removed because it was built
from an archived benchmark payload. The builder may write only below the
read-only `research/ainiusq-niu/derived/` boundary and rejects output below
`product/`.

No overview or dossier fallback is permitted. A replacement requires canonical
E1--E3 evidence and publication through the authority path.

## Truth boundary

- A captured public-web snapshot is benchmark research, not canonical evidence.
- Archive scores, ratings, dossier text and derived judgments must not appear in API responses, reports or product fallbacks.

## Read APIs

- `GET /api/industry-intelligence` returns explicit unavailability until canonical data exists.
- `GET /api/industry-intelligence/dossiers/{code}` returns explicit unavailability until canonical data exists.

## Verification

```bash
python3 -m unittest product.tests.test_industry_intelligence product.tests.test_dashboard product.tests.test_private_beta_http
python3 -m unittest discover -s product/tests -q
node --check product/static/app.js
```
