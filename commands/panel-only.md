---
description: 只跑 65 人评审团，看 65 位投资大佬怎么投票
argument-hint: "[股票名称或代码]"
---

# 50 贤评审团任务

用户输入: $ARGUMENTS

加载 `investor-panel` skill 并执行：

1. 先调用 `deep-analysis/scripts/fetch_basic.py` 和 `fetch_financials.py` 拿基础数据
2. 然后让 65 位投资者各自按自己的方法论打分（参考 `investor-panel/references/group-{a..i}.md`）
3. 输出**评审团专题报告**（HTML，仅评审团模块），包含：
   - 65 人投票分布柱状图
   - 7 大流派态度对比
   - **The Great Divide 世纪分歧**：评分差最大的两位大佬对撞
   - 每人卡片可展开看打分逻辑 + 模拟评语 + 像素头像

不跑完整 19 维分析，速度更快。
