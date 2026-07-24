# Park Equity Research · Epic Execution Plan

> 状态：`R0 Approved · Park approved 2026-07-24`
>
> 本文是正式执行合同，定义目标、现状、Epic、Milestone、Story、测试与成功标准。
> 执行必须复用 2.6 的现有 GitHub 容器；只为缺失 Story 建 child issue，不得改写验收标准。

## 1. 我们的 expectation

### 1.1 最终用户结果

Park Equity Research 是面向 Park、少数朋友和付费社群的私有 beta A 股长期投研产品。

用户输入一个受支持的 A 股代码或公司名称后，应得到：

1. 先从产业世界模型理解市场发展到哪里、价值链如何变化、哪些环节和公司受影响。
2. 再进入具体公司，得到一页决策摘要：产业位置、核心多空逻辑、估值区间、风险、催化剂、置信度，以及在证据充分时给出的建议动作与仓位区间。
3. 一份结构统一、证据可追溯的 30–50 页 Equity Research Report。
4. 报告中的事实、数字、图表和卖方观点都能回到来源、发布时间、原始文件、页码或 raw hash。
5. 数据不足时，产品显示 `partial / missing / stale` 和具体缺口，不用 AI 文案填满。
6. 同一产业或公司重新运行时，能解释数据、观点、估值、催化剂、关系和风险发生了什么变化。

### 1.2 我们希望复刻和超越什么

爱牛研究是信息密度、公司档案深度、产业链视角和研究维度的 benchmark，不是产品数据源。

我们要复刻的是其内容生产能力：

```text
外部来源
→ 可维护的数据 authority
→ 可审计 evidence corpus
→ 确定性计算与中层研究对象
→ 标准化 research compiler
→ Summary + Long Report + 产品视图
→ 持续更新、证伪与质量回看
```

我们不能复制爱牛原文、档案、评分结果或静态快照作为正式产品输出。归档只能作为离线 benchmark 和验收 oracle。

### 1.3 第一版明确边界

- 以 A 股为正式产品范围；港美日数据只服务于跨市场比较、同行与供应链研究。
- 30–50 页是证据充分后的目标深度，不是固定凑页数。
- 先通过 30 家黄金验证集，再通过 100 ticker 跨行业验收，之后才讨论“全 A 股支持”。
- AI/DeepSeek 只能解释冻结证据，不能创造事实、数字或引用。
- UZI/66 评委属于可选 synthesis，不是 evidence，也不是发布依赖。
- 第一版保留私域会员和人工履约；不建设公开注册、自动扣款或交易执行。

### 1.4 最终 Release success criteria

以下条件全部满足，才算达到当前 expectation：

1. 100/100 验收 ticker 身份正确，代码、简称、历史名称和交易所无静默误配。
2. 至少 95/100 能生成有效的 full 或 honest partial Report Model。
3. 至少 80/100 达到 Tier A/B 数据覆盖，其余股票显示可定位的 coverage gap。
4. 正式报告的事实数字与引用 100% 通过 evidence identity、页码/raw hash 和时点校验。
5. 在证据门通过时，能稳定生成一页 Summary 和结构一致的 30–50 页报告。
6. cached Summary 默认 p95 < 2 秒，cached Report payload 默认 p95 < 3 秒；新报告走异步状态流程。
7. 私有 beta 的权限、RLS、密钥、备份、回滚和审计经过专项验收。
8. 至少完成一次真实私域交付循环，并把反馈转化为可追踪的 issue 或 policy/test。
9. AI 算力产业第一版拥有 10–15 个主要节点、至少 104 个可研究细分环节、50–100 家公司的产业位置和可追溯的上下游关系/催化剂内容；这些内容由自有 evidence 生产，不复制 benchmark。

## 2. 我们现在做到哪里了

### 2.1 总体判断

- 距离最终 expectation：约 **20%**。
- 底层架构与代码骨架：约 **50–55%**。
- 用户可依赖的“任意 ticker → 可信 Summary + 深度报告”：约 **5–10%**。
- 当前前端可展示不少内容，但 Atlas 主要仍由 fixture/归档驱动，不能代表正式研究能力。

### 2.2 已完成并进入 main

| 能力 | 当前事实 |
| --- | --- |
| Canonical Data Foundation | A1–A5 已完成：五类数据契约、Supabase schema/raw storage、统一 ingestion、A 股身份/行情/PIT 财务、质量门与不可变 snapshot。 |
| Evidence Corpus Foundation | B1–B6 已完成基础实现：官方公告、卖方研报目录/PDF、页级解析/OCR、预测一致预期、新闻事件、Evidence Set/Context Pack。 |
| Research Engine Foundation | C1–C3 已完成基础实现：18 节 report contract、DCF/reverse DCF/情景估值、卖方观点与修订矩阵。 |
| 爱牛逆向 N1 | #111 字段归因、#112 东财主营构成与预约披露采集已关闭。 |
| Product Skeleton | 已有 ticker/report/member/editorial 的产品骨架与私域访问路径。 |
| Atlas Frontend | 已有产业图、股票表、分级表、公司工作台等第一切片，但数据是开发 fixture，尚未接 canonical API。 |

