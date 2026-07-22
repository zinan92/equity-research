# Canonical Research Refresh v1

## User outcome

Park 只需要触发一次更新：系统选择最新已经收盘的交易日，把现有行情、前复权日线和财务 collector 的结果写入 canonical 数据基座；质量通过后离线生成固定 8 股 `research-report-v1` 标准研报。任一来源或单股失败，都继续保留上一期 8/8 合格版本。

## Contract

```text
explicit primary/fallback adapters
  -> normalized collector bundle + versioned SourceManifest
  -> raw object + ingestion run + canonical source observations
  -> PIT / calendar / status / adjustment / provenance quality gate
  -> immutable snapshot
  -> SnapshotReader inside a network-blocked child process
  -> eight isolated research artifacts
  -> atomic active pointer only when 8/8 pass
  -> /api/reports/{ticker} revalidates and consumes canonical active
```

The operational state machine is `planned -> collected -> ingested -> snapshotted -> reports_built -> activated`. Every transition is written atomically. `in_progress.json` points to the only resumable run; a process lock serializes duplicate triggers.

## Source adapters

`LegacyCollectorAdapter` reuses the already-shipped collectors instead of creating a second data-fetching stack. Each component has its own manifest/run/observations, preserves provider bytes as base64 plus SHA-256, and binds normalized rows, provider hashes and allowlisted source URLs in a normalization receipt:

| Existing collector | Canonical representation |
|---|---|
| Sina mainland exchange calendar (via AkShare decoder) | independent SSE/SZSE open dates and previous-open identity |
| Tencent quote | immutable raw bundle plus `core_intelligence_items` market observation |
| Tencent qfq daily bars | `core_daily_bars` plus adjustment version rows |
| Eastmoney F10 main financials | metric-level `core_financial_facts` with notice-date PIT boundary |

The selected adapter owns one versioned bundle manifest. Its raw payload retains every component source URL and hash. Every collected candidate bundle is frozen before quality evaluation, including failed candidates, so the exact decision input remains replayable. Only the explicitly configured fallback chain can run.

## Activation rules

1. The target date comes from an independent SSE/SZSE calendar and must already be past 15:30 Asia/Shanghai. Without an independent suspension observation, a missing single-stock bar remains `normal` and fails the bar gate; it is never relabelled as a suspension to hide collection loss.
2. A normalized bundle cannot mix `fixture`, `cached`, and `real`; REAL requires an allowlisted HTTPS source and verified provider raw bytes, and trust kind is part of the ingestion identity.
3. Canonical quality must pass before a snapshot exists.
4. Each configured ticker builds independently from `SnapshotReader` in a forked child; CPython audit hooks plus child-local guards reject high- and low-level socket and external-command events without monkeypatching unrelated parent threads.
5. The active pointer changes only after exactly 8/8 artifacts pass the complete M1 `research-report-v1` schema, semantic contract, inner report hash, outer artifact hash and publication identity checks.
6. All-source failure, partial research, or interruption preserves the previous active pointer.
7. The product report endpoint reads canonical active first and rechecks active → publication → artifact identity before returning a report. If active exists but is corrupt, the endpoint returns a conflict and never silently falls back to legacy.

## Operations

Run the production adapter once:

```bash
python3 product/refresh_engine.py --canonical --timeout 12
# Optional, explicit cached fallback; never selected silently:
python3 product/refresh_engine.py --canonical --fallback-bundle <previous-run-bundle.json>
```

Inspect without contacting a provider:

```bash
python3 product/refresh_engine.py --canonical --dry-run
python3 product/refresh_engine.py --canonical --status
```

Acceptance verification:

```bash
python3 -m unittest product.tests.test_research_refresh_v1 -v
python3 scripts/verify_research_refresh.py
```

The LaunchAgent file under `product/automation/` is a portable schedule template. Its `/ABSOLUTE/PATH/TO/equity-research` placeholders must be replaced during installation; the tracked file proves configuration intent, not that a particular machine has executed it.

## In scope / out of scope

In scope: canonical adapter, trading-date gate, explicit fallback, lock/resume, 8/8 activation, dry-run/status/run-once CLI, schedule template, deterministic failure receipts.

Out of scope: online Supabase migration, a second source provider implementation, all-market coverage, automatic DeepSeek generation or approval, Telegram, payment, or trading.

## Truth boundary and remaining gap

The deterministic two-day receipt is fixture-only acceptance evidence. It proves orchestration, failure isolation, resume and offline replay; it does not prove current live provider availability. `LegacyCollectorAdapter` is the real-source cutover path, but its first live run remains an operational acceptance step.

Tencent qfq bars do not expose an independent corporate-action factor series. v1 binds each fetched qfq series to a provider-response adjustment version; unchanged keys are skipped, while a changed response version appends the complete revised series. Production authority still requires an official corporate-action/factor adapter for clean historical revisions. Financial corrections that reuse the same report date also fail closed until the provider adapter exposes an explicit revision identity.

## Gotchas

- A new raw response is not automatically a new trading date; identical canonical input reuses the existing ingestion run and snapshot.
- A successful snapshot is not an active publication. The eight-artifact gate is separate and atomic.
- A fallback is not a retry alias. It must be named and configured before the run.
- A schedule template is not evidence of a successful unattended execution.
- canonical active currently supplies the standard研报 endpoint; the portfolio homepage still uses the legacy publication database until a later milestone unifies the portfolio publication identity.
