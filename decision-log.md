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
