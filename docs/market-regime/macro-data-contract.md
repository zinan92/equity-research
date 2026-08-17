# Market Regime Daily v2 · macro data authority

Status: S1 executable data contract. Tracking Issue #738; story Issue #741.
This authority feeds a later evidence-pack story. It does not change the
existing Market Regime model, API v2, intraday pipeline, scheduler or page.

## Outcome

Provide four frozen, auditable explanatory factors for the completed-daily
macro panel:

| Key | Meaning | Level unit | Change unit | Authority |
| --- | --- | --- | --- | --- |
| `dxy` | U.S. Dollar Index | index points | completed-daily percent return | Yahoo chart, supplementary only |
| `us2y` | U.S. Treasury 2-year par yield | percent | basis points | U.S. Treasury official CSV |
| `us10y` | U.S. Treasury 10-year par yield | percent | basis points | U.S. Treasury official CSV |
| `us2s10s` | `us10y - us2y` | basis points | basis points | same-date derivation from accepted Treasury rows |

The factors are research evidence, not forecasts or trading instructions.
They remain `publication_eligible=false` and `action_eligible=false`.

## Source contracts

### DXY

- Provider symbol: `DX-Y.NYB`.
- Endpoint shape: Yahoo Finance chart JSON, daily interval, two-year range.
- The collector tries the query2 endpoint first and query1 second for the same
  `DX-Y.NYB` identity. A query1 success is a same-day endpoint retry, not a
  substitution with a broad-dollar proxy or another index. The selected
  endpoint and every failed/accepted attempt are retained in the source
  receipt.
- Only completed sessions are accepted. The existing OHLC normalizer enforces
  symbol, currency, timezone, ascending unique dates, finite OHLC, minimum
  history, future-session rejection and completed-session cutoff.
- Yahoo is `supplementary_only`; its presence does not establish commercial
  redistribution rights. Private-beta and public collection fail closed under
  the inherited license gate.

### U.S. Treasury 2Y and 10Y

- Authority page: `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve`.
- Capture endpoint: the official year-scoped Daily Treasury Par Yield Curve
  Rates CSV. The collector starts with the current New York calendar year and
  requests the previous year only when the accepted current-year history is
  shorter than 120 observations.
- Accepted response: HTTP 200, CSV content type, non-empty UTF-8 body and the
  exact `Date`, `2 Yr`, `10 Yr` columns. Every accepted value is finite and in
  `[0, 30]` percent. Duplicate, unordered, future, missing and `N/A` rows fail
  the capture.
- Treasury publishes newest-first CSV rows. A wholly descending file is
  explicitly recorded as `descending_reordered`; a mixed order is rejected.
- Yield levels stay in percent. A one-, five- or 20-session change is computed
  as `(latest yield - earlier yield) * 100` and labelled basis points.

### 2s10s derivation

- Formula: `(US10Y percent - US2Y percent) * 100`.
- Both inputs must come from the same accepted Treasury date. The artifact
  binds that date, both input values and the raw-source SHA-256.
- The spread level and its changes are basis points. It is not an independent
  provider series, price return or candlestick instrument.

## Identity, receipts and replay

Every HTTP attempt preserves method, requested/final URL, safe response
headers, status, content type, redirects, fetch time, body size and body
SHA-256. The complete body is written under the gitignored runtime root. On a
rejection, the run receipt also stores a bounded raw excerpt so an unavailable
claim is not inferred from an adapter classification alone.

Accepted normalized factors are immutable JSON artifacts. `factor_id` hashes
the schema, factor key, normalized observations, units, quality and source body
identity. Fetch time, raw path and run ID are audit metadata outside that
content identity, so replaying identical raw bytes produces the same
`factor_id`. Mutable `latest-good.json` pointers are written atomically only
after the immutable artifact and run receipt exist.

Every completed network attempt, including an HTTP response with a zero-byte
body, receives a raw file and SHA-256. A factor-scoped refresh never shrinks the
global four-factor surface: untouched factors are projected from verified
latest-good artifacts as `not_refreshed`, or explicitly `not_requested` and
unavailable when no prior evidence exists. Such a subset snapshot is partial,
never fresh.

If all same-day DXY endpoints or all required Treasury captures fail, the
current factor is explicitly `quality=unavailable` with `refresh_status=rejected`
and the complete attempt receipt. A prior `latest-good` artifact is retained
for historical recovery but is never copied into the current snapshot. A
successful alternate endpoint remains a fresh accepted factor.

## Freshness and display

Treasury quality uses the latest New York date: `fresh` through four calendar
days, `partial` through ten, then `stale`. DXY reuses the completed-session and
provider-silence policy of the existing daily authority. The later evidence
pack must retain each factor's own completed session and close time; it cannot
claim all markets share one close date.

Rates and the curve render as compact factor rows or sparklines, never
candlesticks. Missing or rejected factors render an explicit unavailable state;
no UI may silently coerce basis points into percent returns or present a
last-good factor as today's value.

## Runtime interface

```bash
python3 scripts/refresh_market_regime_macro_data.py
python3 scripts/refresh_market_regime_macro_data.py --status
python3 scripts/refresh_market_regime_macro_data.py --factor us2y --factor us10y
```

The default runtime is `product/runtime/market-regime/macro/`, which is
gitignored. `--status` verifies immutable references and hashes without making
a provider request. A never-used runtime reports unavailable with exit 0;
existing-but-corrupt evidence exits non-zero. The runtime does not yet schedule,
publish or project these factors into an API.

## Forbidden changes in S1

- No modification of `market_regime_data.py`, `market_regime_model.py`, API v2,
  intraday collectors/models, schedulers or web routes.
- No LLM, news, causal explanation, confidence formula or user action.
- No DRAM proxy, public/member distribution or rights upgrade.
- No direct editing of a latest-good artifact or mutable recomputation of a
  published identity.
