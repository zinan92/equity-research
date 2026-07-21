---
name: screen
description: 量化筛选 — 价值/成长/质量/GARP/做空 5 套筛选标准
---

# /screen <股票代码> [style=quality]

对目标股票跑 5 种经典 quant screen：

| Style | 核心标准 |
|---|---|
| `value` | PE<15 · PB<1.5 · 股息率>3% · FCF>0 · 负债率<50% |
| `growth` | 营收增速>15% · 净利增速>20% · 毛利扩张 · ROE>15% |
| `quality` | ROE 5Y>15% · 净利率>15% · FCF+ · 债务<50% · 护城河≥28 |
| `gulp` | PEG<1.5 · 营收>15% · ROE>15% · Stage 2 |
| `short` | PE>60 · 营收下滑 · ROE<5% · 债务>70% |

## 工作流

```python
from lib.research_workflow import run_idea_screen
result = run_idea_screen(features, style="quality")
```

## 输出

- 每条标准 pass / fail 列表
- `passed / total` 命中率
- `pass_rate_pct ≥ 70%` → 🟢 命中筛选
- `fits_screen` 布尔标记
