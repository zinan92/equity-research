# Decision Log

## 2026-07-30 · C1 adopts Round 7 as its native chapter contract

- Decision: replace the 18-section C1 taxonomy with the nine accepted Round 7 reader units. Production record and Sources remain required publication appendices but receive no Tier credit. Every reader section requires one complete `chapter_draft`; old field-oriented judgments may appear only as transitional optional material and cannot complete a chapter.
- Why: Round 7 already proved the reader-facing shape and specificity target. Mapping it back into 33 fragmented inputs recreated a lower-quality 632-character product instead of moving the production system toward the accepted 4,249-character dossier.
- Evidence: `research-section-contract-v3`, its receipt `round7-m2-section-contract-verification.json`, 647 passing product tests, the Round 7 verifier, and byte-identical hashes for `research_degradation.py`, `evidence_gate.py`, and `decision_policy.py`.
- Gotchas: the nine reader units are not the nine Markdown headings verbatim: “为什么它能赢 / 核心风险 / 大白话点评” are reader units nested under the accepted “风险与点评” presentation heading. Production record and Sources must be publication-gated without being counted as Tier sections. A human approval of one retired field judgment is not approval of a complete Round 7 chapter.

## 2026-07-30 · Model judgments are generated, never templated

- Decision: replace the issuer-specific judgment template with one generic frozen-evidence request and the existing DeepSeek transport. Model text and claim text are retained byte-for-byte; deterministic code may only select evidence, calculate explicitly recorded derived metrics, validate output, and map evidence IDs to page citations.
- Why: a fixed sentence containing a company name is neither analysis nor a rename-resistant issuer judgment. The research boundary requires each sentence and numeric token to be traceable to the exact frozen input that supported it.
- Evidence: `e4_model_judgments.py` enforces sentence/claim equality, claim-local numeric whitelists, page-identity matching, falsification fields, per-sentence rename audits, and typed MISSING output. Focused tests cover poisoned numbers, model outage, same-path second identity, suspicious table-note numbers, and absence of generator f-strings or issuer constants.
- Gotchas: the completed L2 100-ticker batch does not include either acceptance issuer; it cannot be cited for their runs. Existing page-fact receipts can contain column-note numbers that look syntactically valid, so the generator must reject suspicious small tokens rather than let the model rationalize them. A model transport failure propagates and writes no replacement prose or receipt.

## 2026-07-29 · First-report compilation remains offline and partial

- Decision: compile CATL from frozen M1/M2/M3 receipts and bind HTML to a Report Model hash.
- Why: report output must preserve page citations and expose incompleteness rather than promote a partial pipeline.
- Evidence: M4 receipt records input hashes, citation gate result and C1 section states.
- Gotchas: no network or DeepSeek call is permitted during compile; unreviewed judgment content stays separate from deterministic facts.

## 2026-07-29 · AGENTS.md stops restating the global manual

- Decision: `## Workflow Rules` no longer restates Park Operating System process. It now points at `~/work/park-operating-system/manual.md` as the single authority and keeps only two project-local items (Ready for Review after contract evidence, `park-ai-bot` identity for GitHub work).
- Decision: the deleted clauses are the ones that had gone stale and now contradict manual.md — "chain PRs when milestones depend on each other" (manual.md 三: 链式叠 PR 已废止, 做完一环当场自行合并) and "do not merge execution PRs unless Park explicitly asks" (manual.md 四: 三道机器闸全绿即自行 merge; 红线只有真钱/live 和法律层两条). Also removed as pure duplicates: one issue = one branch = one PR, WIP ≤ 3, no `git add -A`, PR body What/Why/Validation/`Closes #N`, and the restatement of the decision-log obligation.
- Decision: `## Testing Policy` and `## Review Policy` are re-anchored onto manual.md's S/M/L complexity scale rather than running a parallel taxonomy. The repo-specific content — which paths count as L — is kept; the competing framework is not.
- Why: two copies of one process rule cannot both be current. Codex has been executing manual.md (self-merging each story) while this file told it to stack PRs and wait for Park, so whichever file it happened to read decided the behavior. Global process now lives in exactly one place.
- Evidence: manual.md 三 and 四 as of POS `194d3fe`; this repo's own history shows the self-merge regime in use (each story merged before the next branch starts, recorded in REGISTRY). No behavior in the repo depended on the deleted clauses.

## Gotchas · AGENTS.md dedupe

