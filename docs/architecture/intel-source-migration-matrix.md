# Intel 情报源迁移矩阵

状态：`Approved for architecture / Not implemented`  
日期：2026-07-17  
上位规格：[A 股长期投委会 · 产品设计](../superpowers/specs/2026-07-17-a-share-investment-committee-design.md)

## 1. 决策

`zinan92/intel` 作为 `intelligence-ingest` 补充情报支线复用，不作为行情、财务、公司行动、证券状态或正式公告的权威源。

- `market_snapshot_id` 是正式 AI Context Pack 的必填输入。
- `intelligence_snapshot_id` 是可选输入；缺失或降级时继续生成 market-only pack，并明确显示 coverage gap。
- Intel 只写原始证据、情报条目、事件和不可变情报快照；不得写 canonical market facts。
- 数值事实只能来自 market snapshot 或带正式证据引用的确定性提取结果；LLM 推断不得伪装成事实。

## 2. 迁移矩阵

| Intel 资产 / source | 当前证据 | Verdict | 目标位置 | 必须改造 | Gate |
|---|---|---|---|---|---|
| SourceRegistry service | DB 驱动、支持 active/retired、priority、schedule | **Direct reuse concept** | 共享 `source_registry` | 新增 `domain_scope`、`authority_tier`、provider/schema version、license policy | 任何 source 必须机器可读地声明 `supplementary_only` 或更高 authority |
| Adapter / Collector interface | 10 类 adapter，统一 fetch/save 路径 | **Direct reuse concept** | `intelligence-ingest` adapters | 输出 SourceManifest、raw object、ingestion run；禁止直接写正式表 | 缺 provenance 时拒绝落入 accepted 区 |
| CollectorRun / scheduler / retry | 有运行记录、错误分类、按类型调度 | **Adapt** | `ingestion_runs`、`quality_results` | 计数拆成 `fetched / saved / unique / accepted / snapshot_included` | 不再用 fetched 总量代表有效覆盖 |
| RSS | 54 configured / 50 active；多数 AI、科技、Crypto，中文财经较少 | **Adapt** | `research.intelligence_items` + Storage | 建立 A 股白名单；首批用华尔街见闻等财经源；保存原文 hash 与 known_at | RSS 只做新闻/叙事；不能更新行情、财务或公司行动 |
| Google News | active；当前 query 主要围绕黄金 | **Adapt** | `research.intelligence_items` | 重写 A 股行业/宏观 query；保留聚合页与原始来源两级 URL | 聚合结果不能冒充一手来源；重复报道需语义去重 |
| Yahoo Finance news | active；当前 ticker 主要是黄金资产 | **Adapt** | 全球宏观/跨市场补充情报 | 扩充与 A 股行业映射有关的全球 ticker；新闻与价格数据分离 | 不能作为 A 股价格、财务或估值权威源 |
| Website monitor | 现有目标为 AI 产品页面 | **Adapt** | Storage + `intelligence_items` | 新增交易所/巨潮/证监会监控；标记 `authority_tier=supplementary_only` | 网页监控只负责发现与留证；正式公告需独立官方 adapter 入 canonical |
| Xueqiu KOL | 已配置 KOL，但当前 inactive、依赖 cookie | **Optional** | sentiment evidence | cookie 失效时整个 source 标记 `stale/unavailable`；禁止混入旧数据 | 不得单独驱动事实、估值或仓位；Context Pack 必须显示 coverage gap |
| Reddit / Hacker News | active，偏全球技术与社区讨论 | **Optional thematic** | `domain_scope=thematic_global` | 仅保留 AI、半导体、Crypto 等主题研究价值 | 默认不进入 A 股 briefing；需要显式主题映射才可引用 |
| GitHub Trending / Releases | active，但与 A 股正式数据无关 | **Optional thematic** | 技术趋势情报 | 保留软件/AI 产业链信号；修正 token/health 配置 | 不进入 canonical 或公司基本面事实 |
| Social KOL | 当前 inactive | **Optional thematic** | KOL evidence | 若恢复，保存帖子证据、时间和作者；失败可降级 | 不得把观点转换成未标注事实 |
| Article 去重 | source_id 唯一；日报另有标题/URL去重 | **Adapt** | `intelligence_items` | 增加 `raw_hash`、canonical URL、中文语义 fingerprint | 同一事件不同措辞必须进入同一证据簇，不得虚增热度 |
| 48h event aggregation | 跨源聚类拓扑可用 | **Split verdict** | `research.intelligence_events` | **拓扑/窗口机制直接复用；中文实体识别、相似度、权重和打分必须重做** | event 必须指向 evidence links；不得把 LLM 数字写成 evidence 字段 |
| LLM tagging / narrator | 能生成 relevance 与 narrative | **Adapt** | 中层推断字段 | 证据字段与推断字段分列；每个推断保存 prompt/model/version | `is_llm_inferred=true` 必填；任何下游不得把它当确定性事实 |
| SQLite `articles` / `briefs` | 可运行，但 schema 缺 provenance、snapshot 与 PIT | **Do not migrate as authority** | 仅作迁移输入/历史档案 | 转换到 Supabase 新 schema；保留旧 DB 只读备查 | 禁止把 SQLite 继续作为生产权威库 |
| 当前 Daily Brief | 24h 内容生产链可用 | **Reuse template only** | AI Context Pack consumer | 改为读取 market + intelligence snapshots；数值引用必须回指 market evidence | 未核验数字不得发布为事实或仓位依据 |
| 硬编码凭据及旧发送脚本 | 公共 tracked 文件发现硬编码机器人凭据 | **Do not migrate / P0 cleanup** | secrets manager / environment | 轮换并确认旧凭据失效；清理当前代码和 Git 历史；形成审计记录 | P0 未通过前，不复制相关脚本进入新 data-core |

