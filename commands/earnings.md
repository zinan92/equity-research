---
name: earnings
description: 财报解读 — 超预期检测 + 同比分析 + 投资逻辑影响
---

# /earnings <股票代码>

最新季报 beat/miss 快速解读。

## 工作流

1. 采集财务历史
2. 调用：
   ```python
   from lib.research_workflow import build_earnings_analysis
   result = build_earnings_analysis(features, raw, consensus={"rev": ..., "ni": ...})
   ```

## 输出

- **Headline**：双超预期 / 双不及 / 分化
- **最新季度**：营收、净利、YoY%
- **vs 共识**：差异 %（+5% 大超 / +2% 小超 / ±2% 符合 / -2% 小不及 / -5% 大不及）
- **投资逻辑影响**：
  - 💪 强化看多（双 +5% 以上）
  - ⚠️ 削弱看多
  - ⚪ 保持观点

## 展示示例

```
Headline: 双超预期 — 营收 +3.2% / 净利 +5.8%

最新季度：
  营收 12.5 亿 (YoY +18.5%) · vs 共识 12.1 亿 · 🟢 小幅超预期 (+3.3%)
  净利 1.6 亿 (YoY +22.1%) · vs 共识 1.51 亿 · 🟢 小幅超预期 (+5.9%)

投资逻辑：💪 强化看多
```
