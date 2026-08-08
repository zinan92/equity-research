# Market Regime Live v1 · product and truth contract

Status: S0 direction contract.  No intraday collector, model, API or UI is
implemented by this contract.  Parent tracking issue: #717.  Story: #718.

## User outcome

The beachhead is one local/private cross-asset market page.  In about 30
seconds it should answer:

1. What is the completed-daily structural regime?
2. Did the verified intraday overlay materially change since its previous
   successful version?
3. Which observable market signals contributed most?
4. Does the A-share tape `confirm`, `diverge`, remain `insufficient`, or sit
   `closed`?
5. Which two deterministic conditions should be watched next?

This is a read-only research explanation, not a forecast, recommendation,
position instruction or trading system.

## Two layers that never overwrite each other

`structural` is the existing `market-regime-model-v1` result over completed
daily bars.  It remains the source of Risk On/Off, offense/defense,
technology/dividend, leadership and scenario labels.

`intraday` is a separate experimental overlay over accepted completed 5-minute
bars.  Its relationship to the structural layer may only be `confirms`,
`diverges`, `insufficient`, or `closed`.  It may list deterministic signal
contributions and threshold-bound watch conditions.  It must never replace a
structural label, join a futures price series to a cash index, invent a news
cause, predict a return or emit a trading action.

## Cadence and user-visible time identity

The v1 operating target is one serial check every 15 minutes.  This is a target
refresh cadence, not an exchange-real-time, tick-level or latency guarantee.
Provider data may be delayed and the delay may be unknown.  Every asset must
carry and display:

- `provider_timestamp`: provider time of the newest accepted completed bar;
- `observed_at`: the UTC instant at which normalization evaluated the capture;
- `received_at`: the UTC instant after the complete HTTP body was received;
- `age_seconds`: `observed_at - provider_timestamp`, never time since the
  product last served or copied the record;
- `session_state`: the asset-specific session state;
- `freshness`: `live_candidate`, `delayed`, `stale`, or `unavailable`.

`live_candidate` means only that a completed provider bar arrived within the
frozen age bound while that asset's session evidence says it may trade.  It
does not prove exchange real time.  Last-good fallback preserves the original
four timestamps and current age; re-serving it can never make it fresh again.

## Fixed identity registry

The completed-daily registry remains unchanged.  Intraday v1 may request only
the identities below.  `proxy_for` describes an explanatory relationship, not
symbol equivalence or permission to splice prices.

| Key | Provider symbol | Identity | Proxy for / role |
| --- | --- | --- | --- |
| `sp500_cash` | `^GSPC` | S&P 500 cash price index | US large-cap cash confirmation |
| `nasdaq_cash` | `^IXIC` | Nasdaq Composite cash price index | US growth cash confirmation |
| `sp500_futures_proxy` | `ES=F` | provider continuous E-mini S&P future | US large-cap risk-appetite proxy |
| `nasdaq100_futures_proxy` | `NQ=F` | provider continuous E-mini Nasdaq-100 future | US growth risk-appetite proxy; **not** Nasdaq Composite |
| `shanghai` | `sh000001` | SSE Composite cash price index | A-share broad confirmation |
| `star50` | `sh000688` | STAR 50 cash price index | A-share technology confirmation |
| `china_dividend` | `sh000015` | SSE Dividend cash price index | A-share dividend confirmation |
| `wti` | `CL=F` | provider continuous front-month future | energy signal |
| `gold` | `GC=F` | provider continuous front-month future | precious-metal signal |
| `silver` | `SI=F` | provider continuous front-month future | precious-metal signal |
| `kospi` | `^KS11` | KOSPI cash price index | Asia ex-China confirmation |
| `nikkei` | `^N225` | Nikkei 225 cash price index | Asia ex-China confirmation |
| `vix` | `^VIX` | VIX cash volatility index | risk evidence |
| `us_dividend` | `SCHD` | US-listed dividend ETF trade price | US dividend-style evidence |

`^GSPC != ES=F` and `^IXIC != NQ=F` are hard invariants.  Futures proxies keep
their own currency, exchange timezone, provider symbol, price basis, session
and evidence identity.  WTI, gold and silver remain provider rolling
continuous contracts rather than frozen exchange contract series.

## Asset-specific session contract

There is no global market-open flag.  Each asset independently reports one of
`pre`, `open`, `lunch_break`, `post`, `maintenance`, `closed`, or `unknown`.
The decision must bind provider session metadata, latest accepted bar time and
an exchange-local schedule evaluated with an IANA timezone.

- A-share fixtures cover pre-open, 09:30–11:30, 11:30–13:00 lunch, 13:00–15:00,
  post-close, weekend and holiday.  Closed periods report `closed` (or
  `lunch_break`) plus `last_completed_session`, never “does not confirm”.
- US cash fixtures cover regular session, pre/post, weekend and DST changes.
- Asian cash sessions are evaluated in Asia/Seoul or Asia/Tokyo.
- Futures use their own electronic session and maintenance boundary; a cash
  session schedule cannot classify them.
- Weekday arithmetic alone cannot prove a holiday is open.  Conflicting or
  insufficient provider/session evidence becomes `unknown`, not `open`.
- Saturday must be `closed` with the last completed session for cash markets.

A 5-minute row is eligible only after its interval end plus the frozen grace
has passed at `observed_at`.  Timestamps must be strictly ascending and unique;
all OHLC values must be finite and internally valid.  Trailing all-null rows
are dropped and disclosed.  Partly null, duplicate, unordered, future or
identity-conflicting rows fail closed.

## Change, driver and history boundary

S2 will freeze directional thresholds, enter/exit hysteresis, a persistence
window and notification-free cooldown.  Until historical replay calibration
exists, every overlay is `experimental` and makes no predictive claim.
Material change compares with the previous **successfully verified overlay**,
not the previous poll or page view.  Failed/duplicate cycles do not advance the
baseline or append a new logical state.

“Driver” means the weighted, evidence-linked market signals that contributed
most to the deterministic score.  It never means a causal news explanation.

## Source and rights boundary

Yahoo Chart and Tencent quote/K-line are `supplementary_only` local-evaluation
sources.  Current permission is `local_evaluation_only` with
`publication_eligible=false` and `action_eligible=false`.  HTTP success, a
public URL, an SDK, a probe or a refresh schedule proves neither reliability,
exchange-real-time status nor redistribution rights.  Private-beta, public and
commercial distribution remain fail closed.

Every network attempt preserves method, requested/final URL, redirects,
status, safe headers, Content-Type, byte count, SHA-256, request/receipt times
and the complete raw body under the gitignored runtime root.  The repository
may contain only a safe receipt with a bounded excerpt and raw hash.  A 429 or
empty adapter result is one debugging observation, not a conclusion that a
provider is unavailable.

## S0 bounded source observation

The non-gating probe covers Tencent's three-index quote batch, one Tencent
Shanghai m5 request, and Yahoo query1/query2 `ES=F` 5-minute requests.  It is
intentionally too small to establish uptime, latency, market-open behavior or
rights.  On 2026-08-08 (Saturday), UI/runtime acceptance may prove only honest
`closed + last_completed_session`; it cannot prove live-open behavior.

## Sequential delivery gates

S0 #718 must merge before S1a #719 enters development.  Then proceed in order:
S1b #720, S2 #721, S3a #722, S3b #723 and S4 #724.  Each story has its own
issue, branch, PR and focused acceptance.  Holdings/personalization, 08:45
delivery, payment/approval workflows, public sharing, news/LLM causality,
WebSocket/ticks/order books, multiple-source consensus, predictions and all
trading actions are outside live v1.
