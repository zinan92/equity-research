# A 股数据基座 v1

状态：M2 implementation baseline  
合同版本：data-foundation-v1  
权威边界：PostgreSQL/Supabase 目标 schema；SQLite 是本地验收 adapter，不是线上权威库。

## 用户结果

研报、组合和 AI 只读取一个指定的不可变 snapshot。采集可以失败、重试或切换显式 adapter，但不能在分析中途刷新某个字段，也不能把 fixture 冒充真实行情。

## 复用而不是重造

| 资产 | 采用 | 不采用 |
|---|---|---|
| zinan92/datafeed | SourceManifest、Port/Adapter、raw response、显式质量和 fallback、source provenance | 独立服务进程和只覆盖 K 线的领域模型 |
| simonlin1212/a-stock-data | 端点维护经验和后续 adapter 候选 | 本地 CSV/cache 作为权威存储、分析时直连 |
| zinan92/quant-data-pipeline | scheduler、backfill、gap detection、health check 的运行模式 | 旧 SQLite schema 和生产运行依赖 |
| zinan92/intel | registry/collector/event topology，作为 supplementary intelligence | 行情、财务、公司行动或公告权威源 |
| PostgreSQL/Supabase | 单一权威数据面、Auth/RLS/Storage 的后续承载 | 本轮虚构线上连接或假装已经部署 |

## 分层

    Source adapters
      -> Raw objects + ingestion receipts
      -> Canonical market facts
      -> Quality gate
          -> passed: Immutable dataset snapshot -> SnapshotReader -> Research / portfolio / AI
          -> blocked: Quality receipt; previous snapshot remains active

### Raw / provenance

每个 accepted 数据链至少包含：source_key、不可变 source manifest hash、run/attempt、source observation、raw hash 与可恢复 payload、fetched_at、UTC-normalized known_at、provider/schema version、license status、storage URI 和 quality status。失败重试创建新 attempt，不能删除旧失败回执。fallback 必须由调用方显式声明，不能静默替换来源。

### Canonical market

- security master：instrument identity、名称、市场、板块、行业、上市/退市日期；
- time：三交易所 calendar 与每日证券状态；
- price：带复权版本的 daily bars；
- corporate action：公告时间、除权日、版本和确定性 details；
- financial fact：报告期、公告时点、修订序号、单位和 point-in-time 可见性；
- intelligence：Evidence 与 LLM Inference 分列；缺失不阻断 market-only snapshot，但必须降级 coverage。

### Snapshot

Snapshot manifest 固定：as_of、known_at、schema/model/dependency version、随机种子、lineage ingestion runs、具体 quality evaluation ID/digest、逐行 hash、冻结 row JSON 和 manifest hash。snapshot kind 从 ingestion run 推导，fixture 不能由调用者升级为 REAL。SQLite trigger 与 PostgreSQL trigger 都拒绝修改或删除已创建 snapshot。

## Gate

以下任一项阻断新 snapshot：

1. 开市证券缺交易日历；
2. 状态为 normal 的证券缺当日 accepted bar；
3. bar 找不到相同版本的 adjustment factor；
4. 财务公告时间或 known_at 越过 snapshot knowledge cutoff；
5. accepted row 缺 successful run、raw object、source manifest 或版本/license provenance；
6. ingestion run 未成功。
7. source observation 数量与 run receipt 不一致；
8. raw payload hash 被篡改或 raw known_at 越过 cutoff；
9. degraded/rejected canonical row 会进入 snapshot；
10. 混合时区换算后，财务公告晚于 knowledge cutoff。

阻断只拒绝新 snapshot，不覆盖上一份合格 snapshot。

## 两套物理实现

- product/data_core/schema.py：零外部依赖的 SQLite 验收实现，表使用 core_ 前缀，服务 fresh clone、测试、离线 replay 和恢复演练。
- product/data_core/migrations/0001_canonical_foundation.postgres.sql：PostgreSQL 15+/Supabase migration，按 market / research schema 分域。

两者共享 data-foundation-v1 逻辑字段。线上连接、RLS、Storage bucket 和备份策略必须在确定部署 region 与 Supabase project 后单独验收；本轮不声称已完成。

## 12 股 fixture 的证据边界

验收 fixture 覆盖 SSE/SZSE/BSE、主板/创业板/科创板/北交所和 10 个行业，并包含 suspended、ex-rights/corporate action、financial revision。它只证明 schema、gate、replay 和 restore 行为，不证明 2026-07-17 的真实市场事实。

运行：

    python3 scripts/verify_data_foundation.py
    python3 -m unittest product.tests.test_data_foundation -v

## 后续接入顺序

1. 将现有真实行情/日线/财务 collector 改为 DataFoundation adapters；当前 product replay 已能只读 canonical snapshot，采集写入仍由 M3 完成；
2. 对 12 只真实 A 股保存 raw object、run 和 quality receipt；
3. 对接 Supabase Storage 与 Postgres migration；
4. 让 refresh engine 只向 SnapshotReader 请求 context；
5. 接入 trading calendar、公司行动和财务修订的正式来源；
6. 做线上 backup/restore 演练后再把 PostgreSQL 标为 production authority。
