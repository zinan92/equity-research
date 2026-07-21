---
name: lbo
description: LBO 快速测试 — 假设 PE 买方用 5x 杠杆能否赚 20%+ IRR
---

# /lbo <股票代码>

作为估值交叉验证，测试"如果 PE 基金今天按市场价买入并 5 年后退出，能否赚到 20%+ IRR？"

## 工作流

```python
from lib.fin_models import quick_lbo
result = quick_lbo(features,
    entry_multiple=8.0,    # 入场 EV/EBITDA
    debt_multiple=5.0,     # 杠杆倍数 (5x EBITDA)
    exit_multiple=8.0,     # 退出 EV/EBITDA
    hold_years=5,
    ebitda_growth=0.08,    # 年化 EBITDA 增速
    interest_rate=0.06,
)
```

## 输出

- **入场**：EBITDA × 8x → EV → 债务 (5x) + 股权
- **5 年 EBITDA 路径**
- **债务偿还进度**：FCF × 70% 还债
- **退出**：Y5 EBITDA × 8x → EV - 剩余债 = 股权
- **IRR / MOIC**
- **verdict**：
  - 🟢 IRR ≥ 20% — PE 可赚
  - 🟡 15-20% — 边际
  - 🔴 < 15% — PE 不会买

## 为什么重要

LBO 测试是"私募买方视角的估值下限"。如果一个股票连 PE 基金用杠杆都赚不到钱，说明市场定价已经很贵了。这是对 DCF 的独立交叉校验。
