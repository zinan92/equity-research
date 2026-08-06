# Market Regime Radar · API and scheduler contract

Status: M3 local read-only runtime. API schema: `market-regime-api-v1`.
Scheduler schema: `market-regime-scheduler-v1`.

## Runtime boundary

The browser and HTTP handler read one verified, immutable API bundle. They do
not fetch Yahoo/Tencent, compile a model, advance a pointer, or place an order.
The refresh process is separate and serial:

```text
M1 refresh -> verify data latest -> M2 compile -> verify analysis latest
           -> write immutable API bundle -> advance API latest -> success
```

If any stage fails, the scheduler records the error and leaves the previous API
latest pointer byte-unchanged. M1 may preserve a failed/partial attempt for
diagnosis, but the reader still sees the last complete cohesive bundle.

Local-evaluation market data is served only when the HTTP server itself is
bound to loopback. Existing dashboard authentication and `dashboard`
entitlement checks remain in force.

## API

- `GET /api/market-regime` returns the verified bundle: nine primary daily
  OHLC charts, VIX/China-dividend/US-dividend probes, complete M2 analysis,
  evidence hashes, data/source quality, license and truth boundary.
- `GET /api/market-regime/health` returns scheduler state and a compact latest
  bundle identity. It does not run a refresh.

Both routes are `Cache-Control: no-store`. Hash, schema, path containment,
bundle identity, source run or analysis identity failures are unavailable, not
best-effort responses.

## One cycle

```bash
python3 scripts/run_market_regime_scheduler.py --once --interval-hours 4
```

The root defaults to `product/runtime/market-regime` and can be changed with
`PARK_MARKET_REGIME_ROOT` or `--root`. The only permitted intervals are 4 and
12 hours. `PARK_MARKET_REGIME_INTERVAL_HOURS` sets the default; an explicit CLI
argument wins.

## Continuous local loop

```bash
PARK_MARKET_REGIME_INTERVAL_HOURS=4 \
python3 scripts/run_market_regime_scheduler.py
```

The process runs one cycle immediately and sleeps for the configured interval
after each attempt. A non-blocking file lock prevents overlapping cycles.
Scheduler health is atomically stored under `scheduler/status.json`; a process
that dies after writing `running` is reported as `interrupted` when its lock is
no longer held.

Installing a launchd service, exposing a refresh POST route, public hosting,
notifications and automatic trading are outside M3.
