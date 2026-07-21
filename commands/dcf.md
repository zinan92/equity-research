---
name: dcf
description: 对指定股票做机构级 DCF 估值 — WACC + 两段 FCF + 终值 + 5×5 敏感性表
---

# /dcf <股票代码或名称>

对目标股票做完整的 DCF 估值，按照 JPMorgan / Goldman / Morgan Stanley 投行标准。

## 工作流

1. 解析股票代码（`002273.SZ` / `00700.HK` / `AAPL` 等）
2. 拉取基础数据：`python skills/deep-analysis/scripts/fetch_basic.py <ticker>`
3. 提取特征：`from lib.stock_features import extract_features`
4. 调用 DCF：
   ```python
   from lib.fin_models import compute_dcf
   dcf = compute_dcf(features, assumptions={
       "stage1_growth": 0.10,
       "stage2_growth": 0.05,
       "terminal_g": 0.025,
       "target_debt_ratio": 0.30,
   })
   ```
5. 展示结果：
   - WACC 分解（k_e / k_d / weights）
   - 10 年 FCF 预测（显式期 5 + 过渡期 5）
   - 终值 + PV 折现
   - EV → 净债 → 股权 → 每股内在价值
   - 安全边际 % 和结论（深度低估/合理/高估）
   - **5×5 敏感性表**（WACC ±200bp × 终值 g ±100bp），中心格等于基础案例

## A 股默认参数（可覆盖）

- 无风险利率 2.5%（10Y 国债）
- 股权风险溢价 6%
- 标准税率 25%（高新 15%）
- Beta 1.0
- 终值永续 2.5%

## 方法论参考

`skills/deep-analysis/references/fin-methods/README.md`
