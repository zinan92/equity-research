---
name: thesis
description: 投资逻辑追踪 — 5 条核心支柱的当前状态 + 信念度 + 建议动作
---

# /thesis <股票代码>

实时监控"我为什么看多这只股"的 5 条核心支柱。

## 5 条自动生成的支柱

1. **营收增速 > 15%** — 当前 `rev_growth_3y`
2. **ROE > 15%** — 当前 `roe_last`
3. **技术面 Stage 2** — 当前 `kline.stage`
4. **估值合理 (PE < 40)** — 当前 `pe`
5. **FCF 为正** — 当前 `fcf_positive`

## 工作流

```python
from lib.research_workflow import build_thesis_tracker
result = build_thesis_tracker(features, raw, direction="long")
```

## 输出

| Pillar | Target | Current | Trend | Verdict |
|---|---|---|---|---|
| 营收增速 > 15% | 15%+ | 18.5% | stable | ✅ |
| ROE > 15% | 15%+ | 11.8% | concerning | ⚠️ |
| Stage 2 | Stage 2 上升 | Stage 2 | stable | ✅ |
| PE < 40 | < 40 | 35 | stable | ✅ |
| FCF 为正 | 持续正 | 正 | stable | ✅ |

## 信念度判定

- `thesis_intact_pct ≥ 80%` → **High** · 建议：Hold / Add
- 60-80% → **Medium** · Hold
- 40-60% → **Low** · Trim / Review
- < 40% → **Broken** · **Exit**
