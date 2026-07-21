# Decision Log

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
