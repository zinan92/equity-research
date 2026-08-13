# Market Regime Daily v2 · Evidence Pack v1

Status: S3 executable evidence contract. Tracking Issue #738; story Issue #743.
This compiler is the only input boundary for the later Daily v2 narrative
compiler. It does not publish an API, run an LLM or change the current page.

## Outcome

Freeze one completed-daily cross-asset view whose numbers can be cited exactly.
The pack contains 16 fixed slots:

- 12 existing verified inputs: S&P 500, Nasdaq, Shanghai, STAR 50, WTI,
  Gold, Silver, KOSPI, Nikkei, VIX, SSE Dividend and SCHD;
- four S1 macro factors: DXY, U.S. Treasury 2Y, U.S. Treasury 10Y and derived
  2s10s.

Every accepted slot has one content-addressed evidence ID. The resolver returns
the exact key, source identity, completed session, close time, value,
five-session change, units, quality and source tier. Unknown IDs fail closed.
An unavailable slot stays in the 16-slot surface without a fabricated value or
citation.

## Verified inputs

The compiler reads three independent latest chains:

1. `MarketRegimeDataStore.latest()` verifies every daily normalized artifact;
2. `MarketRegimeAnalysisStore.latest()` verifies the deterministic analysis;
3. `MarketRegimeMacroDataStore.latest()` verifies macro normalized and raw
   artifacts.

The stored analysis must bind the current daily run. The compiler replays the
existing deterministic compiler only to verify `analysis_id` and
`input_fingerprint`; it neither persists that replay nor changes any model
output. Every accepted daily feature must bind the same normalized artifact
hash and session as its source slot.

Generated `what_is_going_on` text is deliberately excluded. It is not source
evidence and may not enter a future prompt as fact.

## Unit contract

| Input | Level | Five-session change |
| --- | --- | --- |
| Daily indices, futures proxies, VIX and dividend probes | provider instrument unit | percent return |
| DXY | index points | percent return |
| U.S. Treasury 2Y / 10Y | percent yield | basis points |
| 2s10s | basis points | basis points |

Key, factor registry and unit mismatches fail compilation. Treasury yields are
never converted into price returns or candlesticks.

## Time, coverage and quality

The pack does not claim that global markets close on one date. It publishes:

- each slot's completed session and close time;
- `joint_judgment_time`, the earliest accepted close time;
- `latest_evidence_time`, the latest accepted close time; and
- their measured cross-market skew.

Full coverage means 16/16 accepted evidence identities. Critical inputs are
S&P 500, Nasdaq, Shanghai, STAR 50, VIX, DXY, US2Y and US10Y. Any unavailable
slot, stale source, last-good/not-refreshed state, critical absence, analysis
status below full or close skew above 30 hours makes the pack partial. No
accepted evidence makes it unavailable.

Confidence inputs are code-owned. The visible score starts from the verified
analysis confidence and multiplies explicit coverage, close-skew, freshness,
fallback, critical-input and contradiction factors. A missing critical input
forces the score to zero; stale/fallback evidence, >30-hour skew and observable
contradictions reduce it mechanically. A later LLM may explain but cannot
change these factors or score.

The pack exposes code-owned agreement inputs from the existing deterministic
dimensions and observable contradiction candidates already produced by those
dimensions. A contradiction candidate is explicitly non-causal. The pack does
not select a new market posture, confidence label, forecast or action.

## Identity, citations and persistence

`pack_id` hashes the canonical input identities, all 16 slot projections,
coverage, time/skew, agreement inputs and contradiction candidates. Fetch time
and filesystem paths are outside the identity. Replaying the same accepted
inputs produces the same pack ID and byte-identical artifact.

The store writes, in order:

1. immutable pack artifact;
2. immutable completion receipt binding the input IDs and artifact hash;
3. atomic `latest.json` pointer.

Status reads verify pointer paths, hashes, schema, pack identity, receipt/input
binding, canonical digest-derived paths, the immutable false rights/action
boundary, top-level projection and the complete evidence index. Missing,
tampered, escaped or mismatched artifacts fail closed. A never-used output root
may report unavailable with exit 0; an existing corrupt root exits non-zero.

## Runtime interface

```bash
python3 scripts/compile_market_regime_daily_evidence.py
python3 scripts/compile_market_regime_daily_evidence.py --status
```

Defaults:

- daily input: `product/runtime/market-regime/`;
- macro input: `product/runtime/market-regime/macro/`;
- output: `product/runtime/market-regime/daily-v2/evidence-packs/`.

All are gitignored runtime locations. S3 adds no scheduler, API, route, launchd
service, public deployment or history policy.

## Truth and rights boundary

The pack is read-only, non-causal, non-predictive and not investment advice.
It remains `publication_eligible=false` and `action_eligible=false`. A complete
pack proves only that accepted local evidence was consistently compiled. It
does not establish Yahoo/Tencent redistribution rights, provider uptime, an
exchange realtime SLA, member-distribution permission or a trade signal.

News, generated 财经日报 prose, LLM output, DRAM, holdings, alerts and orders are
outside this contract.
