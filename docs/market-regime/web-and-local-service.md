# Market Regime Radar · web and local service

Status: S4 local-only decision reader. Canonical local URL:

```text
http://127.0.0.1:8896/market-regime
```

## Reader contract

The page separates two time horizons that must never be collapsed:

- `STRUCTURAL REGIME · COMPLETED DAILY` is the frozen completed-session
  Risk On/Off, offense/defense, technology/dividend and cross-asset leadership
  view.  Intraday refreshes cannot rewrite this layer.
- `15-MIN TARGET OVERLAY · LOCAL READ MODEL` shows the latest verified
  intraday artifact, its relation to the frozen A-share structure, and whether
  that relation confirms, diverges, is insufficient or is closed.

The first screen answers “what changed?” with the latest material-change
receipt, the three largest signed mathematical contributions, exactly two
threshold-bound watch conditions, and per-asset provider time/session/age for
all 14 identities.  Contributions are evidence-bound market signals, not news
causality.  Cash indices and futures proxies always remain separately named.

Freshness is presentation state, not decoration.  A relation recorded while
the market was open becomes `上次确认/背离` once all three A-share inputs are no
longer `live_candidate` and at most 15 minutes old.  The header can display the
green current state only when those three inputs are open and current.  Closed,
delayed, unavailable and unknown states remain explicit.

Below the first screen are the deterministic confirmation, rotation,
divergence and invalidation text, the five-group leadership ranking, VIX and
the China/US dividend probes, then nine completed-session daily candlestick
charts:

- US: S&P 500, Nasdaq;
- China A-shares: Shanghai Composite, STAR 50;
- commodities: WTI, gold, silver;
- Asia ex-China: KOSPI, Nikkei.

All charts use the same 1M/3M/6M/1Y selector. Candlesticks are drawn locally on
Canvas with MA20 and MA60 overlays. The browser polls the two same-origin,
read-only local endpoints every 60 seconds; it never contacts a market provider
or triggers collection.  The page has no CDN, remote font or external script.
Missing bars render an explicit unavailable card instead of demo data.

## Local service

Three user launch agents keep the service alive:

- `com.park.market-regime.scheduler` — completed-daily cycle, then 4h by
  default (12h is supported);
- `com.park.market-regime.intraday-scheduler` — a separate 15-minute target
  cycle with bounded 15/30/60-minute retry backoff;
- `com.park.market-regime.web` — loopback-only HTTP on port 8896.

Both collectors serialize through the cohesive-pipeline lock.  Each successful
intraday cycle runs collect → verify → compile → verify → publish.  Provider
failure receipts and last-good ages remain visible; a fallback does not erase
the primary failure.  “15-minute target” is deliberately not described as an
exchange realtime feed.

Runtime, logs and the dashboard compatibility database live under:

```text
~/Library/Application Support/ParkMarketRegime/
```

The repository contains code and contracts only. Market payloads, logs and
launch-agent receipts are not committed.

Install or replace the services:

```bash
python3 scripts/manage_market_regime_launchd.py install \
  --repo-root /absolute/path/to/equity-research \
  --interval-hours 4 \
  --intraday-interval-minutes 15
```

Use `--interval-hours 12` to choose the slower supported cadence.

Inspect health:

```bash
python3 scripts/manage_market_regime_launchd.py status
```

Pause and resume only the intraday collector while preserving all runtime
artifacts and the daily/web services:

```bash
python3 scripts/manage_market_regime_launchd.py stop-intraday
python3 scripts/manage_market_regime_launchd.py start-intraday
```

Stop and remove only the service definitions (runtime is preserved):

```bash
python3 scripts/manage_market_regime_launchd.py uninstall
```

The local launch plist explicitly disables inherited auth/private-preview
environment flags for this loopback-only page. Port 8878 was already occupied
on the acceptance machine, so the canonical service uses 8896.

## Boundary

The page visibly propagates `local_evaluation_only`,
`model_generated_unreviewed`, `not_investment_advice=true` and
`action_eligible=false`. It contains no order, position, alert or notification
surface.  The local service is not a public market-data feed and must not be
rebound to `0.0.0.0` under the current source-rights receipt.

Weekend/closed acceptance proves the closed-state branch and service survival;
it does not prove weekday open-session provider latency or a realtime SLA.
