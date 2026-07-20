# A 股长期投委会 v0.1 · 验收记录

日期：2026-07-17  
Verdict：`Accept with caveats`

## 用户视角结果

- 本地产品可在 `http://127.0.0.1:8877` 打开；
- 首页直接显示市场定调、8 只股票、目标仓位、动作、现金和三项风险；
- 股票与现金合计 100%，单股、行业和现金约束通过；
- 三个顶层页面可切换；个股详情可下钻到情景、风险与 Evidence / Inference；
- 8/8 股票接入腾讯真实行情参考价；
- 顶层持续标记 `DEMO / degraded / 不可发布`，没有把演示动作包装成真实建议。

## Outcome Contract 验收

| Success criterion | Status | Evidence |
|---|---|---|
| 一个命令启动，首屏显示完整组合 | Met | `product/server.py`；桌面截图 |
| 组合不变量 | Met | 5 项 unittest；`/api/health` errors=[] |
| 本周变化、风险、详情和数据状态 | Met | 首页、drawer、导航浏览器检查 |
| Database → API → UI | Met | SQLite + `/api/dashboard` + `/api/stocks/{ticker}` |
| DEMO 与真实事实明确区分 | Met | 首屏 DEMO、8/8 real quote、degraded gate |
| 桌面/移动视觉证据 | Met | 4 张 PNG；无 console/page errors |

## 50–60 分评分依据

总分母 100：

- 产品信息架构与 UI：18/20；
- 本地数据库、API 与可运行性：18/20；
- 真实数据覆盖：8/25（仅 8 只实时行情，缺 K 线、财务、估值、公告和 PIT 历史）；
- 组合决策引擎：4/20（约束可执行，结论仍为 DEMO）；
- Auth、审核、发布和持续运维：0/10；
- 测试与视觉证据：5/5。

合计：`53/100`。这是能真实操作的内测骨架，不是可收费发布的正式投研产品。

## 原产品 spec 状态

- M1 真实数据基座：`Partially Met`；仅行情 pilot，缺少正式核心域和 Supabase。
- M2 组合决策引擎：`Not Met`；当前仓位与动作是演示规则。
- M3 完整会员产品：`Partially Met`；用户页面可用，Auth/RLS/审核发布未做。
- M4 四周真实运行：`Not Met`。

## Visual evidence

- `evidence/2026-07-17-investment-dashboard-desktop.png`
- `evidence/2026-07-17-investment-dashboard-mobile.png`
- `evidence/2026-07-17-investment-dashboard-stock-detail.png`
- `evidence/2026-07-17-investment-dashboard-performance.png`

## Next go / no-go

下一步只做真实数据基座：交易日历、日线/复权、财务公告版本、估值与不可变 snapshot。上述字段不能 point-in-time replay 时，不进入真实组合建议开发。
