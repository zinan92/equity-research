# A 股长期投委会 · 80 分内测版计划与验收契约

日期：2026-07-17  
状态：Implemented and verified with caveats

## Outcome Contract

### Intended user outcome

Park 打开本地产品即可看到一套基于真实 A 股数据生成、可解释、可追溯且必须由 Park 批准后才能发布的长期组合；不再把 sample data 或虚构业绩当成产品结果。

### Success Criteria

1. 首屏直接给出 6–10 只 A 股名称、目标仓位、股票/现金合计 100% 和三项组合风险。
2. 每只股票都有真实行情、最近财务、日线特征、四维评分、Bull/Base/Bear 和事实/推断来源。
3. 真实快照覆盖 8/8 行情、每股至少 250 条日线和至少一条财务；不完整时 fail closed。
4. 同一不可变快照可离线重算出同一评分、仓位、现金比例和市场状态。
5. 状态遵循 `quality_passed → approved → published`；批准后内容变化必须使批准失效。
6. 桌面、移动、个股详情、真实业绩空状态和版本历史均有视觉 Evidence。
7. 本地 API、9 项测试、JavaScript/Python 语法检查和浏览器错误检查通过。

### In scope

- 8 只核心 A 股真实数据闭环；
- SQLite 权威快照、来源运行凭证和离线 replay；
- 可审计评分与受约束组合引擎；
- Park 批准、内容哈希锁定、发布和历史记录；
- 本地 Web 产品与响应式视觉验收。

### Out of scope

- 全 A 股候选池、复权因子独立校验、公司行动和正式公告库；
- 生产 Supabase/PostgreSQL、Auth/RLS、会员和支付；
- 云部署、定时调度、通知渠道、券商和自动交易；
- 经过长期实盘或回测验证的超额收益声明。

### Constraints and assumptions

- 面向 Park 和少数内测用户，1000 万元以上、长期持仓；
- 单股 5%–15%，现金 10%–40%，行业不超过 30%；
- 上游免费接口可能漂移，source run 和质量门必须用户可见；
- 发布之前不生成或展示虚构业绩曲线。

### Required Evidence

- REAL API 响应和 source run；
- 快照 replay 零差异；
- fail-closed、组合约束、批准/发布/失效测试；
- 桌面、移动、详情、业绩、历史、隔离发布截图；
- 本地服务健康检查和无浏览器 console error。

## Milestones

### M5 · 真实数据基座

- Goal：真实行情、日线和财务进入同一不可变快照。
- DoD：8/8、2568 日线、96 财务，来源与时间齐全。
- Gate：任一数据类覆盖不足即 No-go。
- Result：`Met`。

### M6 · 可复算的组合引擎

- Goal：真实输入得到确定性评分和 100% 组合。
- DoD：四维评分、6–10 只股票、仓位/现金/行业约束、离线 replay 零差异。
- Gate：重放结果不同或仓位越界即 No-go。
- Result：`Met for 8-stock internal universe`。

### M7 · Park 批准与发布

- Goal：系统结论不能绕过 Park 直接成为发布版本。
- DoD：质量通过、批准、发布三态；批准内容哈希锁定；变更后失效。
- Gate：未批准可发布或批准后可静默改写即 No-go。
- Result：`Met in local isolated acceptance database`。

### M8 · 用户界面真实化

- Goal：用户看到真实组合、证据、数据健康和诚实的业绩状态。
- DoD：桌面/移动无黑屏、无横向溢出；详情和历史可交互；未发布业绩显示空状态。
- Gate：DEMO 混入 REAL、伪历史曲线或关键入口不可用即 No-go。
- Result：`Met`。

### M9 · 80 分验收

- Goal：以固定 100 分分母判断是否达到 Park 要求的 80 分。
- DoD：验收矩阵、Evidence、测试、浏览器路径和剩余差距齐全。
- Gate：无视觉证明或无法解释失分项即 No-go。
- Result：`Met · 80/100`。

## Review decision

未调用 Claude。实现过程中没有出现需要第三方仲裁的方向冲突；Codex 对当前评分和验收负责。
