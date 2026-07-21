---
name: catalysts
description: 构建催化剂日历 — 已发生事件 + 未来 60 天关键节点 + 影响分级
---

# /catalysts <股票代码>

## 工作流

1. 从 dim 15 (事件驱动) 提取历史事件 + 预排标准日程
2. 调用：
   ```python
   from lib.research_workflow import build_catalyst_calendar
   cal = build_catalyst_calendar(features, raw)
   ```

## 输出

- **已发生事件**（按时间倒序，分类打标 high/medium/low）
- **未来 30 天**：
  - 季报披露窗口（高影响）
  - 股东大会 / 投资者关系活动（中影响）
- **未来 60 天**：
  - 行业展会 / 新品发布（中影响）
- **宏观节点**：
  - 美联储 FOMC 会议（参考）
- 统计：`high_impact_count`, `next_30d` 列表

## 展示样式

```
2026-04-30  [HIGH] 2026 Q1 季报披露（关注营收/净利超预期与否）
2026-05-15  [MED]  股东大会
2026-06-15  [MED]  行业展会
2026-05-28  [LOW]  美联储 FOMC (参考)
```
