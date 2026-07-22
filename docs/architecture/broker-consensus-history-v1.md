# Broker Estimates & Consensus History v1

## User outcome

For an A-share ticker, the product can show a consistent forecast-year view of broker EPS, revenue, net profit, and target price, plus how the consensus changes between point-in-time snapshots.

## Reuse

- B2 Eastmoney catalog supplies report ID, broker, analyst, report date, rating, three forward EPS years, and target range.
- The mature a-stock/Vibe patterns supply Eastmoney field mappings and the THS `worth.html` table contract.
- THS supplies per-broker EPS/net-profit rows and independent revenue/net-profit consensus references.
- A3 ingestion preserves raw capture, source manifest, quality receipt, and fail-closed provider errors.

## Canonical model

One `BrokerEstimate` represents one broker report and one fiscal year. It requires ticker, broker, report ID, report date, raw hash, fiscal year, and at least one normalized metric:

- EPS: currency per share
- revenue: base currency units
- net profit: base currency units
- target price: currency per share

THS detail is attached only when broker, report date, and fiscal year uniquely match an Eastmoney report. The Eastmoney raw hash remains the report anchor and the THS raw hash is retained as supporting provenance. Unmatched THS broker rows do not become synthetic reports.

## Snapshot and revision rules

1. Apply the `as_of` cutoff before aggregation.
2. Use only the latest report from each broker for a fiscal year; keep superseded values in quarantine.
3. Detect robust outliers with median absolute deviation when there are at least four contributors.
4. Exclude flagged values before mean/median/min/max; retain the estimate ID, value, metric, year, and reason.
5. Hash canonical inputs, output points, and quarantine into a replayable snapshot identity.
6. Compare two snapshots by metric/year to expose mean direction, absolute/percent change, and contributor change.

THS provider consensus references are stored separately from Park's report-bound aggregate so an external mean never silently replaces the auditable broker set.

## Deferred

- Park-authored earnings forecasts
- forecasts parsed from arbitrary PDF tables
- production scheduling and full-market history backfill
