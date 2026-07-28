# E4 existing-module wiring: three-company readback

Issue: #487  
Scope: `300750.SZ`, `600519.SH`, and `000001.SZ` only.

## What was actually wired

`e4_page_level_filing_facts` now projects an official, page-bound `revenue`
fact into C1's `revenue_quality_and_kpis.revenue_history`.  Every projected
row retains its `document_id`, `raw_hash`, `page_number`, `quoted_anchor`,
period, statement scope, unit, currency, and source URL.  It therefore adds a
real required input without changing a C1 requirement, B6 policy, or Tier
policy.

The section remains `PARTIAL`: `operating_kpis` is still absent.  A single
page-bound revenue observation is not represented as a multi-period KPI
series.

## Existing-module readback (not module-name inference)

| proposed module | intended C1 inputs | result for these three tickers | blocker class |
|---|---|---|---|
| `e4_page_level_filing_facts` | `revenue_history`, `audit_opinions` | `revenue_history` wired from official page facts; no audit-opinion extractor/output exists | data-shape mismatch for `audit_opinions` |
| `e4_market_fundamentals_batch` | `market_snapshot`, `current_market`, `cash_flow_history`, `balance_sheet_history` | no qualifying issuer-level output admitted | module uses market/vendor packet components; this ticket forbids aggregated data as real input |
| `decision_policy` | `decision_summary`, `recommendation_policy_output` | no current receipt bound to the three E4 evidence manifests | module exists but no qualifying ticker receipt |
| `event_intelligence` | `policy_events`, `event_timeline` | no current evidence-bound ticker output | module exists but has not produced a qualifying ticker receipt |
| `e4_valuation_receipts` | `valuation_scenarios` | no receipt with the required canonical sources and human assumption receipt | module exists but has not produced a qualifying ticker receipt |
| `e4_valuation_assumptions` | `valuation_assumptions` | no real approved analyst-assumption receipt | module exists but has not produced a qualifying ticker receipt |
| `e4_sell_side_claim_admission` | `broker_estimates` | no reviewed/accepted claims for these tickers | module exists but has not produced a qualifying ticker receipt |
| `e4_valuation_sellside_coverage` | `consensus_history` | no current qualifying ticker output | module exists but has not produced a qualifying ticker receipt |
| `industry_catalysts` | `catalyst_calendar` | no issuer-specific current evidence output | module exists but has not produced a qualifying ticker receipt |
| `industry_profiles` | `industry_profile` | declarative taxonomy only; does not itself supply a ticker-bound evidence object | data-shape mismatch |
| `company_positions` | `company_profile` | no qualifying output for all three; its entries are self-authored review targets, not a current issuer profile receipt | ticker missing / non-runtime hypothesis |

## F10 `segment_financials` verdict

The #112 Eastmoney periodic collector can structurally emit segment revenue,
cost, and profit fields, so it is a potential **future shape adapter** for
`segment_financials`.  It cannot be wired in this issue: its source manifest
declares `authority_tier="supplementary_only"` and its quality flags include
`vendor_f10` and `provider_notice_time_not_exposed`.  Using it as this
ticket's “real” evidence-bound input would violate the explicit no-aggregator
boundary.  `business_model` therefore remains missing rather than being
promoted with vendor data.

## Resulting completion change

The 2026-07-28 rerun captured all three official filings successfully.  Each
has the same C1 distribution: **1 FULL / 2 PARTIAL / 15 MISSING**.

| ticker | FULL | PARTIAL | MISSING | per-section status difference from #483 |
|---|---:|---:|---:|---|
| `300750.SZ` | 1 | 2 | 15 | `revenue_quality_and_kpis: MISSING -> PARTIAL` |
| `600519.SH` | 1 | 2 | 15 | `revenue_quality_and_kpis: MISSING -> PARTIAL` |
| `000001.SZ` | 1 | 2 | 15 | `revenue_quality_and_kpis: MISSING -> PARTIAL` |

The remaining section state is identical across the three issuers:

```
FULL:    evidence_and_methodology
PARTIAL: revenue_quality_and_kpis, profitability_and_earnings_quality
MISSING: executive_summary, investment_thesis, business_model,
         industry_structure, competition_and_moat, management_and_governance,
         cash_flow_and_balance_sheet, accounting_quality,
         forecasts_and_consensus, valuation, macro_policy_and_costs,
         catalysts_and_events, risks_and_falsification, decision_framework,
         monitoring_and_action_triggers
```

For each of the three current official captures, the only newly connected
input is:

```
revenue_quality_and_kpis: MISSING -> PARTIAL
```

All other sections retain their prior honest state.  This is deliberately far
below the suggested 6–7 FULL baseline: the named modules are implementation
surfaces, not proof that their three-ticker inputs have been produced,
admitted, and provenance-bound.