- Two rules in the deleted block are global process that is **not** in manual.md today: "convert a completed PR to Ready for Review" (legislated in POS #4, dropped when #7 精简 rewrote the executor manual) and "use `park-ai-bot` identity for GitHub work". They are kept here as project-local items rather than deleted, because deleting them would silently retire a rule Park once passed. They belong in manual.md; that call is Park's, not this PR's.
- `~/Documents/投研面板` sits on a detached HEAD behind `origin/main`, and the repo carries 218 registered worktrees. Branch from `origin/main` explicitly — branching from HEAD silently bases the PR on a stale commit.
- `gh` in this repo resolves to `upstream` (`wbh604/UZI-Skill`), not origin. Every `gh` call needs `-R zinan92/equity-research` or it targets the wrong repository.

## 2026-07-23 · N1-3 cross-market price history boundary

- Decision: reuse the existing A-share Tencent/Eastmoney/Sina chain; add Yahoo Chart only for HK/US/JP historical close validation. The adapter preserves raw source URLs and hashes through the canonical ingestion boundary.
- Decision: historical daily bars may validate price only. They cannot reconstruct historical market capitalization, PE, PB, or PEG, so these fields remain separate snapshot facts or explicit missing values; no implied valuation is fabricated from close prices.

## Gotchas · N1-3

- Yahoo's unauthenticated quote endpoint returned HTTP 401 in this environment while its Chart endpoint succeeded. Treat the two endpoints as separate contracts; do not claim valuation coverage from chart availability.

## 2026-07-23 · N1-2 Eastmoney periodic adapters

- Decision: the first directly attributable recurring facts are implemented as two thin adapters on the existing `RawCapture → RecordEnvelope → IngestionRuntime` contract: F10 business composition and appointment disclosure calendar. They are `supplementary_only` vendor evidence, not a claim that Eastmoney is a statutory filing authority.
- Decision: F10 does not expose a filing publication timestamp in its business-composition response. The normalized `announced_at` is therefore explicitly tagged `availability_time_kind=provider_observation`; product code must not relabel it as an issuer notice date.
- Decision: the calendar endpoint caps responses at 500 rows. The collection helper serially requests every reported page; each page has a separate URL and raw hash. It returns no partial records as a complete calendar if any page fails.
- Decision: fixtures cover parser and failure semantics, while `scripts/probe_eastmoney_periodic.py` is an optional live contract probe outside CI. `scripts/validate_eastmoney_periodic.py` accepts a runtime-only expectation file so N1-6 can audit 30 companies without committing benchmark originals.
- Validation: a local 30-company A-share audit against the read-only archive passed on 2026-07-23: business-segment name coverage 93.46% (threshold 90%), complete 11-page appointment calendar, and 0 missing validation tickers. Only derived pass/fail metrics and this collector's own raw hashes were retained outside the archive.

## Gotchas · N1-2

- Eastmoney's `pageSize=10000` parameter is silently capped at 500; treating page one as a full universe produces a plausible but incomplete calendar. Always inspect `result.pages`.
- The calendar filter requires literal double quotes around the security-type codes. Escaped quote characters yield a successful HTTP response with no usable `result`, so contract probes must check parsed payload shape rather than HTTP status alone.
- A changed F10 report period may legitimately alter segment structure. Validation allows report-period changes but must retain the raw page hash and report period; it must not fill missing segments from an archived benchmark.

## 2026-07-17 · 启动 60 分内测版

- Objective：先交付能运行、能看懂、能追溯的 A 股长期投委会面板，不等待完整商业基础设施。
- Decision：第一阶段采用 SQLite 同构数据层 + 本地 API + 独立 Web UI；后续迁移 Supabase 时保持领域表和 API 语义。
- Decision：首个可视版本允许显式 `DEMO` 快照，但页面、API 和数据库必须完整贯通；不能把 JSON 直接写死进前端。
- Decision：UZI 作为中层研究消费者/提供者保留，不让 66 位评委成为首页信息架构。
- Decision：暂不接 Telegram、会员、支付、券商和自动下单。
- Evidence required：数据库记录、API 响应、仓位不变量测试、桌面/移动截图。

## Gotchas

- `DEMO` 标签不能隐藏在帮助页，必须出现在首屏数据状态。
- 股票与现金必须合计 100%，行业和单股约束不能只靠文案约定。
- “接口返回成功”不等于数据可发布；必须携带 as_of、source、quality 和 snapshot。
- 不覆盖当前工作树中的 `.scatter/`、`docs/architecture/`、`evidence/` 等既有未跟踪产物。
- 不把 SQLite 说成最终生产数据库；它是本地可运行基座和 Supabase schema 的前置验证。
- CSS 组件规则可能覆盖原生 `[hidden]`，造成数据加载后仍显示巨大 loading 空白；已增加全局 `[hidden] { display: none !important; }` 并用桌面/移动浏览器断言防止复发。
- UZI `fetch_basic` 在本机真实探测中超过 2 分钟未返回，不能放入产品 HTTP 请求链；采集必须异步、硬超时并保存降级状态。
- 腾讯除权股票简称可能带 `XD` 且截断，例如 `XD长江电`；身份校验以 ticker 为主、规范化简称前三字为辅，不能要求名称完全相等。
- 上游行情时间必须从无时区的 `YYYYMMDDhhmmss` 规范化为带 `+08:00` 的 ISO 时间，避免 replay 歧义。

## 2026-07-17 · 首批真实行情接入

- Source：腾讯行情 `qt.gtimg.cn`。
- Result：8/8 组合股票 accepted，保存 price、change_pct、high、low、quote_time、source URL、raw hash 和 fetched_at。
- Boundary：只升级行情事实，不升级组合建议；顶层继续显示 `DEMO`，质量状态继续为 `degraded / 不可发布`。
- Fallback：真实源失败时保留上次快照并显示覆盖缺口，不阻塞页面、不伪装实时。

## 2026-07-17 · 升级为 80 分真实内测版

- Decision：真实数据基座采用“不可变快照 + 来源运行凭证 + 确定性特征/组合版本”，HTTP 请求只读数据库，不在用户请求内调用 UZI 或上游接口。
- Decision：第一期候选池固定为 8 只 A 股核心资产；只对这 8 只的结果负责，不把它描述成全市场选股。
- Decision：行情与前复权日线暂用腾讯，主要财务指标暂用东方财富 F10；三类覆盖必须全部达到 8/8，否则整期 fail closed。
- Decision：组合评分由质量、价值、趋势、韧性组成；仓位满足 6–10 只、单股 5%–15%、现金 10%–40%、合计 100%。
- Decision：发布状态固定为 `quality_passed → approved → published`。Park 批准时锁定内容哈希，批准后内容变化必须 `invalidated`。
- Decision：真实业绩只从发布时点开始记录；当前没有发布后数据，页面显示“待发布”，不生成 sample performance。
- Evidence：REAL 8/8 行情、2568 日线、96 财务；8 股票 replay 零差异；隔离库批准/发布闭环；桌面、移动、详情、业绩、历史截图。

## Gotchas · 80 分版新增

- 腾讯历史成交量单位可能随板块/接口口径变化；当按手数推导的 ADV 超过市值 30% 时按股数口径修正，但生产版仍需独立成交额源交叉校验。
- `backdrop-filter` 会让后代 `position: fixed` 形成错误 containing block；移动端底部导航曾被固定在 header 内，已在窄屏取消 topbar 毛玻璃并验证 `navBottom=viewportHeight`。
- 浏览器 full-page stitching 会重复 sticky header/页面片段，视觉 Evidence 采用真实 viewport 截图，不把有拼接伪影的长图作为验收证据。
- 当前财务记录按最新报告期取值，已保存 notice_date；完整 point-in-time 回放仍需处理更正公告和版本化财报。

## 2026-07-17 · 深度研报 v1

- Objective：把“摘要卡片”升级成能支持仓位决策的研究底稿，第一只真实样板为宁德时代。
- Decision：Serenity 只作为产业链卡位研究方法和评分器，不采用个人神话、收益记录或 66 专家视觉包装。
- Decision：研报主骨架采用 SNDK PDF 的机构研究顺序；产品入口采用 PrismAIgent 的“30 秒结论 + 逐层下钻 + 固定目录”。
- Decision：PrismAIgent 公共样例的三档估值和完整逻辑受付费墙保护；不绕过，结论只基于公开预览。
- Decision：v1 不新增研究数据库表。结构化研究底稿与当前快照组合生成，先验证 report contract；公告全文、段落级证据和报告版本表进入 v2。
- Decision：宁德时代建议目标仓位沿用当前真实组合的 8%，但拆成“初始 4% + 两次 2% 验证仓”；估值只用显式 EPS × PE 情景，不伪装成尚未完成的 DCF。
- Evidence：2025 年报、2026 一季报、公司最新公告页、不可变行情/财务/K 线快照，以及所有估值输入和来源 URL。

## Gotchas · 深度研报新增

- 公司官网新闻属于一手但带有宣传偏差；市场份额、产能、销量优先回到年报原文，官网新闻只补充近期事件。
- Serenity 的分数是研究优先级，不是预期收益或买入信号；高卡位分不能覆盖估值、周期和技术路线风险。
- 宁德时代 2025 年库存量同比增长 75.47%，与 96.9% 产能利用率、销量增长并存；不能只讲“产销两旺”而忽略库存与在建产能风险。
- 2026 一季度经营现金流只同比增长 2.47%，显著慢于收入和利润增速；需要在现金转化部分单独标红，不能被高增长摘要掩盖。
- 场景目标价必须同时展示 EPS、倍数和相对现价空间；没有输入的目标价一律不显示。

## 2026-07-17 · 深度研报 v1.1 终审修正

- Decision：深度结论增加硬门禁。只有 `REAL + snapshot quality passed + 行情/因子/财务齐备` 才返回仓位和估值；DEMO/CACHED 只展示结构与缺口。
- Decision：仓位改为“当前可执行 4% / 条件上限 8%”，避免把三段验证仓误读为立即满仓。
- Decision：审批内容哈希加入研究底稿哈希；底稿事实、估值假设或来源变化后，旧批准不能继续发布。
- Decision：证据统计按“8 份独立文档 / 18 处文档内定位”分开，并加入 SNE Research 与 IEA 三份外部行业材料。
- Decision：估值增加 2025A EPS 16.14 元到 Bear/Base/Bull 2026E EPS 的增长桥，明确三档分别为 +2.2% / +16.5% / +30.1% 假设。
- Verification：18 项后端与契约测试通过；桌面与 390px 移动视口无全局横向溢出；浏览器返回键能关闭研报并回到组合。
- Evidence：`evidence/deep-report-catl-desktop-v1.2-2026-07-17.png`、`evidence/deep-report-catl-mobile-v1.2-2026-07-17.png`。

## Gotchas · v1.1 终审新增

- 同一份年报拆成十几个证据定位，不等于十几个独立来源；产品必须同时展示独立文档数与引用定位数。
- MOU 只代表合作意向和计划部署，不得写成“已确认大单”或收入。
- 移动端 headless Chrome 的普通 `--window-size=390` 实际 viewport 可能仍是 500px；验收必须用设备指标覆盖后读取 `innerWidth` 和 `scrollWidth`。
- 当前本地服务只绑定 `127.0.0.1`；若未来公网部署，审批 POST 还需要身份验证、CSRF 防护和操作审计，不能直接暴露。

## 2026-07-17 · 深度研报 v1.2 对抗终审

- Decision：`REAL/passed` 标签不再足够。研报门禁同时校验 publication 状态、8/8 accepted 行情、每股至少 250 条 accepted 日线、全组合财务覆盖、三类 source run 成功、宁德时代行情/因子/财务必需字段与 raw hash 完整。
- Decision：DEMO 或空壳数据响应只返回安全状态摘要和缺口，不再嵌套 target weight、reference price、Bull/Base/Bear 或估值文字。
- Decision：审批包增加 `research_logic_hash`，直接绑定 `research_reports.py` 的生成逻辑；EPS、评分、派生字段或证据算法改变都会使旧批准失效。
- Decision：组合首页统一改称“条件满足后的目标配置/条件目标仓位”，宁德时代同时显示“首笔 4% / 条件上限 8%”，不再让 82% 目标权益被理解为当周一次性成交。
- Verification：新增“手工把空库改成 REAL/passed 仍失败”的攻击测试，以及生成逻辑哈希变更导致审批包变化的测试。
- Decision：覆盖率最终按每只持仓逐一校验，不能用“某只股票多 250 条日线”抵消另一只股票零日线；每只必须有 1 条 accepted 行情、至少 250 条 accepted 日线和至少 1 条 accepted 财务。
- Decision：批准/发布状态机也使用数据发布门；即使手工把 DEMO publication 改成 `quality_passed`，仍不能批准或发布。
- Verification：新增“跨股票挪动覆盖仍失败”和“DEMO 手工改状态仍不可批准”两项攻击测试。
- Adversarial review：终审未发现剩余 P0/P1，产品完成度评估 86/100，可认定超过 80 分。

## 2026-07-17 · DeepSeek 研究写作层

- Objective：让 DeepSeek 提升中文投研叙事深度，但不允许其控制事实、行情、估值公式、仓位或发布状态。
- Decision：采用 `证据包 → deepseek-v4-pro → JSON 正文 → 来源/数字校验 → 快照绑定 → 页面渲染`，而不是让模型自由搜索和自由生成完整研报。
- Decision：Key 只在运行时从仓库外的受控密钥文件读取，不复制到项目、不写日志、不进入环境样例。
- Decision：DeepSeek 稿件必须绑定 `snapshot_id + profile_hash + research_logic_hash`；任何一个变化，旧稿自动失效。稿件文件哈希进入 publication approval package。
- Result：宁德时代 DeepSeek 正式稿使用 17/18 个可用来源，未知数字 0，结构校验通过；页面明确展示模型、生成时间和证据校验结果。
- Verification：19 项测试通过；桌面与 390px 移动视口验证；DeepSeek 正文截图保存在 `evidence/deepseek-report-analysis-section-2026-07-17.png`。

## Gotchas · DeepSeek 写作层

- 第一轮稿件把 `risks`、`falsification` 章节名误当成 source ID，审计门正确阻断；这些无效 ID 只做白名单删除，不替模型补写结论。
- 一次全量修复请求因 `finish_reason=length` 被截断，未进入产品；后续改为只重写缺失的仓位论证，避免重复生成和额外上下文成本。
- DeepSeek 可以把已有小数合理四舍五入，但不能创造新数字；数字校验允许与证据值相差不超过 0.5 的整数化表达。
- Codex 事实审计做了两处透明修订：把没有当前数据支持的“应收与库存同步上升”改为“应收仍待验证”；把产品未授权的“严格止损”改为“不再加仓并重审假设”。页面显示修订数量，artifact 保存具体规则和原因。
- 生成稿是当前快照的研究叙事，不是永久真相；新财报、新快照或研究逻辑变更后必须重新生成。

## 2026-07-17 · DeepSeek 写作层 v2 安全终审修正

- Correction：旧版“未知数字 0”只做了全局无符号数字比对，不能证明数字语义可靠；该表述废止。
- Decision：仓位动作、条件和综合执行决议全部由确定性 `executive` contract 生成。模型输出中的 `position_conclusion` 与投委会 `decision` 不进入公共 API，也不在页面渲染。
- Decision：模型正文禁止出现买入、卖出、加减仓、清仓、满仓、止损等执行语言；DeepSeek 只负责行业、经营、竞争、财务、估值分歧和风险因果叙事。
- Decision：数字审计升级为 243 条字段级 metric registry，逐项匹配 `metric_id + signed value + unit + source_ids`；来源 URL、日期、页码和 source ID 不进入数字白名单。
- Decision：AI 稿激活必须同时匹配 evidence hash；同一 snapshot 内任何底层行情或底稿变化也会立即停用旧稿。
- Decision：AI artifact 使用临时文件、fsync 和原子替换；截断、乱码或非法 JSON 只会让 AI 层失效，不能拖垮确定性研报。
- Verification：23 项测试通过，包含仓位越权、负数翻正、页码冒充财务数字、同 snapshot 证据变更、截断 artifact 五类攻击场景；公开 API 中模型仓位字段与执行语言均为零。
- Evidence：`evidence/deepseek-report-safe-final-2026-07-17.png`、`evidence/deepseek-deterministic-position-final-2026-07-17.png`。

## Gotchas · DeepSeek v2

- “模型字段不显示”还不够，必须同时从公共 API 删除，并用 validation version 阻止旧校验产物重新激活。
- 数字相同不代表事实相同；负增长、页码、年份和目标价必须保留正负号、单位、字段身份与本节引用范围。
- AI artifact 是可选增强层。任何读取、校验或写入故障都必须 fail closed 到确定性研报，而不是让整个报告返回错误。

## 2026-07-17 · DeepSeek 写作层 v3 最终边界

- Correction：固定执行词表无法穷尽“扩大风险敞口、调整配置、逐步退出”等同义表达；单靠自动词表不能批准模型稿上线。
- Decision：DeepSeek 正文改为纯定性因果分析，禁止任何阿拉伯数字和中文量化表达。所有行情、财务、估值、目标价与仓位数字只由确定性组件展示，因此不存在“正确数字被安到错误指标”的模型通道。
- Decision：自动生成的 AI artifact 一律为 `editorial_approval=pending`，即使结构与来源校验通过也不会进入公共 API。只有独立编辑批准且 approval hash 与 narrative hash 完全一致时才可展示；正文变化会自动撤销批准。
- Decision：当前宁德时代稿已完成对抗性编辑复核，删除模型执行决议、仓位语言和全部量化表述；公共 API 中模型正文可见数字为零，量化证据继续由确定性研报卡片承载。
- Verification：测试增至 25 项；新增“执行同义词自动校验通过但未获独立批准时仍不可展示”和“真实数字被错配到其他指标时直接阻断”两项攻击测试。
- Adversarial review：第三轮终审 P0=0、P1=0，评分 91/100，通过。

## Gotchas · DeepSeek v3

- 自动事实校验解决不了所有自然语言意图识别；高风险输出必须依靠结构隔离与独立批准，而不是继续扩充关键词。
- 纯定性 AI 叙事会牺牲部分段落中的数字密度，但换来清晰责任边界：数字来自数据库和公式，AI 只解释因果，用户仍可在同页查看完整量化卡片。

## 2026-07-17 · 自动更新引擎与研报版本差异

- Objective：把宁德时代从单份静态样板升级为可重复更新的研究产品；用户能看到本次数据与上一版相比改变了什么。
- Reuse：直接复用 `real_pipeline.py` 的三源采集、8/8 覆盖门、不可变 manifest、特征计算和组合约束，没有另建第二套采集链。
- Decision：统一入口为 `refresh_engine.py`。刷新前先归档当前已验证研报；采集失败或覆盖不足时记录 failed receipt，并继续显示上一快照。
- Decision：新增 `research_report_versions`，以 `snapshot_id + ticker` 为不可回写主键；同一快照再次归档使用 `INSERT OR IGNORE`，不覆盖旧报告。
- Decision：差异层只比较确定性字段，包括价格、估值、趋势、波动、综合评分、最新财务与仓位合同；AI 只报告审批状态，不参与变化计算。
- Decision：新快照使旧 DeepSeek artifact 自动失效。确定性研报立即可用，页面明确显示 AI 等待重生成和独立编辑批准，不偷偷沿用旧稿。
- Decision：页面刷新按钮调用真实更新链，而非只重载 API；历史页同时显示 refresh success/reused/failed receipt。
- Automation：已安装 `com.park.a-share-research-refresh`，工作日 17:30 自动运行；plist 留存在 `product/automation/` 作为可审计配置。
- Real verification：统一刷新经历多轮故障与版本门验证后，最终交付快照为 `snap_real_b0bac1135776` / `pub_real_b0bac1135776`。8/8 行情、2568 日线、96 财务全部通过，最终快照离线重放 8/8 零差异；23 项量化、披露期、市场状态、现金与全组合仓位字段无显著变化，系统如实输出 unchanged。
- Decision：snapshot manifest 同时绑定原始数据 hash、feature version 与 portfolio model version。模型逻辑变化必须升版本并生成新快照，不能因输入未变而复用旧组合文案。
- Failure verification：实际遇到三次腾讯 SSL EOF / 单股日线缺失，回执分别记录为 failed，首页始终保留上一份通过质量门的快照；第四次重试成功后才切换。另用故障注入验证“写入新 snapshot/publication 后立即异常”，半成品会同时标为 blocked。
- UI verification：1440px 桌面与 390px 手机视口均无横向溢出；最终证据为 `evidence/research-refresh-final-desktop-2026-07-17.png`、`evidence/research-refresh-final-mobile-2026-07-17.png`、`evidence/research-refresh-final-mobile-diff-2026-07-17.png`。
- Decision：刷新使用跨进程文件锁；builder result、数据库 publication/snapshot、active dashboard 与最终 report 四层身份必须一致。失败只隔离本次刷新新增的快照，并在失败回执保留其 ID 和 manifest。
- Decision：活动版本只允许 `quality_passed / approved / published`；`invalidated / blocked` 不得进入首页、股票详情或下一次仓位基线。DEMO/CACHED 草稿只用于结构预览。
- Decision：研报版本身份改为 `ticker + report_hash`。同一数据快照上的研究逻辑变化也必须新增不可变版本；入库前重新计算 canonical hash，拒绝伪造或陈旧 hash。
- Decision：研报、审批发布与 replay 共用时点边界：逐股报价日期、最后交易日、财务 notice_date、研究 source known_at 与 evidence ledger known_at/quality 均必须通过；未来或 rejected evidence 同时隐藏并阻断发布。
- Test verification：40 项契约与攻击测试通过；JavaScript 语法检查和 Python 全模块编译通过。
- Adversarial review：三路最终复核 P0=0、P1=0；整体代码 93/100、UI 96/100、金融数据与证据链 97/100，终审通过。

## Gotchas · 自动更新

- 新的原始响应 hash 不一定代表投资结论变化；quote time 等元数据变化会生成新 manifest，但差异层只报告影响研究判断的字段。
- 刷新失败不能让半成品成为首页最新版本；异常后若检测到新写入快照，必须标记 snapshot/publication blocked，首页查询排除 blocked。
- 日常自动更新不自动调用或批准 DeepSeek。外部模型成本和自然语言风险不能藏进无人值守任务。
- 刷新回执必须保存数据库中的完整 `manifest_hash`，不能只把快照 ID 的短后缀冒充数据指纹。
- “首次真实草稿、所有动作均为新建”只能出现在真正首版；有上一通过质量门的快照后必须改为版本变动说明，避免与页面上的“持有”动作互相矛盾。
- LaunchAgent 已安装并启用工作日 17:30 日程，但当前 `runs=0 / never exited`，只能证明调度配置就绪，尚不能声称系统定时任务已经实际触发过；真实刷新链已通过 CLI 和产品按钮独立验收。
## 2026-07-17 · 研报机构化视觉重构

- 决策：将报告唯一视觉方向锁定为“A 股券商深度研报抬头 + 买方投委会备忘录密度”。
- 决策：首屏只回答四件事——投资判断、当前价格、基准目标价、条件仓位上限；不再用巨型总分主导页面。
- 决策：把核心分歧、四项关键指标和三步建仓计划合并为一个投资委员会摘要，减少重复结论。
- 决策：正文统一为白底、细线、宋体标题和等宽数字；金色、情绪化满色卡片及英文装饰性眉题退出研报正文。
- 决策：移动端不允许横向表格滚动；财务、风险、观察清单与评分表在 390px 下改为纵向卡片。
- 决策：报告类型不得写死；由版本差异动态显示“首次覆盖 / 深度更新”。
- 决策：AI 生成与编辑批准是方法记录，不进入编号正文目录；正文只保留“补充研判”，模型与复核信息折叠在方法附录。
- 验证：JavaScript 语法检查通过；40 项产品测试通过；真实浏览器 390px 页面宽度与内容宽度一致，无横向溢出。

### Gotchas

- 研报在应用内是独立滚动容器，浏览器验收必须检查 `#research-report`，不能只检查页面根节点。
- 移动端模拟应使用 CSS 视口测试；启用浏览器 `mobile=true` 会引入额外缩放，不能据此判断实际布局宽度。
- 本轮只改信息架构与视觉表达，不改数据快照、仓位规则、估值公式和 DeepSeek 生成内容。

## 2026-07-18 · JPMorgan / McKinsey 报告语言重构

- 用户结果：研报从墨绿色“金融终端感”改为可直接对外转发的国际咨询/私人银行报告语言。
- 参考基准：JPMorgan Outlook 的投资结论密度与评级模块，McKinsey Insights 的白纸、严格网格、无衬线正文和数据蓝。
- 视觉决策：白色纸面、深海军蓝 `#0B1F3A`、数据蓝 `#005EB8`、冷灰背景；红色只保留给负面风险。
- 字体决策：全面退出宋体，标题与正文统一使用 Helvetica Neue / Arial / PingFang SC；数字使用 Arial。
- 封面决策：公司名与投资命题分两层；评级卡同时展示现价、目标价、隐含空间、仓位上限及悲观—乐观估值区间。
- 导出决策：新增 `report-export` 长图模式，隐藏应用导航与目录，将正文展开为 1200px 报告画布。
- 交付证据：`evidence/宁德时代_深度研究报告_长图_2026-07-18.png`，尺寸 1200×9411；另有桌面和手机首屏截图。
- 出版清理：长图隐藏滚动条，并移除 `Missing`、内部快照 ID、`known_at` 与 AI 生成流程状态；后台仍保留完整审计信息。
- 验证：40 项测试通过；桌面及 390px 手机端均无页面横向溢出。

### Gotchas

- 浏览器对超长页面的单次 `captureBeyondViewport` 会重复首屏，不能把“生成了 9409px 图片”误当成内容正确；本次改为固定滚动坐标逐段捕获并无缝拼接。
- v3 桌面网格规则位于早期移动规则之后，因此移动断点必须显式重置 `report-hero` 和 `report-layout` 的列定义。
- 长图模式只改变展示与导出，不改变任何研究数据、结论、估值或仓位字段。

## 2026-07-18 · Milestone 1：首批 8 股批量研究生产线

- User outcome：一次命令从同一份不可变 REAL 快照生成首批 8 只 A 股研究报告、独立版本和批量回执；单股失败不拖垮其余股票。
- Decision：只刷新一次全组合数据，不按股票重复抓取。批量器复用 `real_pipeline`、研究质量门和 `research_report_versions`，不新建第二套数据管道。
- Decision：宁德时代保留 `deep` 公司级报告；其余 7 股先交付 `quantitative_baseline`。基线只把行情、250+ 日线、财务和四维因子列为已验证证据，并在页面明确披露公司经营、行业、治理和正式估值仍待深度研究。
- Decision：7 股基线使用独立 `stress_test` 契约（`price_basis / stress_multiple / stress_price`），不复用 EPS、PE、target_price 正式估值字段；未经盈利预测和历史/同业估值校准，`valuation.status=pending_company_research`。
- Decision：拆开数据与研究状态。7 股为 `data_status=verified / research_status=baseline`；组合给出的比例只叫“模型观察权重”，`current_executable_weight` 为空，必须完成公司级深度研究并经 Park 批准后才能转成执行合同。
- Decision：量化质量、价值、趋势、韧性分进入独立 `quant_signals`，不写入 `moat`；护城河、治理和行业地位在缺少公司级证据时明确显示待研究。
- Decision：每只报告独立生成、校验、归档和落盘；状态为 `success / reused / blocked / failed`。批量只有 8/8 为 `success/reused` 才能整体标为 `success`。
- Decision：批量回执采用原子写入，包含 batch ID、snapshot/publication identity、逐股 report hash、深度标签、成品路径和质量门计数；`latest.json` 保存最近一次结果。
- Decision：报告身份同时绑定请求 ticker、公司名、snapshot、publication 与 REAL data mode；生产批次必须精确等于配置的 8 股集合，子集不能伪装完整成功。
- Decision：先原子写入单股报告文件，再归档不可变版本；文件失败不会留下“幽灵版本”。批量使用跨进程锁，原子替换后 fsync 父目录。
- Decision：研究 policy hash 按 ticker/report family 分离；七股基线政策变化不会无故改变宁德时代深度稿的 AI artifact/审批身份，组合审批另使用全体 policy hash。
- Verification：47 项契约与攻击测试通过；覆盖 8/8 生成、第二次运行 8/8 复用、单股故障注入后其余 7 股正常落盘、错 ticker 复制攻击、子集伪装、磁盘失败幽灵版本、DEMO/数据不完整 fail closed。
- Real receipt：`batch_20260717T170830Z_real_b0bac1135776_353ea4`，`snap_real_b0bac1135776`，8/8 success；逐股报告哈希与 JSON 成品记录在批次 `index.json`。
- Adversarial review：代码复审与金融证据复审二次终审均为 P0=0 / P1=0；代码验收完成度 100%，金融语义评分 96/100，Milestone 1 通过。

### Gotchas · Milestone 1

- “有 8 份 HTML/JSON”不等于“有 8 份深度研究”。产品必须同时展示 `research_depth`；量化基线不能伪装成公司级深度稿。
- 数据覆盖门不能为批量成功而放松。测试最初只有宁德时代两期财报，另外 7 股被正确阻断；修复方式是补齐测试证据，不是降低财务记录门槛。
- 单股生成失败与共享数据刷新失败是两类故障：前者允许批次 `partial` 并保留其他成品，后者没有安全的新快照，整批必须 `failed`。
- 报告哈希不包含运行时 `update_diff`，否则同一确定性报告仅因历史上下文变化就会产生新版本；归档仍会重新计算 canonical hash，拒绝陈旧或伪造哈希。
- “数据已验证”不能被提升为“公司研究已完成”。对外状态、仓位语义和可执行性必须分层；真实行情和财务完整，不代表已经具备护城河、管理层和目标价结论。

## 2026-07-18 · Milestone 2：公司证据集与 DeepSeek 编辑闭环（完成）

- Objective：每只深度研报都能证明“模型看过哪些原始资料、这些资料在当时是否可知、正文由谁批准”，避免聚合数据、未来信息或陈旧材料直接变成投资结论。
- Reuse：UZI-Skill 只复用为 21 维上游采集器；Serenity 的证据梯级用于确定 strong / medium / lead 边界。没有复制 66 人评委、人格头像或机械评分。
- Decision：新增不可变 `research_documents / research_evidence_sets / research_evidence_set_items`。证据集按 `ticker + snapshot + knowledge cutoff + policy version + document hashes` 冻结。
- Decision：UZI 的每个维度无论显示 full / partial / missing，都只按 `lead` 保存。没有明确底层 URL、发布日期和来源强度的聚合结果不能进入公司证据门，也不能进入 DeepSeek evidence pack。
- Decision：公司证据门至少要求两份有日期的公司原始资料或公司公告、一份有日期的独立交叉来源、合计三份合格文件；未来资料排除，最新公司资料超过 180 天或独立来源超过 365 天则阻断。
- Decision：DeepSeek evidence pack 绑定通过门禁的 `evidence_set_id + manifest_hash`。公司、快照、研究逻辑、证据清单或正文任一变化，旧稿与旧批准都 fail closed。
- Decision：DeepSeek 提示词从写死“宁德时代”改为读取报告 identity；模型仍只写定性因果叙事，数字和仓位继续由确定性组件负责。
- Decision：新增独立编辑批准命令。编辑必须提交自己看过的 `narrative_hash` 与 `evidence_manifest_hash`；自动生成稿始终 pending，哈希不一致、证据过期或重新校验失败时拒绝批准。
- Invalidated evidence：旧快照 `snap_real_b0bac1135776` 曾把 8 份 locator 元数据误标为合格证据；对抗审查后该口径和旧 evidence set 已失效，不能作为验收凭证。贵州茅台 UZI 实跑的 21 维继续只作 lead。
- Correction：初版只冻结 locator JSON，且只按日期比较 `published_at`；这不能证明模型看到哪版原文，也会让同日未来资料或截止后才观察到的资料穿透。该实现已废止。
- Decision：正式证据现在必须保存原始 PDF/HTML bytes，记录 `raw_sha256 + canonical_url + fetched_at + MIME + HTTP status`；manifest 直接绑定原文哈希、角色、发布时间与观察时间。相同原文 bytes 自动去重，不能用两个 document ID 凑两份 primary。
- Decision：时点门统一把 published / observed / fetched / knowledge cutoff 解析为带时区 instant 后转 UTC 比较；只有日期而没有时刻的资料按当日结束处理，同日截止前 fail closed。研究知识截止可晚于行情快照，但不能早于数据快照，并单独进入 evidence manifest。
- Decision：角色不再信任调用方标签。primary/company release 必须来自监管/交易所或该公司的官方域名，independent 必须来自受控独立来源域；无 HTTPS、抓取失败或来源角色不匹配一律降为 lead。
- Decision：时效按每份核心资料检查，不再用一篇新软文掩盖旧年报。通过门禁至少需要两份 180 天内公司/监管资料，其中至少一份监管/正式财报，以及一份 365 天内独立来源。
- Decision：三张证据表由 SQLite trigger 强制 append-only；读取时复算 manifest、gate、角色计数和本地 raw file hash，任一不一致视为无有效证据集。
- Decision：深度报告、组合 approve/publish 与 approval content hash 直接绑定当前 evidence set；缺失证据集时宁德时代降为 `company_evidence_pending`，不返回仓位或估值。
- Real evidence：新真实快照 `snap_real_ae3526c152fb` 已冻结宁德时代 6 份真实原文（4 份公司/监管、2 份 SNE 独立来源），门禁通过。贵州茅台已冻结 3 份真实原文（2025 年报、2026 半年市场工作会、新华网经营结果交叉核验），门禁通过；原 21 个 UZI 维度继续只作 lead。
- Verification：当前 60 项产品测试通过；覆盖同日未来、截止后观察、缺 URL、聚合器冒充、相同 raw 重复计数、陈旧资料掩盖、数据库篡改、深度 report 无证据降级、approval hash 直绑 evidence manifest 等攻击。
- Final review：当前宁德时代 artifact 为独立编辑批准状态，且 snapshot、evidence manifest、narrative、research logic 与 writer logic 全部当前有效；金融证据终审 P0=0 / P1=0。

### Gotchas · Milestone 2

- 上游采集器返回 `full` 只代表该 fetcher 自己认为字段齐全，不代表资料是原始公告、时点正确或能独立支撑研报事实。
- 同一份年报中的多个页码或字段 locator 只能算一份 document，不能用拆 locator 的方式虚增证据数量。
- 自动结构校验通过不等于可以上线；自然语言事实审计存在不可穷尽边界，因此必须保留独立编辑双哈希批准。
- 市场行情快照可以作为支持资料，但不能冒充公司原始资料来凑“两份 primary”门槛。
- 周末或休市日的研究知识截止可以晚于最后行情时间；必须显式记录两个时间，不能把“行情截至周五”误写成“周六新公告不可用”。

## 2026-07-18 · Milestone 3：组合级投委会决策首页（完成）

- User outcome：Park 打开首页即可区分“模型观察、研究完成、建议复核、已经批准执行”，不会把 82% 模型观察仓位误读成真实可执行仓位。
- Success criteria：首屏显示 8 股研究覆盖、1/8 公司级深研、4% 建议复核、0% 已批准执行、78% 待研究；每只股票有下一道研究门；整期 8/8 未完成前组合批准 fail closed。
- Decision：仓位语义固定拆成 `model_observation_weight / decision_review_weight / current_executable_weight`，禁止一个 target weight 同时承担研究观点和执行指令。
- Decision：单股编辑批准只允许其进入 Park 决策复核；整期 publication approval 绑定当前 snapshot、全部研究政策与报告内容哈希，7 只量化基线仍在时不能批准整期组合。
- Decision：批准状态在每次读取时重验。任何报告、证据、正文或逻辑变化都会隐藏复核/执行仓位并使旧批准失效。
- In scope：组合就绪度、研究队列、单股/整期门禁和桌面/移动首屏。Out of scope：自动交易、真实券商持仓、组合收益归因。
- Verification：代码、金融证据、桌面和移动 UI 三路对抗终审 P0=0 / P1=0；证据为 `evidence/m3-committee-home-desktop-2026-07-18.jpg`、`evidence/m3-committee-home-mobile-2026-07-18.png`。

### Gotchas · Milestone 3

- “单股报告获批”不等于“整期组合获批”；两者必须有不同 identity 和不同发布门。
- `0` 与 `null` 语义不同：0 是已评估后明确为零，null 是尚未获得执行资格；页面不得统一格式化成 `0%`。
- 首页视觉层级必须先展示决策就绪度，再展示模型观察池，否则用户仍会先看到大仓位数字并形成错误锚定。

## 2026-07-18 · Milestone 4：可发布的 HTML / 长图 / PDF 版本包（完成）

- User outcome：一条命令生成可转发的独立 HTML、1200px 长图、A4 PDF 和 ZIP，并能证明它们对应当前获批研报，而不是某个陈旧页面。
- Success criteria：五类成品齐全；manifest 和 ZIP 哈希可验证；相同 identity 幂等复用；旧包自动标记 stale；工作日 18:30 自动任务真实退出码为 0；PDF 不裁切且页内结构完整。
- Reuse：直接使用成熟 Playwright/Chromium PDF 引擎，不自造排版器。
- Decision：pack identity 绑定 ticker、snapshot、publication、report、research/profile/evidence/narrative、render version 与 render logic hash。
- Decision：构建使用跨进程锁、隐藏 staging、完整验证后原子 rename；相同 identity 返回 `reused`，不得覆盖有效包。`latest.json` 原子替换。
- Decision：发布门解析 PDF 页数、PNG IHDR 尺寸、HTML meta/正文、render receipt 身份与 733px A4 打印溢出审计；只检查 `%PDF` 或 PNG 签名不算验收。
- Decision：manifest 只能包含精确五文件 allowlist，拒绝 symlink 和路径越界；archive 必须严格位于 `PACK_ROOT/<pack-id>.zip`。
- Decision：ZIP 本身也必须可打开、通过 CRC、精确包含五个成品和 manifest，并逐成员哈希匹配本地已验证文件；任意“存在但不可解压”的 ZIP 不得被重签为 reused。
- Decision：渲染器必须从当前 report API 核对 ticker、公司、report hash 与完整 payload hash；HTML/PDF/PNG 均携带同一报告指纹，PNG 还由像素级 64-bit 校验条复核。构建结束前再次计算 publication identity，避免渲染期间发生版本切换。
- Result：当前包 `pack_300750_SZ_b1ecd13db95491ac`，14 页 A4 PDF，长图 1200×11987，重复构建返回 `reused` 且哈希不变；LaunchAgent `com.park.a-share-publication-pack` 已成功实际运行一次，`last exit code=0`。
- Final review：代码真实性、金融证据与 UI 鲁棒性三路终审均为 P0=0 / P1=0。
- In scope：单股深研发布包与本地自动生成。Out of scope：群发渠道、邮件、Telegram、公开 CDN。

### Gotchas · Milestone 4

- 桌面 1200px 长图不能直接塞进 A4；Chromium 会静默裁掉右侧内容。打印必须有独立 733px 内容宽度、横向溢出硬门和逐页视觉复核。
- 文件哈希自洽不代表文件可用；截断 PDF、伪 PNG 和错误公司 HTML 仍可能拥有“正确哈希”，必须解析结构并核对报告 identity。
- 确定性 pack ID 会把失败重跑指向同一路径；不使用 staging/lock 会先破坏上一个有效包，再报告构建失败。
- `latest` 只验证旧包内部哈希会把陈旧内容继续当成当前版本；读取时必须重新计算当前 publication identity。
- LaunchAgent 没有 Codex 交互会话的 PATH 和 locale；PDF 验证必须使用稳定的 Homebrew 绝对路径并显式按 UTF-8 解码，否则手工运行通过、定时任务仍会失败。

## 2026-07-18 · Milestone 5：少数朋友私域会员交付（完成）

- User outcome：Park 可用邀请码把少数朋友分成预览、研究、付费和 owner 席位；用户能登录，按等级阅读首页/深研/发布包；停用后现有会话立即失效。
- Success criteria：唯一 owner；限次/限时邀请码；PBKDF2 密码哈希；HttpOnly + SameSite session cookie；CSRF 保护写操作；四级 entitlement；下载不泄漏本地路径；成员停用和邀请码撤销；匿名/preview/paid/owner HTTP 验收。
- Decision：v1 不接支付网关。`paid` 是由 Park 控制发放的邀请码等级，先验证内容价值和交付闭环，再决定订阅系统。
- Decision：Session 和 CSRF 只保存 SHA256 hash；密码使用随机 salt + PBKDF2-SHA256 310k rounds；成员停用同时撤销全部有效 session。
- Decision：本地开发默认 `PARK_AUTH_REQUIRED=0`，不影响报告生成；私域部署必须显式开启身份门，公网必须在 HTTPS 下设置 `PARK_COOKIE_SECURE=1`。
- Decision：preview 只看 dashboard，member 增加 deep reports，paid 增加 publication downloads，owner 才能刷新、批准、发布和管理成员。
- Decision：发布包 API 只返回 pack ID、完整性和下载 URL，不返回本机 `pack_dir/archive`；下载使用 allowlist、当前 pack identity 和路径 containment。
- In scope：邀请注册、登录/退出、角色门、下载门、CLI 成员管理、私域登录 UI。Out of scope：支付扣款、邮件找回、二次验证、公开注册、Telegram。
- Verification：79 项测试通过，其中独立 HTTP server 验证匿名 401、preview 深研/内部批次 403、paid 深研 200、owner 无 CSRF 写操作 403，并发创建 owner 只有 1 个成功；发布 ZIP 还经过可解压、CRC、精确成员集和逐成员哈希校验；证据为 `evidence/m5-private-beta-login-2026-07-18.png` 与 `evidence/m5-private-beta-member-home-2026-07-18.png`。
- Final review：代码真实性、金融证据与 UI 鲁棒性三路终审均为 P0=0 / P1=0。

### Gotchas · Milestone 5

- 会员等级不是前端隐藏按钮；每个 API 和下载端点都必须在后端重新检查 entitlement。
- HttpOnly session cookie 不能让前端读取 CSRF secret；登录或 `/api/auth/me` 必须下发轮换后的 CSRF token，数据库仍只保存 hash。
- 本地测试如果默认强制身份门，会让无人值守报告渲染失效；渲染子进程必须明确使用本地无身份模式，公网服务才开启门禁。
- 当前 SQLite 会员层只适合少量私域用户；多实例公网部署需迁移 PostgreSQL/Supabase、共享限流与 RLS。

## 2026-07-21 · Gate 0：私有仓库可恢复基线

- Objective：Park 能从 `zinan92/equity-research` fresh clone 当前投研产品，在不依赖 Wendy 本机路径、不携带密钥或运行时数据库的前提下启动、验证和继续迭代。
- User outcome：仓库首页直接说明产品是什么、真实做到哪里、如何启动、失败时如何表现；新的执行者不再把根目录误认成纯 UZI-Skill。
- Decision：保留 UZI-Skill 作为成熟的数据采集与多维分析基座，不重写 fetcher；产品入口明确固定为 `product/server.py`，根 `run.py` 只属于可复用 skill。
- Decision：本地 dashboard 使用独立最小依赖 `product/requirements.txt`；完整 UZI 数据管道仍使用根 `requirements.txt`，避免只看产品也要安装整套量化依赖。
- Decision：发布渲染器不再依赖 Codex/Wendy 的固定 Node、Playwright 或 Chromium 路径；按环境变量、项目本地 npm 依赖和系统 PATH 依次解析。
- Decision：渲染 identity 绑定 `package-lock.json`；若显式覆盖 `CHROME_PATH`，同时绑定该浏览器的版本输出，避免渲染环境变化却复用旧 pack ID。
- Decision：LaunchAgent 文件降格为可审计模板，仓库内只保留 `/ABSOLUTE/PATH/TO/equity-research` 占位符，安装前必须由执行者替换。
- Decision：新增 `scripts/verify_baseline.py`，用临时数据库和临时端口执行 tracked-file audit、79 项产品测试、服务健康检查和 dashboard smoke；不得触碰用户 runtime。
- Decision：根 README 如实披露当前只有宁德时代达到公司级 deep，另外 7 股只是量化 baseline；无公网生产、支付、全市场选股或自动交易。
- In scope：仓库身份、README、最小依赖、路径可移植性、秘密/运行态边界、fresh-clone 验收与精选视觉证据。
- Out of scope：标准研报结构 v1、研究算法重写、数据库迁移、付费、公网投产。

### Gotchas · Gate 0

- “代码已经 push”不等于“仓库可接手”；错误的根 README 和固定本机路径会让 fresh clone 仍然不可用。
- 上游 UZI 的插件入口与本产品入口同时存在，必须在 README 和 Agent 指令中明确区分，不能把跑 skill 当成启动产品。
- 自动化 plist 提交到 Git 只能证明模板可审计，不证明新机器已安装或定时运行成功。
- gitleaks 通过只证明未命中已知秘密规则；仍要同时审计 tracked file、环境变量样例、runtime/cookie/session 忽略规则。
- 基线 smoke 使用演示数据库，只证明 UI/API 能恢复；不证明外部实时数据源在当前网络下可用。

## 2026-07-21 · Milestone 1：标准研报结构 v1（待评审）

- Objective：无论输入宁德时代、特斯拉或未来公司，用户都得到同一套专业、可验证的内容结构和格式；市场差异显式表达，证据不足不伪造。
- User outcome：研究对象变化不再导致模板漂移。八个必需模块、顺序、单位、币种、声明和证据语义由 `research-report-v1` 统一约束。
- Decision：复用现有确定性 report payload、证据门和 Playwright 发布链，不重写研究算法或渲染器；在其上增加版本化 contract adapter。
- Decision：module manifest 是 Web、390px mobile 与 print/export 的唯一顺序来源。缺失、未知或乱序模块 fail closed，不能静默跳过。
- Decision：`missing_evidence` 与 `not_applicable` 分开。前者表示适用但证据不够，必须可见；后者只用于真实的公司/市场不适用场景。
- Decision：报告身份固定绑定公司、交易所、市场、币种和会计准则；发布 identity、HTML metadata 和 render receipt 同时绑定 schema/contract 版本。
- Decision：事实/推断必须引用存在的 source ID，假设必须声明方法，风险必须有来源与可观察触发器；百分比与百分点不可互换。
- Truth set：宁德时代与 Tesla fixture 只证明结构一致，不承诺实时数据、评级、估值或仓位。两者保持同一模块 ID、顺序、锚点和 content paths，仅市场语义不同。
- Decision：contract envelope 与 renderable payload 都用 Draft 2020-12 JSON Schema 在运行时执行；语义 validator 继续负责交易所/市场、币种、时间顺序、source provenance 与跨字段身份。
- Decision：外部 source URL 只允许 HTTPS；Web 再次做 scheme allowlist，独立 HTML 写入阻断脚本/连接的 CSP。发布包离线验收重新执行完整 contract validator。
- Verification：102 项产品测试、fresh-clone smoke、Node 语法、JSON Schema 自检、Git diff 和 gitleaks 通过。真实产品渲染器在临时测试数据库上验证 desktop/390px/print 的 8 模块顺序一致，733px print overflow=0；receipt 明确 `is_live_research=false`。另有可重复运行的 Playwright DOM 正/负向验收脚本。
- Adversarial follow-up：前端实际消费的行情、仓位、估值桥、护城河/量化信号、压力测试、AI 文本与版本差异字段已从“任意 object/array”收紧为可执行 schema；API 在追加批准状态、AI 补充、报告哈希和版本差异后再次运行完整合同校验，避免只校验中间态。
- Evidence：`evidence/m1-catl-report-contract.*`、`evidence/m1-tesla-report-contract.*` 为双公司结构样张；`evidence/m1-catl-product-contract-receipt.json`、desktop/mobile PNG 与 print PDF 为实际产品渲染链验收。
- In scope：JSON contract、现有 payload 适配、Web/移动/打印顺序、发布身份、CATL/Tesla 结构样张、攻击测试和迁移说明。
- Out of scope：Tesla 实时采集或投资结论、数据库重建、研究算法改写、公网投产、支付和自动交易。

### Gotchas · Milestone 1

- “两家公司都有 JSON”不等于已证明真实研究可比；Tesla 当前样张必须永久标明 structure-only，直到其数据与公司证据门真实通过。
- JSON Schema 只能检查外形，跨字段的市场/币种、引用存在性、状态原因和 payload 身份仍需 semantic validator。
- 前端有固定八段 HTML 不等于结构标准化；目录、章节头、移动和导出必须从同一 manifest 取序并拒绝未知版本。
- disclaimer 若继续硬编码在前端，就不属于报告 contract，也无法被版本和发布 identity 审计；因此它必须进入 payload。
- schema 必须约束 renderer 真正解引用的嵌套字段，并且校验必须发生在最终返回对象上；否则“顶层八模块正确”仍可能因 `{}`、错误类型或后置 mutation 失效。
- HK/US v1 只接受 security master 中已显式登记的发行人；未知代码必须 fail closed，不能从后缀猜测交易所和会计口径。
- AI 正文的生成校验、人工批准、运行时激活和最终 payload 必须共享同一 public schema；遗留或异常 artifact 只能被视为 inactive，不能拖垮确定性研报。

## 2026-07-21 · Milestone 2：可维护、可重放的 A 股数据基座（待评审）

- Objective：所有研报和组合只读取同一个 point-in-time snapshot；采集失败不会把半套新数据混入分析。
- User outcome：数据来自哪里、何时可见、用过哪个版本、为何通过质量门都能追溯；同一 snapshot 能离线重放并恢复到新库。
- Reuse：采用 datafeed 的 SourceManifest、raw response、显式质量/fallback 契约；a-stock-data 只作为后续 adapter 端点，quant-data-pipeline 只复用 scheduler/backfill/gap/health 思路，Intel 只做 supplementary intelligence。
- Decision：线上唯一权威目标仍是 PostgreSQL/Supabase；本轮提供可执行 migration，但不在缺少 project/region/credential 的情况下虚构已部署数据库。
- Decision：SQLite core_ 是零外部依赖的 acceptance adapter，与 Postgres market / research schema 共享 data-foundation-v1 逻辑契约。
- Decision：分析消费者只获得 SnapshotReader；该接口没有 fetch/network method，阻止分析中途刷新字段。
- Decision：fixture、cached、real 是不可混淆的 snapshot kind；随仓库 12 股样本永久是 fixture，不构成实时数据证明。
- Decision：质量门阻断交易日历、normal 证券 bar、复权版本、财务 PIT、source/raw/run provenance 任一缺口；阻断不覆盖上一份合格 snapshot。
- Verification：25 项专项测试、127 项产品测试通过；12 股覆盖 SSE/SZSE/BSE、主板/创业板/科创板/北交所，包含停牌、除权和财务修订；质量门与冻结在同一 write lock 下复核 state digest；相同 snapshot replay digest 与 export/import restore digest 一致；PostgreSQL 16 migration 在一次性数据库连续执行两遍并生成 17 张 market/research 表、16 个 triggers。
- Evidence：evidence/m2-data-foundation/verification-receipt.json；它明确标记 fixture_only=true。
- In scope：canonical contract、SQLite adapter、Postgres migration、quality gate、fixture、replay 和恢复。Out of scope：线上 Supabase、RLS、正式实时源迁移、会员/支付/UI。

### Gotchas · Milestone 2

- 有 PostgreSQL DDL 不等于线上数据库已经存在；必须完成真实 migration、RLS、Storage 与 backup/restore 才能称 production authority。
- 12 股 fixture 只验证失败行为和可重复性，不能被 README、UI 或 PR 描述成 12 股真实数据覆盖。
- 原始 payload hash 只能证明字节身份，不能单独证明来源权威或字段正确；还必须绑定 source manifest、run 和 quality result。
- 前复权日线必须绑定 adjustment version；只存复权后的 OHLCV 而没有公司行动/因子版本，历史重放仍会漂移。
- intelligence 缺失可以降级为 market-only，market 核心缺失必须阻断；两类失败不能混成一个 warning。

## 2026-07-21 · Milestone 3：自动、可恢复的研究更新引擎（待评审）

- Objective：Park 不再手工拼数据和逐股刷新；一次触发完成最新已收盘交易日的 canonical 更新、质量门、8 股标准研报与整体激活。
- User outcome：primary/fallback、数据时点、质量结果、逐股状态和最终 active identity 都有回执；失败、中断或 7/8 不会覆盖上一份合格结果。
- Reuse：直接把现有腾讯行情、腾讯 qfq 日线、东方财富 F10 collector 包在 `LegacyCollectorAdapter` 后面，并复用 AkShare 已采用的新浪交易日历解码逻辑，不另建行情抓取栈。
- Decision：更新阶段固定为 `planned → collected → ingested → snapshotted → reports_built → activated`；每步原子落盘，唯一 `in_progress` 可从最后成功阶段恢复。
- Decision：交易日由独立新浪交易日历和 Asia/Shanghai 15:30 收盘边界选择；当前生产 adapter 没有独立停牌源，因此目标日缺 bar 一律 fail closed，绝不把采集缺失猜成停牌。缺口按 canonical key 修复，qfq 版本以采集时点为主序、raw hash 为同刻后缀，变化时追加完整新版本序列。
- Decision：fallback 必须在执行前显式配置；primary/fallback 每次尝试和最终选择都写回执，全部失败不创建 active。
- Decision：canonical payload 的 `fixture/cached/real` 由 ingestion run 和幂等 identity 强绑定；REAL 只接受 allowlist source、HTTPS manifest、逐对象通过 SHA-256 的 provider raw bytes，以及绑定 normalized rows/provider hashes/source URLs 的 normalization receipt，fixture/cached 不能借既存 REAL run 晋升。
- Decision：研究 builder 在独立 fork 子进程中只接收 `SnapshotReader`，用 CPython audit hook 与 child-local guard 阻断高低层 socket 与 external command；8 只各自生成完整 `research-report-v1`，只有 8/8 通过 schema、语义、内外层内容哈希和 identity 才原子更新 canonical publication 与 active pointer。
- Decision：Web `/api/reports/{ticker}` 优先读取 canonical active，并在返回前重新校验 active、publication manifest、artifact 三层 identity/hash；active 存在但损坏时返回 conflict，绝不静默回退 legacy。旧组合数据库仍负责首页组合，不把两套 active 偷偷混成一个身份。
- Decision：每个 candidate 在 quality gate 前先冻结 bundle；失败 attempt 也保留 bundle path/hash、checks/blockers 和 evaluation identity，不能只留下截断异常字符串。
- Decision：无人值守生成确定性、snapshot-bound 的 `quantitative_baseline` 标准研报，不自动生成或批准 DeepSeek 正文。
- Verification：29 项 M3 专项、156 项产品测试覆盖两连续交易日、按 key 补历史缺口、独立日历与缺 bar 阻断、按采集时点选择 qfq revision、同输入复用、primary 采集/质量失败后 fallback、失败质量审计、cached/REAL 隔离、错误 report hash、全部失败、单股失败、进程中断恢复、重复进程锁、旧版本回滚阻断、研报篡改、active 三层 identity、产品消费路径、真实 adapter 四分源和 no-network report/replay；稳定 receipt 明确 fixture 边界。
- Evidence：`evidence/m3-research-refresh/verification-receipt.json`，明确标注 deterministic fixture acceptance，不冒充 live source run。
- Live smoke：2026-07-21 临时运行拿到 8/8 quotes，但 klines 2/8、financials 3/8，腾讯/东财出现 SSL EOF/connection reset；系统按设计 failed closed 且未创建 active。证据见 `evidence/m3-research-refresh/live-smoke-2026-07-21.json`，不能表述为实时发布成功。
- In scope：adapter、calendar/gap、fallback、lock/resume、8/8 gate、CLI/status/dry-run/schedule、receipt。Out of scope：线上 Supabase、第二个真实 provider、全市场、自动 DeepSeek、Telegram、支付和交易。

### Gotchas · Milestone 3

- 现有腾讯 qfq 数据没有独立公司行动/复权因子序列；v1 可作为 vendor-adjusted 内测源，但正式长期权威库仍需官方公司行动 adapter。
- F10 更正若沿用同一报告期但没有显式 revision ID，canonical conflict 会 fail closed；不能静默覆盖旧财务事实。
- snapshot 通过不代表公司级深研完成；M3 生成的是 M1 合同完整但明确标为 `quantitative_baseline / Missing evidence` 的标准研报，后续公司研究仍须经过公司证据门。
- `plist` 有计划时间只证明模板可审计；未在目标机器实际触发并拿到退出回执前，不能声称自动任务已经运行。
- gitleaks 的 generic-key 规则把 M2 的公开 fixture source key 误报为密钥；本轮只按原提交与 GitHub merge commit 的四条历史 fingerprint 精确忽略，不放宽任何规则或路径。
- canonical 标准研报已经进入实际 `/api/reports`，但组合首页仍来自旧 publication DB；两者的统一 portfolio publication identity 属于后续 milestone，当前不得声称整套组合已切到 canonical。

## 2026-07-21 · Milestone 4：跨公司标准化深度研报生产线（待评审）

- Objective：输入首批覆盖公司的任一 ticker，都走同一份证据门、同一生成身份和同一八模块专业格式；公司差异只改变研究问题，不改变事实标准。
- User outcome：贵州茅台、招商银行、长江电力、美的集团与宁德时代跨五个行业复用一条生产线，不再为每家公司复制模板。
- Reuse：继续使用 M1 `research-report-v1` semantic/schema validator、现有 DeepSeek writer 边界和浏览器 PDF 能力；不建立第二套报告合同或第二套 AI 客户端。
- Decision：`CompanyAdapter` 只保存上市身份、行业语义、价值链、可比公司和证据问题；章节、顺序、币种、引用和 absence policy 仍由统一合同控制。
- Decision：DeepSeek 请求只允许包含 frozen evidence、adapter、模块清单和 prompt/model 版本；不含数据库连接、文件系统 locator、API key 或可供运行时抓取的入口，并写入 `production_input_identity`。
- Decision：冻结门至少要求两个 primary/company document 和一个 independent cross-check；每个文档绑定 allowlisted HTTPS URL、时点、raw/content SHA-256，每个 claim 只能引用当前 manifest source ID。
- Decision：生成 identity 同时绑定 snapshot、evidence manifest、adapter、模板、模型和 prompt；冻结后任何 mutation 均阻断复用。
- Decision：缺少公司、行业、治理或估值证据时必须保留 `Missing evidence`。估值空状态使用零值只为兼容既有 deep schema，正文明确说明它不是目标价或收益率。
- Acceptance truth：根目录五家公司样例为 `ACCEPTANCE_FIXTURE / structure_only / is_live_research=false`；`live/` 另有同一 REAL snapshot 与实际捕获证据生成的五份发布证明。两类 truth set 不混用。
- Decision：schema/source ID 通过不能证明引用蕴含句子。新增 provenance-preserving evidence-editor：保留 DeepSeek 原稿 hash、修订 hash、修订人和原因；任何修订都使旧审批失效。
- Verification：29 项 M4 专项、185 项产品测试通过；覆盖五行业同合同、REAL/fixture truth 分离、REAL 禁用 fixture evidence、snapshot normalized-row attestation 与原地篡改阻断、attestation append-only guard 防改写/替换、同一 SQLite read transaction 防 TOCTOU、真实 `_inputs()` 无锁集成路径、baseline identity mismatch、重定向到未批准/私网目标、危险 URL、未知引用、证据数量门、post-freeze mutation、确定性输入身份、DeepSeek no-network boundary、base artifact 永久留档、审批前后 editor/model/prompt provenance 防篡改、可见 evidence ID/URL、Missing evidence 与 exact DOM order。
- Editorial gate：初始四轮逐句证据审查从 `P1=25/P2=7` 收敛到五家公司内容问题清零；新证据重绑后的独立复审为五家公司 `P0=0/P1=0` 并批准发布，同时诚实保留一项全局 P2（本批原始 base artifact 留档不完整）。审批清单绑定 exact input/narrative/evidence/provenance hash。
- Evidence：`evidence/m4-cross-company-research/verification-receipt.json`、`live/publication-receipt.json`、`live/editorial-audit-receipt.json` 及十套 fixture/live 渲染产物。live 桌面长图均为真实 full-page（1440×4763–5241），移动长图均为真实 full-page（390×6160–7372），PDF 为 7–9 页。
- In scope：五公司 adapter、真实冻结证据/DeepSeek/evidence-editor 边界、统一 report builder、HTML/mobile/print proof。Out of scope：全 A 股覆盖、组合仓位、会员/收费和公网部署。

### Gotchas · Milestone 4

- “五份看起来完整的报告”不等于五份实时深研；acceptance fixture 必须永久显示非实时边界，直到 REAL snapshot 和实际捕获文档都通过门。
- Adapter 不能携带未冻结的公司结论，否则只是把硬编码模板换了一个文件位置。
- 允许模型看到公开 URL 不等于允许模型访问网络；生产输入只把它当引用 locator，生成子进程仍须 no-network。
- HTML、PNG、PDF 同版式不等于同 truth set；每种产物必须保留相同 report identity 和八模块顺序。
- macOS Chrome 有时写完截图后不退出；验收器只在文件大小稳定且 PNG/PDF 头、尺寸、页数通过后终止该独立进程，不能把 timeout 当成功。
- source ID 合法仍可能不蕴含句子；必须逐句核对期间、因果、比较基准和会计口径，不能把 schema passed 当语义 passed。
- 模型容易在投委会情景中偷渡宏观、估值、价格或现金覆盖结论；limitations 对全文生效，情景不是绕过证据门的出口。
- 固定 3600px viewport 不是“长图”；页面内容超过视口时会无声截断。视觉证据必须记录 DOM scrollHeight，并要求 PNG 像素高度与之完全一致。
- 本批修订链能通过内置 validator，但早期重试覆盖了原始 base artifact，留下一个不阻断发布的审计 P2。后续生成必须按公司永久保存 `base-narrative-draft.json`、draft receipt 与 revision receipt，禁止覆盖后才补 provenance。
- provider manifest 只能证明采集输入身份，不能证明 SQLite normalized rows 没有被原地改写；REAL legacy snapshot 还必须在同一 SQLite read transaction 内通过 `snapshot_content_attestations` 重算。attestation 自身由 exact-SQL append-only trigger 保护，guard 缺失或被同名 no-op 替换也必须 fail closed。

## 2026-07-21 · Canonical Milestone 5：统一组合配置与调仓账本（待评审）

- Objective：把固定 8 股的研究结论收敛成一个可复算、可比较、可追责的长期模型组合，直接回答“买什么、建议多少、这期为什么变”。
- User outcome：1000 万元长期资金基准下，产品同时展示股票名称、建议仓位、现金、本期动作、相对上期变化和模型账本，不再由多个页面拼接组合结论。
- Reuse：直接消费 M2/M3 canonical snapshot 与 M1/M4 `research-report-v1` 身份；复用现有真实 replay、Chrome full-page 渲染和 SQLite append-only guard，不建立第二套数据采集或报告系统。
- Decision：权重只由版本化确定性配置生成；DeepSeek 不能设置权重。硬门为 6–12 只、单股 5%–15%、行业不超过 30%、现金 10%–40%、总和 100%。
- Decision：每个 position 绑定相同 snapshot 的 report hash、model/config version、evidence status 和 research depth；组合、指针、期间差异与账本全部内容寻址，读取时重新验证。
- Decision：组合版本与调仓账本独立；账本显式区分上期正式目标、按两期参考价计算的漂移账面权重和本期目标，只允许 `planned → pending → filled | unfilled`。filled 必须是源库中下一已存交易日开盘价，并绑定 attested REAL snapshot 与 exact row hash。
- Truth boundary：2026-07-17 是不可发布的 `retrospective_reference_only`，2026-07-21 才是 attested `canonical_current`；二者都不是券商持仓。当前 5 只为 deep、3 只为 quantitative baseline，逐股可见。
- Verification：13 项 M5 专项与 198 项产品全量测试通过，覆盖约束、完整 report/model/config/evidence identity、研究语义伪造、真实价格漂移、diff 重算、账本 append-only exact guard/idempotence/状态机/空账本/虚构成交、current 回滚、API 200/409、历史补算可见标签和移动端全字段。生成器与独立验证器均通过两个 snapshot 的 8/8 replay；历史 8 笔 filled 与当前 8 笔 pending 均可复核。独立浏览器重渲染与 5 项攻击验收进一步阻断裁图+伪 receipt、自洽伪 diff、空 ledger、研究语义伪造和非有限权重。
- Evidence：`evidence/m5-canonical-portfolio/` 保存两个 JSON 版本、diff、当前/历史 ledger、生成器回执、独立回执、攻击回执、终审回执、HTML、1440×2949 桌面长图、390×7046 移动长图和 4 页 PDF；独立验证器重新渲染 HTML，并要求两张 PNG 的高度与像素哈希完全一致。
- In scope：固定 8 股、确定性权重、组合版本差异、模拟调仓账本、API 与发布级视觉证据。Out of scope：用户输入、全市场选股、券商/自动交易、真实持仓、公网、支付与个性化适当性。

### Gotchas · Canonical Milestone 5

- 历史 REAL snapshot 只能证明输入真实且可重放，不能倒推当时已发布；补算必须永久显示 retrospective。
- 组合总和 100% 不是充分条件；任一单股、行业、现金或 report identity 失败都应阻断整个版本。
- 模拟 filled 不是交易回执，不能出现在“真实持仓”或“实际收益”表述中。
- full-page 文件存在不代表移动端可读；首版八列表被裁切，第二版又隐藏非核心列，最终改为逐股卡片完整展示公司、行业、价格、仓位、动作、观察区间、置信度、研究深度和首要风险，并让 PNG 高度精确匹配 DOM scrollHeight。
- 组合可以包含 quantitative baseline，但不能因此声称 8/8 都是公司级深研；研究深度必须逐股披露。

## 2026-07-21 · Milestone 6：私有会员预览与反馈闭环（待评审）

- Objective：Park 能把一个稳定 HTTPS 私有预览链接发给自己和少数朋友；匿名看不到研究数据，受邀用户按等级读取 canonical 组合/深研并提交反馈，Park 可停用成员。
- User outcome：登录第一屏直接回答 8 只股票、82% 股票/18% 现金、建议动作、观察区间、研究深度和首要风险；不再把 localhost、样稿或旧组合当成可交付产品。
- Reuse：复用 M5 content-addressed canonical portfolio、既有 invite/session/entitlement，以及成熟 Cloudflare named tunnel；不新建第二套研究、身份或反向代理框架。
- Decision：`preview/member/paid/owner` 后端逐端点授权。匿名只见登录壳与最小 health；前端隐藏不构成权限控制。
- Decision：部署 release 同时绑定研究库 attestation、组合/diff/ledger 和产品代码 hash；`current` 只在整包验真后原子切换。研究库与 mutable auth/feedback 库物理分离。
- Decision：release 额外封装并哈希绑定 8 份 exact canonical report；服务返回前逐份重算 `_report_binding` 并与组合 position 精确比较。外部 runner 每次启动前验证 manifest、release identity、全部文件哈希、report bundle hash 和路径边界，拒绝 working-tree fallback。
- Decision：反馈带 member、时间和 page identity，去重、每人每小时五条限流，并由 exact-SQL trigger 保证 append-only；Owner 可查看和导出。
- Decision：公网 origin 只绑定 loopback，独立 named tunnel 和独立 LaunchAgent 不修改其他产品 tunnel。session 使用 `__Host-` Secure/HttpOnly/SameSite=Strict，写操作绑定 CSRF。
- Decision：私有模式使用显式 route allowlist；legacy dashboard、canonical 内部 API、刷新、批准、发布和下载均返回 404，owner 也不能修改 immutable research release。登录失败同时按 identity 与 Cloudflare trusted client IP 限流，阻断轮换 email 的 PBKDF2 消耗攻击。
- Truth boundary：当前是 `Private Preview Ready`，不收款、不接券商、不代表用户持仓，也不是 Production/Paid Pilot Ready；单机 Mac 必须保持在线。
- Verification：15 项 M6 专项与 213 项产品全量测试通过；fresh-clone baseline 同样重跑 213 项并通过临时数据库 server smoke。最终 release `preview_581a1d3ffab5dd25` 从同样包含下载 fail-closed 安全修复的 `preview_355f39a78d2c1eb1` 实际回滚并 roll-forward，随后真实重启 dedicated tunnel；三个阶段外部 health 均为 200。运维回执还在重启前后枚举 Cloudflare tunnel identity/connector，证明另一条 tunnel 身份未变且始终 active。外部 HTTPS 验收核对 8/8 exact report hash、全 route allowlist、邀请注册/退出/停用、反馈、cookie/CSRF、独立 runner 与 dedicated connector；1440×2388 桌面和 390×6199 移动 full-page 截图通过无溢出、移动字号和触控目标检查。36 项对抗攻击全部被拒绝或检测，P0/P1/P2=0。
- Evidence：`evidence/m6-private-preview/` 保存外部验证回执、对抗回执和 authenticated desktop/mobile 长图；密码、邀请码、cookie、session 和 tunnel credential 均不入回执或 Git。
- In scope：私有 HTTPS、canonical first screen、邀请权限、反馈、隔离 runtime、restart/rollback。Out of scope：支付退款、公开注册、MFA、多地域、用户风险输入、券商连接。

### Gotchas · Milestone 6

- 运行 Python 会生成 `__pycache__`；release verifier 若把解释器缓存当产品代码，首次启动后会错误判定整包被篡改。身份只绑定源代码/静态资源，运行器同时禁止写 bytecode。
- auth 初始化曾把会员表写进 research.db，破坏“研究只读、会员可变”的边界；私有模式必须显式使用独立 `PARK_AUTH_DB`，且 server 不能把 research DB 参数传给 auth/feedback initializer。
- launchd `bootout` 后立即 `bootstrap` 偶发返回 5；安装器必须小幅重试并确认 label 是否已经加载，不能因为一次返回码留下 tunnel 停止。
- `launchctl kickstart -k` 在服务切换瞬间也可能返回 113；运维演练必须复查 label/PID、有限重试并以外网 health 恢复作为成功条件，不能只信一次命令返回码。
- HTTP 200 和 tunnel 进程都不是可分享证明；必须从外网登录、核对 canonical identity、执行权限负向路径，并生成真实 authenticated full-page 截图。
- 只按 email 限流会允许攻击者轮换身份制造昂贵密码哈希；公网登录必须叠加 trusted client IP 全局预算。
- 旧的 broad route dispatcher 会让 preview 或 owner 读到/调用私有产品不需要的 legacy API；外部预览采用 allowlist，新增路由必须先明确 entitlement 和 truth boundary。
- 手工写“已回滚/已重启”JSON 不是运维证据；receipt 必须由实际切换 release、重启 tunnel、逐阶段外网探针的同一命令生成。
- stable named tunnel 仍不是高可用：本机睡眠、断网或两个 LaunchAgent 同时失效都会让预览离线。

## 2026-07-22 · Milestone 7：付费社群人工履约闭环（Ready for review）

- Objective：Park 能在不虚构在线支付能力的前提下，为少量社群成员记录已核验的外部付款、开通内容权益，并在退款时立即撤权。
- User outcome：Owner 人工确认外部付款后，成员现有 session 立即获得与当前 canonical portfolio 精确绑定的 8 股研究包；退款注销旧 session，重登后不再有下载权。
- Reuse：复用 M6 invite/session/CSRF/独立 auth DB、M5 content-addressed portfolio 和既有安全 release/Cloudflare rollback；不新建支付 SDK、第二套会员系统或第二套研究包。
- Decision：Paid entitlement 只从 append-only `billing_events` 中未退款的付款事件派生。M7 API 禁止 paid 邀请；为保持 M6 兼容，底层仍可读取旧 paid invite，但 M7 `effective_member` 会把无账单的 stored paid 降回 member，前端状态也不能获得下载权。
- Decision：`manual_external` 是 Owner 自己核验的外部凭据记录，不是支付商 webhook；`acceptance_test` 永久标记 test mode 并排除于真实收入。provider event 与外部付款/退款 reference 分别唯一，金额严格为整数分，退款不得早于付款。
- Decision：完全相同的 provider event 重放返回原事件及原 release identity，即使当前 release、停止开关或 366 日新事件窗口已变化；内容变化拒绝。
- Decision：退款继承原付款的 portfolio/research-pack identity，不会因产品已切到新版本而丢失可追溯性；退款不依赖当前 research pack，不受 stop-new-payments 影响，并撤销该成员全部旧 session。
- Decision：每个 release 生成 deterministic `canonical-research-pack-v1`，绑定 portfolio/diff/ledger/ledger history、8 份 exact report、逐文件 hash 和 ZIP membership；runner 启动与下载时不仅验证包内自洽性，还逐项比较 canonical release 原件。
- Decision：`PARK_MANUAL_PAID_PILOT` 是显式兼容开关。未启用时 M6 billing/pack 路由继续 404、原有权限不受影响；部署 release 必须显式启用并提供已验证 pack path。
- Truth boundary：产品显示 `paid_pilot_ready=false`、`online_checkout=false`、`payment_provider_connected=false`。当前是 `Private Preview Ready + Manual Paid Fulfillment`，不是 Product OS Gate B。
- Verification：13 项 M7 专项、15 项 M6 兼容测试及 226 项 fresh-clone 全量测试/server smoke 通过。外部 HTTPS 验收在最终 release `preview_76e74a7aa8a14266` 完成 test payment → 现有 session 获权 → exact 13-member/8-report ZIP 全成员 hash → 幂等/冲突重放 → stop-new-payments → refund → session revoked → 重登无权，且真实收入前后不变。安全回滚到 M7 release `preview_048f73373ce6e692`、roll-forward 和 dedicated tunnel restart 均为 200，其他 tunnel 保持 active。24 项账单/权限/pack/trigger/视觉攻击全部拒绝或检测，两路独立终审 P0/P1/P2=0。1440×2625 desktop 与 390×6874 mobile full-page 视觉证据无横向溢出，移动文字和下载触控目标通过。
- Evidence：`evidence/m7-paid-community-pilot/verification-receipt.json`、`restart-rollback-receipt.json`、`baseline-receipt.json`、`adversarial-review.json`、`final-review.json` 与 desktop/mobile PNG；event reference、密码、cookie、session 与付款凭据不进入 Git。
- In scope：manual_external/acceptance_test 账单、派生 Paid、退款撤权、停止新付款、对账导出、exact 8 股研究包、外部部署/验收。Out of scope：online checkout、provider SDK/webhook、自动续费、价格/税务/优惠券、佣金归因、真实生产小额支付和 Gate B 声明。

### Gotchas · Milestone 7

- `verify_baseline.py` 已经包含全量 product tests；Ready 前不能再额外跑一次 `unittest discover`，否则只是重复测试。
- M6 旧 release 没有 research pack 或人工账单开关，不能作为 M7 的安全 rollback。必须先保存一份完整 M7 release，再切最终 M7 release。
- 退款发生时 current portfolio 可能已经变化；退款事件必须绑定原付款 identity，而不是退款当天 current identity。
- 内容包损坏不能阻断退款；refund API 必须只依赖原付款账本，并用稳定 reference 在响应丢失后对账清理。
- 幂等不能绑定当前 release 或新事件时间窗；否则同一外部事件在换版或一年后重放会被错误当成冲突。
- acceptance test 看起来与真实 Paid 完全相同，UI、export 和 receipt 必须同时明确“不计收入”，不能只靠后台字段区分。
- content-addressed 内部 pack 不能代替 canonical 原件或 release manifest。只有逐项原件比较、内外两层 hash、启动前重验和固定下载路径同时成立，才能阻断自洽伪包与路径逃逸。

## 2026-07-22 · 两层产品 Roadmap 与 Repo 拼装架构获批

- Objective：把现有投研 skeleton 升级为数据可追溯、研究结构标准化、任意受支持 A 股都能诚实输出 Summary 与长报告的产品。
- User outcome：Park 可以从 7 个 Level 1 方向审核产品价值，并以 37 个独立 Level 2 user story 跟踪每一次可验收交付。
- Decision：Supabase PostgreSQL + Storage 是唯一 production authority；本地 SQLite、外部 repo 自带数据库与缓存都不是线上 truth。
- Decision：datafeed 提供唯一 Port/Adapter/SourceManifest/provenance 入口；a-stock-data、Vibe、quant pipeline、Intel、rollingSirius 和 Day1Global 都按组件粒度 Adapt/Extract/Reference，不合并为第二套平台。
- Decision：研究生成只消费 immutable Research Context Pack；确定性分析和可选 UZI synthesis 均不能直接改写原始 evidence。
- Decision：Roadmap 已创建 7 个 GitHub Milestones、tracking issues #65–#71 和 37 张 Level 2 issues #28–#64。Level 3 只在需要独立 owner/验收时即时创建。
- Verification：所有 Level 2 issues 均包含 User outcome、3–7 项 Success Criteria、In/Out scope、Dependencies、Risk、Allowed Files 和 Verification Commands。

### Gotchas · Roadmap execution

- 当前默认工作区包含未提交的架构文档，不能切分支或清理；所有实现从 `origin/main` 的隔离 worktree 开始。
- GitHub REST issues endpoint 带 60 秒缓存，批量创建后用 `gh issue list` 或单 issue readback 验收，不能把陈旧列表误报为创建失败。
- `roadmap-approved` 表示产品规划已批准，不等于 Dev Queue 的 `park-approved` 风险门标签；没有通过该身份校验前不把 medium/high issues 投入自动队列。
- 每个 Level 2 保持一张 issue、一条 branch、一张 PR。跨 milestone 使用链式 base，但不为文件级小任务制造无价值子票。

## 2026-07-22 · L2-A1 Canonical Data Contract v1

- Objective：任何外部数据源在进入 canonical pipeline 前，都必须用同一套可执行、可拒绝、可追溯的 record contract 表达。
- Decision：合同固定 `market / fundamental / document / estimate / event` 五个 versioned record schema；adapter 状态只允许 `accepted / rejected`。
- Decision：每个有效 `RecordEnvelope` 必须同时绑定 `SourceManifest` 与不可变 `RawCapture`，并携带 source manifest hash、provider/schema version、raw hash 和 UTC known_at。
- Decision：`SourceManifest.domain_scope` 是 capability allowlist，阻止一个 source 越权输出未声明的数据域。
- Boundary：A1 只定义逻辑合同、ADR、组件锁和 contract tests；Supabase DDL/Storage 属于 A2，通用 ingestion runtime 属于 A3。

### Gotchas · L2-A1

- 不能把已有 `data-foundation-v1` 改名冒充新合同；它仍是本地 acceptance baseline，新的 `canonical-data-contract-v1` 是上游 adapter 的稳定逻辑边界。
- `degraded` 不作为 adapter 接受状态；它属于后续 quality gate 的判断，避免不可信记录静默进入 authority。
- 只保存 normalized payload 不足以证明 provenance；没有 raw hash、manifest hash 和 known_at 的 record 必须 fail closed。

## 2026-07-22 · L2-A2 Supabase Canonical Schema & Raw Storage

- Objective：数据和原始证据拥有唯一、私有、可迁移与可备份的 production authority 位置。
- Decision：新 Supabase project 只采用 `canonical-authority-v1` migration；旧 `data-foundation-v1` PostgreSQL 文件保留为 M2 parity baseline，不把两套 table 混成同一 authority。
- Decision：`market` 只存 accepted market/fundamental，`research` 只存 accepted document/estimate/event，`control` 保存 source/run/raw/receipt/snapshot lineage。
- Decision：raw Storage 固定 private `canonical-raw` bucket；blob 路径只由 SHA-256 决定，source URL、MIME 与时点保存在 domain-neutral per-fetch capture，record domain 保存在 receipt，不信任 provider filename 或 URL。
- Decision：raw blob 与 raw capture 分表；同一 bytes 可以在多个 ingestion run 中复用 blob，同时每个 run 保留独立 capture/known_at/manifest lineage。
- Decision：数据库 provenance 补齐 A1 合同字段：raw capture 固定保存 source URL，record receipt 固定保存 contract version；accepted payload 缺字段或与 domain row 不一致时 fail closed。
- Decision：产品 migration 不修改 Supabase-managed `storage.*` schema。Bucket desired state 用 JSON 锁定，部署时通过 Storage API 创建和核对。
- Decision：A2 的浏览器边界是默认全拒绝。anon/authenticated 没有 schema/table privilege，只有 backend service_role 可读写；产品用户 RLS 留给 F1。
- Verification：同一 migration 在两个独立 PostgreSQL 16 空 application DB 重放，schema/RLS signature 一致；bucket desired-state JSON 独立验证；anon 被拒、service_role 可读、append-only trigger 生效。
- Boundary：本轮没有创建真实 Supabase project、没有保存 live provider bytes、没有 member policy，也没有宣称完成 production backup/restore。

### Gotchas · L2-A2

- Supabase “空项目”仍由平台预置 storage/auth schema 和 roles；bare PostgreSQL 验收必须先建立最小 platform stubs，不能误把这些平台表写进产品 migration。
- 不要在产品 SQL 上给 `storage.objects` 加全局 trigger/revoke；它会破坏同一 project 的其他 bucket，且绕过 Supabase Storage API 的平台边界。
- 没有 RLS policy 时是 default deny，但 table grants 仍要显式撤销，避免未来迁移误授 browser role。
- service_role 能 bypass RLS；它是后台 secret，不是高级会员 token，绝不能下发到浏览器。
- dev seed 只保存 inactive fixture manifest，不插入样本行情或研报，避免 seed 被误当成产品数据。
- PostgreSQL 三值逻辑会让 `NOT (NULL comparison)` 仍为 NULL；payload 完整性门必须使用 `(...) IS NOT TRUE`，并用缺字段攻击测试验收。
- 公共 `StorageObjectKey` 可能绕过 factory 直接构造；Python validator 与 SQL CHECK 必须同时校验完整 content-addressed path、hash prefix 和 basename。
- blob 主键若只用 raw hash，storage path 就不能再包含 source/domain/date/MIME；否则同一 bytes 的后续 capture 会指向不存在的新路径，破坏去重与 provenance 一致性。
- RawCapture 在 A1 是 domain-independent；不能给 capture 绑单一 domain 或以 `(run_id, raw_hash)` 去重，否则一个响应无法产生 market + fundamental records，也会吞掉同 run 的独立获取证据。

## 2026-07-22 · Root Agent Instructions Re-scoped to Equity Research

- Objective：后续 agent 进入本仓库时，默认理解为 Park Equity Research 产品开发，而不是 UZI-Skill 插件维护。
- User outcome：Park 不再需要每次纠正“当前 repo 不是 UZI-Skill”；agent 能直接围绕 ticker summary、标准化深度研报、数据基座、证据层和私域产品继续施工。
- Decision：根 `AGENTS.md` 替换为 equity-research 专用规则，明确产品目标、入口命令、架构分层、repo 拼装策略、issue/branch/PR 工作流、decision-log、测试强度、review 风险分级和 secret 边界。
- Decision：根 `CLAUDE.md` 同步替换，避免 Claude/Fable 风格 review 仍把本仓库当成 UZI-Skill plugin。
- Decision：UZI-Skill 降级为历史/reference component，只在明确需要复用 report/rendering、collector behavior 或 research framework 时读取，不再作为 root project contract。
- Verification：手工 readback `AGENTS.md` 与 `CLAUDE.md`，并用 diff scope 确认本轮只改 agent 指令和 decision log；无 product runtime、schema、report engine 或 UI 行为变更。

### Gotchas · Agent instruction cleanup

- 只修 Codex 的 `AGENTS.md` 不够；根 `CLAUDE.md` 也会影响后续 Claude/Fable 复审，两个入口必须一致。
- 不能把 UZI 删除成“不可用”；它仍是可参考的 collector/report 资产，但必须标注 mock、fixture、cached 或 live 边界。
- 治理变更不应混入 A3 ingestion runtime，否则后续 review 会把流程清理和数据层行为混在一起。

## 2026-07-22 · L2-A3 Generalized Ingestion Core

- Objective：把 A1/A2 的 contract + schema 变成可运行的五域 ingestion runtime，让后续 provider 只需要写 adapter/glue code，而不是各自直连数据库。
- User outcome：未来用户输入 A 股 ticker 时，market、fundamental、document、estimate、event 都能走同一套 provenance、quality、fallback、authority 写入路径；数据不足时降级但不冒充正式研报证据。
- Decision：runtime 固定 one primary + explicit fallbacks。source plan 必须无重复、首个为 primary、其余为 fallback；provider adapter 不允许自己声明 cached。
- Decision：raw capture 在 parse 前生成。fetch 成功但 parse/contract 失败时，authority 仍保存 run/raw/capture，保证 parser failure 可审计。
- Decision：SQLiteFetchCache 是 mutable local replay cache，`authority=False`；它只在 live sources 全部失败后提供 degraded、non-publishable view。
- Decision：SupabaseAuthoritySink 采用 DB-API connection factory + object store protocol，不为 A3 增加 Supabase SDK/psycopg runtime dependency；真实 Supabase wiring 留给部署 milestone。
- Decision：cached 与 fixture attempt 不进入 Supabase authority sink。fixture primary 不阻断 real fallback；sink 仍拒绝 fixture 作为直接调用防线。degraded live attempt 可保留 run/raw/capture；未 promotion 的 accepted records 不写 receipts，避免 stale/fixture-like accepted receipt 污染后续 snapshot membership。
- Decision：accepted document record 必须绑定同一 raw capture：`content_hash == raw.raw_hash` 且 `storage_uri == raw.storage_uri`。索引页引用独立 PDF 的情况后续必须建模成独立 capture。
- Verification：`python3 -m py_compile product/data_core/contracts.py product/data_core/ingestion.py product/data_core/local_cache.py product/data_core/authority_sink.py product/tests/test_ingestion_core.py product/tests/test_data_contract.py` 通过；`python3 -m pytest product/tests/test_ingestion_core.py product/tests/test_data_contract.py -q` 37 项 + 17 subtests 通过。

### Gotchas · L2-A3

- 若先 parse 再建 raw capture，parse exception 会吞掉 provider bytes，后续无法复核失败原因。
- live adapter 若把响应标成 cached，也必须作为 contract failure 留 raw audit；不能因为标签异常就让获取证据消失。
- 本地 cache 解析成功也不能写入 authority；否则 stale/cached 数据会污染 production truth。
- fixture primary 不能因为 sink 拒绝 fixture 而提前 abort；runtime 必须跳过 fixture 持久化并继续 fallback。
- non-publishable accepted receipt 比“不写 receipt”更危险，因为未来 snapshot builder 可能只看 `status='accepted'` 而忘记 join run quality。
- document payload 不能指向另一份 raw object；否则 receipt 证明的是索引页，domain row 却引用 PDF，provenance 会错位。
- object storage 上传发生在 DB transaction 前，DB 失败可能留下 content-addressed orphan blob；该 orphan 可重试、可去重，风险低于 DB 先写后找不到 raw bytes。
- 同一 raw bytes 可能产生多个 domain records；capture 不能被强行绑定单域，也不能用 `(run_id, raw_hash)` 吞掉独立 fetch 证据。
- A3 只交付 runtime 和 sink，不声称已有真实 provider coverage、Supabase project、backup/restore 或全市场 ticker 覆盖。

## 2026-07-22 · L2-A4 A-Share Market, Identity & PIT Fundamentals

- Objective：用户输入受支持 A 股 ticker 后，摘要和研报管线获得真实、标准化、可追溯的身份、行情、日线和时点财务数据包，不再依赖 demo placeholder。
- User outcome：`600519.SH` 与 `300750.SZ` 的真实探测均能返回公司身份、现价、前复权日线、财务摘要、资产负债表、利润表和现金流量表；任何必需源缺失都会明确降级且不可发布。
- Reuse：复用 A3 `IngestionRuntime`、A1 canonical record contract、A2 authority sink 边界，以及既有 `real_pipeline.py` 已验证的腾讯/东财数据源；只新增 provider adapter 与 typed packet glue code。
- Decision：ticker 先规范化为 `CN:{code}.{exchange}`；无后缀但能按板块唯一推断时接受，冲突或歧义输入抛出 typed error。
- Decision：腾讯 quote 与 qfq daily bars 分别独立采集；东财财务摘要、资产负债表、利润表和现金流量表各自独立 raw capture，保留 source URL、raw hash、known_at 与 provider notice date。
- Decision：一次 packet refresh 的六个 provider fetch 并发执行，并使用唯一 request ID；重复刷新不会因为固定 idempotency key 覆盖上一轮 ingestion run。
- Decision：只有六类 live outcome 全部通过质量门才允许 `packet.publishable=true`。fixture、cache fallback 或任何 statement 缺失都只返回 degraded/gap，不补 sample value。
- Verification：专项与上下游测试 47 passed + 17 subtests；277 项产品全量测试通过；真实 SH/SZ 探测均六源 success、无 gap、latest report period 为 2026-03-31；Python compile 与 diff check 通过；对抗终审 P0=0/P1=0。
- Boundary：A4 未进行全市场历史回填，未创建真实 Supabase project，也未把 packet 接入最终 30–50 页 report compiler。

### Gotchas · L2-A4

- 东财 main finance highlights 不能替代三张财务报表；验收必须单独采集 balance/income/cash-flow，而不是把 ROE、利润和经营现金流/股拼成“完整财务”。
- provider `NOTICE_DATE` 是 point-in-time 边界；只按 `REPORT_DATE` 排序会把尚未披露的财务放进历史回放。
- packet API 若复用固定 request ID，Supabase sink 的 idempotent run ID 会吞掉后续刷新；每次逻辑刷新必须产生新 request identity，cache key 仍只由 source/entity/parameters 决定。
- 腾讯 K 线 `limit=5` 的实测响应可能包含 6 个交易日；下游应按返回日期排序和自身窗口裁剪，不能假设 provider 返回行数严格等于请求值。
- 交易日当天收盘前返回的是未收盘 bar；`observed_at` 必须取 provider close time 与 fetch known_at 的较早值，不能写一个未来的 15:00。
- 股票代码与交易所后缀必须交叉验证；`300750.SH`、沪市 B 股 `900xxx` 等不能因为格式像 ticker 就进入 A 股 canonical identity。
- 身份源没有行业字段时必须保留 `null`；不能用 ticker 前缀猜行业或把旧 demo 分类冒充 source-backed identity。
- provider filter 不是身份保证；每一条东财财务 row 都必须用 `SECUCODE/SECURITY_CODE` 与请求 ticker 交叉验证，错配时整批 fail closed。
- 六个 adapter outcome success 仍不是 packet 可发布证明；必须再检查 typed identity、quote、完整 OHLCV 与同一最新报告期的最小三表字段集。
- 本轮真实探测证明当前网络与两个样本可用，不等于全市场 SLA；批量覆盖率、重试预算与 provider 备源属于后续 milestone。
- `NOTICE_DATE` date-only 足以表达当前 capture 的披露先后，但不支持历史 intraday cutoff replay；该能力与真实 A2 Supabase 落库 replay 留给后续 milestone。

## 2026-07-22 · L2-A4 Roadmap Contract Completion

- Objective：补齐 approved issue #31 中 PR #79 尚未覆盖的 security aliases、日线/估值/交易日双源校验、财务修订身份、官方公司行动证据和 source conflict 留痕。
- User outcome：宁德时代 `300750.SZ` 的 live validated packet 同时给出 canonical identity/aliases、腾讯与东财估值对照、腾讯与新浪最近日线/交易日对照、东财四类财务 component revision identities、巨潮官方权益分派实施公告；任一身份错配或阈值冲突都会 fail closed。
- Reuse：继续使用 A1/A3/A4 packet 与 runtime，只新增 Eastmoney quote、Sina daily、CNINFO corporate-action 三个 adapter 和 cross-source validation glue；不新建数据库或第二套 ingestion framework。
- Decision：估值 PE(TTM)/PB 任一缺失或相对差异超过 10% 阻断；最近两日 provider 日期必须完全一致，复权/近期 close 差异超过 0.5% 阻断。
- Decision：财务 revision identity 由完整 provider row content hash 生成，并保存 provider update time；修订后的 row 形成新 canonical receipt，不覆盖先前证据。
- Decision：CNINFO `权益分派实施公告` 元数据和官方 PDF 是公司行动 evidence anchor；adjusted history 没有任何官方 action document 时 validated packet 不发布。
- Decision：网络稳定性优先于并发速度。A4 base 六源完成后，三个 cross-check source 顺序采集，避免同机同时建立九条境内 TLS 连接造成假冲突。
- Verification：issue 指定专项 6 passed；上下游 53 passed + 17 subtests；283 项产品全量测试通过；live CATL 三个 secondary source success，估值与最近两日一致，8 条官方 action announcement，blocking conflicts=0，validated packet publishable=true；对抗终审 P0=0/P1=0。
- Boundary：当前不声称 full-market alias coverage、historical intraday PIT replay、官方交易所 adjustment-factor series 或真实 A2 Supabase replay。

### Gotchas · L2-A4 Roadmap Completion

- provider 返回 filter success 不代表证券身份正确；Eastmoney 与 CNINFO adapter 都必须逐 payload 校验 code，再写请求 instrument ID。
- 腾讯 PE(TTM) 与东财 PE(TTM) 会因刷新时点/口径产生小差异；必须用明确 tolerance 留痕，不能要求浮点完全相等，也不能无限放宽。
- “最近两个交易日一致”是当前 calendar conflict gate，不是完整交易所日历 authority；全历史 calendar replay 仍需官方 calendar snapshot。
- 新浪近期日线可用于独立 close/date cross-check，但不是官方复权因子；官方可信部分是 CNINFO action document，不能把两者合并表述成“官方价格”。
- 巨潮全文搜索返回 HTML `<em>` 高亮；title 入 canonical event 前必须清理标签，同时保留 announcement ID 和 official PDF URL。
- 九源同时并发在本机触发过 Eastmoney/Sina TLS timeout；顺序执行 cross-check sources 后 live probe 稳定，不能把瞬时网络失败写成数据冲突。

## 2026-07-22 · L2-A5 Orchestration, Quality & Immutable Snapshot

- Objective：一次数据刷新要么形成可回放、raw-bound 的完整 snapshot，要么隔离失败并继续保留上一有效版本。
- User outcome：运维方可用同一入口完成 schedule/backfill/gap planning、canonical refresh 和审计回执；无需从多个内部 JSON 猜测刷新是否可信。
- Reuse：复用 `CanonicalResearchRefresh` 的 adapter selection、锁、断点、质量门、snapshot、8/8 activation 与 failure isolation；A5 只增加薄 orchestration/audit 层，不建立第二套状态机。
- Decision：交易日必须由调用方提供权威列表；planner 只负责 Asia/Shanghai 17:30 cutoff 和逐 ticker/逐日期缺口检查，不用 weekday 猜开市日。
- Decision：snapshot manifest 显式绑定排序后的 raw hashes 与集合 digest；replay 校验 raw membership、frozen rows、quality digest 和 manifest identity。
- Decision：pre-A5 snapshot 保持向后可回放，但 A5 refresh 不会直接复用缺少显式 raw lineage 的 active version；下一次刷新会生成新的 A5 snapshot identity。
- Decision：fresh run receipt 直接包含 actual ingestion runs 与完整 quality evaluation；source failure receipt 包含 `active_preserved`，同输入强制重跑复用 snapshot identity。
- Decision：无缺口的正常 schedule 返回 `skipped/network_called=false`；`force=true` 只用于人工复核或恢复演练，不改变幂等身份。
- Decision：scheduler skip 也原子保存 immutable check receipt；canonical `partial/blocked_before_activation` 在 A5 回执中归一为 `failed`，并显式写入 preserved active、原始 status/stage 和可回放的新 snapshot。
- Boundary：本轮是 fixture-backed deterministic acceptance，不声称 live provider SLA、官方全历史交易日历、真实 Supabase authority 或生产 scheduler 已安装。
- Verification：issue 专项 7 passed；orchestration/upstream 61 passed；产品全量 290 tests completed successfully；compile 与 diff check 通过。
- Adversarial review：初审发现 later-stage isolation receipt P1 与 scheduler skip persistence P2；修复后窄复审确认两项关闭，剩余 P0=0/P1=0。

### Gotchas · L2-A5

- 全库最大日期会掩盖单股缺 bar；backfill 必须按 `(ticker, trade_date, component)` 判断。
- 停牌日没有 bar 是合法状态，但 calendar、status 与 adjustment factor 仍不可缺；不能补零成交 bar 冒充真实记录。
- 已经把 raw object 冻结进 snapshot items 仍不够直观；manifest 应直接列出 raw membership，才能让回执低成本验真。
- 旧 snapshot 没有 A5 raw-membership 字段时仍可 replay；新 snapshot 一旦声明这些字段就必须严格校验，不能默默降级。
- orchestration 层不能再持有另一份 active pointer；唯一真相仍是 canonical refresh 的 `active.json`。
- snapshot 已创建但下游 artifact gate 失败不等于刷新成功；对 scheduler 必须给出明确 isolated failure，而不是含糊的 partial。

## 2026-07-22 · L2-B1 Official Filing & Announcement Ingest

- Objective：把公司官方披露稳定转成可引用、可追溯的 immutable document evidence。
- Reuse：复用 A3 ingestion、A2 raw storage identity、A4 ticker normalization；不新建 document database。
- Decision：CNINFO index 只负责发现，PDF 必须作为独立 raw capture 下载；document content hash 只能绑定 PDF bytes。
- Decision：official primary 由固定 source key、official manifest 和 HTTPS host allowlist 联合校验；aggregator 不能自报角色。
- Decision：增量以 known document IDs 跳过旧 PDF；分类明确区分完整年报、摘要、季报、半年报、重大与普通公告。
- Verification：专项 6 passed；A3/A1 upstream smoke 43 passed + 17 subtests；CATL CNINFO 五份 PDF、CATL 2026 Q1 报告和 SZSE 官方 PDF live probe 通过。
- Boundary：未做 OCR、卖方研报、全市场 SLA 或真实 Supabase 部署。

### Gotchas · L2-B1

- index JSON 与 PDF 是两份不同 raw evidence，不能共享 content hash。
- “半年度报告”包含“年度报告”字样，分类顺序错误会把半年报标成年报。
- 非财报公告不应全部标成 major；常规董事会决议属于 other announcement。

## 2026-07-22 · L2-B2 Sell-Side Report Catalog & PDF Archive

- Objective：让用户能查到支撑结论的券商研报，并明确区分已归档原始 PDF 与只有目录元数据的报告。
- Reuse：采用 a-stock-data 的东财目录/PDF/限速重试模式和 Vibe-Trading 的券商研报元数据字段，继续复用 A2/A3 raw storage 与 ingestion contract，不重建第二套管线。
- Decision：catalog 与 PDF 分开采集；known report ID/canonical URL 在下载前去重，下载后再按 SHA-256 去重。
- Decision：PDF 失败不阻断同批其他报告，保留为带 error 的 `metadata_only`；卖方证据固定为 supplementary，不能冒充官方披露。
- Decision：目录支持 broker、analyst、date、rating、pages、archive status 查询；原始 PDF 绑定 raw hash 与 content-addressed storage URI。
- Verification：专项 6 passed；A3/A1 upstream smoke 43 passed + 17 subtests；CATL live probe 3 条目录、3 份 PDF 均成功归档。
- Boundary：未做 OCR、观点综合、全市场 SLA 或生产 scheduler。

### Gotchas · L2-B2

- 目录存在不等于 PDF 可获取；metadata-only 必须是正式状态，不能静默丢弃。
- canonical URL 只能避免重复下载；不同 URL 仍可能返回相同 bytes，因此必须再做 SHA 去重。
- 限速要覆盖 catalog 和 PDF 且串行记录最近调用时间；仅对 429/5xx/网络失败重试，4xx 不应反复打源站。
- PDF host、HTTPS 和 `%PDF` magic 必须同时校验，避免把反爬 HTML 当研报归档。

## 2026-07-22 · L2-B3 Page-Level Document Intelligence

- Objective：进入正式报告的每条引用都能回到准确 PDF document/page/raw hash，错引用连同 claim 一起阻断。
- Reuse：native text 用 pypdf；稀疏页用 Poppler `pdftoppm` + Tesseract OCR；继续以 B1/B2 document ID 与 PDF raw hash 为 authority，不新建文档框架。
- Decision：page 和 chunk 都绑定 one-based page、raw hash、parser version 与 extraction method；chunk 永不跨页。
- Decision：同 raw + 同 parser version 可确定性重跑；升级 parser version 生成不同 parse identity，不覆盖旧结果。
- Decision：默认抽检 page mapping ≥95%、scanned searchable coverage ≥90%；OCR 失败标 `unreadable`，疑似表格无可靠坐标标 `possible_unlocated`。
- Decision：citation gate 按 claim fail closed；document ID/page/raw hash 必须 100% 命中，提供 quote/chunk 时一并核验。
- Verification：专项 6 passed；B1/B2/A3 upstream smoke 34 passed；真实本地 pdftoppm + Tesseract 双页探测得到 native 1 页、OCR 1 页、页码准确率 100%、扫描页覆盖率 100%。
- Boundary：未生成投资结论、未做表格 cell 坐标重建、未部署 managed OCR workers。

### Gotchas · L2-B3

- PDF page index 对用户必须统一 one-based；内部 zero-based index 若外泄会造成整份报告错页。
- OCR 文本存在空格/断行差异；质量抽检应验证页面 marker 与可检索覆盖，不应要求全文逐字符相等。
- document ID 和 page 命中仍不足以证明引用同一份 bytes；raw hash 必须是 citation gate 的硬字段。
- table-like text 没有坐标时只能用于搜索，不能静默声称已精确抽取单元格。
- 默认本地 OCR 只在页面 native text 稀疏时触发，避免对数百页可搜索 PDF 做无意义重 OCR。

## 2026-07-22 · L2-B4 Broker Estimates & Consensus History

- Objective：用户按预测年度看到一致的 EPS/营收/净利润/目标价、券商分歧与 consensus 修订方向。
- Reuse：复用 B2 东财 report catalog 的 report identity 与 a-stock/Vibe 字段模式；同花顺 `worth.html` 经 A3 ingestion 抽取 broker profit 与 revenue/profit provider reference，不新建预测源框架。
- Decision：每条 BrokerEstimate 必须绑定 ticker/broker/report ID/report date/raw hash/fiscal year；THS 只有在 broker/date/year 唯一命中东财 report 时才补净利润，不能合成不存在的 report。
- Decision：同券商同年度只取 cutoff 前最新报告进入 consensus，旧报告保留为 superseded quarantine。
- Decision：至少四个 contributor 时用 MAD 检测异常；异常值在均值前剔除并保留 estimate/value/metric/year/reason。
- Decision：snapshot identity 绑定 as_of、全部输入、aggregate 与 quarantine，可离线 replay；revision 显示均值方向、绝对/百分比变化与 contributor 变化。
- Verification：专项 8 passed；B2/A3 upstream smoke 30 passed；CATL live probe 得到东财 20 份报告/56 条年度 estimate、THS 36 条记录/6 条 provider reference、3 条 report-bound profit match、7 个 consensus point，snapshot replay 通过。
- Boundary：不生成 Park 自研盈利预测，不解析任意 PDF 预测表，不声称全市场历史已回填。

### Gotchas · L2-B4

- 同一券商多份历史报告不能重复进入同一时点均值，否则高频覆盖券商会被重复加权。
- THS broker row 没有 Eastmoney report ID；只有 broker/date/year 唯一匹配时才能补字段，unmatched row 只能作为 provider evidence。
- 东财 `currentYear` 决定 this/next/next-two year，不能用系统当前年硬猜历史 report 的 forecast year。
- 目标价区间取 midpoint 只是一条 report-bound metric，不应复制到后三个 fiscal year。
- THS “亿/万亿/万”必须归一到 base units；字符串去单位但不缩放会造成 1e8 量级错误。
- outlier 不能静默丢弃；被排除值和原因必须进入 snapshot identity，才能解释 consensus 为什么变化。

## 2026-07-22 · L2-B5 A-Share News & Event Intelligence

- Objective：让重要 A 股事件被及时发现、跨源去重并显示覆盖缺口，同时保持新闻证据与模型推断的硬边界。
- Reuse：采用 `zinan92/intel` 的 SourceRegistry/Collector、RSS/Google News/Yahoo/website monitor、source-status degradation 和 48 小时 event topology 模式；复用 A3 ingestion contract 与 A4 security master，不引入 Intel SQLite authority。
- Decision：四类 discovery source 统一输出 EVENT `SourceManifest`，authority tier 固定为 `supplementary_only`；official monitor 只能接收配置 host 内链接，但仍不等于 B1 官方事实。
- Decision：A 股实体只能由 security master 的 source ticker、代码、公司名或显式 alias 解析；共享 alias 记为 ambiguous 并 fail closed。
- Decision：event topology 使用同 ticker、48 小时窗口、canonical URL 或标题 token similarity 做确定性聚类；每个 event 保留全部 evidence ID 和 source key。
- Decision：模型产物只允许进入独立 `InferenceEnvelope`，provider/model/prompt ID/prompt version/generated_at/evidence IDs 缺一即拒绝。
- Decision：单源失败、超时或零可发布记录不阻断健康源，但必须输出含 manifest hash 的 `CoverageGap`。
- Verification：issue 专项 7 passed；A3/A1 upstream smoke 44 passed + 17 subtests；直接复用 Intel `GoogleNewsCollector` 对宁德时代 live probe 得到 10 条 evidence、9 个 event、零 coverage gap。
- Boundary：未安装生产 scheduler、未回填全市场、未加入社交舆情或交易动作、未自动生成 event impact 结论。

### Gotchas · L2-B5

- Google News/RSS 是发现入口，不是事实 authority；标题聚类不能升级证据等级。
- collector 返回 ticker 也必须经过 A 股 security master 校验，不能接受任意字符串成为 canonical instrument。
- 公司简称可能对应多个证券；歧义 alias 不能用“第一个命中”静默消解。
- URL 去 tracking 参数有利于去重，但不能跟随跳转后丢掉原始 batch raw hash。
- 同一事件多篇报道必须保留全部 evidence ID；去重不能变成删证据。
- source failure 与“没有相关新闻”含义不同，但两者都不能伪装成完整覆盖；当前 v1 统一进入 coverage gap，并保留具体 reason。
- 模型生成时间、模型名和 prompt 版本必须与 output 一起冻结，否则历史 event interpretation 无法 replay。

## 2026-07-22 · L2-B6 Evidence Set, Conflict & Coverage Gate

- Objective：报告生成器只能看到完整度、时点、新鲜度和冲突政策全部通过的 immutable Context Pack。
- Reuse：复用 A3 `RecordEnvelope`/`SourceManifest` provenance、A5 cutoff/snapshot identity、B1–B5 的 document/estimate/event records；不再扩展 legacy SQLite evidence authority。
- Decision：`EvidenceCandidate.from_record` 必须验证 record 与 manifest hash 绑定；primary 只允许 canonical/official，independent 必须 subject-independent，lead 固定 supplementary-only 且永不进入 Context Pack。
- Decision：policy 显式冻结 as-of、每 component 的 primary/independent/total 下限、角色 freshness、blocking quality flags/conflict severities 和 subject-controlled source family。
- Decision：known_at 晚于 as-of、effective_at 晚于 known-at、stale、rejected、fixture/mock/sample、角色伪装和 lead-only 均逐条进入 rejection receipt，不静默删除。
- Decision：blocking conflict 阻止 Context Pack；non-blocking conflict 仍进入 gate hash。required source gap 阻断，optional gap 只保持可见，不因为额外源偶发失败让已满足的 policy 无条件失效。
- Decision：evidence manifest hash 只绑定 accepted evidence + policy；gate hash 另绑定全部 rejection/conflict/coverage，二者分开回答“用了什么证据”和“为什么可发布/不可发布”。
- Verification：issue 专项 7 passed；A5 与 B1–B5 upstream smoke 47 passed；未跑全量测试，符合当前 milestone test policy。
- Boundary：本轮不设计报告 section、不生成文本、不做 UI、不部署新 receipt 到生产 Supabase。

### Gotchas · L2-B6

- role label 不是 authority；supplementary feed 改名成 primary 必须被机器拒绝。
- `known_at <= as_of` 只证明当时已知，不证明内容新鲜；freshness 应看 `effective_at`，两道 gate 不能合并。
- lead 是找证据的线索，不是弱一点的 evidence；把 UZI/LLM lead 放进 Context Pack 会让推断循环引用自身。
- optional source gap 必须显示，但不能自动等同 required coverage failure；是否阻断由 policy 决定。
- 冲突不应修改或删除原证据；它是独立 receipt，blocking 时只阻止发布。
- 只 hash accepted evidence 会漏掉 gate 判断变化；因此 gate hash 必须同时冻结 rejection、conflict 和 coverage。
- Context Pack 即使 dataclass frozen，内部普通 dict 仍可变；索引必须使用 read-only mapping，证据列表必须使用 tuple。

## 2026-07-22 · L2-C1 Research Section Contract v2

- Objective：所有公司使用同一套可机器验收的深度研报骨架、完成语义和页数预算，行业差异不再复制整份模板。
- Reuse：采用 rollingSirius 九章的逻辑顺序和估值/来源纪律；把 Day1 A–P 的收入质量、利润率、现金流、指引、KPI、管理层、宏观、筹码、研发、会计、反偏见和行动触发重写成 typed inputs；UZI 只贡献定性模块线索。
- Decision：主合同固定 18 节、32–50 页；行业 appendix、earnings bridge、A/H comparison 作为 profile optional modules，不改变主 section order。
- Decision：每节显式声明 required/optional input key、value type、purpose、page budget 和 taxonomy origin；unknown section/input/type fail closed。
- Decision：`full`=全部 required input 齐全；`partial`=有 recognized input 但 required 未齐；`missing`=无 recognized input。optional 缺失不把 full 降为 partial。
- Decision：section schema、profile、contract version 分别 hash；input content 另有 input hash，事实变化不应伪装成 schema 变更。
- Decision：structure-only 合同不要求 B6，且不能声称 live；live acceptance 必须绑定 publishable B6 evidence set ID/manifest hash。
- Verification：issue 专项 7 passed；v1 report contract + B6 upstream smoke 共 35 passed；未跑全量测试。
- Boundary：C1 不写具体公司正文、不验收真实 evidence、不实现 recommendation/target-price/position policy（留给 C5）。

### Gotchas · L2-C1

- 九章原始模板适合人读，但粒度不足以给每节独立 completion；必须拆开收入、利润、现金流、会计、预测和宏观，才能诚实显示缺口。
- Day1 16 模块不能原样搬入 A 股通用报告；US-tech-only 与不存在 reference 的部分只能抽 taxonomy，不能成为 runtime dependency。
- optional input 缺失不等于 partial，否则几乎所有公司都会永远不 full；completion 只由 required input 决定。
- `full` 只表示输入合同齐，不表示结论正确；真实发布仍必须通过 B6、后续 section compiler 和 citation gate。
- 页数预算是信息密度规划，不是凑页数；总上限 50，行业附录只能在 profile budget 内替换/压缩。
- C5 尚未实现时第 16 节自然显示 missing；不能临时让模型编一个仓位来填满合同。

## 2026-07-22 · L2-C2 Deterministic Financial & Valuation Engine

- Objective：用户可以从同一 frozen numeric input 复算历史财务桥、Bull/Base/Bear DCF、reverse DCF、comps、历史区间和 sensitivity。
- Reuse：采用 rollingSirius 的多方法估值纪律和 reverse DCF/sensitivity 方法；采用 UZI `fin_models.py` 的纯函数 bridge/grid 模式；拒绝其缺股本时从市值反推或默认 10 亿股的 fallback。
- Decision：输入统一使用一个 currency、显式 unit scale、absolute diluted shares；price × shares 与 market cap 差异超过 2% 阻断。
- Decision：每期资产负债表必须在资产 0.5% 内平衡；股本跨期变化超过 50% 必须有 explicit share event；历史期必须唯一、升序。
- Decision：scenario 固定 Bear/Base/Bull 各一个、概率和为 1、forecast horizon 一致；每个 scenario assumption 单独 hash。
- Decision：DCF、peer EV/EBITDA、historical P/E 全部输出同 currency/share，绑定同 input hash；Bear/Base/Bull value 非单调时 fail closed。
- Decision：reverse DCF 用二分法求 Base margin/capital intensity 下当前价格隐含的 constant revenue growth；sensitivity 固定 5×5 WACC/g grid。
- Verification：issue 专项 7 passed；C1/v1 contract/B6 upstream smoke 42 passed；deterministic replay input/output hash 稳定；未跑全量测试。
- Boundary：C2 不允许 LLM 写数字、不生成 action/position policy、不做交易执行。

### Gotchas · L2-C2

- 财务金额按“亿元”而股本按“股”时，所有 per-share 方法必须先乘 unit scale；忘记这一步会差 1e8 倍。
- price × shares 是比任意字段名更可靠的单位 sanity check；不能同时接受互相矛盾的市值和股本。
- 资产负债平衡不证明财报正确，但不平衡一定不能进入估值。
- reverse DCF 只改变增长而固定 Base margin/capital intensity，输出必须说明它回答的是“当前价隐含什么”，不是预测。
- Bear/Base/Bull 标签本身不保证单调；计算后仍必须验证 per-share value 顺序。
- sensitivity grid 如果 terminal growth 接近或超过最低 WACC 会数学爆炸，必须在生成 table 前阻断。
- comps 与 historical multiple 是 cross-check，不是把三个数机械平均；C2 只并列可复算结果，最终政策留给 C5。

## 2026-07-22 · GitHub audit-lineage repair

- Objective：恢复 #79–#89 缺失的里程碑合同映射，并阻止以后用 PR 风格 commit message 代替真实 GitHub PR。
- Fact：相关实现 commit 均在 `main`，但 GitHub Issue/PR API 对 #79–#89 返回不存在，commit-to-pull-request API 也没有关联对象；保留事件不足以证明具体低层写入路径。
- Decision：不改写 Git 历史、不伪造旧 PR；使用明确标记为 reconstructed 的 #90–#100 绑定原缺失编号与 immutable commits，并提交机器可验的 ledger。
- Decision：`main` branch protection 要求真实 PR 且对 admin 生效，approving review count 保持 0，以符合 Park OS 自动挡。
- Verification：专项 verifier + 3 个单元测试；PR 合并前执行本仓默认测试与 gitleaks。
- Secrets gate：gitleaks 的两条旧历史命中经只读、值遮蔽检查确认均为 UZI fetcher schema 字符串而非 credential，按 commit/file/rule/line 精确 fingerprint 豁免；未输出或读取密钥值。
- Boundary：不改变任何投研、数据、估值或产品运行逻辑；C3 仍是下一产品里程碑。

### Gotchas · GitHub audit lineage

- `Merge pull request #N` 或 `feat: ... (#N)` 只是文本，不能证明 GitHub 存在 PR；必须查询 PR object/commit association。
- 已被占用或缺失的 GitHub 编号不能由客户端指定复用；重建记录必须保留 original → reconstructed 映射。
- 追求“看起来连续”的历史会诱发伪造；不可恢复的历史必须显式标为 reconstructed。
- 自动合并与强制 PR 不冲突：required approvals 可为 0，同时对 admin 禁止 direct push。

## 2026-07-22 · L2-C3 Sell-Side Viewpoint Matrix

- Objective：用户可以逐篇验证券商观点、共识、分歧和修订，而不是看到没有出处的“机构综合认为”。
- Reuse：直接复用 B2 report/PDF identity、B3 document/page/raw-hash citation gate、B4 normalized `BrokerEstimate` 与 robust consensus quarantine、C1 section 11 typed inputs。
- Decision：一份 `SellSideViewpoint` 必须绑定 report/document/raw hash；estimate 的 ticker/broker/analyst/date/target/raw identity 任一不一致即阻断。
- Decision：compiler 纯确定性且不联网；历史报告全部保留，latest 只影响当前 broker row 和 B4 consensus，不覆盖旧观点。
- Decision：rating、target、EPS/revenue/net profit 按同券商相邻报告产生 immutable revision；unknown rating label 只标 `changed_unclassified`，不猜升级或降级。
- Decision：citation 失败的 claim 保留在 blocked ledger，但不能进入 topic 或 summary；bull/bear claim IDs 分开展示，不自动裁决谁正确。
- Decision：summary language 是 evidence ceiling：tentative、single-report、multi-broker、documented disagreement、≥4 broker 且 ≥80% alignment 五档，不能被叙事层升级。
- Verification：6 个 issue 专项测试；B3/B4/C1/C2/C3 targeted 34 passed；全量按文件隔离执行 25 个 pytest 模块，353 passed + 34 subtests passed；gitleaks 无泄漏。
- Boundary：不生成 LLM 数字、不做 C5 recommendation/target/position policy、不做 UI 重构或交易执行。

### Gotchas · L2-C3

- “有 PDF”不等于观点可引用；document/page/raw hash/quote 任一不匹配都必须阻断该 claim。
- 同一券商多份报告不能同时进入当前共识，否则会把一个机构重复计票；旧值进入 superseded quarantine 和 revision timeline。
- 数值 outlier 不能删除整份报告；它只退出对应 metric aggregate，报告和定性观点仍可审计。
- 多篇报告都看多也不等于事实正确；matrix 只描述 sell-side distribution，不提升来源 authority。
- 不同币种 target price 不能放进同一共识；A 股跨币种报告必须先有显式换算合同。
- tentative claim 即使有页码也不能被 summary 改写成明确结论；citation validity 与 claim strength 是两道不同的门。
- 本仓单进程 `unittest discover` 会被旧 research-refresh 的进程隔离测试提前终止，且不会给可靠 summary；全量闸采用每个 test file 独立 pytest 进程，既覆盖 pytest function，也避免跨模块全局状态污染。

## 2026-07-23 · Code-first Industry Intelligence v1

- Objective：把已归档网页中的 489 份公司档案和两套来源三高坐标做成可分享、默认封闭、可复验的专业前端。
- Decision：产品只复现 38 个产业段节点和 94 家材料公司节点的来源坐标，不重算三高分，也不把 38 个 segment 自动映射到 489 份档案。
- Decision：489 份正文按公司代码独立加载；总览 API 只返回索引，避免首屏下载全部 Markdown。
- Decision：新增 code-first 登录；一次性码只存 hash、事务内消费，且仅接受 `max_uses=1` 的邀请。兑换后创建内部 guest identity，不收集访客邮箱、姓名或密码；Owner/既有成员仍可用邮箱密码登录。
- Decision：归档数据独立打包进 content-addressed private-preview release，页面固定显示来源 URL、源 SHA-256、归档日期和“不是实时行情/未过独立证据门”的边界。
- Verification：industry/auth/private-preview 专项 104 tests passed；完整 pytest 361 passed + 34 subtests；Node syntax、Python compile、browser desktop/mobile smoke 和 gitleaks 均通过。
- Boundary：不声称这是实时数据，不声称档案逐条事实已独立溯源，不生成 489 家公司的新三高排名，不连接券商或执行交易。

### Gotchas · Industry Intelligence v1

- 来源的 38 个产业段 taxonomy 与公司档案的 segment 名称没有可直接接受的精确 crosswalk；自动关联会制造虚假精度。
- `sangao` 宽口径标签与少量详细公司 assessment 存在冲突；界面只复述来源标签，不把它升级为本产品结论。
- 一次性访问码不是短信或邮箱 OTP：它是 Park 线下转交的单次 bearer secret；转发前必须按密码对待。
- D3 在站内 vendored，避免第三方 CDN 泄露访问元数据或在网络受限时使图表失效。
- 浏览器图表必须有键盘列表和来源详情；只有气泡 tooltip 会把复杂研究信息锁在鼠标交互里。

## 2026-07-23 · N1-1 爱牛字段归因总表

- Objective：把归档中的 49 个主表字段与 34 个分级字段写成可机器验证、可供后续采集与公式复现使用的生产归因地图。
- Decision：字段性质严格分为原始事实、派生、研究判断、AI 推断。候选来源只表示待复现假设；只有归档逐路径明确保存的 `src` 才能标为直接溯源。
- Decision：产业链、角色、三高、S/A/B、上下游、layer/segment 与解释文本一律归为研究判断或 AI 推断，不进入产品事实输出，也不伪装为找到单一接口。
- Decision：`stfin` 与 `ern` 不重新猜来源；直接引用 provenance 里的 1,161 条明确标签（东财 F10 主营构成 578、东财预约披露 583），并保留“来源标签计数不等于全部字段可用行数”的边界。
- Verification：`build_field_attribution.py` 从只读归档生成 JSON/Markdown；`verify_field_attribution.py` 对 classification manifest 验证 83/83 覆盖及两类直接来源标签计数。
- Boundary：不请求 ainiusq.com、不访问任何外部数据源、不写采集器、不修改 `product/static/**`，也不将爱牛档案正文或评分结果导入产品。

### Gotchas · N1-1

- 578/583 是 provenance 中精确来源标签的全归档计数，不是主表中 `stfin`/`ern` 字段存在行数；混用补池与主表会造成错误的来源覆盖率。
- `classification-manifest.json` 只说明字段被归入慢知识、周期研究或快快照，不能单独证明该字段的外部来源。
- 市场行情、财务和卖方字段当前仅是中置信度候选来源，必须由后续 issue 以原始响应、as-of 和 hash 再验证。
- 归档是本地只读输入且不进本 PR；验证命令必须显式传入 archive root，避免产品仓在没有归档时伪造通过。

## 2026-07-23 · N1-3 跨市场行情与估值快照

- Objective：为 A/HK/US/JP 建立统一的价格、涨跌、市值、PE、PB、PEG 来源策略；把历史价格复查与当前估值快照分开，避免日 K 线被误用为历史估值。
- Decision：Yahoo Chart 只用于 HK/US/JP 的日线价格历史；Yahoo Snapshot（经 `yfinance` 完成 provider 握手）只用于当前时点的价格、市值、PE、PB、PEG 与涨跌。后者的原始物是客户端规范化载荷，manifest 明确标成 `client_normalized_capture`，不伪装成抓到 Yahoo 原始 wire response。
- Decision：非美元 `mcap_usd` 没有同日冻结 FX 时必须留空；所有 snapshot record 标注 `historical_reconstruction_eligible=false`。
- Verification：30 个跨市场样本在 2026-06-30 至 2026-07-02 的价格窗口中，Yahoo 日线可取回 30/30；22/30 在 ±0.5% 内匹配，8 个 residual 原样写入运行时 diff。全部同日估值字段都因没有历史估值/FX 源而显式标记 gap，没有用 K 线倒推。
- Boundary：验证差异报告仅生成到本地 `/tmp`，不提交爱牛记录、数值、评分或档案文字；不请求 ainiusq.com，不改 `product/static/**`。

### Gotchas · N1-3

- 归档的“快照”并非所有市场同一收盘时点：美股样本大量精确命中 6/30，港股样本在 6/30–7/2 窗口外更接近 6/22。不能把站点构建日期当作每个字段的 as-of。
- Yahoo 的香港代码使用四位 display symbol（`0700.HK`），canonical identifier 保留五位证券代码（`00700.HK`）；美股类别股在 Yahoo 用连字符（`MOG-A`），不能直接复用带点 code。
- 日本与部分港股在严格窗口仍有 1.6%–6.7% residual；在找到同口径历史来源前，这些是未解决的 source/date discrepancy，不应通过放宽默认容差消失。

## 2026-07-24 · N1-3 历史估值与残差收口

- Decision：将价格验证窗口扩展为“声明窗口 + 只用于解释残差的 45 天回看”。窗口外精确匹配只能标 `explained_residual`，不能改写为窗口内通过。
- Decision：美国历史市值、PE、PB 使用 Yahoo 同日收盘加 SEC companyfacts 中 `filed <= as_of` 的股本、TTM 净利和净资产重建。非美元估值必须绑定同日冻结 FX。
- Decision：PEG 的 benchmark 增长率基础未披露；SEC TTM 同比是另一种定义，统一标 `definition_mismatch`，即使数值偶然接近也不宣称复现。
- Decision：A/HK/US/JP 七个字段的 28 个来源单元写入 `HISTORICAL_MARKET_FIELD_POLICY`；24/28 为高/中置信度候选归因，4 个 PEG 单元保持低置信度。
- Why：满足“30 家都能解释”和“字段来源 ≥80% 归因”，同时不靠放宽容差、当前估值冒充历史值或未披露 PEG 定义制造假通过。
- Evidence：运行时 30 家验证得到 22 家声明窗口通过、8 家在 2026-06-22 精确匹配、0 unexplained price outlier、0 missing price；涨跌幅为 28 pass / 2 previous-close reference mismatch / 0 missing；106 个估值字段为 52 pass / 3 outlier / 39 missing / 12 definition mismatch；SEC 和 Yahoo 原始响应均保留 raw hash，完整 diff 仅写 `/tmp`。

### Gotchas · N1-3 历史估值

- 港股/日股 8 个价格 residual 全部精确对应 2026-06-22，证明归档快照混合了至少两个市场日期；网页构建日不能当作统一 as-of。
- SEC companyfacts 后续 proxy 可能重复 10-K 数字；按期间去重会让 DEF 14A 覆盖正式 10-K，必须把 filing form 纳入事实身份。
- `EntityCommonStockSharesOutstanding` 可能只包含一个股份类别；Mobileye 等多类别发行人的市值不能把单类股本当总股本。
- 外国发行人的 ordinary shares 与 ADR 价格需要 ADR ratio；没有比率时必须留 gap。

## 2026-07-23 · N1-4 已披露评分公式复现

- Objective：只复现页面明示的综合分、机会分与 PEG 分档，并把不能被可见输入解释的等级明确隔离为人工判断。
- Decision：综合分采用 `(0.28G + 0.12Q + 0.13V + 0.08A) / 0.61`；机会分采用 `0.45G + 0.20Q + 0.35V`；二者按多数样本可复验的最近整数序列化。PEG 使用 `<1 / <2 / ≤4 / >4` 四档。
- Decision：缺失输入不做填充；少数公式 residual 保留在运行时审计输出，不能为匹配个别档案而修改全局权重或 rounding 规则。
- Decision：S/A/B 等级标为 `manual_judgment_not_formulaically_reproducible`：同一可见 score 出现多个 grade，且绝大部分记录缺少 barrier、毛利/净利或三高输入。不得用 score 阈值伪造一个等级公式。
- Verification：外部本地归档验证器按 `universe=main` 锁定 649 家主池；综合分 453/453、机会分 575/578（99.48%），分级池 PEG 276/276。验证输出同时报告缺输入覆盖率与 residual；公式单元测试覆盖 61% 归一、机会分和四个 PEG 边界。
- Boundary：归档评分、公司代码和等级 residual 仅写到调用者指定的本地审计 JSON，不进入产品数据或本仓 Git。

### Gotchas · N1-4

- 实际可完整计算 composite 的记录数可能少于页面/issue 中的横截面口径；报告必须分别写出可计算分母，不能把缺输入的公司算作公式通过。
- 0.5 tie 在少数行与多数样本的序列化行为不一致，连同非 tie residual 一起视为疑似人工覆盖；不要把它错误归因成一个“隐藏 rounding 公式”。

## 2026-07-23 · N1-5 档案生产模板与五家公司试产

- Objective：定义可复跑的公司档案合同，并用五份自有档案完成盲评主样本；另保留两份 A 股产品样例验证跨行业适用性。第三方档案仅在本地运行时用作盲评标杆，不进入产品输出或 Git。
- Decision：模板强制分开事实、研究判断、待核验问题；每个数字事实必须映射到来源 ID，且业务、财务、护城河、反题材、生产成本和复跑策略为固定章节。
- Decision：盲评主样本为北方华创、比亚迪、中际旭创、新易盛与 NVIDIA；宁德时代、贵州茅台是额外产品样例。A 股只使用巨潮资讯正式披露，NVIDIA 只使用 SEC 与发行人官方材料。
- Decision：生产清单记录每家公司 Goal token 区间差、耗时、人工介入点、来源数量与原始捕获 SHA-256。Goal token 是包含研究、推理、工具与写作的执行区间，不冒充模型 API 计费用量。
- Decision：同公司复跑采用冻结证据与冻结正文的确定性 replay，receipt 同时记录源文件和输出的结构签名；它证明结构可复现，不冒充重新抓取了最新事实。
- Verification：`verify_dossier.py` 校验模板、七份样例、章节、schema、数字引用、来源 URL、生产清单与统一结构签名；`replay_dossier.py` 对 NVIDIA 生成独立复跑版本并验证结构签名一致。
- Verification：外部读者使用 runtime-only A/B 包盲评五家公司，自有档案总分 56、标杆总分 43，比例 130.2%，五组均超过 100%。评分模型实际返回 `deepseek-v4-flash`，收据保留请求 ID、token 用量与 pack hash。
- Boundary：Round 1 外部读者按旧三维分数偏好自产，但 Park 明确拒绝逐维打分，改为每组选择整体更好的文档。Park 选择 `P1A/P2A/P3B/P4B/P5B`，解码后为 benchmark 5/5、自有 0/5，因此 Round 1 明确失败，不能合并 #115。
- Decision：盲评合同改为 Park 与 external reader 各自完成五组整体 A/B 偏好，自有档案须分别胜出至少 4/5；平局不计胜出。旧分数不换算成通过证据，新一轮必须重新随机化标签。
- Evidence：Round 1 的脱敏 Park preference receipt 记录 pack hash、五家公司 selected origin 和 0/5 结果；A/B key 与 benchmark 正文继续留在 Git 外。
- Iteration：Round 2 在五份档案中补充公司特异的人与组织、发展路径、三年与最新季度财务、时点评估以及“市场在交易什么”，随后使用新随机标签重建盲评包。
- Evidence：Round 2 外部读者完成五组整体 A/B 选择，自有档案胜出 5/5，超过独立角色 4/5 门槛；总门禁仍因 Park 角色尚未提交而 fail closed。
- Boundary：Park 的 Round 2 选择解码后仍为 benchmark 5/5、自有 0/5，因此 #115 再次失败。外部读者恰好自有 5/5，说明审计严谨度与产品交付力出现系统性分歧，外部通过不得覆盖 Park 失败。
- Decision：Round 3 不再靠增加表格和免责声明修补。保留数字、来源、口径冲突与可证伪条件，但读者层改为“最新数据卡 → 有立场的一句话 → 人与发展史 → 产品/商业模式 → 财务估值 → 风险 → 明确结论”；除财务和时间线外去表格化。
- Evidence：Round 3 使用全新随机标签；DeepSeek 连续返回 503 后，按既有第三视角授权改用 Claude Code CLI `opus` alias 作为 external_reader。CLI 不暴露 token usage，因此收据明确写 unknown，不伪造；其盲选解码为自有 5/5，总门禁仍等待 Park。
- Boundary：Park 的 Round 3 选择再次解码为 benchmark 5/5、自有 0/5，故 reader-first 改写仍未通过。五份自产文本实际比 benchmark 长 1.28–1.61 倍、数字数量更多；失败不能再解释为“内容不够多”。
- Decision：Round 4 聚焦编辑选择而非扩写。读者层统一为六段式：最新数据、定位、创始人与团队、发展时间线、技术/产品/商业模式、财务估值、风险与点评；删除可见财务表和 9 个正式审计式标题，把来源与生产记录保留在文后审计层。
- Evidence：Round 4 使用全新随机标签。DeepSeek 的旧密钥路径已不存在，未伪装为已调用；按既有第三视角授权改用 Claude Code CLI `opus`（实际模型 `claude-opus-4-8`），外部盲选解码为自有 5/5。总门禁仍等待 Park 独立盲选。
- Boundary：Park 的 Round 4 选择解码后仍为 benchmark 5/5、自有 0/5。只把自产稿改成相同六段式并删除表格没有改变产品偏好，说明缺口不是版式相似度，而是人物、产品与业务变化的公司特异信息选择。
- Decision：Round 5 不再对五份文档做统一机械改写。逐家公司建立“人物与组织转折 / 关键技术产品节点 / 收入与利润结构变化 / 市场正在押注什么 / 最关键反证”五项内容卡，只把从各自官方披露独立核验的内容写入读者稿。
- Evidence：Park 进一步明确标杆优势是用“第一、绝对龙头、最硬、弹性之王”等方向性词汇压缩 uniqueness。Round 5 将强定位纳入模板，但要求限定比较范围并标记研究判断；外部 reader 盲选结果为自产 5/5，总门禁仍等待 Park。
- Decision：Park 认为 Round 5 已接近，但强定位之前仍缺一张可定位公司的 map。Round 6 在读者层新增“产业坐标”：产业链位置、国内同类、全球竞品/替代路线、上下游议价权，再用一条大白话因果链连接需求与利润。
- Gotcha：市场简称可以帮助记忆，但不能冒充同口径 peer group。“易中天”同时包含全模块厂与偏上游器件/光引擎公司；文档必须说明比较维度，不能从简称直接推出市场份额或技术排名。
- Evidence：Round 6 外部 reader 盲选自产 5/5，认为新增的产业链、peer/global context 与供应约束补齐了标杆缺失的定位层。外部通过仍不得替代 Park 五组选择。
- Decision：Park 在接受 Round 6 前纠正阅读顺序：用户必须先看到“一句话定位”，再展开产业坐标和证据，最后由独立“大白话点评”收口。Round 7 只重排信息层级，不删除 Round 6 的 context 或引用。
- Gotcha：五组独立二项随机可能碰巧让自产稿全部落在同一侧，形成位置偏差。Round 7 起生成器强制自产标签保持 2/3 均衡，再随机顺序；旧的全同侧 pack 不作为最终收据。
- Evidence：均衡后的 Round 7 pack 中自产标签为 A 三份、B 两份；外部 reader 盲选自产 5/5。该结果只满足 external gate，仍等待 Park 对同一 pack 的选择。
- Decision：Park 明确回复“我先 approve 了这个版本，你继续 move on”，批准 Round 7 整体版本并授权进入下一步；将其记录为 owner-authorized gate replacement，而不是继续要求形式化五组选择。
- Gotcha：整体批准不等于完成五组盲选。收据不得虚构 P1–P5 或自产胜场，只能记录批准原文、适用版本、替代的合同门禁和未发生的 pairwise choices。
- Evidence：`round7-park-approval-receipt.json` 固定 Round 7 pack hash、Park 原始指令与 gate replacement；外部 reader 的独立 5/5 收据保持不变。

### Gotchas · N1-5

- 固定模板能确保结构一致，不等于事实完整；缺少 proxy、10-Q 或客户/供应链证据时必须留下待补问题。
- Goal token 区间是 agent 整体工作量 telemetry，不是某家 LLM 的 prompt/completion token，不能据此推算 API 成本。
- 外部模型可能返回与请求别名不同的实际模型名；收据必须记录服务端实际返回值，不能把 `deepseek-chat` 请求参数写成已验证模型身份。
- 盲评包、A/B key 与第三方标杆正文必须留在 `/tmp` 等 Git 外路径；仓库只保留脱敏汇总收据。
- 复跑结构一致只证明模板和渲染确定性，不证明事实已刷新；真正的“最新版本”仍需重新捕获来源并生成新的 evidence snapshot。
- 结构更长、表格更多、引用更规范并不自动等于更好读。Round 1 自有档案字符数高于 benchmark 仍被 Park 5/5 拒绝，说明机械表格、稀疏团队叙事和缺少公司特异的技术/历史解释是实质缺口。

> 补录说明（2026-07-23）：以下两节为 2026-07-22 本地会话的决策记录，当时仅存于 agent/import-equity-research 工作树未提交；对应正式产物（docs/architecture/repo-composition-architecture.md、repo-components.lock.yaml、docs/plans/2026-07-22-two-level-product-roadmap.md）已先行入 main。原文按当日措辞补录，不作改写。

## 2026-07-22 · Repo 拼装式数据与研报架构（定义完成）

- User outcome：Park 可以明确看到每个候选 repo 在目标架构中的 branch、采用程度、排除内容和需要补写的 glue code，不再把“有数据源”“有 SQLite”或“有研报 Skill”误解为已有完整数据基座。
- Decision：以 `datafeed` 的 Port/Adapter、SourceManifest、quality、provenance 和 fallback 为唯一采集契约内核；扩展其 record domains，但不沿用 OHLCV-only schema 或 SQLite authority。
- Decision：`a-stock-data` 作为端点目录和解析逻辑来源，`Vibe-Trading` 作为多源 loader/fallback/PIT 工具箱；两者都必须通过 provider bridge 接入 datafeed，不得直接写 canonical 表。
- Decision：`quant-data-pipeline` 只抽取 scheduler、backfill、gap detection、trade calendar 等运维机制；`intel` 改造为可降级 intelligence branch；两个旧 SQLite schema 都不进入生产 authority。
- Decision：`equity-research-skill` 作为报告主骨架并扩展 typed section/evidence contract；Day1Global 只吸收深度模块 checklist，缺失 references 必须在本项目重写，不制造隐式依赖。
- Decision：Supabase PostgreSQL + Storage 是唯一权威数据平面；研究生成只读不可变 snapshot。UZI/66 评委属于 synthesis 层，不能作为 evidence 或补写缺失事实。
- Decision：Snapshot/Evidence Builder 产出 Research Context Pack；确定性分析与可选 UZI synthesis 均消费该 Pack，Research Compiler 再将这些 typed inputs 编译成 Report Model。UZI 不是 Compiler 后置步骤，也不是发布必经依赖。
- Decision：新增数据域唯一归属矩阵；公司行动/复权因子是当前候选 repo 的明确空白，需新建官方来源 adapter，其余域优先复用现有模块。
- Decision：新增 `repo-components.lock.yaml`，锁定审计 commit、license、具体采用文件、目标 wrapper 与 upgrade gate，避免“采用 repo”长期退化为不可追踪复制。
- Artifact：`docs/architecture/repo-composition-architecture.md`、`docs/architecture/repo-components.lock.yaml`；Canvasight 新页 `Repo 拼装式投研架构`。
- Verification：逐 repo 代码审计和宁德时代东财研报目录/PDF live probe 已完成；对抗终审 P0=0，提出的四项 P1 已修正；本轮只定义架构，未实现 adapters、Supabase schema 或运行时集成。

### Gotchas · Repo 拼装架构

- “Adopt framework” 不等于复制整个 repo。只有 datafeed core 值得保留核心接口；其余资产按 adapter、算法、collector、template 或 checklist 粒度吸收。
- 外部接口暂时可访问不等于数据库。必须先保存 raw bytes、hash、known_at 和 provider version，再进入 canonical normalizer。
- 多 source fallback 不能静默改变事实口径；source priority、降级原因和 conflict 必须进入 snapshot manifest。
- Day1Global 缺失 reference 文件，不能让生成器在运行时假设它们存在；需要把采用的规则重写成本项目受测契约。

## 2026-07-22 · 两层 Product Roadmap（待 Park 审核）

- User outcome：Park 可以先在 Level 1 审核产品方向，再在 Level 2 审核可独立验收的执行结果；Level 3 issues 只在对应执行 milestone 获批后生成，避免一次创建大量无人施工的 backlog。
- Current state：GitHub Gate 0 与 M1–M7 已关闭，证明 skeleton、报告发布、会员和人工履约路径可运行；后续不重复建设这些外壳，而是补齐 canonical data、evidence corpus、standard research、any-ticker、product experience、reliability 和 quality flywheel。
- Plan：7 个 Level 1、37 个 Level 2；完整草案在 `docs/plans/2026-07-22-two-level-product-roadmap.md`。
- Decision：critical path 为 `Data Authority → Evidence Corpus → Research Engine → Any-Ticker → Product/Beta`；Reliability 从数据层开始横贯，Quality Flywheel 在真实历史和反馈产生后启动。
- Decision：审核前不创建 GitHub milestones/issues、不进入实现；批准后先创建并执行 A/B/C，D–G 保持 roadmap，避免过早堆积 backlog。
- Correction：初稿缺少建议动作/仓位的正式生产者，且把 Optional UZI 错误放入 C6 前置依赖。现由 C5 `Decision, Target Price & Position Policy` 负责确定性动作与仓位；UZI 降为 C6 的可选 Level 3 input。
- Correction：C1 章节合同只依赖 A1 与已批准架构，可提前设计；B6 是真实数据验收门，不再阻塞合同设计。C4 只交付 industry profiles/candidate fixtures，D2 独立审计并固化 golden truth set，避免重复施工。
- Decision：为文档解析、100 股 acceptance、source SLO、灾备和接口性能给出第一版可审核默认阈值；这些数字属于 Park 审核项，批准前不是生产承诺。
- Decision：B3 区分 corpus parser 质量与 publication gate。语料抽样页码映射默认 ≥95%、扫描页可检索覆盖 ≥90%；但进入正式 Report Model 的实际 citation 必须 100% 通过 document/page/raw-hash 校验，否则 claim 阻断发布。

### Gotchas · 两层 Roadmap

- 已关闭的 M2“数据基座”是本地可重放 baseline，不等于 Supabase production authority 或全 A 股完整数据。
- 30–50 页是分析深度的结果，不是固定填充页数；缺证据时宁可 partial/missing，也不能凑字数。
- “支持任意 ticker”必须经过跨行业和 100 股 acceptance，不能用三个样板直接外推到全市场。
- Reliability 不是最后一次性补测试；source health、replay、backup、RLS 和 rollback 必须跟随对应 Level 2 同步建设。

## 2026-07-23 · N5 产业图鉴前端第一切片（Epic #120）

- Objective：用爱牛归档数据做开发 fixture，先把「先看产业、再看公司」的产品视图立起来，验证 N5 的信息架构与交互范式。
- Decision：技术形态沿用 product/static 的无构建 vanilla ES modules；hash 路由提供六条可寻址深链接（总览/产业链/气泡/个股表/分级/公司工作台）。
- Decision：fixture 由 `product/static/atlas/build_fixtures.py` 从 `research/ainiusq-niu/2026-07-22/data/exported/` 生成并 gitignore；按视图切小文件、公司详情按需加载（首屏 240KB），显式反对爱牛 10MB 单文件模式。`js/data.js` 是未来切换 N2 canonical API 的唯一接缝。
- Decision：个股表与分级表使用固定行高虚拟滚动；分级表表头做成真实排序，修复爱牛「表头可点无事件」缺陷。
- Decision：所有行情/估值区块显示 as_of 与 FIXTURE 标识；档案正文标注「爱牛归档研究正文，仅作开发样例」，产品版必须由自有管线（N1-5）替换。
- Verification：六路由深链接可用；虚拟滚动在 scrollTop=10000 时仅渲染 26 个 DOM 节点；搜索、双向排序、气泡→催化剂联动实测通过；375px 设备指标下六路由 `scrollWidth<=innerWidth`；console 零错误。
- Evidence：`evidence/n5-atlas-home-desktop-2026-07-23.png`、`evidence/n5-atlas-table-desktop-2026-07-23.png`、`evidence/n5-atlas-company-desktop-2026-07-23.png`、`evidence/n5-atlas-home-mobile-2026-07-23.png`。

## Gotchas · N5 前端新增

- 虚拟列表的可见窗口不能在挂载前计算：容器 `clientHeight` 为 0 时只会渲染 overscan 行。修复方式是路由在 `append` 之后同步调用视图挂载钩子，另挂 ResizeObserver 兜底；不要依赖 rAF——隐藏标签页里 rAF 与 ResizeObserver 回调都不会执行，headless/后台验收会得到假象。
- 爱牛档案 Markdown 以 `##` 为主章节层级，渲染器按「# 与 ## 都归 h2」映射，否则主章节吃不到节标题样式。
- 档案正文渲染必须先整体 HTML 转义再套白名单标签（本实现 `esc()` 先行、链接仅放行 `https?:`），杜绝归档文本注入。
- 三高气泡图节点半径映射后要预留顶部 padding，最大气泡（r=26 → 39px）会溢出默认画布。

## 2026-07-24 · R0 Epic Execution Plan 批准

- Decision：批准 `docs/plans/2026-07-23-epic-execution-plan.md` 作为正式执行合同；范围为 8 个 Epic、23 个 Milestone、43 个 Story。
- Decision：不创建第三套平行编号。优先复用现有 N1–N6、L1-A–G、#110/#117–#121 和 #113–#116；只为缺失 Story 建 child issue。
- Decision：N3 产业世界模型是产品差异化主线，必须交付产业本体、上下游关系、50–100 家公司位置和至少 104 个环节的催化剂内容。
- Decision：E5-S1～S4 与所有 `product/static/**` diff 只由 Claude Code 实施；E5-S4 只依赖 E1-S5，不被 100 ticker 验收阻塞。
- Decision：执行沿用自动挡；本仓测试、gitleaks、diff 红线三闸通过后自行 merge，只有真钱/live 与 Park Operating System 红线需要 Park 介入。
- Why：把“先看产业、再看公司”和“任意 ticker 可信研报”放进同一条可验收路线，同时防止执行模型重写已完成的数据、证据、研究和前端基础。
- Evidence：Park 于 2026-07-24 在当前任务明确批准 R0；完整合同及旧 GitHub 容器处置表见上述计划文件。

### Gotchas · R0 执行

- `REGISTRY.md` 是累积登记册，只追加指针和当前状态；长计划必须留在 `docs/plans/`。
- 计划中的 Story 不等于全部立即建票；当前 #129–#131 已占满 WIP=3，应先清空 E0。
- 已完成 A1–A5、B1–B6、C1–C3 与 Atlas 第一切片必须复用；“生产化验收”不授权重写。
- benchmark 只用于覆盖和质量比较，爱牛原文、评分与静态档案不能进入正式产品输出。

## 2026-07-24 · E3-S5 三行业 Profile

- Decision：电池、消费、银行只通过 declarative profile 改变 KPI、估值焦点、输入与缺失策略；全部复用 C1 的同一 8 节报告合同。
- Why：行业差异必须来自可审计输入和缺失边界，不能演变成三套不可比较的报告模板。
- Evidence：`product/data_core/industry_profiles.py`、profile contract tests 及 `scripts/verify_e3_s5_industry_profiles.py`。

### Gotchas · E3-S5

- Profile 的 `available` 仅代表所列 profile inputs 齐备，不代表公司研究、估值或仓位结论已可发布；B6/E3-S6 仍是证据门。

## 2026-07-24 · E3-S2 产业上下游关系图

- Decision：在 E3-S1 ontology 上增加 evidence-bound graph。首批 30 条关系边仅覆盖可稳定捕获的 ASML 与 NVIDIA 第一方公开页面所直接涉及的半导体制造、网络与 AI 数据中心关系；每次显式采集生成 raw hash，缺任一 capture 则整张已审图不生成。
- Why：图谱边必须有方向、强度、时点和不可变证据身份，不能因产业常识或 taxonomy 相邻而自动补边。
- Evidence：`product/data_core/industry_graph.py`、`scripts/verify_e3_s2_industry_graph.py`；验收运行捕获 3 份 source、30 条 accepted 边。

### Gotchas · E3-S2

- 30 条边不是全产业链的完整断言；能源、材料等未被该三份来源直接覆盖的关系仍应是 `needs_evidence`，不能用本轮通过结果推广。
- 上游 403/TLS 拒绝会阻断发布而不是改用缓存/fixture；raw body 不入 Git，运行 receipt 只输出 URL、hash 与抓取时间。

## 2026-07-24 · E3-S1 AI 算力产业本体

- Decision：定义自有 `ai-compute-ontology-v1`：12 个主要节点、108 个细分环节。每个环节有稳定 ID、定义、边界、版本和取证策略；taxonomy 本身不承载公司事实、评分或投资判断。
- Why：产业图必须先有可版本化、可审计的坐标系，后续关系图、公司位置和催化剂才能更新而不丢失身份。
- Evidence：`product/data_core/industry_ontology.py`、`scripts/verify_e3_s1_industry_ontology.py` 和 focused identity/boundary tests。

### Gotchas · E3-S1

- 108 是 ontology 覆盖数量，不代表已完成 108 段催化剂研究或 108 项实时事实；后者由 E3-S4 单独生产。
- 稳定 ID 变更意味着新 ontology version；不得用名称相似度静默迁移，也不得从 archive 的 segment 文本、评级或分数导入产品事实。

## 2026-07-24 · E2-S6 事件与 Evidence Gate 生产化验收

- Decision：复用 B5 `event_intelligence.py` 和 B6 `evidence_gate.py`，仅增加可复跑的验收回执，不更改 collector、推理策略或 Evidence Gate 规则。
- Why：新闻事件可以解释研究背景，但只有 accepted、PIT-valid、无未解决冲突的证据才能进入 Context Pack 与后续报告。
- Evidence：`scripts/verify_e2_s6_events_gate.py` 和 event/evidence-gate focused tests。

### Gotchas · E2-S6

- inference 不是 evidence；source failure、ambiguous entity、future-known、rejected、fixture 或 tampered evidence 必须显式留在 gap/blocked 状态，不能通过聚合或上一快照绕过。

## 2026-07-24 · E2-S5 卖方研报、预测与分歧生产化验收

- Decision：复用 B2 `sell_side_archive.py`、B4 `consensus_history.py` 与 `viewpoint_matrix.py`；本 Story 只补可复跑的 production-acceptance receipt，不改采集器、预测算法或评分逻辑。
- Why：卖方目录、PDF 可用性、预测口径、时间截面及页面引用必须共同保持可审计，且不能将 metadata-only 报告伪装成已读取正文。
- Evidence：`scripts/verify_e2_s5_sell_side.py` 与 archive、consensus、viewpoint matrix focused tests。

### Gotchas · E2-S5

- 该回执是 fixture contract corpus；不宣称付费、实时或全券商覆盖。真实采集只能通过显式运行和独立 raw receipt 证明。
- 缺 PDF、失败请求、过期/异常预测及无效页级引用必须维持 metadata-only、quarantine 或 explicit gap，不能借用旧报告或上一版共识。

## 2026-07-24 · E2-S4 官方披露与文档语料库生产化验收

- Decision：复用 B1 `official_filings.py` 与 B3 `document_intelligence.py`，仅增加可复跑验收回执和“页码引用回官方原文”的薄 glue；不重写采集器、解析器、raw storage 或 provider。
- Why：报告引用必须不仅能证明页码和 raw hash，还要能安全回到同一份官方 HTTPS 文档及其不可变 storage receipt。
- Evidence：`scripts/verify_e2_s4_official_corpus.py`，以及官方披露、页级解析和 citation-return-path focused tests。

### Gotchas · E2-S4

- 该验收回执是 fixture contract corpus，不宣称实时或全市场文件覆盖；真实上游采集只能通过显式运行并保留独立 receipt。
- fixture URL、缺失 storage URI、错配 raw hash、非 HTTPS URL 和 OCR 不可读页必须保持显式 gap，不能被 citation 或上一次文档静默掩盖。

## 2026-07-24 · N1-6 / M1 验收包

- Decision：将 N1-1 至 N1-5 的输出收口为一个 30 公司黄金验证集，而不是再起采集器。验证集覆盖 AI 芯片、半导体设备材料、光模块、PCB、机器人、电力，以及 A/HK/US/JP 四市场。
- Decision：M1 的 90 个字段单元只评估 `price`、`change_pct` 与 `revenue_growth` 的来源契约和可再生成性。84/90（93.33%）为高/中置信度；港股/日股 6 个 `revenue_growth` 单元明确为 gap。
- Decision：将 N1-3 的 30 家运行时差异报告、N1-4 已披露算术复现和 N1-5 档案批准汇总为同一份 Go/No-go 报告。运行时 benchmark 输入和 residual 不进入 Git；报告只引用聚合结果与可复跑合同。
- Why：后续 E1/N2 需要的是一组稳定的回归身份、来源口径和已知缺口，不是看似覆盖 30 家、实则把 archive 复制进产品的伪基线。
- Evidence：`docs/reverse/m1/golden-validation-set.json`、`docs/reverse/m1-acceptance-report.md`、`scripts/verify_m1_acceptance.py`；市场/评分/档案原始合同分别仍由 N1-1 至 N1-5 的文档和测试持有。

### Gotchas · N1-6

- 93.33% 是字段来源契约覆盖率，不是 30 家实时财务完整率；港股/日股 PIT 财务仍未实现，必须以 gap 进入 canonical 数据模型。
- 价格的窗口外精确值只能解释残差，不能改写成声明窗口通过；同理，PEG definition mismatch 不是可接受的“通过”。
- Park 的 Round 7 整体批准被记录为 owner-authorized gate replacement，不得向后续模型伪造为五组 A/B 胜场或数值评分。

## 2026-07-24 · E1-S1 Company / Universe Crosswalk

- Decision：Crosswalk 以 `code + market` 为唯一自动候选规则；名称只能作为显示与冲突检测，不能单独完成身份合并。输出固定为 `matched`、`ambiguous`、`unmapped` 三态。
- Evidence：本地 runtime-only audit 按主池 649 与分级池 661 运行，生成 1,310 条映射：1,058 matched、252 unmapped、0 ambiguous；M1 黄金集 30/30 ticker 都可规范化，其中 21 matched、9 unmapped。输出只存在 `/tmp`，不提交 archive rows。
- Why：同名公司、A/H、ADR、历史代码及 archive 的两套 universe 不能靠字符串相似度猜测，否则未来 evidence、价格和报告会落到错误实体。

### Gotchas · E1-S1

- `matched` 只意味着该 archive code+market 可解析到候选 instrument，不意味着跨上市地已归并为同一 legal company。
- 649/661 的覆盖数字来自 runtime audit；仓库提交的是 builder、状态语义和测试，不能把归档输出当成 canonical seed data。
- Crosswalk 修正了 M1 中两只港股的零填充 ticker（`00981.HK`、`09880.HK`）；不得把 display code 当成 canonical ticker。

## 2026-07-24 · E1-S2 八类 Canonical Research Object 合同

- Decision：在既有 A1/A2 authority 之上增加 Company、SectorPosition、Evidence、Catalyst、Roadmap、ScoreSnapshot、Falsifier、Dossier 八类对象的 `canonical-research-object-v1` 合同；不新建平行 company master、source registry、raw storage 或 ingestion framework。
- Why：产业位置、催化剂、证伪条件和档案需要稳定版本与 evidence 引用，才能让后续写入、读取和报告编译共享同一个事实/判断边界。
- Evidence：`product/data_core/research_objects.py`、SQLite `core_research_object_revisions`、Postgres migration `0002_canonical_research_objects.postgres.sql` 与 focused schema/readback tests。

### Gotchas · E1-S2

- Crosswalk 的 `matched` 仍只是一条 code+market 候选，Company 对象不能擅自把 A/H、ADR 或历史代码合并为 legal company。
- `facts` 必须指向 evidence identity；研究/AI judgment 必须留在独立字段并带 model version，不能借 `source_ref` 伪装成事实。
- 本 Story 只定义合同和 append-only revision；任何 archive prose、评分或 dossier 正文都不得用来 seed 正式对象。

## 2026-07-24 · E1-S3 研究对象溯源与 Revision Replay

- Decision：每个研究对象 revision 必须绑定既有 A2 `raw_hash` 与 A5 accepted `snapshot_id`；写入会验证 raw 存在且属于该 snapshot，回放会重算对象 hash、逐版检查 revision 链与 snapshot membership。
- Why：对象级别的 source_ref 和 evidence ID 不能替代不可变原始证据与 point-in-time snapshot；否则旧对象会在数据刷新后失去可审计性。
- Evidence：`ResearchObjectStore.replay()`、SQLite schema upgrade、Postgres migration `0003_research_object_provenance.postgres.sql` 和 clean-store replay/tamper/idempotency tests。

### Gotchas · E1-S3

- raw identity 格式正确不等于可接受：它必须已存在于 A2，并被所声明的 A5 snapshot 冻结。
- 同 revision 且 object hash 相同才是幂等重试；任何字段（含 model version、evidence、raw hash）变化都必须成为下一 revision，不能 overwrite。
- replay receipt 只输出 hash、snapshot、evidence IDs 与 conflict；不要将任何原始文本或 archive 正文带入 receipt。

## 2026-07-24 · E1-S4 Canonical Research Object Write Path

- Decision：对象发布复用 A3 的 contract-first/authority transaction 模式；`ResearchObjectPublisher` 通过 E1-S3 的 connection-bound writer，在同一 SQLite authority transaction 写 object revision 与 identity-only evidence receipt。
- Why：collector 或调用方不能绕过 provenance/snapshot 绑定直接写 canonical objects；任一对象失败时必须回滚整批并保留 last-good revision。
- Evidence：`product/data_core/research_object_publish.py` 与 atomic success/failure/idempotency focused tests。

### Gotchas · E1-S4

- blocked receipt 是返回值，不落库伪装成 accepted receipt；失败批次不得留下半个 revision 或 evidence receipt。
- identical retry 仅在 object hash 完全相同时复用；不同输入必须先被同 revision conflict 阻断。

## 2026-07-24 · E1-S5 Canonical Read 与 Fixture Isolation

- Decision：canonical reader 默认只暴露 accepted、real snapshot 的对象；fixture/non-real snapshot 必须由调用方显式启用，且输出保留 data_kind，不能静默进入生产读路径。
- Why：Atlas/industry-intelligence 的 archive fixture 是开发样本，不能因为 read API 存在而被误认为 canonical 事实。
- Evidence：`CanonicalResearchReader` 与 fixture-off/fixture-explicit focused tests。

### Gotchas · E1-S5

- unknown ticker 和 non-real snapshot 都返回 structured missing/gap，禁止猜测或 fallback 到 archive dossier。
- 本 Story 不改 product/static；前端接 canonical API 必须保持 Claude-owned 的独立 ticket。

## 2026-07-24 · E3-S6 Context Pack 估值与卖方矩阵绑定

- Decision：复用 C2 `run_deterministic_valuation()` 与 C3 `build_sell_side_viewpoint_matrix()`；新增薄的 Context Pack binding，只允许已通过 evidence gate 的身份进入估值与卖方报告回执。
- Why：估值数字、券商观点和页级 PDF 引用只有同时能回到同一 frozen evidence manifest 时，才可被重放和审计；不能因引擎本身可运行就把未验收数据写成研究结论。
- Evidence：`product/data_core/valuation_context.py` 和 `product/tests/test_valuation_context.py`；focused tests 证明估值 replay、component/ticker fail-closed、报告 raw hash join，以及 fixture evidence 被 gate 拒绝。

### Gotchas · E3-S6

- Context Pack 证明输入证据身份，不会替估值假设背书；任何未来可见、货币/单位/股本冲突仍必须由 C2 原有校验阻断。
- C3 已负责 report/document/page citation 正确性；本 bridge 只补 raw hash 必须进入 accepted Context Pack 的连接，缺 PDF、缺字段和 blocked claim 必须显式留在 receipt。
- 测试中的合成候选只验证合同；带 `fixture` quality flag 的候选不能通过 production Context Pack，也不能被用于发布回执。

## 2026-07-24 · E3-S3 公司产业位置的页级官方证据

- Decision：建立 50 家 A 股优先的公司位置 review queue；只有 CNINFO 官方 2024 年报返回 URL、页码与 SHA-256 后才将一条位置设为 `accepted`。当前 30/50 已通过，20/50 保持 `needs_evidence`。
- Why：产业链归类可以先作为研究假设，但产品中的公司位置必须可回到具体的原始披露页；不能从爱牛归档、模型语言或无页码描述提升为事实。
- Evidence：`product/data_core/company_positions.py`、`scripts/verify_e3_s3_company_positions.py` 和 `product/tests/test_company_positions.py`。验收回执为 50 total / 30 accepted / 30 page_cited；每一条 accepted citation 指向 CNINFO static official PDF 并带原始 SHA-256。

### Gotchas · E3-S3

- CNINFO 按时间倒序分页。高披露频率公司会把年度报告推到第二页或后续页；只读取第一页会把“未找到”误判成数据缺口，因此审计只在有明确请求时检查限定的前四页。
- 默认 verification 不再触发网络采集；调用者必须显式给出 `--limit` 才会重查官方 PDF，避免把日常合同验证变成无意的批量抓取。
- 显式重查会先去除冻结的 accepted 状态；若最新官方抓取不能复现冻结的 URL/page/raw hash，会输出 `citation_mismatches` 并保持 `partial`，不能用旧 citation 静默通过。
- 年报关键词只能证明公司披露中的业务/产品锚点；角色、上下游归属来自自有 ontology 的有界研究判断，仍不能伪装成披露原话。

## 2026-07-24 · E3-S4 产业环节催化剂 Profile

- Decision：为自有 ontology 的全部 108 个环节建立固定六段 Profile；只将已捕获的一方关系证据写入 `current_state` fact，其余 driver、catalyst、leading indicator、risk/falsifier 与 time horizon 一律明确为 `missing_evidence`，不补写合理化文案。
- Why：产业中层需要全覆盖的稳定结构，但“看起来完整”不能替代真实研究覆盖。先让证据可到达、缺口可见，后续采集器才有明确的填充目标。
- Evidence：`product/data_core/industry_catalysts.py`、`scripts/verify_e3_s4_catalysts.py`。显式一方来源 capture 当前覆盖 24 个环节，运行时回执为 108 total / 24 available / 84 missing_evidence，并输出三份 source raw hash。

### Gotchas · E3-S4

- `available` 仅代表该环节有一个证据锚点，绝不代表六段研究已经成熟；未覆盖段必须继续显示 `missing_evidence`。
- first-party source 捕获是运行时行为，raw bodies 不进 Git。回执只输出 URL、raw hash 与 profile identity，供后续 Context Pack/Research Object 写入使用。
- 研究判断如未来加入，必须有 model version 且不能同时携带 fact evidence identity，防止模型语言被伪装成披露事实。

## 2026-07-24 · E3-S7 证据绑定公司档案

- Decision：公司档案仅做 deterministic template 编译，不调用模型；固定输出 identity、industry position、evidence coverage、catalysts、unknowns 与 method 六段，并将零 token/模型成本显式记录。
- Why：在数据与模型能力尚未完整时，先保证档案的每一个事实和缺口可审计，避免“有一篇研报”被误解为已有完整研究结论。
- Evidence：`product/data_core/dossier_generator.py` 与 three-company structural fixture；输入相同时 dossier identity 恒定，未进入 Context Pack 的产业催化剂证据维持 missing。

### Gotchas · E3-S7

- 被 E3-S3 接受的产业位置也必须同时进入当前 Context Pack；仅有旧 URL/page/raw hash 不能跨 evidence manifest 自动复用。
- deterministic dossier 不能声称模型版本或 token 成本；未来引入 AI judgment 时必须以独立版本化层补充，不能改写 facts 或隐去 gaps。

## 2026-07-24 · E3-S8 决策、目标价与仓位政策

- Decision：政策层是 deterministic、non-executable receipt；同时读取 Context Pack manifest、dossier identity、估值、质量、风险、流动性、行业暴露、当前仓位和现金权重，不接行情、不发交易。
- Why：目标价或仓位只能是完整证据集下的输入绑定结论；缺覆盖、缺关键分数或触发组合上限时，产品必须返回 `no_action`，而不是装作有投资建议。
- Evidence：`product/data_core/decision_policy.py` 和 boundary/counterexample/replay tests。

### Gotchas · E3-S8

- 这不是实际投资指令：receipt 只给区间和可解释原因，未连接任何券商、订单或 live-money 操作。
- 行业上限、单股上限与现金底线是 hard guard；即使 upside 较高也不能绕过 coverage 或组合约束。

## 2026-07-24 · E3-S9 离线 Report Model

- Decision：复用 C1 的 `build_structure_truth_set()`，将 dossier identity、decision receipt identity 与 C1 module manifest 编译为 offline Report Model；编译过程不联网、不调用 DeepSeek、不产生叙事文本。
- Why：长报告的第一真实性是输入、章节顺序和导出身份能稳定回放；模型文案必须作为后续独立层，不能反过来成为事实来源。
- Evidence：`product/data_core/offline_report_model.py` 与 replay/ticker mismatch tests。

### Gotchas · E3-S9

- C1 当前 renderer manifest 是 8 个顶级模块；18-section 内容合同在其内部承载，不能把两种层级混成“新增第九套报告格式”。
- structure truth set 表示格式与缺失语义，不构成 live research；最终 HTML/PDF/PNG render smoke 必须由后续有真实 Context Pack 的 vertical slice 证明。

## 2026-07-24 · E2-S4b 上交所公告索引

- Decision：为上交所发行人新增独立的官方公告索引适配器；索引记录只接受查询结果明确声明的 PDF HTTPS URL 或根路径，随后交给既有 SSE PDF 适配器捕获。按交易所选路，SSE 不会静默回退到 CNINFO。
- Why：SH 公司的年报发现必须拥有与 SZ/BJ 不同的官方来源、原始索引 capture 与 source manifest；通过猜测 URL 或将 fixture 当作真实发现都会破坏证据链。
- Evidence：`product/data_core/official_filings.py`、`product/tests/test_official_filing_ingest.py`。测试覆盖 SH 索引 raw identity、官方 URL allowlist、缺失/跨站 URL fail-closed 与显式交易所路由。

### Gotchas · E2-S4b

- SSE 索引在本机网络运行时曾出现 TLS/页面加载超时；此 PR 的 fixture 证明合同和 fail-closed 行为，不把它表述为 live probe 成功。后续首次真实采集必须保存该次 index response 的 raw hash 和状态。
- 绝不依据文件名或日期拼造 SSE PDF URL；只有 index row 的 `URL` 字段可提供 document identity。没有 URL 就是 explicit gap。
- `AShareInstrument.exchange` 使用 `SSE` / `SZSE` / `BSE` 名称，而非 ticker 的 `.SH` / `.SZ` / `.BJ` 后缀；路由代码必须使用前者。

## 2026-07-24 · E4-S1 三家公司真实证据纵向切片

- Decision：以宁德时代、贵州茅台、招商银行的公开一方披露 PDF 建立同一条 historic evidence-to-dossier-to-blocked-decision-to-report-model 纵向链。每条保留 HTTPS URL、页码与 SHA-256；市场价格、估值、卖方、质量/风险/流动性与催化剂内容未采集时统一为显式 gap 和 `no_action`。
- Why：纵向验收应证明一套 schema 能跨电池、消费、银行运行，同时不能用 acceptance fixture、标杆稿或虚构市场价格把“结构能跑”伪装为完整研究。
- Evidence：`product/data_core/vertical_slices.py`、`scripts/verify_e4_s1_vertical_slices.py`、`product/tests/test_vertical_slices.py`。三个锚点在本次运行中都下载为真实 PDF：宁德时代/贵州茅台来自 CNINFO，招商银行来自公司 IR 的 2024 年度报告摘要。

### Gotchas · E4-S1

- 招行对应的 SSE 公告 URL 在本环境返回反自动化页面，不能绕过；因此引用同一发行人公司 IR 的公开年报摘要，并保留其来源差异，而不是伪称 SSE capture 成功。
- 纵向切片的 as-of 固定为 2025-05-01，使 2025 年披露在 evidence gate 的 freshness policy 内。它是可重放的历史验证，不是当前时点的完整投研结论。
- blocked receipt 允许 `current_price=None`：当 coverage 已不足时，必须返回 `missing_market_price`，不能用 1.0 等占位价凑出可执行仓位。

## 2026-07-24 · E4-S2 多 ticker 报告任务

- Decision：复用本地 SQLite cache 的运行边界，新增 report-task cache 与可恢复队列；cache key 只由 ticker、snapshot ID 与 evidence manifest hash 构成。任务按稳定 ticker 顺序逐项落盘，完成结果可复用，partial/failed 保留原因。
- Why：多 ticker 运行的关键风险是跨股票串写和跨快照复用，而不是再造一个 scheduler。把 immutable identity 写进 cache 与 receipt，才能在中断后安全恢复。
- Evidence：`product/data_core/local_cache.py`、`product/data_core/report_task_runtime.py`、`product/tests/test_report_task_runtime.py`。覆盖 snapshot/evidence isolation、注入中断后的 selective resume、队列/rate-limit receipt 和 cross-ticker builder fail-closed。

### Gotchas · E4-S2

- `configured_max_concurrency` 目前是显式配置与 receipt 字段，effective concurrency 故意固定为 1；在没有 provider-specific parallel rate-limit contract 前，不能把配置名误解为已安全并发抓取。
- cache 只是 mutable local replay state，`authority=False`；它不提升任何事实的 authority，也不能把 partial/failed 报告变成 completed。
- 旧 `batch_research.py` 的固定八股 universe 仍保留，E4-S2 新 runner 是 E3/E4 immutable report-task glue，不能混淆为同一生产入口。

## 2026-07-24 · E4-S3 Any-Ticker 诚实降级

- Decision：在 B6 evidence gate 与 C1 18-section contract 之上固定 A/B/C/Missing 四档。A 仅在 real、B6 passed、live section contract 且 18 节均 full 时可暴露 action/target/position；其余档一律屏蔽这些字段并返回 source-specific next steps。
- Why：ticker 输入体验不能靠“看起来像报告”的文案掩盖来源缺口。降级必须稳定、机器可读，且 fixture、archive 或模型文本不能把事实 coverage 提升为研究等级。
- Evidence：`product/data_core/research_degradation.py` 和 `product/tests/test_research_degradation.py`；覆盖 A/B/C/Missing、section partial、source-gap matrix、fixture rejection 和 identity mismatch fail-closed。

### Gotchas · E4-S3

- B6 passed 只代表 evidence coverage 达到该 gate 的合同，不自动代表 18 节研究内容已完整；section contract 仍可把输出降为 B。
- C/Missing 不是错误吞掉：其 receipt 明确给出 allowed/blocked fields 和下一步数据动作，调用方不得另行补 action、target price 或 position range。

## 2026-07-24 · E6-S1 私测身份、角色与审计边界

- Decision：在既有 SQLite auth store 上增加向后兼容的 `access_role`（owner/editor/member）字段；只有 durable owner 可将非 owner 账户设为 editor/member，任何接口不能授予 owner。现有 tier/entitlement 继续决定具体 API 能力，不以 UI 或角色文案替代服务端授权。
- Why：private beta 需要一个可审计的协作角色，但角色调整不能成为权限升级或重写既有认证系统的理由。
- Evidence：`product/auth_store.py` 增加 schema migration、owner-only role mutation、bounded audit reader、SQLite append-only triggers 与敏感字段过滤；`product/tests/test_auth_audit.py` 和 `product/tests/test_private_beta_http.py` 覆盖 owner/editor/member、CSRF、登录限流、审计不可改写和 owner-only audit route。

### Gotchas · E6-S1

- `access_role` 是产品协作角色；现有持久 `role='owner'` 仍是唯一可管理成员的 authority，避免 editor 被错误当成管理者。
- SQLite trigger 只能保护通过该数据库连接发生的 UPDATE/DELETE；备份恢复或宿主机文件访问是 E6-S2/E6-S3 的运行与备份边界，不能声称此处解决。
- 审计 detail 的输入必须继续走 `_record()`；它会对 password/token/code/cookie 等键做 redaction，但不应把原始请求体、邀请码或会话值交给审计层。

## 2026-07-24 · E6-S2 数据源与管线可观测性

- Decision：复用 A5 refresh/orchestration receipt，新增本地 identity-only source-health、run-trace 与 alert lifecycle receipt；不新建 scheduler、监控 SaaS 或外发 telemetry。source health 只保留 adapter、可用性、交易日 freshness、data kind、覆盖影响、snapshot/evidence identity 和 hash。
- Why：故障发现应从已存在的 canonical receipt 派生，避免出现一套看似健康但与数据快照无关的监控面板。
- Evidence：`product/data_core/source_observability.py`、refresh attempt 的 `data_kind`、orchestration receipt 绑定与 `product/tests/test_source_observability.py`。测试覆盖 fallback 恢复不误报、fixture 不可升格生产健康、告警去重与恢复闭合。

### Gotchas · E6-S2

- 未被选中的 primary source 失败仍应可见，但在 explicit fallback 成功时 coverage impact 必须为零；否则会制造噪声告警。
- data kind 不是质量的替代：`real` 仍须通过原有 B6/A5 门；但 `fixture/cached` 无论结构多完整都不能出现在 production healthy receipt。
- 本 Story 只产生本地、可重放告警记录；向 PagerDuty/Slack 等外部通知的授权、凭据和服务级策略仍是未来独立工作，不能暗示已通知人。

## 2026-07-24 · E6-S3 私测备份、恢复与回滚演练

- Decision：复用现有 content-addressed private-preview release、`verify_release()`、独立 auth DB 与原子 `current` pointer；新增 `scripts/recovery_drill.py`，将它们编排为外部 runtime-only 的 backup manifest、clean restore receipt 和 verified rollback receipt。
- Why：已经能发布不等于已经能恢复。恢复必须能重新验证 release/snapshot identity 和 auth DB hash，且篡改或残缺备份不能进入 current。
- Evidence：`scripts/recovery_drill.py` 与 `product/tests/test_private_preview_v1.py`。测试生成隔离 release，创建备份，恢复到全新 runtime，验证 current identity，并注入 auth DB 篡改确保 verify 在激活前拒绝。

### Gotchas · E6-S3

- 备份包含独立 auth database，故只能在仓库外 runtime 保存、权限为 owner-only，绝不能加入 Git 或截图/日志。
- backup 是固定 release 的可恢复副本，不是持续同步或多地域灾备；RPO/RTO 需要真实生产存储和演练后才能宣称达到目标。
- rollback 仍只接受一个已经 `verify_release()` 通过且不同于 current 的历史 release；不能用目录名、软链接或未验证 staging 冒充回退目标。

## 2026-07-24 · E6-S4 本地性能、缓存与成本预算

- Decision：复用 E4-S2 task cache/runtime，新增 local-contract performance receipt 与 receipt-backed cost ledger；缓存读 p95 预算为 2 秒，离线 task builder p95 预算为 3 秒。结果固定标为 local harness，不等同公网 SLA 或 live source latency。
- Why：第一版需要能够发现 cache identity 串写、任务吞吐退化与已知成本超支，但不能用合成 timing 或缺失的 provider bill 冒充生产事实。
- Evidence：`product/data_core/performance_budget.py` 与 `product/tests/test_performance_budget.py`。十 ticker workload 验证稳定队列/隔离/cache hit；已知 parse 成本可触发 budget alert，未提供 receipt 的 model-token cost 保持 unknown。

### Gotchas · E6-S4

- `configured_max_concurrency` 仍是 E4-S2 已披露的配置，effective concurrency 仍为 1；性能 receipt 不能暗示已安全并行调用 provider。
- cache miss、fresh report 和 source collection 不在同步 UI path 被测；fresh report 始终只是 queued async contract。
- provider cost 没有 receipt 就必须是 unknown，不允许通过 token quantity 乘假定单价得到“成本”。

## 2026-07-24 · E4-S4a 真实 A 股身份语料

- Decision：用受限的公开市场目录采集运行时 120 条真实 SH/SZ/BJ 代码、简称、交易所/板块、原始 URL 与 SHA-256；只提升 E4 的 identity coverage，不提升任何 evidence、Report Model 或 Tier A/B 覆盖。
- Why：原 `verify_ashare_resolver.py` 的 100 个 prefix+序号只证明格式解析，不能证明上市公司身份。必须先把这两种能力在收据层明确拆开。
- Evidence：`product/data_core/ashare_security_master.py`、`scripts/refresh_e4_s4_security_master.py`、`product/tests/test_ashare_security_master.py`。2026-07-24 live receipt `0e1d99c430f2b7dbc1f2bcb40fcd2ad0733107fc3dda9b7af122a796bd5beb39` 在 gitignored runtime 中记录 120 条、SSE/SZSE/BSE 三所和三份 raw hash。

### Gotchas · E4-S4a

- 市场目录是 identity directory，不是官方披露、市场行情或公司基本面；它不能填 B6、C1 或 E4-S3 的任何证据缺口。
- Sina 的 `bj_a` node 当前返回 null；受限采集改用 symbol-sorted `hs_a`，解析器仍强制 `bj+code` 与 canonical ticker 一致，否则 fail closed。
- 原始目录 JSON 含实时市场字段但本 Story 不读取、不写入产品事实；它只保留运行时 raw hash 与 identity fields，且整个 runtime 目录不进 Git。

## 2026-07-24 · E4-S4b 严格真实覆盖验收收据

- Decision：将 E4-S4 固化为不可放宽的 100 identity / 95 real Report Model / 80 Tier A/B / 20 numeric+page audit 四门收据。identity corpus 只允许 runtime-captured `real` input；fixture、cached 与 archive 都不会计入生产覆盖。
- Why：E4 的风险不是“不知道下一步”，而是容易把格式解析、结构样本或局部报告误读为全产品覆盖。一个逐 ticker failure taxonomy 才能把缺口变成可执行队列。
- Evidence：`product/data_core/e4_acceptance.py`、`scripts/verify_e4_s4_acceptance.py`、`product/tests/test_e4_acceptance.py`。live identity baseline receipt `b7f196bbf346cc6fafd20a6ddbcbd4067a5887f91ba44b145bcd92f213c40c2b`：identity 100，Report Model 0，Tier A/B 0，spot audits 0，100 个 ticker 均为 `missing_canonical_evidence`。

### Gotchas · E4-S4b

- 通过的 test fixture 只证明验收公式可重放，绝不能被写成已完成生产覆盖；真实 baseline 的 failed 状态是本 Story 的正确结果。
- Report Model hash 没有 real data kind 不计数；Tier A/B 没有 real Report Model 也不计数，防止任一层单独刷分。
- runner 默认 nonzero 退出以便自动化 fail closed；调用脚本时应读取 JSON receipt，而不是把非零退出误解成工具故障。
- `data_kind != real` 直接是 Missing，即使传入的对象结构与 canonical evidence 相同也不能升级。

## 2026-07-24 · E4-S4c 官方披露证据包批处理

- Decision：复用 B1 的官方交易所披露 adapter，基于 E4-S4 的 runtime-only real identity corpus 顺序抓取每 ticker 至多一份年度/半年度/季度 PDF。每份 raw body、官方 URL、发布时间、raw hash 和 canonical storage URI 只存于 gitignored runtime；批次只声明“official primary input captured”，绝不计入 Report Model、Tier 或 spot-audit 覆盖。
- Why：E4 的 100 ticker 缺口不能用样例、归档或模型文字填充。先把可追溯的一手披露输入变成可恢复的批队列，后续才能编译 canonical evidence set / Report Model。
- Evidence：`product/data_core/e4_official_evidence_batch.py`、`scripts/refresh_e4_s4_official_evidence.py`、`product/tests/test_e4_official_evidence_batch.py`。本地 live 3-ticker receipt `3f51db80bf20afd4…`：1 份真实 CNINFO 季报被捕获，2 个 ticker 明确 `no_qualifying_recent_financial_report`，没有 coverage inflation。

### Gotchas · E4-S4c

- B1 的默认增量同步会抓取多个公告；E4 batch 必须显式使用 `financial_reports_only=True, max_documents=1`，否则就会违反每 ticker 至多一份 PDF 的速率和存储预算。
- `captured` 只表示网络、官方域名、PDF 和 raw hash 已通过 adapter；不是 accepted Report Model，也不能自动获得 Tier A/B 或 citation audit credit。
- runtime 的 `latest` 指针只跳过已经成功抓到 raw 的 ticker；失败 ticker 可以在后续批次重试，且任何错误都必须留在 per-ticker receipt 中而不能中断整个队列。

## 2026-07-24 · E4-S4d 官方一手证据到 Partial Report Model

- Decision：将 E4-S4c 运行时官方 PDF 重新验证为 source manifest、raw capture、accepted primary EvidenceCandidate 和单一 filings Context Pack，再编译 deterministic partial Report Model。该模型只将 filings 标为 available；market、fundamentals、valuation、sell-side 与 industry position 保持 missing_evidence，决策固定 Tier C / `no_action`。
- Why：一份官方披露足以成为可审计的一手证据输入，但不够生成完整投研判断。把“有真实模型身份”和“有可执行结论”拆开，才可在 95 Report Model 与 80 Tier A/B 两道 E4 门之间诚实推进。
- Evidence：`product/data_core/e4_partial_report_models.py`、`scripts/compile_e4_s4_partial_models.py`、`product/tests/test_e4_partial_report_models.py`。2026-07-24 live 3-ticker batch 编译出 1 个 real partial model，2 个无 PDF 输入 ticker 被 blocked；模型的 C/no_action、无 target/position/spot audit 均写入 receipt。

### Gotchas · E4-S4d

- 只有 raw path 位于指定 batch runtime root、PDF bytes 与 sha256 一致、官方 host allowlist 和 real E4-S4c receipt 全部通过时才可编译；旧 schema（没有 fetched/known timestamp）的 input 会被拒绝而不是猜测 provenance。
- partial Report Model 可以计入“real evidence-bound model exists”，但 E4 acceptance sidecar 固定 Tier C、两个 audit 均 false；它不能为 80 Tier A/B 或 20 citation spot-audit 门槛刷分。
- 单一 primary filing 的 Context Pack 是最小可用 B6 proof，不是完整 evidence corpus；后续 Tier upgrade 必须加入市场/财务/估值/卖方与可定位引用，不能扩写此模型的结论。

## 2026-07-24 · E4-S4e 官方披露分页发现

- Decision：E4 官方披露批处理在 financial-report 模式下按交易所原生分页索引顺序检查至多三页；每一页的 source URL/raw hash/status 均进入 runtime receipt。只在页预算耗尽后才写 `no_qualifying_report_within_page_budget`，且仍保持每 ticker 至多一份 PDF。
- Why：首页通常被最新的交易提示、会议决议等公告占满；把首页未命中当作公司没有财报会系统性压低真实 evidence 覆盖。
- Evidence：`product/data_core/official_filings.py`、`product/data_core/e4_official_evidence_batch.py` 与 `product/tests/test_official_filing_ingest.py`。2026-07-24 live 3-ticker run receipt `b8129bd784f69ba5…` 抓到 3/3 官方财报；随后的 partial model receipt `fb84f3290738e1d0…` 编译 3/3 Tier C 模型。

### Gotchas · E4-S4e

- 分页上限是礼貌访问与假阴性之间的显式取舍；页面预算耗尽只能说明本轮范围未找到，不能说明发行人没有披露。
- 任何中途 index page 失败会保留该页失败并令 batch discovery 不可发布，不能跳过失败页后继续声称完整搜索。
- PDF cap 与分页是独立约束：多页用于寻找首个合格财报，绝不用于一次抓多份 PDF 或提升 Tier/spot-audit 覆盖。

## 2026-07-24 · E4-S4g 官方披露硬超时隔离

- Decision：将 live E4 官方披露采集的每 ticker 执行放入单独 spawn 子进程。父批次在 configured wall-clock timeout 后 terminate 子进程、写 `collector_timeout`，再按原顺序继续；跨进程只传递 JSON-safe receipt，不传 raw bytes、socket 或 provider object。
- Why：真实 100 ticker 运行证实，`asyncio.to_thread()` 的取消不能中断已卡在 SSL read 的 urllib worker，导致单一 issuer 能阻塞整个 batch。子进程是这条 public-source boundary 的可终止执行单元。
- Evidence：`product/data_core/e4_official_evidence_batch.py` 和 `product/tests/test_e4_official_evidence_batch.py`。测试模拟 first ticker hangs，父批次在 timeout 内 kill 并继续 second ticker；live 2-ticker smoke 在 20 秒 wall-clock cap 内 2/2 capture。

### Gotchas · E4-S4g

- 这不是并行化：父进程 join 一个 child 后才启动下一个，effective concurrency 始终为 1；timeout 是隔离手段，不是提速或绕限流。
- 子进程若在 raw write 前被 terminate，父 receipt 只记录失败；没有 raw hash 的工作绝不能 resume 为 captured 或生成 Report Model。
- 测试 seam 的 in-process custom adapter 仅用于 fixture unit tests；真实运行永远走 default `sync_exchange_filings` 的 spawn path，避免把测试方便性误带到 production behavior。

## 2026-07-24 · E4-S4h 市场与 PIT 财务 companion batch

- Decision：复用 A4 `collect_ashare_packet`，以单 ticker spawn child 收集 quote、qfq daily bars、财务摘要、资产负债表、利润表和现金流量表。只输出每一组件的 real source/raw/manifest/known-at receipt 与 availability，不复制数据到新底座，也不将这些输入自动升级为 Tier 或投资动作。
- Why：E4-S4d 的 primary filing 只能形成 Tier C partial model；市场和财务是后续估值、质量与风险模块的必要 canonical inputs，需先独立审计其真实来源和 PIT 边界。
- Evidence：`product/data_core/e4_market_fundamentals_batch.py`、`scripts/refresh_e4_s4_market_fundamentals.py` 和 `product/tests/test_e4_market_fundamentals_batch.py`。2026-07-24 live 000001.SZ smoke receipt `1d9e58e059676f7f…` 显示 quote、qfq bars、main finance 与三张财务报表皆为 real/publishable。

### Gotchas · E4-S4h

- `collect_ashare_packet` 内部会并行获取六个组件，但 E4 batch 在 ticker 之间保持 spawn/join 串行；这不是跨 ticker 并发采集。
- 原 packet 可能有部分组件成功，故 receipt 分别报告 market/fundamentals availability 与 typed gaps；任何失败都不能被另一组件的 success 掩盖。
- 实时市场和 PIT 财务收据是估值输入，不等价于 accepted evidence corpus、Tier A/B、目标价或仓位；这些升级必须由后续 evidence gate 和 decision policy 完成。

## 2026-07-24 · E4-S4i 官方证据批次逐 ticker checkpoint

- Decision：官方证据批次在每个 ticker 得到 captured 或 failed 终态后，原子写入 runtime-only in-progress checkpoint；latest pointer 明确标记 `in_progress` 或 `completed`。恢复只能复用 identity receipt hash、ticker 数量、限流、分页与 timeout 完全一致的 checkpoint。
- Why：真实 100 ticker 运行在 39 个已捕获 issuer 后中断，原先仅在全量结束时写总 receipt，已完成工作无法可靠恢复。逐 ticker checkpoint 把外部采集的长运行失败隔离为可重放的进度状态。
- Evidence：`product/data_core/e4_official_evidence_batch.py` 与 `product/tests/test_e4_official_evidence_batch.py`。interrupted-run fixture 在第二 ticker 抛出 `KeyboardInterrupt` 后保留首个 captured row；下一次运行只从未完成 ticker 继续，并输出 completed receipt。

### Gotchas · E4-S4i

- checkpoint 是运行进度，不是 canonical evidence：它和最终 receipt 一样不提供 Report Model、Tier A/B 或 numeric/page audit credit，且永远位于 ignored runtime root。
- corpus 或采集策略任一绑定字段不一致即 fail closed；不能为了“继续跑”而静默拼接不同页数、timeout 或 identity universe 的结果。
- 成功完成后 checkpoint 文件会被删除，latest pointer 指向 completed receipt；中断期间 latest pointer 指向 checkpoint，消费者不得将它误读为完整 100-ticker baseline。

## 2026-07-24 · E4-S4f 真实 100 ticker 基线结果

- Decision：发布 100 identity / 40 real Report Model / 0 Tier A/B / 0 numeric+page audit 的失败基线，不修改 #218 的 100/95/80/20 阈值。
- Why：真实运行完成后，40 个官方一手披露可编译为 Tier C partial model；其余输入与覆盖门槛仍缺失。失败收据是下一轮 source/coverage 工作的合同，而不是可以被文字解释绕过的验收。
- Evidence：runtime-only official receipt `115bdd8d6ac1f5c5`、partial-model receipt `b27d7e8c8cc752a1`、acceptance hash `b24009621a40897fc0336b86ef0a4fa55a70967158d1f4626159666c7ab76609`，以及 `docs/evidence/2026-07-24-e4-s4f-100-ticker-baseline.md`。

### Gotchas · E4-S4f

- 40 个 Tier C model 是真实 evidence-bound inputs，不是 95/80/20 gate 的替代；不得因为有模型 hash 就输出 target、position 或 Tier A/B 语言。
- runtime raw path 相对采集 worktree；编译必须从同一运行根目录执行，否则会将存在的 PDFs 错判为 `partial_model_input_invalid`。跨 worktree 的错误编译结果不进入基线证据。

## 2026-07-24 · E4-S4j 市场与 PIT 财务批次 checkpoint

- Decision：复用 E4-S4h 的 A4 companion collector，并为长运行的 100-ticker batch 增加逐 ticker runtime checkpoint、in-progress/completed pointer 与 exact-config/input-hash resume contract。
- Why：市场与 PIT 财务是后续估值/质量模块的必要输入；100 ticker 外部采集不能因进程中断重复请求已完成 issuer，且任何不同 identity 或 official baseline 都不能静默混入同一 receipt。
- Evidence：`product/data_core/e4_market_fundamentals_batch.py` 与 `product/tests/test_e4_market_fundamentals_batch.py`。interrupted-run fixture 在首 ticker checkpoint 后中断，重跑仅处理未完成 ticker；mismatch fixture fail closed。

### Gotchas · E4-S4j

- companion receipt 是 market/fundamentals availability 证明，不是 accepted evidence corpus；即使全部组件 real/publishable，也不会独自提升 Tier、target、position 或 audit credit。
- checkpoint 绑定 official receipt hash，故新的官方 corpus 或配置必须创建新的 runtime root；不得为省时手改 pointer 或拼接两个 corpus。

## 2026-07-24 · E4-S4j 真实 100 ticker market/PIT 基线

- Decision：发布 100 requested / 67 market available / 67 fundamentals available / 33 failed 的 aggregate baseline，保留其 receipt hash 和 input-only boundary。
- Why：这将后续估值与质量模块的输入缺口量化为真实、可重放的 component coverage，不能以“已有市场数据”替代 primary evidence、Tier 或投资动作。
- Evidence：runtime-only receipt `99177f8d263adbcd26c88594c5e575af34e20357813ce807f307938705bb7be6` 与 `docs/evidence/2026-07-24-e4-s4j-market-pit-baseline.md`。

### Gotchas · E4-S4j live baseline

- 市场与财务可用性均为 component-level availability，不能推断同一 ticker 已拥有完整 valuation、sell-side、industry position 或可审计报告。
- runtime receipt 仅在 exact official baseline / identity / config 组合下可复用；后续 source rerun 必须重建 companion input，而不是复制 aggregate count。

## 2026-07-24 · E4-S4l primary 与 market/PIT 模型绑定

- Decision：在既有 E4-S4d partial model contract 内可选绑定 exact official receipt lineage 的 market/PIT companion receipt，组件仅将 market/fundamentals sections 从 missing 标为 available；决策边界保持 Tier C / `no_action`。
- Why：模型需要同时显示一手披露与真实市场/PIT 输入的可用性，但 valuation、sell-side、industry position 与 audit 仍缺失，不能把输入扩展误译为行动升级。
- Evidence：`product/data_core/e4_partial_report_models.py`、`product/tests/test_e4_partial_report_models.py`。不同 official lineage 的 companion fixture fail closed。

### Gotchas · E4-S4l

- companion receipt 的 official hash 必须严格等于编译输入的 official receipt bytes hash；相同 ticker 但不同批次也不能混拼。
- 没有 companion、或 companion 的该 ticker 不可用时，仍编译真实 primary partial model，但 market/fundamentals 保持 `missing_evidence`。

## 2026-07-24 · E4-S4m 真实双输入回放证据

- Decision：发布 E4-S4l 的双输入 replay aggregate：100 requested 中 40 个 real primary partial Report Model、60 个 typed block；40 个中 27 个同时绑定 real market 与 PIT fundamentals component。保持所有输出 Tier C / `no_action`。
- Why：单独的 primary 与 companion baseline 不能证明两者在同一 official-receipt lineage 下可组合。该回放使后续估值/质量工作可从可复验的、非夸大的 component coverage 出发。
- Evidence：`docs/evidence/2026-07-24-e4-s4m-dual-input-replay.md`，其记录 official receipt bytes SHA-256 `60f5dc8a…` 和 companion receipt bytes SHA-256 `52f34bca…`，并给出必须从 official runtime owning worktree 执行的 replay command。

### Gotchas · E4-S4m

- 27 只代表同一 partial model 上 market/PIT 两个组件均 available；它不是 27 份完整研报，也不减少 valuation、sell-side、industry position 或人工数字/页级抽检的缺口。
- official receipt 内 raw PDF 路径相对其采集 worktree；从其他目录 replay 会把真实 PDF 错判缺失。绝不通过复制 runtime payload 到 git 来规避该路径约束。

## 2026-07-24 · N3-S1 公司到产业位置索引

- Decision：将 E3-S3 的 `REVIEW_TARGETS` 投影为唯一的 company↔segment 查询索引；默认查询只返回带官方页级引用的 accepted 位置，review 查询才可显式读取 `needs_evidence` 记录。
- Why：产业世界模型需要从公司到产业环节、也从产业环节到公司的稳定查询，但不能复制一套位置数据或把待验证假设包装成产业事实。
- Evidence：`product/data_core/industry_company_index.py` 复用 `company_positions.position_coverage` 和 E3-S1 ontology；`scripts/verify_n3_s1_industry_company_index.py` 发出 50 total / 30 accepted / 20 needs-evidence 的确定性 receipt。

### Gotchas · N3-S1

- 20 条 needs-evidence 记录是工作队列，不是事实查询结果；只有调用者明确要求 review access 才会看见它们。
- 该索引只投影 E3-S3，不能自行填补 role、客户、收入暴露或产业关系；这些仍需独立证据与后续 N3 票据。

## 2026-07-24 · N3-S2 AI 算力产业关系基线

- Decision：复用 E3-S2 的 first-party capture 与 evidence-bound graph，发布 12 nodes / 108 segments / 30 accepted edges 的真实 replay aggregate，而不新建关系推理或第二张产业图。
- Why：N3 需要可重放的产业链结构，但结构关系与公司竞争结论不同；先固定每条 edge 的 raw evidence identity 才能在后续公司档案中安全引用。
- Evidence：`docs/evidence/2026-07-24-n3-s2-ai-compute-relationship-baseline.md` 记录 2026-07-24T15:04:00.777739Z 的 ASML/NVIDIA 三个 first-party captures 和 sha256；`scripts/verify_e3_s2_industry_graph.py` 重放 graph receipt。

### Gotchas · N3-S2

- segment edge 不能推导“某公司是龙头”“某公司直接受益”或任何投资结论；company claim 必须另有 N3-S1/E3-S3 的页级公司证据。
- raw 内容留在 runtime；以后 source capture 失败时，不得拿旧 hash 假装 fresh replay，必须显式记录 source gap。

## 2026-07-24 · N3-S3 AI 算力催化剂基线

- Decision：复用 E3-S4 的 108 profile contract 发布真实 coverage：24 个 profile 有一条 first-party `current_state` fact，84 个 profile 保持全量 missing-evidence，所有其他 section 均不从关系图自动填充。
- Why：催化剂对象必须先区分“已知当前状态”与“仍未知的驱动、触发、指标、证伪和时限”，否则看似完整的产业图会把结构关系误包装成可交易判断。
- Evidence：`docs/evidence/2026-07-24-n3-s3-ai-compute-catalyst-baseline.md` 与 `scripts/verify_e3_s4_catalysts.py`；replay 使用 ASML/NVIDIA 的 3 个 first-party raw captures。

### Gotchas · N3-S3

- profile `available` 只表示至少一个 fact section，不表示有可投资 catalyst；下游报告必须逐 section 检查 evidence state。
- 任何 source failure 或 stale/future evidence 都必须留出 missing-evidence，不能借用上次抓取或生成性文本补齐。

## 2026-07-24 · N3-S4 三家公司研究闭环基线

- Decision：发布 E4-S1 的三家公司 vertical slice receipt，复用同一 Context Pack、dossier、offline report 和 decision policy 契约；三家公司全部保持 partial-evidence-bound 与 `no_action`。
- Why：R2 需要验证“产业—公司—证据—档案—决策”能走通，但可运行闭环不能被误说成已具备估值、卖方、市场和催化剂输入的完整研报。
- Evidence：`docs/evidence/2026-07-24-n3-s4-three-company-dossier-baseline.md` 与 `scripts/verify_e4_s1_vertical_slices.py`，记录 300750.SZ、600519.SH、600036.SH 的 filing page/raw identity、Context Pack、dossier 和 report receipt。

### Gotchas · N3-S4

- 三家公司使用的是 historic evidence-bound anchor；它不能替代 fresh ticker collection 或 R3 的 100 ticker acceptance。
- `no_action` 是 evidence gate 的正确输出，不是投资观点；后续必须接入真实 market、valuation、sell-side、quality/risk/liquidity 和 catalyst 证据才能谈升级。

## 2026-07-24 · N3-S5 二十家公司档案批次

- Decision：将 E3-S3 的 20 个排序稳定、accepted/page-cited 公司位置逐份重新拉取其 CNINFO 官方 PDF，只有 raw SHA-256 精确匹配才进入既有 Context Pack → dossier → offline report → decision pipeline；失败留下 typed row。
- Why：R2 的档案放量必须证明二十个公司真实输入可复验，不能从历史位置表直接“相信”引用仍有效，更不能用 fixture 或生成文本补齐失败。
- Evidence：`product/data_core/n3_dossier_batch.py`、`scripts/refresh_n3_s5_dossiers.py` 与 `product/tests/test_n3_dossier_batch.py`。runtime receipt 记录 selection identity、每行 citation/context/dossier/report/decision 和 counts。

### Gotchas · N3-S5

- 默认位置选择与引用集合的 hash 是 batch input identity；更换任意 ticker、URL、page 或 raw hash 都是新批次，不能把旧 receipt 当作可续跑结果。
- 即使二十份 dossier 都编译成功，输入仍只有 filing；固定缺口使 decision 保持 `no_action`，不产生 Tier、target 或 position credit。

## 2026-07-24 · N3-S5 真实 20 家批次失败基线

- Decision：发布 real batch 的 19/20 failed-acceptance receipt，不把 19 说成 20；`601138.SH` 的 CNINFO PDF 在重试后仍为 `TimeoutError`，保留 typed failure，后续单独恢复。
- Why：N3-S5 的放量阈值本身是 R2 合同的一部分。单一来源传输失败只能缩小覆盖，不允许以旧 hash、替代源或 PR 文字解释绕过。
- Evidence：`docs/evidence/2026-07-24-n3-s5-20-company-dossier-baseline.md`，runtime receipt sha256 `0bedbe4c…`，selection identity `39786334…`，counts 20 requested / 19 compiled / 1 failed / 19 no_action。

### Gotchas · N3-S5 live baseline

- checkpoint resume 只能复用 exact selection identity 下已成功且 citation raw hash 一致的 row；所有 failed row 都会重新请求，避免把短暂网络失败永久冻结为结论。
- 19 个成功 dossier 依旧只含 filing input；统一 `no_action` 是正确边界，绝不将其描述为 full report、Tier A/B、target 或 position 进展。

## 2026-07-24 · N3-S5a 工业富联官方输入恢复

- Decision：只使用原 CNINFO URL/page/raw hash 重试 `601138.SH`，成功后以 exact selection identity 恢复原 batch；最终达到 20 requested / 20 compiled / 0 failed / 20 no-action。
- Why：此前失败是传输超时而非证据缺失；恢复必须重新验证同一 PDF hash，不能替换来源或把旧结果直接升级为成功。
- Evidence：`docs/evidence/2026-07-24-n3-s5a-601138-recovery.md` 与 runtime receipt `10dd875e…`；PDF hash 为 `42d4d1f5…`，与冻结 E3-S3 citation 一致。

### Gotchas · N3-S5a

- resume 只复用 receipt selection identity 完全相同的 compiled row；失败 row 始终重新请求。一次成功不能变成未来 refresh 的永久缓存结论。
- 20/20 仅满足 R2 的 filing-backed dossier coverage 数量条件；所有决策仍为 `no_action`，并不接近 R3 的 valuation/sell-side/Tier A/B 门槛。

## 2026-07-24 · N3-S6 R2 产业世界模型验收

- Decision：建立 fail-closed R2 audit，将 ontology、company position/index、industry graph、20-company receipt、五问覆盖与 archive isolation 作为独立 gates；所有 gate 同时通过才允许 R2 `passed`。
- Why：节点数、公司数和 dossier 数量不能证明产业研究闭环已可用。五问中的 moat、财务兑现、市场未来和 falsifier 必须有各自公司级 evidence，不能从产业结构或 filing existence 推断。
- Evidence：`product/data_core/r2_acceptance.py`、`scripts/verify_r2_ai_compute_world_model.py` 与 `product/tests/test_r2_acceptance.py`。

### Gotchas · N3-S6

- 当前 R2 预期为 `partial`：它会如实显示仅 layer 有 20 个 accepted positions，其他四问的 coverage 不会因数量门通过而变成事实。
- archive isolation 是生产代码与输出契约的非依赖检查；它不是读取或复用 archive 内容的授权。

## 2026-07-24 · N3-S7 PIT 财务兑现输入

- Decision：复用 A4 isolated market/fundamentals collector，在 N3-S5 exact 20-company selection 上生成含 report period、announced_at 和 source/raw/manifest/known-at identity 的 financial-delivery receipt，并使 R2 audit 只对这些 accepted rows 增加 coverage。
- Why：财务兑现不能由年报存在、产业位置或估值模板推断；必须有明确 period 和 PIT source identity，且与同一公司 selection 对齐。
- Evidence：`product/data_core/n3_financial_delivery.py`、`scripts/refresh_n3_financial_delivery.py` 和 R2 audit optional receipt bridge。

### Gotchas · N3-S7

- 仅 fundamental source receipts 全部 real/publishable 且有 latest report period 的 row 才计入 financial_delivery；任何一项缺失均是 gap。
- financial delivery 是 input-only，不是 valuation、Tier、target 或 position evidence；即使 20/20 可用，R2 的其他三问仍单独受 gate 控制。

## 2026-07-24 · N3-S7 真实 PIT 财务失败基线

- Decision：发布 11/20 financial-delivery receipt 并保留 9 个 `packet_validation_failed` / `missing_latest_financial_period` gaps；R2 audit 仅从 0/20 提升至 11/20，不修改门槛。
- Why：真实 provider packet 缺少 latest period 时，年报引用、旧缓存或其他字段不能替代 PIT financial-delivery evidence。
- Evidence：`docs/evidence/2026-07-24-n3-s7-financial-delivery-baseline.md` 与 runtime receipt `4dd8be33…`；九个 ticker 的 failures 均可逐行回看。

### Gotchas · N3-S7 live baseline

- A4 的 packet validation 会将缺 latest fundamental period 的行拒绝，即使部分 raw sources 已到达；部分成功不可被改写为完整 financial delivery。
- 11 个 PIT inputs 只解决五问的一项且仍无 valuation/recommendation credit；后续恢复应在同一 source contract 下重跑并重新审计。

## 2026-07-24 · N3-S7a PIT 财务交付恢复

- Decision：Eastmoney 预约披露行仅保留在 raw capture 中，不在其 `NOTICE_DATE` 晚于 capture `known_at` 时进入 PIT records；N3 financial-delivery 同时从共享 market packet 中拆出，只验证四个已声明财务来源，并对瞬时失败做至多三次相同来源的 isolated re-pull。
- Why：未来预约披露不是当时已知事实；反之，日 K 线传输失败也不是财务来源缺失。两种情况都不能通过改写日期、复用陈旧结果或切换未声明 provider 来“修复”20-company gate。
- Evidence：`docs/evidence/2026-07-24-n3-s7a-pit-financial-recovery.md`，runtime receipt `e3cd6e06…`，selection identity `39786334…`，真实结果 20 requested / 20 available / 0 gaps；R2 audit 将 financial delivery 提升为 20/20。

### Gotchas · N3-S7a

- retry 只会重新拉取同一个 ticker 的同一 A4 adapters；final row 仍必须拥有新抓取的 raw/manifest/known-at identity，旧 receipt 或 cache 不可作为成功结果。
- 财务输入 20/20 不会让 R2 pass：moat、market-future、falsifier 仍为 0/20，继续禁止 Tier、target、position 或 action 输出。

## 2026-07-25 · N3-S8 公司证伪条件证据

- Decision：对 N3 既有 20-company selection 逐份重拉同一 CNINFO 官方年报，接受一条同时具备可观察弱化条件、官方 URL、PDF raw hash、页码和 known-at 的 issuer-disclosed risk；R2 falsifier 只读取这份 receipt。
- Why：产业 profile 的 generic risk 不能替代公司级证伪条件；风险标题或模型总结不足以证明“什么情况会削弱判断”。
- Evidence：`docs/evidence/2026-07-25-n3-s8-company-falsifier-evidence.md`，runtime receipt `0ef0c3c1…`，selection identity `39786334…`，20 requested / 20 accepted / 0 gaps；R2 falsifier 为 20/20。

### Gotchas · N3-S8

- CNINFO 大 PDF 需使用相同官方 URL 的 Range read 才能在连接中断后完成；assembled bytes 必须命中既有 citation SHA-256，不能以 partial response 或 mirror 补齐。
- 证伪条件只解决 R2 五问之一；它不构成 moat、市场预期、估值、Tier、target、position 或 action 证据。

## 2026-07-25 · N3-S9 公司护城河证据

- Decision：对相同的 N3 20-company selection 逐份重拉同一 CNINFO 官方年报，仅接受同时具备 issuer-described advantage、具体能力锚点、官方 URL、PDF raw hash、页码及 known-at 的 capability observation；R2 moat 只读取该 receipt。
- Why：产业层或 AI 归纳出的“护城河”不能代替公司级一手证据。泛化的领先口号不具备可审计的竞争能力含义。
- Evidence：`docs/evidence/2026-07-25-n3-s9-company-moat-evidence.md`，runtime receipt `3e3be84f…`（SHA-256 `6eef6ee0…`），selection identity `39786334…`，20 requested / 20 accepted / 0 gaps；R2 moat 为 20/20。

### Gotchas · N3-S9

- issuer 的能力披露只能证明其自述的可观察能力，不能自动推出持久竞争优势、估值、Tier、target、position 或 action。
- R2 仍因 market-future 0/20 而 partial；不得因四问通过而绕过最后一问。

## 2026-07-25 · N3-S10 公司市场未来证据

- Decision：对原 N3 20-company selection 逐份重拉同一 CNINFO 官方年报，仅接受同时包含前瞻标记和市场/行业/需求等市场上下文的 native-text passage，并以 source URL、full raw hash、页码、known-at、observation type 绑定；R2 market-future 只读取该 receipt。
- Why：公司愿景、模型预测或爱牛归档不能替代可审计的公司级前瞻市场证据；同时，不应把 issuer outlook 伪装成 sell-side consensus。
- Evidence：`docs/evidence/2026-07-25-n3-s10-company-market-future-evidence.md`，runtime receipt `1dd226f9…`（SHA-256 `235d7e2a…`），selection identity `39786334…`，20 requested / 20 accepted / 0 gaps；R2 全五问 20/20 且 `passed`。

### Gotchas · N3-S10

- issuer-disclosed market outlook 是事实性观察，不是市场共识、预测、估值、Tier、target、position 或 action。
- R2 `passed` 只代表本阶段 evidence gate 完成；20 份 dossier 仍是 `no_action`，下一阶段不得用它跳过 valuation、sell-side 或发布门。

## 2026-07-25 · E4-S4k 官方披露失败分类

- Decision：E4 official-evidence receipt 在官方 discovery 不可发布时，按现有 attempt 证据区分 TLS/SSL transport timeout、明确 access denial、官方索引空结果与无法分类的失败；只在证据足够时分类，否则保留 generic failure。
- Why：SH 握手超时、BSE 官方页面的明确拒绝访问与 CNINFO 对 BJ 的空索引是不同的可恢复性和 source-coverage 状态。把它们都写成“无披露”会污染覆盖率判断。
- Evidence：Issue #274 的 2026-07-25 bounded probes；`product/tests/test_e4_official_evidence_batch.py` 覆盖四种 receipt taxonomy。

### Gotchas · E4-S4k

- 分类只解释 failed source attempt，不能提供 primary evidence、Report Model、Tier、numeric/page audit、target、position 或 action credit。
- access denial 不是授权绕过、代理或 aggregator fallback 的理由；后续 source adapter 必须仍是已登记的官方来源。

## 2026-07-25 · E4-S4k SSE 同源 TLS transport fallback

- Decision：仅当 Python urllib 对 `query.sse.com.cn` 的官方 SSE index 出现 TLS/SSL handshake failure 时，使用系统 curl 对**完全相同的官方 URL、headers 与 HTTPS host allowlist**进行一次有界 transport fallback；curl 失败或跳出 host 仍失败。
- Why：同一 URL 在本运行环境中 curl 可成功返回 SSE 官方 index，而 urllib 会在 TLS handshake 超时。保持同源和 raw capture 能恢复 discovery，不需要 aggregator 或跨交易所 fallback。
- Evidence：2026-07-25 live probe `600519.SH`：SSE index 以 `sse_official_filing_index_v1` 成功捕获 30 条官方 discovery（raw hash `f57a8b8c…`）；focused adapter tests 覆盖 final-header parsing。

### Gotchas · E4-S4k SSE fallback

- fallback 只修复 discovery transport，不保证 PDF document capture，也不产生 Report Model、Tier、target、position 或 action credit。
- curl 是运行环境依赖；缺失、失败或 redirect 超出 `query.sse.com.cn` 时必须 fail closed，不能替换为其他下载器或非官方 URL。

## 2026-07-28 · E4-S4 page-bound numeric facts before any human audit

- Decision：停止用行情报价生成 E4 审计候选；只从官方 PDF 解析出的页级数值事实生成候选。每条候选把数值、同一文件的 document_id/raw hash/页码、原文锚点、报告期、合并口径、单位和币种绑在一起。
- Why：最新行情价格不会出现在年报 PDF，原有“行情价 + 任意 filing 页”在物理上不可审。先产出三个可翻页验证的 filing facts，才有值得审的对象。
- Evidence：B3 `parse_pdf_document` 对宁德时代、贵州茅台和招商银行三份官方 2024 年报均抽取成功；runtime receipt 保留成功或 missing，而不以聚合器数据补位。

### Gotchas · E4-S4 page facts

- 页级事实是一个窄 Report Model projection，仍固定 Tier C/no_action；它不完成 #218，也不产生 Tier、目标价、仓位或人工审计 credit。
- 下载或页内锚点失败必须保留为 missing；禁止改用东财/F10 等结构化聚合器伪装为页级原始事实。

## 2026-07-28 · E4-S4 20-ticker page-fact batch

- Decision：页级事实放量时只扫描已捕获官方 PDF 的合并利润表（或合并及银行/公司利润表）页面；自动抽取仅限营业收入和已明确标注的归母净利润，要求页面同时提供单位与币种。
- Why：营业成本等字段在附注、分部表和会计政策中会出现同名词，宽松匹配会产生错误数值。宁可少抽，也不能将相邻或相似科目当作报表行。
- Evidence：20 个既有池 ticker 的官方捕获在 SH/SZ/BJ 三个市场均产生至少一条符合完整身份字段的事实；批处理保留每个 ticker 的 missing 原因。

### Gotchas · E4-S4 20-ticker facts

- 本批不接入 Report Model、审计工作台或任何结论层；它只是可供后续人工核验的 primary evidence。
- 北交所 discovery 必须传 `category_ndbg_szsh` 取正式年度报告；否则最新“业绩说明会预告”会被误当作 financial report。

## 2026-07-28 · E4 three-slice B6/C1 degradation bridge

- Decision：宁德时代、贵州茅台、平安银行的真实官方页级事实先进入 B6 证据集，再以完全相同的 manifest hash 创建 live C1 合同，最后只调用既有 `assess_any_ticker` 判定 Tier。
- Why：页级事实若停在 E4 partial side path，永远只能是 C；B 的正确含义是“证据门和合同已通，但章节仍不完整”，而不是伪造完整分析。
- Evidence：三家 B6 receipt 均为 `passed`，filings 覆盖均为 primary 1/1；C1 合同均 live_eligible，章节为 1 full、1 partial、16 missing；原策略输出均为 B，理由仅为 `partial_or_missing_sections` 与 action-field block。

### Gotchas · E4 B6/C1 bridge

- 这条桥不能替代 B6 policy、freshness 或 conflict gate；任一真实官方文件被门禁拒绝时必须保持 C，而不是调低要求。
- FULL 仅用于 evidence_and_methodology（有 evidence receipt、citation index 和方法）；财务章节因只有收入等事实、缺利润桥而是 PARTIAL，其余章节必须 MISSING。

## 2026-07-28 · R2 world-model gate uses receipt-bound evidence, not count-only narratives

- **Decision：** Record the current R2 pass only through the five receipt hashes and the existing fail-closed verifier; preserve the previous partial audit as historical evidence.
- **Why：** The N3 structural counts were already present when R2 was partial. The pass became valid only after each of the five company questions had 20/20 receipt-bound coverage.
- **Evidence：** `scripts/verify_r2_ai_compute_world_model.py` returned `status=passed` with 12 nodes, 108 segments, 30 accepted positions, 20 compiled dossiers and all five question dimensions at 20/20; see `docs/evidence/2026-07-28-r2-current-acceptance.md`.
- **Gotchas：** Runtime receipt paths are reproducibility coordinates, not committed product facts. R2 does not promote the dossiers beyond `no_action`, and cannot substitute for R3's 100/95/80/20 acceptance or an independent numeric/page audit.

## 2026-07-28 · Retire benchmark-derived industry snapshot from product serving

- **Decision：** Remove `product/data/industry-intelligence-v1.json` and make its API fail explicitly until canonical E1--E3 evidence-backed industry data is published.
- **Why：** The artifact was deterministically built from the archived benchmark payload and carried scores, ratings, dossiers and derived judgments. A truthful label was insufficient because the product API still served it as research content.
- **Evidence：** `scripts/build_industry_intelligence.py` identified `http://ainiusq.com/niu/` as its source; the retired payload had 489 dossier, 649 score and 1,138 rating/score fields.
- **Gotchas：** Do not replace this with an empty but implicit success response, a fixture fallback, or copied archive content. The existing frontend must be updated only by Claude Code when canonical data is ready; backend 410 is intentionally fail-closed in the meantime.

## 2026-07-27 · Official filing transport resilience

- Decision：以单一可复用 HTTP session 的有限指数退避策略替换 SSE 专用 curl fallback；SH、SZ、BJ 均使用 CNINFO 这个统一官方披露平台，SSE adapter 保留为显式组件而非 SH 采集的单点依赖。
- Why：实测 CNINFO 官方 PDF 只是间歇性连接中断，不是源端封锁；把失败行当成终态并只依赖 SSE 会把可恢复的官方 primary evidence 错判为不可用。
- Evidence：100 ticker 重跑将 captured official-primary / evidence-bound partial Report Model 从 40 提升到 80；剩余 20 条 BJ 返回 HTTP 200 且索引为空，没有 TLS、429 或 5xx retry exhaust。

### Gotchas · Official filing transport resilience

- completed receipt 重跑时必须保留原先 captured row 的 raw identity；把它降为 `skipped` 会让 partial-model compiler 遗失旧证据，造成计数表面不变。
- HTTP 200 空索引不是传输重试的适用对象；不能把它伪装成 TLS/WAF 失败或用聚合器补成 primary evidence。

## 2026-07-27 · CNINFO structured issuer discovery

- Decision：CNINFO filing discovery 先经 `topSearch/query` 对证券代码做唯一精确匹配并取得 `orgId`，再以 `hisAnnouncement/query`、交易所 column 和本地 document-type 过滤获取公告；不再用裸代码全文搜索判断披露可得性。
- Why：全文搜索对北交所裸代码返回空，但官方结构化查询可返回同一 issuer 的公告及 PDF。100 ticker rerun 将 official-primary / partial Report Model 从 80 提升为 100。
- Evidence：人工 session 请求 `835185 → gfbj0835185` 后，`hisAnnouncement/query` 返回 HTTP 200、`totalAnnouncement=615`；runtime receipt `official-evidence-batch-a999bb485985c945.json` 为 100 captured / 0 failed。

### Gotchas · CNINFO structured issuer discovery

- topSearch 的实际响应可以是顶层 list；必须支持它，但仍只允许一个 exact code match 和非空 orgId，绝不按第一个模糊结果猜测。
- HTTP 200 空列表只说明该一次查询的参数或语义需要核实，不是“源端没有数据”的证据。任何不可得结论必须先保留人工原始请求与完整响应。

## 2026-07-27 · CNINFO 北交所代码迁移 identity

- Decision：当 CNINFO history 的 `secCode` 与请求旧代码不同，保留旧代码为 alias，并将当前代码、orgId、观察时间和 top-search raw hash 写为官方迁移事实；文档和 E4 partial-model identity 使用当前代码。该事实直接喂入 E1-S1 `UniverseCrosswalk.apply_code_migrations`，不建立第二张映射表。
- Why：北交所历史代码可在同一稳定 orgId 下迁移到 `92xxxx`。若仍以旧 ticker 登记当前披露，会把 issuer identity 绑到失效代码。
- Evidence：人工 CNINFO 请求显示 `835185 → 920185`，`orgId=gfbj0835185`；100 ticker pool 内 20 个 BJ 当前 ticker 的 structured check 为 0 个 code mismatch / 0 个 delisted。`832317` 则返回同码 25 条终止北交所上市与跨市场转登记公告，属于转板退出而非 92xxxx 迁移。

### Gotchas · CNINFO 北交所代码迁移 identity

- `delisted=true` 是必须保留的官方状态信号，但不能单独推断迁移；只有 history `secCode` 变化才形成 code migration fact。
- checkpoint resume 必须按 `requested_ticker` 定位旧任务；否则已迁移 row 的 current ticker 会在后续重跑中被误认为未采集。

## 2026-07-25 · E5-S5b private-preview spot-audit route allowlist

- Decision：将 owner-only spot-audit assignment read 与 review export 纳入 private-preview 的显式 GET allowlist；review POST 沿用既有 owner entitlement、CSRF 与 append-only store，不新增成员权限。
- Why：审阅工作台必须能在私测产品实际运行时读取任务。仅在普通模式可用会让前端呈现无效表单；扩大到 dashboard/member 又会泄露审阅身份和证据元数据。
- Evidence：`test_private_preview_v1.py` 覆盖匿名 401、成员 403、Owner 读取任务和 Owner 成功写入 append-only review；全 private-preview suite 通过。

### Gotchas · E5-S5b

- allowlist 只开放准确的 assignment path 和 review export；私测模式依旧对未列 API 返回 `private_preview_route_unavailable`。
- Owner 成功写入的是显式人工决定，并不改变 E4 acceptance、Tier、target、position 或 action；表单加载或 assignment 可读都不能被称为审计完成。

## 2026-07-25 · E5-S5a spot-audit assignment read API

- Decision：review workstation 通过 owner-only API 读取单条经 receipt identity 验证的 assignment projection；只返回 ticker、数值目标、document identity、页码要求和审阅状态，不返回 raw path 或 PDF bytes。
- Why：前端审阅界面需要一条稳定的安全数据合同，不能自行解析 runtime 文件或把技术路径暴露给用户。
- Evidence：`test_spot_audit_assignment_reader.py` 覆盖安全投影、缺失 ticker 与 receipt 篡改拒绝；private-beta HTTP 与全量 suite 通过。

### Gotchas · E5-S5a

- 可读 assignment 仍是 pending human review，不等于可提交结论；API 不产生任何 E4 acceptance、Tier、target、position 或 action credit。

## 2026-07-25 · E4-S4ai explicit valuation assumptions

- Decision：估值假设必须由具名作者显式提交，绑定研究截止日、理由、来源身份与完整 bear/base/bull 参数；缺任何输入即拒绝，不存在默认参数。
- Why：C2 能复算但不能替代分析判断；将假设与事实来源分开，才能让未来估值输入可审计且不伪装为 provider fact。
- Evidence：`test_e4_valuation_assumptions.py` 覆盖确定性与缺少情景拒绝；全量产品测试通过。

### Gotchas · E4-S4ai

- 收据只记录 analyst judgment，不构成 Tier、target、position 或 action；实际 authoring 与独立审阅仍未发生。

## 2026-07-25 · E4-S4ah human spot-audit decision store

- Decision：审计结论只能由 active owner 通过追加不可改的记录写入；每条记录绑定 assignment receipt 的 SHA-256、ticker、model/document/raw identity、reviewer、时间、数字/页码结果、页码、引用标签与理由，并可确定性导出。
- Why：E4-S4ag 冻结了待审对象，但没有可信的审阅结论存储就无法证明谁核过哪一条来源；append-only 使重新审阅成为新记录而非覆盖历史。
- Evidence：`test_spot_audit_store.py` 覆盖 owner append/export、member 拒绝和 duplicate 拒绝；private-beta HTTP suite 保持通过。

### Gotchas · E4-S4ah

- 这只是记录人类审阅的系统，不会由 agent、fixture 或空记录生成 `pass`；没有独立人类核验时 #218 spot audit 仍为 0。
- exported decision 不会改写 partial model 或 E4 acceptance flags，也不产生 Tier A/B、target、position 或 action。

## 2026-07-25 · E4-S4ag pending human spot-audit assignments

- Decision：从同一张已验 hash 的 real Tier-C partial-model receipt 中确定性选择 20 个同时具备 official document identity、完整 market/fundamentals source components 与数值事实的 ticker，生成 runtime-only assignment receipt 和 reviewer guide；所有 assignment 都是 `pending_human_review`。
- Why：#218 需要 20 个独立、数字与页码级别的检查，但自动检查无法替代具名的人类审阅。先冻结可审对象和身份，避免审阅时换 ticker、换模型或用未绑定的 PDF。
- Evidence：`test_e4_spot_audit_assignments.py` 覆盖确定性选择、少于 20 个/篡改输入拒绝、无 raw path 和 guide 输出。真实 receipt `d1822a2cd6e51232ba01382b3bb6c6b22a9d9af64a656b467fb452c65edd6443` 已生成 20/20 pending assignments。

### Gotchas · E4-S4ag

- assignment 不等于 audit result：它明确产生 completed=0，也不修改 E4 acceptance 的 `numeric_spot_audit` 或 `page_citation_spot_audit` 标志。
- guide 仅包含 document/hash identity 和待核数值，不含 runtime raw path 或 PDF bytes；实际 reviewer record 必须独立记录 reviewer、时间、page、quoted label、pass/fail 和理由。

## 2026-07-25 · E4-S4af partial-model product read API

- Decision：新增只读、会员权限受控的 `/api/research/partial-model/{ticker}`，只从配置 runtime root 内的 content-addressed latest pointer 读取，并重验 pointer、receipt hash、schema、ticker 与 Tier-C decision boundary；对合法但未编译的 ticker 返回明确 `unavailable`，不回退或猜测数据。
- Why：现有部分模型已有真实的市场/财务输入和证据身份，但只存在 runtime receipt。产品需要安全读取面，不能把文件路径、未验证 receipt 或不完整模型直接暴露给调用方。
- Evidence：`test_partial_model_store.py` 覆盖安全投影、blocked row、receipt 篡改与 pointer escape；`test_private_beta_http.py` 覆盖付费成员访问、preview 拒绝与真实模型缺失时的明确响应。实际 runtime receipt `partial-report-models-cb023224c7b23f82.json` 已返回 `000001.SZ` 的 source-bound facts，且 `600519.SH` 返回 unavailable。

### Gotchas · E4-S4af

- endpoint 不是 full report API：所有可用返回仍为 Tier C / `no_action`，target price 与 position range 必为 null；它不能成为付费推荐或 action 的后门。
- runtime root 是部署配置，不进入版本库；pointer 只能选择 root 下的普通文件，hash 不匹配、schema drift、symlink 或 ticker identity drift 一律冲突失败，不能悄悄读旧 receipt。

## 2026-07-25 · E4-S4ad source-bound display facts

- Decision：E4 market/fundamentals runtime receipt 只投影 A4 已验证 packet 中白名单行情、最新复权日线和最新已披露财务字段；partial model 仅在每个引用 component 都保有 raw hash、manifest hash 与 known-at 时携带该 projection。
- Why：原收据只保存 availability 与 identity，导致产品无法展示真实数值。直接复制已验证的 packet 值并保留各 component identity，既能支持摘要输入，又不将数据可用性错误提升为估值、审计或建议。
- Evidence：`test_e4_market_fundamentals_batch.py` 与 `test_e4_partial_report_models.py` 覆盖白名单、缺值拒绝、来源身份与 legacy availability-only receipt；真实 `000001.SZ` bounded runtime receipt `market-fundamentals-batch-1efd59226b58e28a.json` 同时写入 market/fundamentals display facts。

### Gotchas · E4-S4ad

- display facts 是 runtime-only input projection；没有新产生 raw capture、估值 assumption、numeric/page spot audit 或 Tier A/B credit。
- 旧 receipt 没有 display facts 时必须保持 availability-only，不能重新请求当前行情去填历史研究模型；某一次 provider packet 不完整时，整块 display facts 为空并写 blocker。

## 2026-07-25 · E4-S4ae component failure receipts and retries

- Decision：E4 packet batch 将每个 required source 的 non-real/non-publishable 状态和已有 data-gap reason 写成 `component_blockers`；仅对相同 collector、相同注册 source plan 最多尝试两次，记录每次 blocker history。
- Why：原先任一 component 失效会被压缩为 `packet_validation_failed`，无法区分真实 source gap 与短暂 transport failure，也无法诚实指导后续补采。
- Evidence：`test_e4_market_fundamentals_batch.py` 覆盖 component-level non-real/timeout taxonomy、无 display facts 和 bounded same-plan retry history。

### Gotchas · E4-S4ae

- retry 不得替换 source key、调用另一个 provider、读取 cache 或填入推断值；最终成功的 raw/source identity 是本次成功 attempt 的 identity，先前失败只保留 typed gap。
- 同一个 completed receipt 不能因重试策略变化被续跑；`max_component_attempts` 进入 config identity，配置变化必须另开 runtime lineage。

## 2026-07-25 · E4-S4k official document failure taxonomy

- Decision：E4 official-filing batch now classifies failed document captures as access denial, TLS failure, timeout, non-PDF response, or generic capture failure without retaining response body text in the receipt.
- Why：SH discovery may succeed while the same official static-document endpoint returns a bot-denial HTML page. Treating that as a generic failure hides the boundary and encourages unsafe fallback; a typed receipt makes source work auditable.
- Evidence：focused official evidence tests cover content/transport taxonomy. A live `600000.SH` probe is classified `official_filing_document_not_pdf`; live `920002.BJ` remains `official_filing_index_empty` from the registered CNINFO official index.

### Gotchas · E4-S4k document taxonomy

- A 200 response is not a successful official document capture unless it is validated PDF bytes; HTML challenge/denial pages cannot be treated as evidence.
- Classification is observability only. It does not bypass an official source, substitute a mirror, or increase report/Tier/audit/target/position/action coverage.

## 2026-07-25 · E4-S4ab persisted sell-side reviewer decisions

- Decision：复用现有独立 auth DB 与 owner entitlement，以 append-only store 保存 sell-side candidate 的单次人工接纳/拒绝；导出严格复用 E4-S4aa decision receipt schema，再由既有 admission compiler 验证。
- Why：候选必须经真实人工判断，不能让产品流程依赖手工编辑 JSON，也不能允许 member 或匿名访问伪造 reviewer 决策。
- Evidence：`test_claim_review_store.py` 验证 owner 接纳→schema export→admission compile、重复拒绝和 member 拒绝；`test_private_preview_v1.py` 回归私有预览 auth 流程。

### Gotchas · E4-S4ab

- server 仅从受控 runtime root 的 content-addressed latest pointer 读取 candidate receipt；客户端不能指定任意路径或传入伪造 candidate identity。
- 接纳的内容仍是已签名的 broker assertion，不是 verified company fact；它不自动增加 Tier、numeric/page audit、target、position 或 action。

## 2026-07-25 · E4-S4ac companion-bound partial report models

- Decision：复用既有 partial-model compiler 的 companion contract，将 exact-lineage 的 market/fundamentals runtime receipt 接入 writer/CLI；同时兼容早期 caller-relative raw path，但只能在 supplied runtime root 的 `raw/<hash>.pdf` 内按 basename 重定位并重验 SHA-256。
- Why：市场与财务数据已经存在，却因 writer/CLI 未传 companion 而未进入实际 report model。恢复这条已定义的数据链比再造报告框架更直接提升真实可交付内容。
- Evidence：focused tests 覆盖 matching lineage、mismatch fail-closed 与 legacy runtime path replay。真实 runtime replay 编译 40 个 partial models，其中 27 个 market 和 fundamentals sections available；60 个未捕获官方 PDF 保持 blocked。

### Gotchas · E4-S4ac

- relative-path compatibility 不是放宽路径边界：候选文件仍必须在 supplied root，且 raw bytes/hash/PDF identity 全部复验。
- `available` 只表示该 model 的 input section 可用；没有 valuation、industry position、accepted sell-side claims 或 audit 时，模型仍为 Tier C/no_action，不能称为完整 equity research report。

## 2026-07-25 · E7-S1 三层 cadence receipt

- Decision：在既有 A5 orchestration receipt 中附加 versioned slow/periodic/fast cadence plan；fast lane 的 last-good 只读取 canonical active 的 `activated_at`，slow/periodic 在没有各自独立成功 receipt 时显式为 missing。
- Why：不能把一次 fast market refresh 错当成基本面或产业研究已经刷新。A5 继续是唯一执行器、锁、回填和 last-good 机制。
- Evidence：`product/data_core/research_cadence.py` 与 `test_snapshot_orchestration.py` 的 deterministic receipt coverage。

### Gotchas · E7-S1

- cadence state 是 freshness policy，不是新增事实或 recommendation；missing/stale 不可静默升级为 fresh。
- 此阶段只绑定 fast lane 到现有 A5 active identity；slow/periodic 的实际 runner 必须以后续 source-specific receipt 接入。

## 2026-07-25 · E7-S2a Thesis object contract and migration

- Decision：新增 versioned `thesis` research object，并同时迁移 SQLite 与 PostgreSQL 的 object type contract；不把 thesis 塞进 catalyst 或 dossier prose。
- Why：thesis 必须有独立 evidence identity 和 revision history，后续 catalyst、falsifier 与 event 才能引用它而不丢失语义。
- Evidence：focused object-contract/schema tests 覆盖 fresh schema、PostgreSQL migration presence，以及一张有对象记录的 legacy SQLite 表重建后保留 object hash 和 append-only protection。

### Gotchas · E7-S2a

- SQLite 不能 in-place 修改 CHECK；仅当既有表缺少 `thesis` 时显式 rebuild，逐列复制当前字段并重装 append-only triggers。
- thesis 是研究上下文，不能据此生成 rating、target price、position 或 action。

## 2026-07-25 · E7-S2 Versioned trigger history

- Decision：复用 B5 `IntelligenceEvent` 与 E1 append-only object store；event match 只产出可审计 proposal，只有调用既有 store append 才会持久化下一 revision。
- Why：event 不能静默重写 thesis/catalyst/falsifier，也不能直接产生 recommendation 或 action。每个 trigger 因此带 thesis_ref、direction、threshold、time_window、status 和 event-evidence reference。
- Evidence：`test_research_trigger_history.py` 覆盖 fulfilled revision proposal、原 revision 不变、immediately-prior hash binding、unmatched evidence 与非法 direction fail closed。

### Gotchas · E7-S2

- `fulfilled`、`delayed`、`broken` 是显式人/规则判断结果，不是新闻标题或模型自动结论；需要 event evidence identity 和 rule/model version。
- proposal 不等于写入，写入仍必须通过 raw hash/snapshot authority。没有 action、target、position 或 order output。

## 2026-07-25 · E7-S3 发布时点 outcome attribution

- Decision：复用 canonical publication/report identity；将 report 的 `as_of`/`known_at` 与 starting market price 冻结，之后的价格、benchmark、industry 与 basic fundamental observation 只能进入独立 outcome window。
- Why：回看研究价值必须有结果，但不能让后来可见的数据回写为当时的研究依据。
- Evidence：`test_research_outcomes.py` 验证 component attribution、frozen basis 与 cutoff/identity fail-closed；`test_research_refresh_v1` 确认 publication/report contracts 未回归。

### Gotchas · E7-S3

- outcome window 不是历史投资业绩或 backtest；缺失 benchmark、industry 或 fundamental component 必须保持 missing。
- outcome receipt 不能生成或升级 rating、target、position、recommendation 或 order。

## 2026-07-25 · E4-S4o 估值与卖方收据绑定

- Decision：只在 valuation 与 sell-side runtime receipts 同时绑定到同一 partial-model receipt、ticker、as-of、accepted Context Pack 时，才将相应 section 标记为 available；输出永远维持 Tier C / no_action。
- Why：E4 的目标是可追溯的 100 ticker 覆盖，不能用“有一份估值”或“有一篇研报”跨公司/跨时间地填充 partial model。
- Evidence：`product/data_core/e4_valuation_sellside_coverage.py` 和 `product/tests/test_e4_valuation_sellside_coverage.py` 覆盖同源成功、context/as-of 不匹配、fixture/lineage 拒绝及 decision boundary。

### Gotchas · E4-S4o

- 这是 compiler glue，不会采集数据，也不会生成估值参数、broker 观点、target、position 或 action；collector 的 runtime payload 仍必须在仓库外。
- 现有 C2/C3 dataclass 的输出需要由后续 runtime adapter 加上 real data kind、partial receipt lineage 与 as-of；缺任一项必须显示 missing/blocked，而不是升级覆盖率。

## 2026-07-25 · E4-S4p 卖方证据 batch

- Decision：复用 B2 的 Eastmoney catalog/PDF archive，以每 ticker 至多一份 PDF、顺序限流、checkpoint/replay 的 runtime receipt 接入 E4；catalog 与 metadata-only 都保留，但不产生 Tier 或决策 credit。
- Why：C3 matrix 前必须先知道真实 corpus 中每只股票的 catalog、PDF 与失败状态，不能把“未抓到”静默变成无覆盖或将目录 metadata 当作页级证据。
- Evidence：`product/data_core/e4_sell_side_evidence_batch.py` 与 `product/tests/test_e4_sell_side_evidence_batch.py` 覆盖 PDF、metadata-only、异常隔离、配置重放与 fixture 输入拒绝。

### Gotchas · E4-S4p

- B2 archive output 是卖方 input；没有通过 C3 page citation 与 Context Pack 绑定前，不能作为 matrix、Tier、target、position 或 action 的证据。
- runtime receipt/PDF 一律不提交；collector 遇到反爬、404 或超时只能记录 metadata/typed failure，不能切换 proxy、cookie 或其他数据源。

## 2026-07-25 · E4-S4q 卖方 PDF runtime raw 保存

- Decision：E4-S4p 的 ingestion attempts 使用 content-addressed runtime sink 保存已成功抓取且 SHA-256 验证一致的 catalog/PDF bytes；receipt 只在本地文件存在且复验哈希后暴露 runtime path。
- Why：B2 的 raw hash 和 storage URI 足以说明归档身份，但 B3/C3 的页级 citation 还需要可重读的 PDF bytes；不能为方便解析而将 PDF 提交进仓库。
- Evidence：`RuntimeRawAuthoritySink` 与 `test_e4_sell_side_evidence_batch.py` 覆盖 hash-bound write、mismatch 拒绝与 metadata-only 不产生本地 path。

### Gotchas · E4-S4q

- runtime path 是本机临时材料，不是 canonical storage authority；正式发布仍需由已配置的 authority sink 接管同一 raw hash。
- 每次写入都重验 payload hash；任何 collision、path escape 或文件漂移都是阻断，不可用旧 PDF 替代。

## 2026-07-25 · E4-S4r 卖方页级证据

- Decision：复用 B3 parser，仅对 E4-S4q receipt 中已归档、路径受 runtime root 限制且 SHA-256 一致的 PDF 输出 page/chunk identity；metadata-only、路径缺失、hash 不一致和 parser 异常一律按单文档阻断。
- Why：C3 matrix 的页级引用需要真实 PDF 文本和 page identity，不能从 catalog title、评级或 LLM 摘要推断文本。
- Evidence：`product/data_core/e4_sell_side_page_evidence.py` 与对应测试覆盖 native PDF、hash mismatch 和 metadata-only boundary。

### Gotchas · E4-S4r

- parser receipt 的 page/chunk identity 不是 analyst claim，更不是 matrix 或 recommendation；claim extraction 仍需独立、可审计的 C3 step。
- runtime path 只能在 supplied root 下读取，并在每次 parse 前 re-hash；不能将其他临时 PDF 伪装成该 report 的 source evidence。

## 2026-07-25 · E4-S4s 页面验证卖方矩阵

- Decision：复用 C3，仅让同时具备 catalog broker/rating 与已 page-verified PDF 的报告进入 matrix；不从 PDF 文本推断 claim、target 或 forecast。
- Why：评级 metadata 与 PDF/page identity 可以作为有边界的 matrix 输入，但缺失字段必须保留，不能借页面文本生成未经审计的分析师观点。
- Evidence：`test_e4_sell_side_matrix.py` 覆盖真实 page-verified report matrix、missing target/estimate fields 与 lineage mismatch。

### Gotchas · E4-S4s

- rating-only matrix 不是 page-cited claim matrix，因此不产生 numeric/page audit、Tier、target、position 或 action credit。
- `as_of` 是 caller 明示的 point-in-time cutoff；不能从当前时间或 later report 自动补全。

## 2026-07-25 · E4-S4t Context Pack receipt binding

- Decision：复用 B6 的 official-primary Context Pack identity、E4 partial model 与 E4-S4o coverage binder，将同一 official lineage 下的市场/财务 receipt 和 C3 page-verified matrix 编译为 per-ticker Context Pack binding；所有输入 source receipt、matrix 与 partial model 必须完全匹配同一 `as_of`。
- Why：报告模型必须能回答每个 section 的来源、原始哈希与截至时点；相邻时点或其他 ticker 的数据看似完整，却会破坏 point-in-time research 的可审计性。
- Evidence：`test_e4_context_pack_models.py` 覆盖同源确定性编译、official lineage 拒绝、market cutoff mismatch 显式 blocked 和缺失 sell-side matrix 不借用。

### Gotchas · E4-S4t

- 这里的 Context Pack 是 B6 已通过的 official-primary identity 加上 E4 component bindings；它不是放宽 B6 coverage policy 的新入口，也不代表 market/sell-side 已成为可发布 research evidence。
- C3 rating-only matrix 不是 valuation receipt；即使 market 与 matrix 都 available，valuation 保持 missing、Tier C/no_action 不变。未能同步采集的 source receipt 必须 blocked，不能以最近交易日替代。

## 2026-07-25 · E4-S4v C3 research cutoff identity

- Decision：保留 C3 原有用于报告日期筛选的 date-level `as_of`，在 E4 matrix runtime receipt 额外强制记录 caller 提供的 timezone-qualified `research_cutoff`；它不改写任一报告发布日期或 C3 matrix core identity。
- Why：研究截止时点与报告发布日期是不同概念。前者必须精确绑定到跨源 Context Pack，后者仍是 C3 正确过滤 historical report 的业务语义。
- Evidence：`test_e4_sell_side_matrix.py` 验证 timestamp 保存、date-only cutoff 拒绝、同 inputs/cutoff replay与改变 cutoff 后 receipt identity 变化。

### Gotchas · E4-S4v

- `research_cutoff` 是显式 caller contract，绝不能默认取当前时间；它只标识 E4 runtime receipt 的研究边界，不将 rating-only matrix 升为 valuation、claim、Tier、target、position 或 action。
- C3 matrix 的 `as_of` 仍为 date-level，Context Pack compiler 必须读取新的 `research_cutoff`，而不是把两者混为同一字段。

## 2026-07-25 · E4-S4u canonical research cutoff

- Decision：E4 Context Pack 以一个 timezone-qualified `research_cutoff` 为本次研究的 point-in-time boundary；B6 official Context 和 A4 source `known_at` 可以早于该 cutoff，但不得晚于它，C3 matrix receipt 必须显式声明完全相同的 cutoff。
- Why：不同采集器不可能保证同一秒完成。把 source capture timestamp 强行设为同值会伪造来源历史；用 `known_at <= cutoff` 保留真实 capture identity，同时仍阻止 future leakage。
- Evidence：`test_e4_context_pack_models.py` 覆盖 earlier-on-time 绑定、later-known source blocking、exact matrix-cutoff mismatch、ticker/official-lineage mismatch 和 deterministic rerun。实际 replay 在 `2026-07-25T23:59:59Z` cutoff 下编译 40 个 Context Pack inputs，其中 27 个 market/fundamentals 与 18 个 sell-side sections available；全部仍为 Tier C/no_action。

### Gotchas · E4-S4u

- `official_context_as_of` 是已有 B6 official-primary evidence 的时间，不能被 output cutoff 覆盖；所有两者都保留以便审计。
- C3 catalog rating matrix 仍不是 valuation 或 page-cited analyst claim；available sell-side section 不增加 Tier、numeric/page audit、target、position 或 action credit。

## 2026-07-25 · E4-S4w real valuation receipt adapter

- Decision：复用 C2 deterministic valuation engine；E4 只负责把 canonical source receipts、显式 assumption receipt 与 partial Context Pack identity 绑定成 runtime-only valuation receipt。
- Why：C2 可以验证计算，却不能证明数值或情景假设从哪里来。adapter 因此拒绝缺少 hash、晚于 cutoff 的 source 或未经身份绑定的公司输入。
- Evidence：`test_e4_valuation_receipts.py` 覆盖 deterministic replay、real lineage、future-source block 和 Tier C boundary。

### Gotchas · E4-S4w

- assumption receipt 是可审计的研究判断输入，不是 provider fact；没有它不允许默认 bear/base/bull 参数。
- 即便 C2 输出可复算，receipt 也只提供 valuation section input，绝不产生 Tier A/B、target、position 或 action。

## 2026-07-25 · E4-S4z bounded sell-side candidate extraction

- Decision：复用 E4-S4q/r 的既有 evidence batch 与 page-evidence contracts，以同一输入哈希生成 lineage-bound runtime checkpoint；每次只解析一个有界文档切片，完成时直接由 checkpoint rows 写最终 candidate receipt，不重跑整批 PDF。
- Why：72 份真实 PDF 的整批重新解析在交互式运行中不稳定。断点和恢复必须保留已验证的 per-document output，同时不能让性能优化改变候选、来源或证据边界。
- Evidence：`test_e4_sell_side_claim_candidates.py` 覆盖中断后的 continuation、最终 receipt 和 non-actionable boundary；真实 runtime corpus 完成为 72 documents：71 compiled、1 blocked、1,047 unreviewed candidates。

### Gotchas · E4-S4z

- checkpoint 仅对完全相同 batch/page-evidence input hashes 有效；换输入必须新建 lineage，不得混用旧 rows。
- candidate 是 broker assertion candidate，不是已接纳的 C3 claim；必须经过后续 accept/reject gate 才可被任何研究输出引用，且本 story 不改变 Tier、审计、target、position 或 action。

## 2026-07-25 · E4-S4aa sell-side claim admission gate

- Decision：候选卖方断言只能由显式、具名、带时间和理由的 reviewer decision 接纳；decision 必须重述并精确匹配 candidate 的 raw hash、parser、页面、chunk、字符范围和文本，接纳后仍标为 broker assertion 而非公司事实。
- Why：页面文本抽取能定位可能有价值的断言，却不能判断语义、立场或是否适合引用。将自动候选与人工研究判断分隔，才可让 C3-compatible claim 具备可审计来源与责任边界。
- Evidence：`test_e4_sell_side_claim_admission.py` 覆盖显式接纳、无决策不接纳和 identity drift fail-closed；真实 runtime receipt 绑定 1,047 candidates，因无真实 reviewer decision 而 accepted=0、rejected=0、unreviewed=1,047。

### Gotchas · E4-S4aa

- `--init-empty` 仅写明确的零决策 receipt，绝不伪造 reviewer 或 LLM 审核；实际接纳需要独立提供 decision receipt。
- 接纳输出是 C3-compatible page-cited broker assertion，不自动升为 Tier A/B、numeric/page audit、target、position 或 action；这些需要其各自的后续验证合同。

## 2026-07-25 · E4-S4k SSE 同源 TLS transport fallback

- Decision：仅当 Python urllib 对 `query.sse.com.cn` 的官方 SSE index 出现 TLS/SSL handshake failure 时，使用系统 curl 对完全相同的官方 URL、headers 与 HTTPS host allowlist 进行一次有界 transport fallback；curl 失败或跳出 host 仍失败。
- Why：同一 URL 在本运行环境中 curl 可成功返回 SSE 官方 index，而 urllib 会在 TLS handshake 超时。保持同源和 raw capture 能恢复 discovery，不需要 aggregator 或跨交易所 fallback。
- Evidence：live probe `600519.SH` 成功捕获 30 条 SSE official discovery；focused adapter tests 覆盖 final-header parsing。

### Gotchas · E4-S4k SSE fallback

- fallback 只修复 discovery transport，不保证 PDF document capture，也不产生 Report Model、Tier、target、position 或 action credit。
- curl 是运行环境依赖；缺失、失败或 redirect 超出 `query.sse.com.cn` 时必须 fail closed，不能替换为其他下载器或非官方 URL。
# 2026-07-28 — Existing module names do not satisfy C1 inputs

- **Decision:** Wire `e4_page_level_filing_facts.revenue` to
  `revenue_quality_and_kpis.revenue_history` only when it carries the official
  document/page/hash accounting identity; reject the proposed F10 connection
  in this story.
- **Why:** C1 input presence must mean a real, ticker-specific and
  evidence-bound object.  A module map is not runtime evidence, and the F10
  manifest explicitly marks its output supplementary/vendor data.
- **Evidence:** `product/data_core/e4_page_level_filing_facts.py` emits the
  page identity and accounting fields; `product/data_core/eastmoney_periodic.py`
  declares `authority_tier="supplementary_only"` and `vendor_f10`.
- **Gotchas:** Do not turn a shape-compatible vendor record into a FULL C1
  section.  Future module wiring must check an actual per-ticker receipt and
  its source identity, not only the module's Python API.
# 2026-07-28 — CATL official-only vertical stops before C2

- **Decision:** Stop the CATL fact-to-decision vertical after the multi-period
  CNINFO extraction rather than manufacture the missing C2 inputs.
- **Why:** C2 requires page-bound capital expenditure for every historical
  period, plus peer EV/EBITDA and historical PE anchors.  Capital expenditure
  was not safely extracted from any of the eight official PDF layouts, and the
  two multiple anchors are not facts in one issuer's official PDFs.
- **Evidence:** `docs/evidence/2026-07-28-e4-catl-vertical-stop.md` records
  the eight runtime captures, admitted counts and the direct PDF sample.
- **Gotchas:** A line wrapping over a PDF table boundary is not permission to
  concatenate neighbouring text.  Do not label a company self-multiple as a
  peer anchor or use a vendor multiple to make C2 look runnable.

# 2026-07-28 — CATL page context and partial-C2 semantics

- **Decision:** Official-PDF extraction carries statement scope and reporting
  unit linearly across pages, changing only when a later statement title is
  encountered. C2 may emit a visibly partial result when approved comparable
  inputs are absent; the receipt records methods actually run and those missing.
- **Why:** A page can contain the tail of a consolidated table before the title
  of a parent-company table. Page-level title detection therefore misassigns a
  correct number. A DCF must not impersonate an unavailable comps or
  historical-multiple cross-check.
- **Evidence:** CNINFO document `1216084559`, p109, contains CATL consolidated
  capex `4,821,526.81` with the prior p108 statement/unit header; p110 then
  contains the parent-company value. Tests cover this inherited-state shape and
  C2 receipts expose partial methods explicitly.
- **Gotchas:** Original units remain on the fact (`万元` in 2022 versus `千元` in
  2025); conversion belongs to an explicitly identified downstream calculation.
  Every missing/indeterminate extraction conclusion must retain a bounded raw
  source excerpt, not a speculative diagnosis.

# 2026-07-28 — Vertical validation boundaries

- **Decision:** Keep CATL's partial C2 as an explicit no-action artifact; do not generalize its numerical extraction to Moutai or banks without column validation and sector profiles.
- **Why:** Moutai exposed label/column collisions, while Ping An Bank's balance sheet and valuation economics are structurally different.
- **Evidence:** `docs/evidence/2026-07-28-m2-moutai-generalization.md`, `docs/evidence/2026-07-28-m3-pingan-bank-pressure.md`, and `docs/evidence/2026-07-28-m4-vertical-handoff.md`.
- **Gotchas:** Share-capital amount and share count are separate fields; a plausible target price still remains non-actionable while assumptions and independent valuation methods are incomplete.

# 2026-07-28 — Page fact column identity and duplicate-source validation

- **Decision:** Retain a separate fact for every recognized numeric column;
  do not deduplicate same ticker/metric/report-period values from different PDFs.
- **Why:** The later filing's prior-period column is the independent audit
  object for the earlier filing's current-period fact.
- **Evidence:** CATL 2024FY revenue `362,012,554 千元` is present in
  `1222806982` p119 and `1225002214` p116; automated comparison reports it
  consistent.
- **Gotchas:** Unknown headers do not authorize a guessed second column. A
  missing balance-sheet validation is safer than a balance calculation built
  from unqualified candidates.

# 2026-07-28 — M2 uses CNINFO structured report categories for period retrieval

- **Decision:** The 20-ticker financial-sequence collector sends CNINFO's
  official report category with each bounded period window and captures only
  one matching official filing per requested period.
- **Why:** A broad announcement window is dominated by board notices and can
  miss an annual report despite it being present in the issuer index.  A
  category-constrained request is still the official CNINFO discovery route,
  while avoiding needless downloads and preserving one-document provenance.
- **Evidence:** `CninfoFilingIndexAdapter` now forwards the optional category
  parameter; `test_cninfo_category_is_forwarded_to_structured_history_query`
  proves it reaches the structured history POST unchanged.
- **Gotchas:** The original 20-ticker raw receipt was intentionally runtime
  only.  The M2 cohort records its replayable replacement selection separately;
  issuer selection is never used as a substitute for page-bound financial data.

# 2026-07-29 — M1–M6 handoff keeps incomplete audit coverage visible

- **Decision:** Record M4's seven real page-bound assignments and thirteen
  gaps as the final state of this batch; do not create synthetic audit objects.
- **Why:** An incomplete reviewable set is safer than a 20-row façade when a
  PDF worker timeout prevented capture.
- **Evidence:** `docs/evidence/2026-07-29-m1-m6-handoff.md` and M2 runtime
  receipt `4502bb32938478ea`.
- **Gotchas:** A process timeout is a local runtime failure, not evidence that
  CNINFO lacks a filing. The next worker must enforce a process-level timeout
  before the M4 gap can be called a collection result.

# 2026-07-29 — Official recovery keeps parser gaps distinct from missing filings

- **Decision:** Treat the remaining audit gaps as documented parser/OCR work,
  not missing source evidence, after direct official CNINFO PDF retrieval.
- **Why:** The structured index and direct official document URLs returned
  valid PDFs for issuers previously recorded as uncaptured; one recovery path
  yielded page facts while two PDF layouts still require dedicated parsing.
- **Evidence:** PR #516 preserves the transport retry budget; PR #518 preserves
  short native text. CNINFO `1225047590` is a valid CMB annual report whose
  PDF p127 displays the RMB-million consolidated balance sheet.
- **Gotchas:** A human-visible PDF is not automatically a machine-admitted
  page fact. Do not promote a manually observed number into M4 until the
  extractor records the same PDF identity, page, unit, scope and anchor.

# 2026-07-29 — M4 selects against cross-document disputes

- **Decision:** Classify multi-document instances as `cross_verified` or
  `disputed`, retain both source instances, and exclude disputed rows from the
  pending-human-review M4 queue.
- **Why:** A human audit is most valuable when it tests a consistent,
  independently repeated number; a known mismatch must first be explained as
  a restatement or extraction defect rather than presented as a normal fact.
- **Evidence:** Runtime M4 v5 contains 20 distinct assignments: 5
  cross-verified, 15 explicitly unverified, zero selected disputed candidates.
  The CSCEC 2021 operating-cash-flow pair is retained as an inspectable
  disputed example in the final handoff.
- **Gotchas:** Cross verification is evidence of agreement, not a completed
  human audit. `unverified` does not mean false, and `disputed` does not mean
  an accounting error; neither status permits changing the evidence gate,
  Tier, target, position or action policy.

# 2026-07-29 — Statement metadata is linear document state

- **Decision:** Carry a recognized table header, unit/currency source, and
  audit status through following pages until the next statement title; reset
  only the column header at that table boundary.
- **Why:** CNINFO 1225107946 places the balance-sheet header on p5 while the
  valid consolidated current-liabilities row is on p7.
- **Evidence:** Official-PDF replay resolves p7 `流动负债合计` as period-end
  434,010,194 for 2026Q1; regression coverage exercises p5-to-p7 inheritance.
- **Gotchas:** Never replace missing context with a first-column heuristic.
  An unresolved fact is safer than a page-cited fact assigned to the wrong
  period.

# 2026-07-29 — Unreviewed AI judgments are receipt-bound partial inputs

- **Decision:** Wire an AI judgment into its corresponding C1 input only when
  its exact real-run receipt hash and every cited official page identity pass
  validation.  A required input carrying
  `ai_generated_judgment_unreviewed` makes the section `PARTIAL` with
  `pending_judgment_review`; a reviewed successor may complete it without
  changing C1 requirements or the Tier policy.
- **Why:** “Content exists” is useful research-progress information, but it is
  not the same as an analyst-approved conclusion.  Completion semantics must
  make that distinction before any caller evaluates Tier A eligibility.
- **Evidence:** `product/data_core/e4_judgment_wiring.py` verifies the receipt
  hash, ticker, real data kind, and `document_id`/page/anchor/raw-hash/source
  URL citation set; `product/tests/test_e4_judgment_wiring.py` covers both the
  no-FULL rule and tamper rejection.
- **Gotchas:** Do not infer a receipt from a module name or a dossier ID.  A
  receipt with missing page citations, a mismatched ticker, a changed hash, or
  fixture data is not a C1 input and must remain missing.

# 2026-07-29 — R2 industry inputs require an issuer-specific bridge

- **Decision:** Project the passed R2 world model into C1 only for an issuer
  that has both an accepted page-cited industry position and a compiled R2
  dossier.  For CATL this wires `company_profile` and `industry_profile`;
  it does not synthesize `market_size`, `segment_financials`, events, or a
  dated `catalyst_calendar`.
- **Why:** Nodes and segments describe an industry model, not company facts.
  CATL's accepted battery position supplies the required issuer bridge, while
  R2's catalyst profiles contain no issuer-specific future date/mechanism
  object suitable for the C1 catalyst calendar.
- **Evidence:** R2 acceptance rerun receipt
  `8d0b6122b8ce78edca201ce6299590f27c6b2ef6b12ecef7848758e3c8323989`
  passed all gates; N3 dossier receipt
  `10dd875e32907e146963ff7161fe5fef9539b9fd3f60f39d67e823aec95c4d21`
  identifies CATL's dossier and the official CNINFO page-cited position.
- **Gotchas:** A passed R2 count gate is not a universal company profile.
  Moutai and Ping An have no accepted R2 position, and sector-wide catalyst
  text without issuer, date and mechanism remains a shape mismatch rather
  than a report input.

# 2026-07-29 — Human review is the only completion path for AI judgments

- **Decision:** Generate a receipt-bound review queue that contains each draft
  judgment's full body, page-level citations, review writeback state, impact
  rank, and the precise C1 section outcome after approval.  The report banner
  and receipt expose the count of unreviewed judgments.
- **Why:** A reviewer needs a usable work item rather than a vague “AI content
  exists” flag, while the product must visibly distinguish a pending draft from
  a completed chapter.
- **Evidence:** CATL queue source receipt
  `e4-m3-catl-judgments-v1:dd1922d6fa58f09dbaa6f853d27430f04a4995afc13733ee3749a523b8c6b01d`
  produces 10 pending items.  The Tier regression test proves a contract with
  otherwise complete inputs remains Tier B when one required input is
  unreviewed.
- **Gotchas:** Reviewing one half of a multi-input chapter is not enough.  The
  queue reports the status after all pending inputs in that section are
  approved, and still keeps independently missing requirements explicit.

# 2026-07-29 — Wired reports remain Tier B after recompilation

- **Decision:** Recompile and retain both CATL and Moutai reports beneath
  `artifacts/e4-reports/`, with data time, validation summary, 18-section
  state, and an unreviewed-AI banner in each output.
- **Why:** A durable reader artifact must show its actual receipt-bound inputs
  and degradation outcome; it cannot imply that the new wiring made a target
  price, position, or Tier A available.
- **Evidence:** `e4-m4-wired-report-verification-v1` confirms CATL at
  4 FULL / 10 PARTIAL / 4 MISSING and Moutai at 4 FULL / 3 PARTIAL / 11
  MISSING; both receipts are Tier B with action fields blocked.
- **Gotchas:** CATL's new answerable navigation entries include unreviewed
  judgment-backed content and must stay visibly marked pending review.  A
  Moutai report with zero unreviewed drafts is not more complete; it still has
  its own independently missing inputs.

# 2026-07-29 — L1 human-review handoff remains deliberately incomplete

- **Decision:** Finish L1 with an explicit human-review pack rather than
  synthetic approvals: CATL has nine receipt-bound, page-linkable judgment
  drafts, zero approvals, and only `risks_and_falsification` plus
  `monitoring_and_action_triggers` can become FULL solely after all of their
  listed human approvals.  Retire stale spot-audit assignments instead of
  calling the old 20-item list current.
- **Why:** The unresolved boundary is human judgment, not a machine status
  gap.  A document identity that no longer appears in the current financial
  sequence cannot honestly remain an active audit task.
- **Evidence:** L1-M6 verification receipt
  `artifacts/e4-reports/e4-l1-m6-review-prep-verification.json` binds the
  judgment queue to `e4-m3-catl-judgments-v2:ba5e1b96eae378a3a116c88e39024ffbebcafab8bba54cd098d7b2a0f7b7281e`;
  all nine items have `pdf_page_url` links.  Against financial-sequence receipt
  `4502bb32938478ea07f8e01b6a7793b9369bdb87f3f122ee4a7d556c1ff1f0f5`,
  eight legacy assignments retain document/hash lineage, twelve are stale,
  and the conservative regenerated receipt has seven current assignments plus
  thirteen coverage gaps.
- **Gotchas:** Lineage-valid is not a completed audit, and the current seven
  assignments do not restore the missing thirteen.  No reviewer record was
  written, no unreviewed judgment became FULL, and neither Tier nor issue #218
  receives credit from this preparation.

# 2026-07-29 — L2 scale receipts remain input coverage, not #218 completion

- **Decision:** Complete L2 with explicit runtime/provenance boundaries and a strict #218 replay rather than adapting thresholds to the new 100-ticker financial and narrative corpus.
- **Why:** The new corpus proves official document coverage but does not create the canonical accepted Report Models, Tier A/B results, or independent page/numeric audits required by #218.
- **Evidence:** L2 financial receipt `7534f6a9f3b2c81b93340676e11019f8548631676edee9bb5bd2d6a324fd08fc`; narrative receipt `b3afef60ddc186c83a36fd073a749a6f10e738cab4f080eb450d8034aeb60ab6`; strict acceptance receipt `9d4d9ea64a28503e4fc10543e6ab07e46894e4d12b3f715fdcfbb9aacf4b60be` reports 100/100 identity and 0/95 Report Models, 0/80 Tier A/B, 0/20 audits.
- **Gotchas:** A runtime-only cache, page-level fact, narrative block, unreviewed valuation profile, or canonical read endpoint is never evidence that a report meets #218. Do not let a presentation layer or input receipt manufacture a Tier, target, position, action, or audit credit.

# 2026-07-29 — L3 reliability evidence preserves explicit maturity boundaries

- **Decision:** Record the L3 reliability layer as verified private-preview/local-contract capability, not production completion.
- **Why:** Backup, rollback, cache performance, auth and cadence proofs are useful only when their runtime and unimplemented deployment boundaries remain visible.
- **Evidence:** L3-M1 through L3-M10 evidence records under `docs/evidence/2026-07-29-l3-*`; recovery and performance receipts remain external runtime artifacts.
- **Gotchas:** No L3 artifact upgrades #218, Tier, reviewer approval, production Supabase/RLS, slow/periodic live cadence, correction SLA, or member deletion/export.

# 2026-07-30 — Model judgments accumulate only validator-accepted outputs

- **Decision:** Generate each judgment with an independent real DeepSeek call,
  allow at most two model repair attempts, and resume only outputs that are
  revalidated against the identical frozen input, prompt, generator and
  validator hashes.  Failed tasks remain MISSING.
- **Why:** One malformed response must not discard unrelated valid judgments,
  while a restart must never smuggle stale or differently sourced prose into
  the final receipt.
- **Evidence:** CATL receipt
  `e4-model-judgments-v1:a1398e135d132d6b547f70217fa8026e601a61cac3a800657550b88a6cdd9fb0`
  contains seven accepted judgments from real `deepseek-v4-pro` calls.  Its M2
  verifier passes 11/11 name-swap sentences, 12/12 numeric tokens and reports zero
  generator f-strings or issuer hardcoding.
- **Gotchas:** Retry is not review and does not change
  `ai_generated_judgment_unreviewed`.  Two model outputs still fail strict
  inference or quote validation and remain MISSING; cumulative model
  receipts are audit history, not independent research facts.

# 2026-07-30 — The same model path is issuer-generic

- **Decision:** Generalize the official narrative capture receipt to any
  requested ticker and run Moutai through the unchanged model-judgment
  generator and verifier.
- **Why:** A CATL-only success does not prove that reasoning comes from frozen
  evidence rather than hidden issuer branches.
- **Evidence:** Moutai narrative receipt
  `e4-official-narrative-evidence-v1:a520cc7cd01ddbbdbd721ee689fa31f95936e19c54c210872807f5cc74d8d0da`
  binds 86 resolved blocks across 34 pages to official document
  `1225114741`.  Judgment receipt
  `e4-model-judgments-v1:630a6c847bbbfdae4010c4aed71577c1892ab4d593ef4902f4c70366ab1f8892`
  passes the same verifier with eight accepted judgments, 11/11 specific
  sentences and 20/20 numeric tokens.
- **Gotchas:** Explicit risk sections must outrank generic management
  discussion; otherwise a model can falsely report that no risk evidence
  exists.  `monitoring_kpis` still fails quote validation and remains MISSING;
  it is not replaced with a company-specific template.

# 2026-07-30 — Report completion requires human-reviewed judgments

- **Decision:** Recompile CATL and Moutai from the issuer-generic model
  receipts, bind every rendered draft to its source receipt and review queue,
  and keep every draft-backed section at PARTIAL with
  `pending_judgment_review`.
- **Why:** A model output can make a required input present, but it is not a
  completed research conclusion and must not unlock Tier A, target price,
  position sizing, or an action recommendation.
- **Evidence:** Verification artifact
  `artifacts/e4-reports/e4-m4-model-report-verification.json` cross-checks the
  report banner, source receipt, complete impact-sorted queue, full judgment
  body, page-level citations and all 18 C1 section states. CATL is 5/10/3
  with seven pending drafts; Moutai is 4/8/6 with eight; both remain Tier B.
- **Gotchas:** Report HTML still uses a deterministic layout template; that is
  presentation, not judgment prose. Missing model outputs remain missing, and
  approving one draft does not fill another required input in the same
  section.

# 2026-07-30 — Round 7 is the product north star

- **Decision:** Freeze the accepted Round 7 template, five blind samples and
  NVDA replay as the sole reader-facing north star. Its nine reader units—not
  the legacy CATL/Moutai pilot headings and not C1's 18-field-oriented
  sections—define what later report iterations must approach.
- **Why:** The Round 7 reader won the external blind comparison 5/5 and Park
  explicitly approved it. The later 18-section system improved evidence
  infrastructure but regressed the reader output into a status table, fact
  dump and 632–673 characters of disconnected field judgments.
- **Evidence:** `artifacts/evidence/round7-north-star-baseline.json` binds the
  accepted structure signature, exact blind set, replay, approval receipts,
  nine reader units, quality gates and current safety-boundary source hashes.
- **Gotchas:** CATL and Moutai are `additional_product_samples`, not members of
  the Round 7 blind canonical set. Body length is only a smoke check. B6,
  Tier and blocked-field safety must survive the later section-contract
  replacement even though the 18-section taxonomy itself will be retired.
