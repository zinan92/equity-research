---
name: initiate
description: 生成机构风格首次覆盖报告 — Executive Summary + 投资论点 + 估值桥 + 风险
---

# /initiate <股票代码>

按照 JPMorgan / Goldman / Morgan Stanley 首次覆盖报告格式，生成一份完整的 initiating coverage。

## 工作流

1. 全量采集（`run_real_test.py <ticker>`）
2. 计算 DCF + Comps (dim 20)
3. 调用：
   ```python
   from lib.research_workflow import build_initiating_coverage
   report = build_initiating_coverage(features, raw, dcf, comps)
   ```
4. 输出六个标准章节：
   - **I. Executive Summary** — 推荐评级 / 目标价 / 空间 %
   - **II. Investment Thesis** — 3-5 条核心看多支柱
   - **III. Valuation Bridge** — DCF + Comps + Blended
   - **IV. Key Risks** — 5 条风险 + 严重度
   - **V. Financial Snapshot** — 5 年历史 ROE/营收/净利
   - **VI. Coverage Universe Positioning** — 分析师覆盖密度

## 评级规则

- Upside ≥ 25% → 买入 (Overweight)
- 10-25% → 增持 (Outperform)
- -10-10% → 持有 (Neutral)
- < -10% → 减持 (Underperform)