### 2.3 当前在途但未完成

| PR | 状态 | 已有结果 | 未达合同 |
| --- | --- | --- | --- |
| [#129](https://github.com/zinan92/equity-research/pull/129) | Draft | 跨市场日线、当前估值 adapter、30 家差异报告 | 8 家严格窗口残差；历史 mcap/PE/PB/PEG 与冻结 FX 缺口 |
| [#130](https://github.com/zinan92/equity-research/pull/130) | Draft | 综合分/机会分/PEG 公式复现 | composite 可计算分母为 585，不是合同中的 649；残差需定性 |
| [#131](https://github.com/zinan92/equity-research/pull/131) | Draft | dossier template + NVIDIA 自有证据样例 | 还缺 4 家档案、可复跑成本记录、Park + 外部读者盲评 |

### 2.4 关键缺口

1. 还没有经过验收的生产级数据覆盖，尤其是历史估值、公司行动、跨市场比较口径和数据新鲜度。
2. 现有 Evidence/Report 基础模块还没有在真实 30 家、3 行业、100 ticker 上形成完整闭环。
3. 还没有稳定的 dossier 生产流水线，当前只有模板和一份样例。
4. 还没有可审计地产生建议动作、目标价和仓位区间的 policy。
5. 前端还没有完全接上 canonical read API。
6. 还没有完成 100 ticker、权限安全、恢复、性能、成本和持续更新验收。

### 2.5 规划文件的现状说明

`docs/plans/2026-07-22-two-level-product-roadmap.md` 仍可作为架构背景，但其中引用的旧 #28–#71 在当前 GitHub 不存在，不能交给执行模型当作当前 issue 合同。

本文经 Park 批准后，先映射到现有 GitHub 容器，再只为缺失 Story 补 child issue。批准前它仍是审核稿。

### 2.6 现有 GitHub 结构处置表

原则：不创建第三套平行编号。批准 R0 后，优先复用现有 milestone/epic/issue；只有缺少独立 Story 合同时才新建 child issue。以下状态截至 2026-07-24。

| 现有容器 | 新计划归属 | 处置 |
| --- | --- | --- |
| Milestone N1 #8 + Epic #110 | E0 | 保留；#113–#116 直接承接 E0，不建重复 issue；E0-S6 通过后关闭容器 |
| Issue #113 + PR #129 | E0-S1、E0-S2 | 这是既有合并合同，不再拆重复 issue；S1/S2 两组 criteria 都通过后才可完成 |
| Issue #114 + PR #130 | E0-S3 | 继续使用现有 issue/PR，禁止新建“评分复现”平行票 |
| Issue #115 + PR #131 | E0-S4、E0-S5 | 这是既有“模板先审、再放量”合同；模板 gate 和 5 份盲评都通过后才可完成 |
| Issue #116 | E0-S6 | 保留为 N1 最终验收包；依赖 #113–#115 的真实交付，不靠说明绕过 |
| Milestone N2 #9 + Epic #117 | E1 | 保留并作为 E1 容器；批准后只补缺失 child issues |
| Milestone N3 #10 + Epic #118 | M3.1 产业世界模型内容生产 | 保留并恢复为产品差异化主线；不得被“任意 ticker 研报”路线替代 |
| Milestone N4 #11 + Epic #119 | E7-S2 | 保留；验收合同由 E7-S2 取代，不另建平行 epic |
| Milestone N5 #12 + Epic #120 | E5 | 保留；前端仅由 Claude Code 实施 |
| Milestone N6 #13 + Epic #121 | E7-S1 | 保留；验收合同由 E7-S1 取代 |
| L1-A #1 | E1/E2 | 已完成 A1–A5 全部复用；只处理剩余生产化缺口，不重写 foundation |
| L1-B #2 | E2 | 已完成 B1–B6 全部复用；E2 是 production acceptance，不是重新实现 |
| L1-C #3 | E3 | 已完成 C1–C3 全部复用；只补产业模型、真实数据验收、dossier、decision 和 compiler glue |
| L1-D #4 | E4 | 保留为 E4 容器；批准后逐张补 Story contract |
| L1-E #5 | E5 | 与 N5 合并管理：L1-E 承接非 Atlas 产品能力，N5 承接 Claude 前端 |
| L1-F #6 | E6 | 保留；复用已有 auth/cache/snapshot/deployment 能力，仅补可靠性验收 |
| L1-G #7 | E7 | 保留；N4/N6 是其已有子方向，不另建重复 epic |

旧容器最终关闭前，必须在其描述或关闭评论中写明“由 E/M/S 编号替代”的链接；禁止无说明关闭。

## 3. 总体执行图

```text
E0 基线收口
  ↓
E1 Canonical 研究对象
  ↓
E2 生产数据与 Evidence 覆盖
  ↓
E3 标准研究与决策引擎
  ↓
E4 Any-Ticker 与 100 股验收
  ↓
E5 用户产品与私有 Beta

E6 可靠性贯穿 E1–E5
E7 更新与质量飞轮在 E3 后启动
```

规划规模：

- 8 个 Epic。
- 23 个执行 Milestone。
- 43 个未来 Story；每个 Story 优先映射现有 issue；缺失时才在批准后新增一张 GitHub issue 和一个 PR。
- WIP 不超过 3；同一依赖链默认顺序执行。

### 3.1 Milestone 映射与验收标准

Milestone 是可独立验收的一段产品能力；Story 是交给执行模型的最小合同。只有同一 Milestone 下全部 Story 达标，该 Milestone 才算完成。

| Milestone | Outcome | Milestone success criteria | Stories |
| --- | --- | --- | --- |
| M0.1 来源与公式可复现 | 把已有逆向研究变成自有、可重跑的基线 | 来源策略、30 公司快照、评分分母与残差都能离线复算；无爱牛原文或评分进入产品输出 | E0-S1～S3 |
| M0.2 档案生产方法定型 | 证明不是只会逆向，也能自行生产研究档案 | 模板先通过人工审核；5 份自有档案满足字段、证据和盲审门槛 | E0-S4～S5 |
| M0.3 N1 验收关闭 | 将 N1 交付变成可审计完成状态 | 统一验收包列出来源、公式、档案、测试、已知缺口和可复验命令 | E0-S6 |
| M1.1 对象与身份统一 | 所有数据围绕稳定公司身份和统一对象流动 | 证券代码变更、上市地、公司身份可解析；8 个对象 schema 有版本和校验 | E1-S1～S2 |
| M1.2 权威写入与修订 | 同一事实可追溯、可修订、可复现历史状态 | 所有正式记录保留 source、known_at、hash、revision；重复写入幂等 | E1-S3～S4 |
| M1.3 统一读取接口 | 前端和编译器只读 canonical API | API 明确区分 live/cached/fixture；无静默 fixture fallback | E1-S5 |
| M2.1 行情与财务覆盖 | 建立可持续的 A 股量化底座 | 股票池、行情、财务、公司行动均有 point-in-time 语义、质量门和 last-good 策略 | E2-S1～S3 |
| M2.2 文件与预期证据库 | 报告能引用公告、财报和卖方预期 | 文档可检索到页级证据；预期可按机构、日期、口径比较并显示冲突 | E2-S4～S5 |
| M2.3 事件与发布证据门 | 数据不足时系统诚实降级 | 事件流可追溯；覆盖度、冲突、新鲜度共同决定 full/partial/blocked | E2-S6 |
| M3.1 产业世界模型内容生产 | 建立“先看产业、再看公司”的自有 AI 算力产业底图 | 10–15 个主要节点、≥104 个细分环节、50–100 家公司位置、上下游关系和催化剂正文均由自有 evidence 生成 | E3-S1～S4 |
| M3.2 行业与定量研究模板 | 不同行业用同一骨架、不同驱动 | 3 个行业 profile 生效；财务、估值、预期模块用真实 canonical 数据跑通 | E3-S5～S6 |
| M3.3 投资判断生成 | 从证据形成明确、可反驳的结论 | 档案、目标价、仓位、风险和 falsifier 均有规则、版本和证据链接 | E3-S7～S8 |
| M3.4 标准报告编译 | 同一输入稳定产出同一结构 | 离线重放能生成 summary 与标准长报告；数字和引用身份保持一致 | E3-S9 |
| M4.1 跨行业真实闭环 | 证明系统不只适配单一明星股票 | 宁德时代、贵州茅台和一家银行从采集到发布完整跑通 | E4-S1 |
| M4.2 批处理与诚实降级 | 任意 ticker 请求不会假装成功或无限卡住 | 支持排队、缓存、断点续跑；缺数据时给结构化原因和下一步 | E4-S2～S3 |
| M4.3 100 ticker 验收 | 达到第一版可用覆盖面 | 100/100 identity；≥95 可产 Report Model；≥80 达 Tier A/B | E4-S4 |
| M5.1 进入与快速决策 | 用户输入 ticker 后先得到清楚的研究状态和摘要 | 搜索、状态旅程、summary 在桌面和移动端可用；状态不误导 | E5-S1～S2 |
| M5.2 深度阅读与分享 | 长报告可读、可核验、可导出 | 章节导航、证据抽屉、版本差异、PDF/PNG 导出通过真实数据 E2E | E5-S3 |
| M5.3 私测交付 | Atlas 和会员流程承接真实研究能力 | Atlas 不再依赖 fixture；受邀用户可登录、阅读、反馈，编辑流程可控 | E5-S4～S5 |
| M6.1 安全与可观测 | 私测用户和数据边界可控，故障可见 | Auth/RLS/secret/audit 通过；来源和管线健康状态可观测、可告警 | E6-S1～S2 |
| M6.2 恢复与性能 | 系统可恢复、可回滚、成本可控 | 备份恢复演练成功；发布可回滚；缓存性能和成本预算达标 | E6-S3～S4 |
| M7.1 持续更新与历史 | 报告不是一次性快照 | 三层更新节奏运行；观点、催化剂、反证和版本变化可回看 | E7-S1～S2 |
| M7.2 结果反馈与扩张 | 用结果质量决定下一批覆盖 | 预测结果和误差可归因；质量看板控制行业与股票扩张 | E7-S3～S4 |

## 4. Epic 与 Story 全量拆解

## E0 · N1 基线收口与复现验收

**Goal**：结束“我们大概知道爱牛怎么做”的阶段，形成可执行的自有来源合同和 30 家黄金验证集。

**Epic success criteria**：

1. #113–#116 的验收口径被满足或由新的合同正式替代，不能靠 PR 说明绕过。
2. 快数据字段至少 80% 达高/中置信度来源归因。
3. 已披露评分公式在可计算样本上至少 95% 复现，残差有分类。
4. 5 份自有档案盲评均值达到 benchmark 的 80%，每个数字都有来源。
5. 30 家验证集覆盖 A 股核心公司、海外同行和不同数据缺口。

| Story | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- |
| E0-S1 市场来源口径收口 | 明确 price/chg/mcap/FX/PE/PB/PEG 的主源、fallback 和 as-of | 每字段有主备源、币种、时点和缺失策略；不从日 K 线倒推历史估值；8 个 residual 有原因分类 | source matrix readback；fixture parser test；独立 live probe；JSON/MD diff | #129 |
| E0-S2 30 家快照复算 | 对 30 家按正确交易日/市场口径复算 benchmark | 30/30 有可解释结果；通过/残差/缺失分开；容差变化有理由和版本 | deterministic replay；跨源 comparison；断网复跑；不提交 benchmark 原文 | E0-S1 |
| E0-S3 评分公式分母与残差 | 关闭 585/649 分母差异与机会分残差 | 逐类说明缺失输入、重复 code、人工覆盖；可计算分母固定；≥95% 可复算 | formula unit tests；完整外部归档 audit；residual JSON | #130 |
| E0-S4 Dossier 模板审核 | 让 Park/Claude 能判断模板是否值得放量 | 模板章节、事实/判断边界、来源格式、反题材与成本字段获批准 | schema/readback；NVIDIA 样例引用检查；Claude review notes | #131 |
| E0-S5 五份自有档案与盲评 | 证明档案可持续生产 | 共 5 家且至少 1 家海外；数字 100% 有来源；记录 token/时间/人工点；Park+外部读者盲评均值 ≥80% | dossier validator；同公司复跑结构 diff；盲评 receipt | E0-S4 |
| E0-S6 N1 验收包 | 给后续执行模型一个不依赖爱牛的基线 | 30 家 golden manifest、field/source matrix、formula report、5 dossier results、已知 gap 和 Go/No-go 结论齐全 | fresh-clone readback；hash manifest；benchmark 泄漏扫描 | E0-S2,S3,S5 |

## E1 · Canonical 研究对象与知识库

**Goal**：把公司、产业位置、证据、催化剂、路线图、评分快照、证伪条件和档案建成统一可版本化对象。

**Epic success criteria**：

1. 八类对象都有 schema、identity、source、known_at、confidence 和 revision history。
2. 649/661 benchmark universe 与正式 A 股 security master 有显式 crosswalk。
3. 任何对象都能回到 evidence；研究判断不能冒充事实。
4. 前端通过 read API 读取 canonical 数据，不读取 benchmark fixture。

| Story | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- |
| E1-S1 Company/Universe Crosswalk | 统一 ticker、公司、市场和 benchmark code | SH/SZ/BJ identity 唯一；649/661 逐条 matched/ambiguous/unmapped；别名不静默猜测 | crosswalk fixture；collision test；人工抽检 30 家 | E0-S6 |
| E1-S2 八类对象 Schema | **扩展 A1/A2 canonical contract，禁止另建平行 schema。** 建立 Company/SectorPosition/Evidence/Catalyst/Roadmap/ScoreSnapshot/Falsifier/Dossier | 每类 required/optional 字段、状态和版本固定；事实与判断字段分离 | schema tests；invalid payload rejection；migration readback | E1-S1 |
| E1-S3 Provenance 与 Revision | **复用 A2 raw storage 与 A5 immutable snapshot；只扩展研究对象 revision。** | source/known_at/raw hash/model version 完整；append-only revision；冲突可查询 | replay test；tamper test；revision idempotency | E1-S2 |
| E1-S4 Canonical Write Path | **复用 A3 `ingestion.py`/`authority_sink.py`；禁止 collector 直写或另建 ingestion framework。** | adapter 不直写正式表；失败保留 last-good；对象和 evidence 原子发布 | adapter contract suite；failure injection；clean migration | E1-S2,S3 |
| E1-S5 Canonical Read API 与 Fixture 隔离 | **复用现有 canonical store/report API 结构，只补八类对象读取和 fixture 隔离。** | company/sector/dossier/score/roadmap API 有 schema；fixture 与 production 配置隔离；无归档正文泄漏 | API contract tests；auth tests；fixture-off smoke | E1-S4 |

## E2 · 生产数据与 Evidence 覆盖

**Goal**：把已经存在的 A/B 基础模块变成可持续运行、有覆盖率和降级策略的生产数据链。

**Epic success criteria**：

1. 30 家黄金集能够持续刷新行情、财务、公告、研报、预测和事件。
2. 每条正式事实绑定 source、as-of、raw hash 和质量状态。
3. provider 失败不会污染上一个有效 snapshot。
4. Evidence Gate 能给出 Tier A/B/C/Missing 与具体缺口。

| Story | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- |
| E2-S1 A 股 Universe 与 Resolver | **复用 A4 `ashare.py` 与 security master；只做全量生产验收，禁止重写。** 输入代码/简称/历史名都找到正确证券 | SH/SZ/BJ 全量主数据；ST/停牌/退市按时点；ambiguous query 返回候选 | resolver corpus；100 ticker identity test；名称历史 test | E1-S1 |
| E2-S2 行情与 PIT 财务 Authority | **复用 A4/A5 ingestion、snapshot 与 quality receipts；只补覆盖和生产运行，禁止另建数据底座。** | 双源行情；公告日/修订版财务；币种单位一致；刷新幂等 | fixture + live contract；PIT/no-lookahead；replay | E1-S4,E0-S2 |
| E2-S3 公司行动、复权与估值补口 | **复用 A4 CNINFO corporate-action anchors 和 #129 adapter；只补缺口，禁止替换 canonical contract。** | 分红/拆并股/停复牌/复权版本化；历史估值和 FX 口径明确；无法取得时显式 gap | 官方来源 cross-check；adjustment test；valuation reconciliation | E2-S2 |
| E2-S4 官方公告与文档 Corpus | **复用 B1 `official_filings.py` 与 B3 `document_intelligence.py`；本 Story 只做生产化验收，禁止重写 collector/parser。** | 增量发现；raw PDF/HTML/hash/MIME；页码/OCR；citation 可回原文 | fixture parser；live probe；page-map ≥95%；OCR coverage ≥90% | E1-S4 |
| E2-S5 卖方研报、预测与分歧 | **复用 B2 `sell_side_archive.py`、B4 `consensus_history.py` 和 `viewpoint_matrix.py`；只补覆盖与验收。** | catalog/PDF/metadata/预测年度统一；重复/旧值/outlier 隔离；缺 PDF 显示 metadata-only | PDF/hash dedupe；estimate PIT；consensus replay；citation audit | E2-S4 |
| E2-S6 新闻事件与 Evidence Gate | **复用 B5 `event_intelligence.py` 与 B6 `evidence_gate.py`；只做生产运行和 coverage gate 验收。** | entity resolution、跨源去重、Evidence/Inference 分离；Context Pack 只含 accepted evidence；coverage tier 可复算 | event topology test；source failure test；gate/tamper test | E2-S1,S4,S5 |

## E3 · 产业世界模型、标准研究与决策引擎

**Goal**：先生产可审计的产业世界模型，再把产业位置和冻结的 Context Pack 编译成同结构、可审计的 Summary 和 Long Report。

**Epic success criteria**：

1. AI 算力产业先形成 10–15 个主要节点、至少 104 个可研究细分环节、50–100 家公司位置和可追溯上下游关系。
2. 产业节点、关系、公司位置和催化剂正文全部由自有 evidence 生产；benchmark 只能用于覆盖验收，不能作为内容来源。
3. 编译过程中禁止联网，所有输入来自 versioned Context Pack。
4. 报告使用统一 18 节 contract，行业差异通过 optional profile 处理。
5. 所有数字由确定性模块提供，AI 只写叙事并保持 citation identity。
6. 建议动作、目标价和仓位来自版本化 policy；证据不足时为空。
7. HTML/PDF/PNG/API 输出绑定同一 Report Model/hash。

| Story | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- |
| E3-S1 AI 算力产业本体 | 定义自有的产业节点与细分环节身份 | 10–15 个主要节点；≥104 个细分环节；每项有稳定 ID、定义、边界、版本和来源策略；不能直接复制 archive 分类正文 | schema/identity tests；duplicate/boundary audit；Park/Claude ontology review | E1-S2,E2-S6 |
| E3-S2 上下游关系图 | 建立可计算、可更新的产业关系 | 每条边有 source/target/type/direction/strength/as_of/evidence；冲突和未知不静默补全；可从任一环节遍历上下游 | graph integrity；cycle/edge validation；30 条人工证据抽检 | E3-S1 |
| E3-S3 公司产业位置生产 | 回答一家公司在价值链中做什么、受谁影响 | 50–100 家公司完成 segment/role/product/customer/revenue-exposure 映射；A 股为主、海外仅作同行/供应链；模糊映射进入待审队列 | coverage report；30 家 page-cited audit；ambiguous mapping test | E3-S1,S2,E2-S6 |
| E3-S4 104 环节催化剂内容 | 生产“市场发展到哪里”的中层研究内容 | ≥104 个环节均有 current state、driver、catalyst、leading indicator、risk/falsifier、time horizon；事实 100% 引用，人工/AI 判断显式标记 | section completeness；citation gate；staleness test；20 个环节盲审 | E3-S1,S2,E2-S6 |
| E3-S5 三行业 Profile | 电池、消费、银行使用同主结构和不同 KPI | profile 定义 inputs/sections/缺失策略；通用结构不分叉；行业 fixture 可审 | profile contract tests；三公司 expected-section test | E2-S6,E3-S1 |
| E3-S6 真实数据 Financial/Valuation/Matrix | **复用 C2 valuation engine 与 C3 viewpoint matrix；只接真实 Context Pack 并验收，禁止重写。** | 财务桥接平衡；Bull/Base/Bear、reverse DCF、comps 可复算；卖方矩阵逐报告引用 | golden number tests；sensitivity stability；broker citation audit | E2-S5,S6,E3-S5 |
| E3-S7 Dossier Generator | 从 evidence 和产业位置生产公司档案，而非复制 benchmark | 固定结构；数字 100% 有 source；事实/判断/未知分开；产业位置来自 E3-S3；成本/版本可记录；同输入复跑稳定 | dossier schema；citation gate；rerun structural diff | E0-S5,E2-S6,E3-S3,S4 |
| E3-S8 Decision/Target/Position Policy | 生成可解释的动作、目标价和仓位区间 | 估值、质量、流动性、风险、coverage 共同决定；单股/行业/现金上限；不足时为空 | policy boundary tests；counterexample cases；identity/hash tests | E3-S6,S7 |
| E3-S9 Offline Research Compiler | **复用 C1 `report_contract.py`、现有 renderer 和 UZI 参考模式；只补 compiler glue，禁止另建报告合同。** | compiler 不联网；18 节 full/partial/missing；DeepSeek 文案与事实分离；HTML/PDF/PNG/API hash 一致 | offline replay；citation/number gate；golden Report Model；render smoke | E3-S1–S8 |

## E4 · Any-Ticker 与 100 股验收

**Goal**：证明系统不是只对宁德时代或少数样板工作。

**Epic success criteria**：

1. 宁德时代、贵州茅台和一家银行完成独立人工审计。
2. 100 ticker 覆盖至少 10 个行业、不同市值及 SH/SZ/BJ。
3. 100/100 identity 正确；≥95 生成有效 full/partial；≥80 达 Tier A/B。
4. 批处理可恢复、幂等，单票失败不拖垮整批。

| Story | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- |
| E4-S1 三公司 Vertical Slice | 验证跨行业同一 pipeline | 三家公司事实、产业位置、估值、引用和报告人工签字；差异来自数据/profile，不来自三套模板 | independent audit；golden artifacts；review receipt | E3-S9 |
| E4-S2 Batch/Cache/Resume | **复用 A5 refresh/idempotency 和 `local_cache.py`；只扩展到多 ticker 报告任务，禁止另建 scheduler/cache。** | per-ticker isolation；resume/idempotency；cache 绑定 snapshot；并发和限流可配 | interruption test；cache isolation；rate-limit test | E2-S6,E3-S9 |
| E4-S3 Honest Degradation | **复用 B6 evidence tier 和 C1 full/partial/missing contract；只固化 Any-Ticker 降级 policy。** | Tier A/B/C/Missing 固定；每 tier 可输出结论固定；低覆盖不输出高置信仓位 | tier policy tests；missing-source matrix；UI/API contract | E4-S2,E3-S8 |
| E4-S4 100-Ticker Acceptance | 达到可对外描述的覆盖基线 | 满足本 Epic 的 100/95/80 指标；至少 20 股人工抽检数字与页级引用；失败分类固化 | full acceptance runner；human audit receipt；regression corpus | E4-S1–S3 |

## E5 · 用户产品与私有 Beta

**Goal**：让用户真正完成“输入 → 等待/状态 → Summary → 深度报告 → 验证证据 → 分享反馈”。

**Epic success criteria**：

1. 用户能理解 cached/fresh/generating/partial/failed 状态。
2. 五分钟内可以从 Summary 判断是否继续研究。
3. 长报告可导航、可验证证据、可打印和安全分享。
4. Atlas 完全切到 canonical API，正式模式不依赖 fixture。
5. 少数朋友能凭权限独立使用并提交可定位反馈。

**Ownership hard boundary**：E5-S1～S4 以及任何 `product/static/**` diff 只归 Claude Code。Codex 或便宜执行模型只能交付 API、数据 contract 和验收证据，不得修改前端文件。跨前后端工作必须拆成两个 issue。

| Story | Owner | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- | --- |
| E5-S1 Ticker Entry 与 Status Journey | Claude Code | 用户知道系统正在做什么 | search/resolver 快速反馈；状态和恢复路径清楚；权限不足与数据缺失文案不同 | browser E2E；mobile keyboard；failure/retry flow | E4-S3 |
| E5-S2 One-Page Summary | Claude Code | 五分钟读懂核心决策 | thesis/anti-thesis/valuation/action/position/risk/catalyst/coverage 首屏可见；数字回到 snapshot | DOM contract；desktop/mobile screenshots；evidence-link smoke | E3-S9,E4-S3 |
| E5-S3 Report Reader/Evidence/Version/Export | Claude Code | 深度阅读与分享保持同一事实身份 | 目录、section status、页级 evidence、版本 diff、HTML/PDF/PNG identity、安全分享完整 | browser/print visual test；citation click E2E；export hash test | E3-S9 |
| E5-S4 Atlas Canonical Integration | Claude Code | **复用现有 `product/static/atlas/` 和 `js/data.js` seam，禁止重做 Atlas。** 产业图和公司工作台停止依赖 benchmark fixture | `js/data.js` 切 canonical API；正式模式无 fixture；as-of/coverage 可见；六路由保持；100 ticker 仅是后续数据增强，不阻塞接 API | API mock + live smoke；route/mobile visual regression | E1-S5 |
| E5-S5 Private Beta/Editorial/Feedback | 执行模型（非 `product/static/**`） | 复用现有 `auth_store.py`、私域预览和 editorial skeleton，补齐后端交付闭环 | 邀请/entitlement、approve/publish、撤权、反馈绑定 ticker/report/section、纠错状态与 SLA；所需 UI 另开 Claude issue | auth E2E；editorial audit；feedback lifecycle；pilot receipt | E5-S1–S4,E6-S1 |

## E6 · Production Reliability

**Goal**：系统出现权限、数据源、数据库、成本或部署问题时能发现、隔离和恢复。

**Epic success criteria**：

1. Auth/RLS/secrets/audit 边界通过专项测试。
2. 交易日默认 19:00 前形成日快照，关键 source 连续失败 15 分钟内可见告警。
3. DB/Storage 恢复演练达到 RPO ≤24h、RTO ≤4h。
4. cached API、异步报告、成本和缓存满足已批准预算。
5. staging→production 和 rollback 有可重放 receipt。

| Story | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- |
| E6-S1 Auth/RLS/Secrets/Audit | **复用 `auth_store.py`、现有访问码流程和 Supabase migration；只做生产权限加固与验收，禁止重写登录体系。** | owner/editor/member 后端强制；service role 不进前端；audit append-only；密钥扫描无泄漏 | RLS policy tests；CSRF/session/rate tests；gitleaks | E1-S5 |
| E6-S2 Source/Pipeline Observability | **复用 A5 receipts、`research_refresh.py`、B6 coverage gate；只补生产指标、trace 和告警。** | source health/freshness、run trace、coverage impact、告警与降噪完整 | injected source outage；stale-data alert；run trace receipt | E2-S6,E4-S2 |
| E6-S3 Backup/Restore/Release/Rollback | **复用 A5 immutable snapshot/last-good 与现有 `product/deployment/`；只补恢复和回滚演练，禁止另建部署栈。** | DB/Storage 独立备份；restore 后 hash 验证；last-good read-only；staging/prod 隔离；rollback 成功 | clean restore drill；migration rerun；deploy/rollback smoke | E6-S1,S2 |
| E6-S4 Performance/Cache/Cost | **复用 `local_cache.py`、snapshot identity 与现有 report runtime；只做容量、成本和性能验收。** | p95 2s/3s；fresh report 异步；10×负载无串写；token/parse/storage cost 可查询和告警 | load test；cache identity test；cost receipt；concurrency test | E4-S2,E3-S9 |

## E7 · 三层更新与研究质量飞轮

**Goal**：让产品从静态报告升级为会更新、会证伪、会回看错误的研究系统。

**Epic success criteria**：

1. 慢知识、周期研究、快快照按不同 cadence 更新。
2. thesis、forecast、valuation、catalyst 和 falsifier 有版本历史。
3. 事件可以把假设标为 fulfilled/delayed/broken，但不能自动交易。
4. 研究质量以 coverage、citation、forecast 和 correction 衡量，不以报告数量衡量。

| Story | Goal | Success criteria | Required tests/evidence | Depends on |
| --- | --- | --- | --- | --- |
| E7-S1 三层 Cadence | **复用 A5 schedule/backfill 与 `research_refresh.py`；只增加 slow/periodic/fast 分层 policy。** | slow/periodic/fast 的 schedule、freshness、drift 和依赖固定；失败不覆盖 last-good | scheduler/backfill test；staleness simulation；replay | E2-S6,E6-S2 |
| E7-S2 Thesis/Catalyst/Falsifier History | **复用 B5 event intelligence、E1 revision model 和 E3-S4 催化剂对象；禁止另建事件体系。** | versioned thesis/forecast/valuation；trigger 有方向/阈值/时间窗；状态回指 evidence | history immutability；event matching；false-positive feedback | E3-S9,E7-S1 |
| E7-S3 Outcome 与 Attribution | 回看研究价值而非只看涨跌 | 建议按发布时点冻结；相对基准/行业/基本面分解；不用未来数据重算 | no-lookahead tests；benchmark attribution；paper ledger audit | E7-S2 |
| E7-S4 Quality Dashboard 与受控扩展 | **复用 A5 quality receipts 与 B6 coverage gate；只做跨周期质量聚合和扩张门。** | coverage/freshness/citation/forecast 指标；manual correction 形成 issue；新源/行业先 truth set 再放量 | metric integrity tests；source onboarding contract；Go/No-go receipt | E7-S1–S3,E6-S4 |

## 5. 测试合同

### 5.1 按工作类型选择测试

| Story 类型 | 最低测试 |
| --- | --- |
| 文档/计划 | readback、链接和 diff-scope；不跑全量产品测试 |
| 外部数据 adapter | fixture parser + schema/identity + 独立 live contract probe；live 失败不让 CI 随机红 |
| 数据库/schema | 空库 migration、重复 migration、RLS、rollback/restore |
| Provenance/evidence | raw hash、known_at、replay、tamper、冲突和 last-good failure injection |
| 评分/估值/建议 | 单元边界、golden cases、counterexamples、no-lookahead、版本/输入 hash |
| Report compiler | offline replay、number/citation gate、full/partial/missing、HTML/PDF/PNG/API identity |
| UI | targeted browser E2E、desktop/mobile screenshot、console/network error、权限/失败状态 |
| Auth/会员 | backend authorization、RLS、session/CSRF/rate、撤权 |
| 运营/可靠性 | source outage、staleness、load、backup/restore、deploy/rollback receipt |

### 5.2 禁止 over-testing

- S 级：只跑本模块专项测试与 diff/gitleaks。
- M 级：专项测试 + 一个直接上下游测试。
- L 级：先审计划；只在 schema、provenance、auth、compiler、publication gate 或数据库变化时跑相关完整 suite。
- 不因文档、小文案、局部 UI 修改重复跑全仓。
- 不为了追求“全绿数字”跳过真实验收缺口或放宽容差。

### 5.3 每张未来 Issue 的 Definition of Done

1. Issue 在开工前已存在，Outcome、3–7 条 success criteria、In/Out scope、禁区不含糊。
2. 一 issue = 一 branch = 一 PR。
3. 只改 issue 允许范围，不使用 `git add -A`。
4. Required tests 全绿；gitleaks 无新泄漏；红线路径未触发。
5. PR 包含 What / Why / Validation / `Closes #N` 与可展示 evidence。
6. `decision-log.md` 记录 Decision / Why / Evidence / Gotchas。
7. 完成后转 Ready；本仓测试全绿 + gitleaks 无泄漏 + diff 不触红线时，执行者自行 merge，不等待人工 approve。
8. merge 后更新本 REGISTRY 的“现在在哪里 / 下一步”。

红线只有两类：diff 涉及真钱/live 时必须等 Park 本人添加 `park-approved`；修改 `park-operating-system` 时只提 PR、由 Park 亲合。本计划不授权任何真钱/live 行为。

## 6. Release Gates

| Gate | 可见结果 | Go 条件 |
| --- | --- | --- |
| R0 规划批准 | 本文经 Claude 审核和 Park 批准 | 重大缺口已修订；43 Story 已逐张映射到现有或待建 issue |
| R1 N1 baseline | 自有来源和 30 家黄金验证集 | E0 全部通过；不依赖爱牛正文或评分输出 |
| R2 产业与三公司研究闭环 | AI 算力产业世界模型 + 宁德/茅台/银行 Summary + Long Report | M3.1 达标；E1–E3 核心完成；产业内容与三家公司独立审计 |
| R3 100 ticker acceptance | 可量化覆盖与失败清单 | E4 的 100/95/80 指标通过 |
| R4 Private Beta | 少数朋友能独立使用 | E5 + E6 关键门通过；真实 pilot receipt |
| R5 Sustainable Research | 持续更新和质量回看 | E7 运行一个完整周期并有校准结果 |

## 7. 审核与执行顺序

1. Claude 只审核本文：找遗漏、依赖错误、验收不可测、重复 Story 和过度建设。
2. Park 根据 Claude review 修改并批准 R0。
3. 批准后先按 2.6 映射现有容器；只为缺失 Story 新建 issue，不得生成第三套 epic/milestone，也不得把整段计划塞进一个大 issue。
4. 便宜模型严格按 issue 顺序执行；不自行改 success criteria；遇到已实现模块先复用并验收，禁止重写。
5. 默认关键路径：`E0 → E1 → E2 → E3 → E4 → E5`；M3.1 在 E1-S2 与 E2-S6 可用后启动，不能被 Any-Ticker 路线跳过。
6. E5-S4 只依赖 E1-S5，可在 100 ticker 验收前完成 API 接入；E4-S4 只增强其全量数据。
7. E6 随对应风险模块进入；E7 在 E3 有稳定输出后启动。
8. E5-S1～S4 和所有 `product/static/**` diff 只由 Claude Code 实施。Codex/便宜模型不得触碰；跨栈工作拆成 frontend/backend 两张 issue。
9. 前后端可并行，但正式验收必须使用 canonical API，不得用 fixture 代替。
10. 每张 PR 满足三道机器闸后自行 merge；只有 5.3 所列红线需要 Park 介入。

## 8. 下一步

当前下一步是完成 E0：

1. #113 / PR #129 完成 E0-S1、E0-S2。
2. #114 / PR #130 完成 E0-S3。
3. #115 / PR #131 完成 E0-S4、E0-S5。
4. #116 完成 E0-S6 并验收 R1。

上述 issue 已存在，不建重复票。当前 WIP 已达到 3，在 #129–#131 清空前不创建后续执行 issue。
