# Market Regime Radar · web and local service

Status: M4 local-only reader. Canonical local URL:

```text
http://127.0.0.1:8896/market-regime
```

## Reader contract

The first viewport renders the M2 receipt without changing it:

- large Risk score and Risk On/Off label;
- risk, offense/defense, technology/dividend and leadership cards;
- confidence, evidence status and cross-market close skew;
- deterministic confirmation, rotation, divergence and invalidation text.

The rest of the page contains the five-group leadership ranking, VIX and the
China/US dividend probes, then nine completed-session daily candlestick charts:

- US: S&P 500, Nasdaq;
- China A-shares: Shanghai Composite, STAR 50;
- commodities: WTI, gold, silver;
- Asia ex-China: KOSPI, Nikkei.

All charts use the same 1M/3M/6M/1Y selector. Candlesticks are drawn locally on
Canvas with MA20 and MA60 overlays. The page has no CDN, remote font, external
script or browser-side market-data request. Missing bars render an explicit
unavailable card instead of demo data.

## Local service

Two user launch agents keep the service alive:

- `com.park.market-regime.scheduler` — immediate cycle, then 4h by default;
- `com.park.market-regime.web` — loopback-only HTTP on port 8896.

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
  --interval-hours 4
```

Use `--interval-hours 12` to choose the slower supported cadence.

Inspect health:

```bash
python3 scripts/manage_market_regime_launchd.py status
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
`action_eligible=false`. The local service is not a public market-data feed and
must not be rebound to `0.0.0.0` under the current source-rights receipt.
