# A 股长期投委会 v0.2 · 80 分验收

日期：2026-07-17  
Recommendation：`Accept with caveats`  
Score：`80/100`

## 用户视角结果

- REAL 快照：`snap_real_e1347cc6b85b`
- 当前状态：`quality_passed`，仍待 Park 真实批准；没有替 Park 点击。
- 组合：股票 82% + 现金 18% = 100%，8 只股票，单股 8%–13%。
- 最高仓位：长江电力 13%、美的集团 12%、中国神华 11%。
- 数据：8/8 行情、2568 条前复权日线、96 条财务记录；3 个 source run 全部 success。
- 离线重放：8 只股票，评分/仓位/现金/市场状态零差异。

## 固定分母评分

| 维度 | 满分 | 得分 | 证据与失分原因 |
|---|---:|---:|---|
| 用户决策界面 | 20 | 19 | 直接给名称、仓位、风险、证据；尚无用户自定义 mandate |
| 数据基座 | 25 | 20 | 真实快照、来源、raw hash、replay；尚非全市场/官方公告/公司行动/PIT 全覆盖 |
| 决策与组合引擎 | 20 | 14 | 四维评分与约束仓位可复算；候选池固定为 8 只且无长期回测验证 |
| 运营与发布流程 | 15 | 11 | 质量门、Park 批准、哈希锁定、发布、历史；尚无 Auth/RLS 和定时调度 |
| 工程与证据 | 10 | 9 | 9 tests、API、桌面/移动/交互、零 console error；尚无持续 CI |
| 产品化基础设施 | 10 | 7 | 本地一键启动和明确迁移边界；尚无 Supabase、云部署、会员体系 |
| **合计** | **100** | **80** | **达到本轮门槛** |

## Verification

- `GET /api/health` → `status=ok, data_mode=REAL`
- `python3 real_pipeline.py --replay snap_real_e1347cc6b85b` → `passed`, 8 tickers, 0 errors
- `python3 -W error::ResourceWarning -m unittest discover -s tests -v` → 9 passed
- `node --check static/app.js` → passed
- `python3 -m py_compile ...` → passed
- 浏览器：8 行组合、3 个 source run、详情财务/评分、真实业绩空状态、3 个历史版本均可见
- 移动端：390×844，`scrollWidth=390`，无横向溢出；底部导航修复后位于 782–844px
- console warning/error：0
- 隔离数据库：`quality_passed → approved → published`，事件为 `quality_gate, park_approval, park_publish`
- 真实数据库：仍为 `quality_passed`，只含 `quality_gate`

## Visual Evidence

- `2026-07-17-investment-dashboard-v0.2-real-desktop.png`
- `2026-07-17-investment-dashboard-v0.2-mobile.png`
- `2026-07-17-investment-dashboard-v0.2-stock-detail.png`
- `2026-07-17-investment-dashboard-v0.2-performance.png`
- `2026-07-17-investment-dashboard-v0.2-history.png`
- `2026-07-17-investment-dashboard-v0.2-published-isolated.png`

## Known gaps / No overclaim

- 当前不是生产数据库，仍是本地 SQLite；Supabase/PostgreSQL 迁移未做。
- 数据源为腾讯和东方财富聚合接口，不等于交易所/巨潮官方公告基座。
- 只在 8 只人工候选里分配仓位，不是全 A 股选股器。
- 没有发布后真实净值，因此业绩页有意显示“待发布”，没有伪造曲线。
- 没有证据证明模型能产生超额收益；需要影子组合和至少一个完整运行周期。
