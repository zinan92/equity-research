# L2-M3 · 三行业估值 profile

实现入口：`product/data_core/valuation_profiles.py`。

| Profile | 计算族 | 必需行业输入 | 未满足或未审阅时的行为 |
| --- | --- | --- | --- |
| `manufacturing` | FCFF DCF，复用现有确定性引擎及其可比 EV/EBITDA、历史 PE 交叉检查 | 五年财务序列、现金债务与股数、市场快照、情景假设 | 缺输入 `blocked`；假设未真人审阅为 `partial`。 |
| `consumer` | DCF + 历史 PE + 同行 PE | 另加量/价/结构、渠道库存、现金转化、派息政策和同行 PE | 缺任一驱动或比较输入 `blocked`；不以制造业 capex 叙事替代消费驱动。 |
| `bank` | 剩余收益 + 股利折现 + 同行 P/B | 账面价值、股数、ROE、资本成本、派息、增长、CET1/总资本/RWA、NIM、信用成本、不良率及经审批的同业银行集合 | 缺输入 `blocked`；未审阅为 `partial`。绝不调用 FCFF DCF。 |

三者均要求 receipt-bound 的来源身份和显式 `assumption_review_status`。即使模型计算成功，输出也显式禁止改变章节契约、Tier、目标价、仓位和行动；它是给既有 C2 receipt adapter 的行业模型选择层，不是研究完成或投资建议。

验证：`python3 -m unittest product.tests.test_valuation_profiles -v`。测试覆盖制造业未审阅降级、消费双 PE 交叉检查、银行无 DCF 路径及缺失输入 fail-closed。
