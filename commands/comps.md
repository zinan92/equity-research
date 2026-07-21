---
name: comps
description: 同行对标相对估值 — PE/PB/EV-EBITDA 分位分析 + 隐含目标价
---

# /comps <股票代码>

对目标股票做机构级 Comparable Company Analysis，识别相对同行的估值位置。

## 工作流

1. 拉取目标股票基础数据 + 同行列表 (`fetch_similar_stocks.py`)
2. 调用：
   ```python
   from lib.fin_models import build_comps_table
   comps = build_comps_table(target, peers)
   ```
3. 输出：
   - 同行池（默认 4-10 家）
   - 关键倍数统计：min / p25 / median / p75 / max / mean
   - 目标公司在每个倍数上的百分位排名
   - 中位 PE × EPS → 隐含每股价
   - 中位 PB × BVPS → 隐含每股价
   - 估值结论（便宜 / 合理偏低 / 合理偏高 / 昂贵）

## 展示规范

- 峰值排序：PE / EV-EBITDA / P/S 三栏为主
- 颜色：低于 p25 标绿，高于 p75 标红
- 百分位：0-25 便宜 / 25-50 合理偏低 / 50-75 合理偏高 / 75-100 昂贵
