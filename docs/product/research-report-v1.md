# Research report contract v1

`research-report-v1` is the single content and rendering contract for every company report. It standardizes structure, not conclusions: CATL and Tesla must share the same eight modules and the same order, while market-specific accounting, currency and disclosure regimes remain explicit.

## Authoritative module order

| Order | Module ID | Required content |
|---:|---|---|
| 01 | `executive_summary` | identity, as-of, conclusion, position semantics and validation conditions |
| 02 | `investment_thesis` | source-bound facts, inferences and assumptions |
| 03 | `business_and_industry` | business model, industry position, competition and management |
| 04 | `financial_quality` | periodized financial quality and measurement units |
| 05 | `framework_assessment` | deterministic research framework and methodology |
| 06 | `valuation` | method, scenarios, assumptions and issuer currency |
| 07 | `catalysts_risks` | catalysts, risk triggers, falsification and watchlist |
| 08 | `evidence_ledger` | source ledger, evidence boundary, source contract and disclaimer |

The manifest in `product/report_contract.py` is authoritative. Desktop, 390px mobile and print/export must render from that manifest in the same order. An unknown, missing or reordered module is a hard error; it is never silently dropped.

## Identity and measurement semantics

- Identity requires ticker, company name, exchange, issuer market, reporting currency and reporting standard.
- v1 supports explicitly mapped CN, HK and domestic US issuer regimes: CNY/PRC GAAP, HKD/HKFRS-IFRS and USD/US GAAP. An unsupported exchange or a foreign private issuer using a different presentation standard must fail closed until a new mapping/schema is added.
- Monetary fields inherit the issuer currency unless they declare an explicit override.
- Price values use issuer currency per share. Financial-statement amounts ending in `_yi` use the contract's explicit `100,000,000` scale and render as `亿元`, `亿港元` or `亿美元`; the UI must not hard-code an A-share unit.
- `percent` and `percentage_point` are different units. A 2% growth rate is not a 2 percentage-point change.
- Market data time and research knowledge cutoff are separate required fields for runtime reports.

## Required, optional and nullable fields

- Required report identity/control fields: `ticker`, `name`, `exchange`, `title`, `industry`, `as_of`, `known_at`, `data_mode`, `research_status`, `research_depth`, `report_version`, `generated_from.snapshot_id` and `report_contract`.
- All eight module payloads are required. Their renderer-critical nested fields are required by `research-report-payload-v1.schema.json`; an arbitrary non-empty object is rejected.
- Optional enrichment fields include `ai_narrative`, `narrative_provider`, `update_diff`, `portfolio_context`, `publication_approval`, `stress_test` and model-specific supporting blocks. They cannot add, remove or reorder standard modules.
- Nullable values are restricted to measurements that can genuinely be unavailable, such as PE/PB or selected financial ratios. Required prose, source IDs, triggers, module arrays, identity and disclaimer are never nullable.
- A deep valuation requires scenarios and an earnings bridge; a quantitative baseline instead requires explicit `status` and `reason`. The two are not interchangeable.

## Claim and absence semantics

Claims use one of `fact`, `inference`, `assumption` or `risk`.

- facts and inferences require source IDs that exist in the report ledger;
- assumptions require a stated method;
- risks require both source support and an observable trigger;
- `missing_evidence` means the module applies but evidence is incomplete, so the module stays visible with a reason;
- `not_applicable` means the concept does not apply to the issuer or market. It cannot hide missing evidence.

The JSON Schema validates the envelope. `validate_report_contract()` applies the stricter semantic and cross-field checks. Both are part of the contract.

Runtime validation uses the mature Draft 2020-12 `jsonschema` implementation against both the contract envelope and the renderable payload schema. Source IDs must be unique; every rendered source carries document identity, type, strength, knowledge time and provenance, with HTTPS allowlisting for external URLs. Market snapshots additionally bind the generated snapshot ID. Source knowledge time cannot exceed the report cutoff.

## Cross-company truth sets

The fixtures below prove structural parity only:

- `product/tests/fixtures/report_contract/catl.structure.json`
- `product/tests/fixtures/report_contract/tesla.structure.json`

They deliberately set `truth_set.scope=structure_only` and `is_live_research=false`. They contain no current data, rating, valuation or position advice. CATL uses CN/CNY/PRC GAAP and Tesla uses US/USD/US GAAP; all module IDs, order, anchors and content paths remain identical.

Actual product-renderer evidence is recorded in `evidence/m1-catl-product-contract-receipt.json`: desktop and 390px Web return the exact manifest order, and the 733px print audit reports zero overflow. Its temporary test database scope is explicit and is not a current investment conclusion.

With a verified deep/baseline test server running, the DOM contract can be reproduced with:

```bash
cd product
npm ci
CHROME_PATH="/path/to/Chrome" npm run verify-report-contract-dom -- --base-url http://127.0.0.1:8877/ --tickers 300750.SZ,600519.SH
```

The check runs desktop and 390px layouts and also removes a required node to prove the client rejects an incomplete DOM.

## Migration from the pre-contract report

1. Build the existing deterministic report payload as before.
2. Call `attach_report_contract()` before artifact binding and report hashing.
3. Render only when the schema version and exact manifest order are supported.
4. Replace hard-coded currency and disclaimer text with payload/contract values.
5. Bind publication identity, HTML metadata and render receipt to schema and contract versions.
6. For incomplete company research, keep applicable modules visible as `missing_evidence`; do not manufacture prose or targets.

Breaking a module ID, order, meaning or required field requires a new major schema version. Additive clarification within the same semantics may increment `contract_version` after fixtures, tests, migration notes and renderer support are updated together.
