# L2-M1 · 100-ticker official financial-sequence batch

## Result

The complete 100-ticker acceptance cohort was run sequentially against the
existing CNINFO official-PDF extraction and page validation chain.  The real
financial-sequence receipt is runtime-only; this committed verification record
binds its hash and aggregate outcomes without committing raw PDFs or facts.

| Measure | Result |
| --- | ---: |
| Requested tickers | 100 |
| Exchanges | SZSE 34 / SSE 34 / BSE 32 |
| Report periods attempted | 6 per ticker (2021FY–2025FY, 2026Q1) |
| Available official reports | 492 / 600 |
| Page-bound financial facts | 14,483 |
| Tickers with at least one page fact | 98 / 100 |
| Missing reports | 108 / 600 |

## Receipt lineage and failure taxonomy

- Identity-only input receipt:
  `630acdb221751f3cc576de5e1ad24237b5652a5dba805fe7eb25f9a38ee6b05b`.
  It selects canonical ticker identities only; it is not a financial-fact
  source.
- Official financial-sequence receipt:
  `7534f6a9f3b2c81b93340676e11019f8548631676edee9bb5bd2d6a324fd08fc`.
- Verification artifact:
  `artifacts/evidence/e4-l2-m1-financial-batch-verification.json`.

| Missing reason | Count |
| --- | ---: |
| `official_annual_report_not_captured` | 90 |
| `ticker_collection_timeout` | 12 |
| `page_parse_exception` | 5 |
| `page_parse_timeout` | 1 |

All unavailable periods remain explicitly missing with their captured
diagnostic.  The run uses only official CNINFO PDF facts with document/page
identity; it creates no Tier, target, position, action, or issue #218 credit.
