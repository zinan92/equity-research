# Decision Log

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
- Boundary：外部读者已完成，但 Park 角色仍缺失，故总门禁保持 `passed=false`；Park 未独立提交盲评分数前不得合并 #115 或声称档案生产能力通过最终验收。

### Gotchas · N1-5

- 固定模板能确保结构一致，不等于事实完整；缺少 proxy、10-Q 或客户/供应链证据时必须留下待补问题。
- Goal token 区间是 agent 整体工作量 telemetry，不是某家 LLM 的 prompt/completion token，不能据此推算 API 成本。
- 外部模型可能返回与请求别名不同的实际模型名；收据必须记录服务端实际返回值，不能把 `deepseek-chat` 请求参数写成已验证模型身份。
- 盲评包、A/B key 与第三方标杆正文必须留在 `/tmp` 等 Git 外路径；仓库只保留脱敏汇总收据。
- 复跑结构一致只证明模板和渲染确定性，不证明事实已刷新；真正的“最新版本”仍需重新捕获来源并生成新的 evidence snapshot。

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
