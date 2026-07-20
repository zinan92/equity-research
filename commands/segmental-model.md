---
name: segmental-model
description: 分业务收入 bottom-up 建模 (v2.10) — 拆产品线 × 3 情景 × 3 年 projection，对 DCF 自上而下做反向校验
---

# /segmental-model <股票代码或名称>

对目标股票做 **bottom-up 分业务收入模型**，跟自上而下的 DCF 互补校验。

## 为什么需要这个方法

现有 17 种机构方法里，DCF/3-statement/IC Memo 都是 **top-down**——从整体营收 × 单一增速假设推未来。遇到业务结构在转型的公司就失真：

- 贵州茅台 直销比例 17% → 目标 50%+
- 宁德时代 动力电池 vs 储能 vs 海外 三条曲线增速完全不同
- Credo 收购 SiPh 后，Optics 线增速和 AEC 线差两倍

**单一营收增速掩盖了这些分化**。本方法把公司拆 3-5 条业务线，每条独立给 driver，三情景 3 年 projection，总量必须对账回当前营收。

## 工作流（agent 必须走完 5 步）

### Step 1 · 生成骨架（脚本）

```bash
python skills/deep-analysis/scripts/compute_segmental.py discover <ticker>
```

读 `5_chain.breakdown_top` + `1_financials.revenue_history` + `15_events`，产出 `.cache/<ticker>/segmental_skeleton.json`：

```json
{
  "ticker": "600519.SH",
  "name": "贵州茅台",
  "currency": "CNY",
  "total_revenue_latest_yi": 1721.4,
  "segments": [
    {"name": "茅台酒", "latest_revenue_yi": 1460.3, "latest_share_pct": 84.83, ...},
    {"name": "系列酒", "latest_revenue_yi": 246.0, "latest_share_pct": 14.29, ...}
  ],
  "inflection_candidates": [
    "直销渠道占比持续提升",
    "1935 新品上市拓展年轻客群"
  ]
}
```

### Step 2 · 读骨架 + 识别核心 thesis（agent）

Agent 必做：
1. 打开 `.cache/<ticker>/segmental_skeleton.json`
2. 结合 `6_research.reports`（卖方研报对业务分段的看法）+ `14_moat` + `13_policy`
3. 识别 **核心 inflection**（1-2 条）——例如：
   - 茅台 = "直销占比 17% → 50%+"
   - 宁德 = "海外储能 0 → 30%+"
   - Credo = "copper → SiPh optics"
4. 围绕 inflection 组织 segment 叙事

### Step 3 · 填 driver（agent）

对每个 segment 写：
- **drivers**: 价 × 量 × 市占 × 渗透 —— 至少列 2 个
  - ✓ 好例子：`["ASP +5%/年", "shipment +20%/年"]`
  - ✗ 坏例子：`["行业景气"]`
- **thesis_tag**: `growth_engine` / `cash_cow` / `declining` / `cyclical` / `turnaround`
- **bull_growth_3y_cagr** / **base_growth_3y_cagr** / **bear_growth_3y_cagr**
  必须满足 **bull ≥ base ≥ bear**

### Step 4 · 写回 + 校验（脚本）

写 `.cache/<ticker>/segmental_model.json`，然后：

```bash
python skills/deep-analysis/scripts/compute_segmental.py validate <ticker>
```

校验规则：
- 🔴 sum(segment.latest_revenue) 必须对账回 total_revenue ±10%
- 🔴 每个 segment bull ≥ base ≥ bear 单调
- 🟡 Base 情景 3 年总增速 > 100% 需要明确收购/新业务 note
- 🟡 每个 segment 必须有 ≥ 1 个 driver

不过不发。

### Step 5 · 进报告（脚本）

`assemble_report` 看到 `segmental_model.json` 存在 → 在 DCF 块下面加「分业务 Build-Up」块 · 用 top-down DCF 的 FCF projection vs bottom-up segmental 的 revenue projection 做交叉校验。

## 什么时候该用这个

**适合**：
- 业务结构正在转型的公司（收购/新业务/出海/高端化）
- `5_chain.breakdown_top` 有明确分段数据
- 营收同比在明显分化的公司（部分 segment +50%、部分 -10%）

**不适合**：
- 纯单一业务公司（如银行/保险/航空）
- 业务分段数据缺失且 agent 无法从研报补齐的公司
- 小市值 ST 股（没卖方研报，无法定 driver）

## 不替代 DCF / Comps

这是**第 18 种方法**，和 DCF 互补，不是替代。两个结论应该对得上：
- 自上而下 DCF 说营收 3Y CAGR 15%
- 自下而上 Segmental 说 15% = (60% × 主业 +5% + 40% × 新业务 +30%)
- 对齐 → 可信；打架 → 重查假设

## 参考

方法灵感来自极客厨子《Credo Model 拆分》。原文作者用 Claude 15 分钟为 Credo 拆出分业务收入模型，比卖方研报还细。UZI 版做了两点本土化：
1. 数据源绑定 A/H/U 市场的 `5_chain` / `6_research` 字段
2. 加对账 + 情景单调性 + driver 完整性三重自校
