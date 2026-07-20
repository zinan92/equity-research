---
name: dd
description: 生成尽调清单 — 5 大工作流 21 项检查 + 自动状态推断
---

# /dd <股票代码>

自动生成 PE/M&A 风格的 Due Diligence Checklist。

## 5 大工作流

1. **财务尽调 (Financial DD)** — 5Y 营收 / ROE / FCF / 资产负债率 / 审计意见
2. **商业尽调 (Commercial DD)** — TAM / 竞争格局 / 客户集中度 / 上下游
3. **法律尽调 (Legal DD)** — 股权结构 / 重大诉讼 / 关联交易 / 质押
4. **运营尽调 (Operational DD)** — 护城河 / 研发 / 管理层 / ESG
5. **市场尽调 (Market DD)** — 政策 / 舆情 / 事件 / 杀猪盘风险

## 工作流

```python
from lib.deep_analysis_methods import build_dd_checklist
dd = build_dd_checklist(features, raw)
```

## 输出

- 每条 ✅ 已有数据 / ⚪ 需人工核查 / ❌ 缺失
- `items_auto_verified / total_items` 完成率
- `manual_review_required` 剩余人工待办数

## 展示样式

```
📋 DD Checklist — 水晶光电 (002273.SZ)

财务尽调:  ✅ 营收  ✅ ROE  ✅ 债务  ✅ FCF  ⚪ 审计
商业尽调:  ✅ TAM  ✅ 竞争  ⚪ 客户  ✅ 上下游
法律尽调:  ✅ 股权  ⚪ 诉讼  ⚪ 关联  ✅ 质押
运营尽调:  ✅ 护城河 ⚪ 研发  ⚪ 管理  ⚪ ESG
市场尽调:  ✅ 政策  ✅ 舆情  ✅ 事件  ✅ 杀猪盘

15/21 auto-verified (71%) · 6 items need manual review
```
