# Snapshot Orchestration v1

## User outcome

一次计划内刷新要么生成可离线回放的新 canonical snapshot，要么明确失败并继续展示上一有效版本。运维方能从一份回执中看到缺口、source attempts、ingestion runs、完整 quality result、raw hashes、snapshot identity 和 replay digest。

## Reuse decision

A5 不新建第二套 collector、数据库或刷新状态机。`SnapshotOrchestrator` 是既有 `CanonicalResearchRefresh` 的薄层：

```text
authoritative expected trade dates
  -> schedule cutoff + per-ticker/per-date gap detector
  -> RefreshPlan (idle / incremental / backfill)
  -> CanonicalResearchRefresh (lock / fallback / ingest / quality / snapshot / activation)
  -> explicit raw-hash-bound snapshot manifest
  -> verified replay digest
  -> atomic orchestration receipt
```

既有 state machine 继续唯一负责 source selection、文件锁、断点续跑、ingestion、quality、snapshot 和 active pointer。A5 只补齐过去缺少的可执行 schedule/backfill plan 与单份审计回执。

## Contract

1. 调度器必须传入外部权威交易日列表。系统不会用“周一至周五”猜交易所开市日。
2. 当日只有在 Asia/Shanghai 17:30 后才进入 eligible dates；历史日期始终可参与 backfill。
3. 缺口按 `(ticker, trade_date, component)` 检查，不能用全库最大日期掩盖单股缺 bar。正常交易日要求 calendar、status、factor、OHLCV；停牌日不伪造 bar。
4. 同一输入的重复强制刷新复用同一 ingestion/snapshot identity；没有缺口的正常调度直接返回 `skipped` 且不调用 provider。
5. snapshot manifest 显式写入排序后的 `raw_hashes` 及 `raw_hash_digest`。replay 同时校验 manifest、frozen rows、quality digest 与 raw membership。
   pre-A5 active snapshot 仍可由旧 reader 回放，但不能被 A5 refresh 当作已满足新合同而直接复用；下一次刷新会生成带显式 raw lineage 的新 identity。
6. source、quality 或后续阶段失败都不能切换 `active.json`；失败回执必须保存 `active_preserved`。canonical `partial/blocked_before_activation` 在 orchestration contract 中明确归一为 `failed`，同时保留原始 canonical status/stage 与已完成 snapshot replay evidence。
7. orchestration receipt 使用临时文件、fsync 和原子替换，保存于本次 run 目录并更新 `orchestration-latest.json`；无缺口的 scheduler skip 也保存 immutable check receipt 和 latest pointer。

## Success criteria mapping

| Issue #32 criterion | Evidence |
|---|---|
| scheduler/backfill/gap detection | `build_refresh_plan` + `detect_canonical_gaps`; two-date fixture starts as backfill and ends with zero gaps |
| ingestion run/quality result complete | orchestration receipt contains source attempts, every ingestion run/raw hash, evaluation ID, all checks and blockers |
| snapshot manifest binds raw hashes | manifest-level raw membership + digest; replay rejects membership tampering |
| concurrent refresh lock + idempotency | existing canonical file lock rejects a second process; complete coverage skips network and forced identical input reuses snapshot |
| failure preserves previous valid version | injected primary outage returns failed receipt while `active.json` stays on previous snapshot |

## Verification

```bash
python3 -m pytest product/tests/test_snapshot_orchestration.py -q
python3 -m pytest \
  product/tests/test_snapshot_orchestration.py \
  product/tests/test_research_refresh_v1.py \
  product/tests/test_data_foundation.py -q
python3 -m unittest discover -s product/tests -q
```

Final result: issue-specific `7 passed`; focused orchestration/upstream `61 passed`; full product suite `290 tests` completed successfully. Adversarial review found one later-stage failure-receipt P1 and one skipped-schedule persistence P2; both were fixed and narrow re-review reported remaining P0=0/P1=0.

## Truth boundary

- Fixture acceptance proves deterministic orchestration, failure isolation and replay behavior; it is not live-provider SLA evidence.
- A5 receives expected trade dates from the caller; an official full-history exchange-calendar adapter remains separate work.
- The current canonical foundation remains local SQLite acceptance infrastructure. Real Supabase authority wiring, backup/restore and production scheduler installation are not claimed here.
- Research writing and user notification are outside issue #32. A5 freezes data identity; it does not improve the 30–50 page report content.

## Gotchas

- A maximum trade date is not coverage. Every ticker/date identity must be checked independently.
- A content-addressed raw object row inside snapshot items binds bytes indirectly; A5 additionally makes raw membership explicit in the manifest so operators can audit it without reconstructing every row.
- A schedule template or pure planning result does not prove a provider call ran. The orchestration receipt distinguishes `skipped`, `success` and isolated `failed` while retaining the canonical status.
- canonical 内部 `partial` 表示 snapshot 已建立但下游 artifact gate 未通过；面向 scheduler 的 A5 contract 必须把它报告为隔离失败，不能让运维方误以为刷新已完成。
- Replaying old pre-A5 snapshots remains supported. New raw-membership validation is mandatory when the manifest contains A5 fields.