## 3. Supabase 目标边界

共享控制表沿用上位规格的唯一权威定义：

- `source_registry`
- `ingestion_runs`
- `quality_results`

Intel 情报域新增：

- `research.intelligence_items`
- `research.intelligence_events`
- `research.intelligence_event_links`
- `research.intelligence_snapshots`

原始 payload、HTML、PDF、抓取响应与正文副本进入 Supabase Storage，不塞进业务表大字段。

### 3.1 必填 provenance 契约

进入 accepted 区的情报记录至少必须满足：

- `source_key NOT NULL`
- `domain_scope NOT NULL`
- `authority_tier NOT NULL`
- `fetched_at NOT NULL`
- `known_at NOT NULL`
- `raw_hash NOT NULL`
- `provider_version NOT NULL`
- `schema_version NOT NULL`
- `license_status NOT NULL`
- `quality_status NOT NULL`
- `ingestion_run_id NOT NULL`
- `is_llm_inferred NOT NULL DEFAULT false`
- `source_url` 与 `provider_item_id` 至少一个存在

`published_at` 可以缺失，但不得用 `fetched_at` 冒充；所有回测和 replay 以 `known_at` 截断可见性。

### 3.2 证据与推断分离

| 类型 | 允许内容 | 下游权限 |
|---|---|---|
| Evidence | 原文、确定性提取、正式 market snapshot 数值、来源时间与 hash | 可进入事实摘要并被引用 |
| Inference | LLM relevance、主题、情绪、事件解释、A 股映射假设 | 必须标记模型版本和置信度；不能覆盖 Evidence |
| Recommendation | AI 综合后的观察与候选动作 | 只能在 Context Pack 之后生成，并受发布 Gate 约束 |

## 4. Context Pack 合并契约

```text
canonical market snapshot (required)
                +
intelligence snapshot (optional, degradable)
                ↓
versioned AI Context Pack
```

- Market sections：identity、market、valuation、financials、factors、liquidity。
- Intelligence sections：events、news_evidence、sentiment、coverage_gaps。
- 每个 intelligence item 必须携带 evidence pointer、known_at、quality 和 inference 标记。
- 情报源失败不会阻断 market-only pack，但必须降低覆盖状态；market 核心失败仍阻断正式建议。
- 数字冲突时 market snapshot 优先，情报文本只能作为待核实线索。

## 5. 实施顺序与 Go / No-go

### Phase 0 · Security cleanup

- 轮换已暴露凭据并证明旧凭据失效。
- secrets 改为环境变量/secret manager。
- 当前树和 Git 历史完成扫描并保存审计结果。

**Gate：** 任一旧凭据仍有效，`No-go`。

### Phase 1 · Contract and schema

- 定义 SourceManifest、上述 NOT NULL/CHECK 约束、Storage 路径和 snapshot manifest。
- 定义 `domain_scope`、`authority_tier`、Evidence/Inference 字段边界。

**Gate：** adapter 能绕过 provenance 或 LLM 推断能写入 evidence 字段，`No-go`。

### Phase 2 · Two-source pilot

- 1 个 A 股财经 RSS：建议从现有华尔街见闻开始。
- 1 个官方页面 monitor：交易所/巨潮/证监会发现入口；仍标记 supplementary-only。

**Gate：** pilot source 与 A 股无关，或网页监控被当作 canonical 公告源，`No-go`。

### Phase 3 · 24h replay and quality test

- 验证 `known_at` 截断，不允许未来数据进入历史 Context Pack。
- 验证相同事件在 RSS、Google News、雪球不同措辞下的语义去重。
- 分别验证 fetched、saved、unique、accepted、snapshot_included。
- 验证 Xueqiu cookie 失效时 stale/unavailable 和 coverage gap。
- 验证 LLM 数字不能进入 evidence 字段。

**Gate：** 不能 deterministic replay，或重复报道虚增事件热度，`No-go`。

### Phase 4 · Controlled expansion

- 依次接入 Google News、Yahoo Finance、更多 RSS、Xueqiu。
- Reddit/HN/GitHub 维持 thematic_global，默认不进入 A 股 pack。

### Phase 5 · Event and Context integration

- 复用 48h event topology，重做中文实体解析、相似度与权重。
- 生成不可变 intelligence snapshot。
- 与必填 market snapshot 组合成 AI Context Pack。

**Gate：** 任一消费者可以绕过 snapshot 或读取未标记推断，`No-go`。

## 6. 本轮验收状态

- Intel 角色边界：`Met`
- Source 迁移 verdict：`Met`
- Target schema contract：`Met at architecture level`
- Secret cleanup：`Not Met`
- Supabase migration：`Not Met`
- Real-source pilot：`Not Met`
- Replay evidence：`Not Met`

