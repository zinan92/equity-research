# Market Regime Live v1 · intraday data contract

Status: S1a Yahoo authority.  Schema:
`market-regime-intraday-data-v1`.  Issue: #719.

This layer collects and freezes completed 5-minute evidence.  It does not
calculate an impulse, material change, forecast, recommendation, API payload
or trading action.  Tencent/A-share support belongs to #720.

## Fixed Yahoo registry

The registry is code-owned by
`product/data_core/market_regime_intraday_data.py`.  It contains exactly these
eleven Yahoo identities in S1a:

| Key | Symbol | Session | Identity boundary |
| --- | --- | --- | --- |
| `sp500_cash` | `^GSPC` | US cash | S&P 500 cash price index |
| `nasdaq_cash` | `^IXIC` | US cash | Nasdaq Composite cash price index |
| `sp500_futures_proxy` | `ES=F` | US future | independent large-cap risk proxy |
| `nasdaq100_futures_proxy` | `NQ=F` | US future | Nasdaq-100 future; not Nasdaq Composite |
| `wti` | `CL=F` | commodity future | provider continuous front month |
| `gold` | `GC=F` | commodity future | provider continuous front month |
| `silver` | `SI=F` | commodity future | provider continuous front month |
| `kospi` | `^KS11` | Korea cash | KOSPI cash price index |
| `nikkei` | `^N225` | Japan cash | Nikkei 225 cash price index |
| `vix` | `^VIX` | US volatility cash | VIX cash index |
| `us_dividend` | `SCHD` | US cash | ETF trade price, style evidence |

`^GSPC != ES=F` and `^IXIC != NQ=F` are import-time invariants.  A proxy
relationship is metadata; no consumer may splice, backfill or compare absolute
price continuity across those identities.

Unknown keys are rejected before the transport is called.  The primary URL is
Yahoo `query1` Chart with `interval=5m&range=5d`; `query2` is attempted only
after the primary response fails status, MIME, JSON, identity or bar
validation.  Each attempt remains visible.  A fallback response never erases
the failed primary capture.

## Raw response and normalization

Every attempt stores the complete response body under the gitignored runtime
root and records method, requested/final URL, redirects, safe headers,
Content-Type, byte length, SHA-256, request timestamp, `received_at`, raw path,
accept/reject state, reason and a bounded failure excerpt.

Acceptance requires:

- HTTP 200 and declared JSON;
- one Chart result with exact provider symbol, currency and IANA timezone;
- equal-length timestamp and OHLC arrays;
- strictly ascending unique integer timestamps;
- finite OHLC with high/low containment and non-negative optional volume;
- at least two completed bars;
- no partially-null, future, unordered or duplicate row.  A fully-null OHLC
  placeholder is droppable only when volume is null/zero and its timestamp
  remains in the original ordered grid.

Yahoo timestamps are treated as interval starts.  A row is complete only after
`timestamp + 5 minutes + 30 seconds <= observed_at`.  Yahoo can emit fully-null
placeholders both across futures maintenance gaps and at the tail.  Null/zero-
volume placeholders are dropped without closing the timestamp gap and are
listed as internal or trailing.  A partially-null row or an all-null OHLC row
with non-zero volume is corruption and rejects the attempt.  Trailing
unfinished priced rows are separately dropped and disclosed.

## Independent sessions and freshness

There is no global open flag.  Each instrument is classified independently as
`pre`, `open`, `lunch_break`, `post`, `maintenance`, `closed`, or `unknown`.
Provider `currentTradingPeriod` must cover the observation before the system
asserts pre/open/post.  Weekday arithmetic alone cannot prove a holiday open.
US DST is evaluated through `zoneinfo`; Japan lunch, futures daily maintenance,
Friday close and weekend boundaries are explicit.  Saturday is closed.

Each accepted artifact keeps:

- `provider_timestamp` (latest accepted bar start);
- `last_completed_bar_end_at`;
- `observed_at` and `received_at`;
- original `age_seconds` and snapshot-time `current_age_seconds`;
- `last_completed_session`, `session_state`, and freshness.

Freshness is one of `live_candidate`, `delayed`, `stale`, or `unavailable`.
Only an open asset with a latest bar no older than 15 minutes may be
`live_candidate`; this still does not prove exchange real time.  Closed assets
remain visibly closed and normally carry `delayed` freshness.  Provider delay
may be unknown.

## Immutable store and failure behavior

Runtime paths are rooted under `intraday/`:

- `raw/<run>/<key>-<endpoint>.*` — complete immutable response bodies;
- `normalized/<run>/<key>.json` — accepted immutable asset artifacts;
- `instruments/<key>/latest-good.json` — atomic verified asset pointers;
- `snapshots/<sha>.json` and `latest.json` — aggregate attempt state;
- `runs/<run>.json` — accepted/rejected attempt receipt.

An accepted artifact is written and hashed before its latest-good pointer
advances.  If both endpoints fail, the asset pointer remains byte-unchanged.
An aggregate partial snapshot may project that last-good artifact, but preserves
its original provider/received/observed timestamps, recomputes only
`current_age_seconds`, and can only keep or worsen freshness.  Re-serving an
old record never makes it fresh.

The snapshot quality describes coverage: `complete`, `partial`, or
`unavailable`.  It is not a latency claim.  Snapshot and artifact reads verify
schema, path containment, SHA-256 and deterministic identity.

## Rights and live-probe boundary

Yahoo Chart remains `supplementary_only` and `local_evaluation_only`.
`publication_eligible=false` and `action_eligible=false` are propagated through
every artifact.  Private-beta/public/commercial modes fail closed.  HTTP 200,
fixture success or a one-time live run proves neither reliability, latency nor
redistribution rights; a 429 does not prove general source unavailability.

Run a bounded local refresh with:

```bash
python3 scripts/refresh_market_regime_intraday_data.py \
  --instrument sp500_futures_proxy
```

Importing the module has no network or scheduling side effect.
