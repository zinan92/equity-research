# L2-M4 · 诚实降级输出政策

`product/data_core/output_degradation_policy.py` 是展示许可层：它只消费既有
Tier 与覆盖状态，不计算 Tier，也不改 C1、B6 或 `decision_policy`。

| Tier / 覆盖 | 允许展示 | 严格抑制 |
| --- | --- | --- |
| A / complete | 完整研报、决策摘要、证据、估值方法；仅在既有 decision receipt 存在时展示目标/仓位/行动 | 无政策层自行生成的建议 |
| A / partial 或 missing | 研报/证据与缺口 | 目标价、仓位、行动与高置信表述 |
| B | 研报、摘要、证据、估值方法、带标签的未审阅判断 | 目标价、仓位、行动 |
| C | 证据浏览和明确的 partial-model 缺口 | 研报结论、目标价、仓位、行动 |
| missing | 诊断和缺失原因 | 证据、研报、建议 |

任何 `partial` / `missing` 覆盖都会加入
`coverage_not_complete_no_high_confidence_position`，并显式关闭目标价、仓位与
行动展示。测试覆盖 A/B/C/missing 四种 Tier，证明低覆盖无法绕过该显示边界。
