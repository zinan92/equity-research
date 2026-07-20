---
name: ic-memo
description: 投委会备忘录 — 8 章节结构化决策文档（含三情景回报 + Top 3 风险）
---

# /ic-memo <股票代码>

生成 PE/VC 风格的 Investment Committee Memo，适合正式决策。

## 工作流

1. 采集完整 raw_data + features
2. 调用 DCF / Comps / Porter / DD 前置结果
3. 调用：
   ```python
   from lib.deep_analysis_methods import build_ic_memo
   memo = build_ic_memo(features, raw, dcf_result, comps_result)
   ```

## 输出章节

- **I. Executive Summary** — 建议 + 前 3 风险
- **II. Company Overview** — 行业 / 业务 / 市值 / 营收
- **III. Industry & Market** — TAM / 增速 / 生命周期
- **IV. Financial Analysis** — 5Y ROE / 净利率 / 债务 / FCF
- **V. Valuation** — DCF + Comps 双路径
- **VI. Risks & Mitigants** — 5 条主要风险 + 严重度 + 缓解措施
- **VII. Returns Scenarios** — Bull / Base / Bear 三情景（含概率）
- **VIII. Recommendation** — PASS / CONDITIONAL PASS / HOLD / REJECT

## 推荐逻辑

质量分 (ROE 持续性 + 现金流 + 护城河 + 净利率) + 估值分 (安全边际) → 综合得分决定建议。
