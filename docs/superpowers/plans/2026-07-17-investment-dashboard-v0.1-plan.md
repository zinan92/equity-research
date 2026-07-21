# A 股长期投委会 · 60 分内测版实施计划

日期：2026-07-17  
状态：Implemented and verified with caveats

## Outcome Contract

### Intended user outcome

Park 和少数内测用户打开产品后，不需要理解 UZI 的 22 维和 66 位评委，就能在 3 分钟内看懂：当前市场状态、一套 A 股长期模型组合、每只股票的目标仓位、本周动作、核心理由、主要风险，以及这些结论基于哪一批数据。

### Success Criteria

1. 一个命令可以在本机启动面板，首页直接显示市场状态、股票/现金仓位和 6–12 只股票。
2. 组合仓位严格等于 100%，单股 5%–15%，行业不超过 30%，现金 10%–40%。
3. 用户可以查看本周变化、组合风险、个股摘要和数据状态，而不是只看到 UZI 原始报告。
4. 页面数据通过 API 从数据库读取，不直接硬编码在 HTML；每期组合绑定 snapshot、model version、as_of 和 quality。
5. 样例、缓存和真实数据必须显式区分；核心数据缺失时显示阻断或降级，不伪装成实时数据。
6. 保存桌面端和移动端视觉证据，并通过最小 API、数据库不变量和浏览器路径检查。

### In scope

- A 股长期模型组合首页；
- 本周变化、组合风险、个股抽屉/详情；
- 最小 SQLite 权威库及可迁移 schema；
- 数据快照、来源、质量和模型版本；
- 本地启动、测试和视觉验收。

### Out of scope

- Supabase 生产部署、Auth/RLS、会员和支付；
- Telegram、飞书或其他推送；
- 券商连接和自动下单；
- 全市场历史数据回填；
- 把演示组合描述成真实投资建议。

### Range and constraints

- 先服务 Park 和少数朋友；
- 组合面向 1000 万元基准资金、6 个月至 3 年持仓；
- 不改写 UZI 现有分析引擎；产品层通过适配器消费它；
- 无 Supabase 凭据时先用 SQLite 跑通，API 和表边界避免与前端耦合；
- 保留当前工作树所有既有修改和未跟踪产物。

### Required evidence

- 可启动页面及桌面/移动截图；
- `/api/dashboard` 和 `/api/stocks/{ticker}` 响应；
- 数据库 schema 与 seed/import provenance；
- 仓位、行业、现金、数据标签和快照不变量测试；
- 失败/降级状态的用户可见证明。

### Key risks, unknowns and assumptions

- 当前仓库只有 UZI 与 mock cache，没有可直接用于产品的真实组合数据库；首个 UI 版本会使用明确标记的 `DEMO` 快照，随后接真实 ingestion。
- 免费上游接口可能反爬或口径漂移，不能让 fetch 成功等同于可发布。
- 组合算法在 60 分版只提供可审计的规则骨架，不宣称经过长期回测。
- Supabase 凭据、正式域名和会员体系尚未提供，本轮不把它们伪装为已完成。

## Milestones

### M1 · 产品骨架与最小数据契约

- Goal：形成 database → API → UI 的真实运行链。
- Definition of Done：SQLite schema、seed snapshot、dashboard API 和启动命令可用。
- Constraints：前端不得直接读取 seed JSON；所有组合必须绑定 snapshot。
- Required Evidence：schema、API 响应、数据库不变量测试。
- Contribution：解决“这是不是只有 mockup”的问题。
- Gate：API 不能读取数据库或组合不等于 100% 时 No-go。

### M2 · 60 分决策首页

- Goal：让用户一眼看到该持有什么、多少仓位、为什么。
- Definition of Done：市场状态、组合表、本周变化、风险和数据状态在桌面/移动可用。
- Constraints：隐藏 66 位评委噪音；DEMO/REAL 状态始终可见。
- Required Evidence：桌面与移动截图、关键交互浏览器检查。
- Contribution：交付用户可感知的第一个完整产品面。
- Gate：黑屏、首屏无结论、数据状态不可见时 No-go。

### M3 · 个股详情与证据链

- Goal：从仓位结论下钻到依据、估值、风险和来源。
- Definition of Done：每只组合股票可打开详情，显示 thesis、风险、情景、证据和更新时间。
- Constraints：推断与事实分开，缺证据显示 Missing evidence。
- Required Evidence：至少两只股票详情路径和 API 检查。
- Contribution：让组合可解释而不是黑盒荐股。
- Gate：关键数字无来源或详情只是装饰时 No-go。

### M4 · 验证与下一阶段入口

- Goal：证明该版本可重复启动，并清楚界定 60 分与生产版差距。
- Definition of Done：测试通过、视觉证据保存、README/decision log 完整、真实数据接入任务明确。
- Constraints：不把 DEMO 快照算成真实数据基座完成。
- Required Evidence：测试输出、截图、验收矩阵。
- Contribution：给 M1 真实数据基座留下清晰接口，而不是推倒重来。
- Gate：缺少视觉证据或无法解释剩余差距时 No-go。

## Third-party review decision

本轮先由 Codex 独立推进。当前边界已有 Park 批准的产品 spec，尚不存在需要第三方仲裁的重大方向分歧；如实现中出现数据模型或交互方向冲突，再按 Park 授权调用 Claude CLI。

## Verification result

- M1 · 产品骨架与最小数据契约：`Met`
- M2 · 60 分决策首页：`Met for internal demo / Partially Met for real product`
- M3 · 个股详情与证据链：`Met for demo + real quote evidence`
- M4 · 验证与下一阶段入口：`Met`

重要边界：8/8 股票已接腾讯真实行情快照；组合动作、估值、置信度、业绩曲线和文字判断仍为 `DEMO`。原产品 spec 中的真实数据基座、组合引擎、Auth/RLS、正式发布和四周运行均未因此完成。
