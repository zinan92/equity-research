# 宏观 K 线产品领域词汇

## Reader contract

Daily edition 与 Weekly edition 共用同一个用户阅读结构。每个资产先展示身份与观察时点，再按周期展示图表和解释，随后给出位置、结构、赔率以及综合结论与市场含义。
_Avoid_: 两套互不相容的日报/周报阅读范式

## Daily edition

以交易日为观察边界的宏观 K 线报告。日线是所有资产的基础周期，盘中周期只在真实数据源声明支持时出现。
_Avoid_: 把未纳入合同的周期标成失败

## Weekly edition

以周度观察边界的宏观 K 线报告。周线解释长期位置，日线解释结构，并在资产合同允许时加入 4 小时上下文。
_Avoid_: 用周报周期规则推断日报周期

## Period card

一个用户可读的周期单元，由图表、周期文字分析和观察时点组成。未纳入合同的周期不显示；已请求但抓取失败的周期保留暂缺状态。
_Avoid_: 只显示“数据覆盖/周期可用”而不展示图表

## LLM provider fallback

所有需要模型解释的层都遵循同一 fallback 规则：单资产周期解释、单资产综合结论、机制解释和跨资产总 thesis 在 DeepSeek 最终失败时由 Codex CLI 接管。最终失败包括余额、网络、超时、schema、引用校验及其它 provider 错误；数据源问题不由模型 fallback 修复。
_Avoid_: 只为总 thesis fallback，或用模型补造行情

## Codex fallback boundary

Codex CLI 只接收冻结 evidence 和结构化任务，不能访问外部工具、重新获取行情、读取其它日报、修改文件或运行时状态，只返回待验证 JSON。
_Avoid_: 让 Codex 绕过 evidence/schema 校验

## Provider disclosure

正文保持可读；报告底部的来源与状态区域显示实际 provider、是否发生 fallback 以及简短失败分类。若 DeepSeek 与 Codex CLI 均失败，必须明确写出两者均未生成解释及各自原因。
_Avoid_: 用笼统的“综合 thesis 不可用”掩盖双重失败

## Degraded edition

当两个模型都失败时，报告仍发布真实图表和代码读数，但不生成模型 thesis；这是一份明确标注的降级版，不是完整模型分析。
_Avoid_: 复用旧 thesis 或把 deterministic 读数包装成 LLM 结论

## Delivery surfaces

网页、Obsidian 和小程序文章共享同一个用户内容结构。三者都必须真正呈现周期图表和文字分析；HTML 使用静态图片，Markdown 使用图片引用，小程序使用文章图片资源。snapshot ID 和内部状态不能替代用户可见图表。
