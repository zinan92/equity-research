# Canonical Portfolio and Model Ledger v1

## User outcome

面向 1000 万元以上、以六个月至三年为持有周期的长期资金，产品直接给出 6–12 只 A 股的股票名称、建议仓位、现金比例和本期动作，并且能回答“相对上期为什么变了”。每个数字都能回到同一时点的 canonical snapshot、标准研报和证据身份。

## Contract

```text
retrospective REAL reference (non-publishable) OR attested REAL current snapshot
  -> exact report identity per ticker
  -> deterministic scoring and allocation constraints
  -> content-addressed canonical portfolio version
  -> period-over-period diff
  -> independent append-only model ledger
  -> API + HTML / desktop PNG / mobile PNG / PDF
```

AI 可以解释冻结证据，但不能设置或修改权重。v1 的权重只来自版本化的确定性配置与约束引擎。

## Hard constraints

- 股票数量：6–12 只。
- 单股仓位：5%–15%。
- 单一行业：不超过 30%。
- 现金：10%–40%。
- 股票与现金合计：精确等于 100%。
- 任一股票必须绑定与组合相同 snapshot 的 report hash、model version、evidence status 和 research depth。
- current pointer、portfolio payload、period diff 与 ledger 均使用内容哈希；不匹配时 fail closed。

这些约束不是前端提示。`validate_portfolio_version()` 在生成、读取和 API 返回前执行；无效组合不会被降级展示。

## Version and truth model

`portfolio_id` 由完整 payload hash 派生。同一份输入重放得到相同身份；snapshot、研报、模型、配置或权重变化都会产生新版本。`current.json` 只保存指向已验证版本的哈希指针，历史文件不因新一期生成而改写。

M5 验收包含两个已保存的 REAL snapshot：

- `2026-07-17`：`retrospective_reference_only`，只证明已保存 REAL 输入可以事后重放；因为当时没有同步生成 content attestation，它不属于可发布 canonical current，也没有冒充当日已发布持仓。
- `2026-07-21`：当前模型建议，8 只股票 82% + 现金 18%；不是券商账户持仓，也没有自动成交。

当前 5 只股票绑定 `deep` 研报，3 只绑定明确标注的 `quantitative_baseline`。完整的组合身份不会把 baseline 冒充深度研究。

## Model ledger

组合版本与模拟调仓账本存放在独立 SQLite 文件中。版本、订单和订单事件均由 exact-SQL trigger guard 保护为 append-only。每期先按上期目标仓位和两期参考价计算价格漂移后的账面权重，再计算本期目标与漂移权重之间的调仓差额：

```text
marked_value_i = previous_target_i × current_price_i / previous_price_i
drifted_weight_i = marked_value_i / (sum(marked_values) + previous_cash)
rebalance_i = current_target_i - drifted_weight_i
```

状态机为：

```text
planned -> pending -> filled | unfilled
```

`filled` 必须绑定下一可交易日、开盘价、来源 snapshot 和 source row hash；没有可核验开盘价时保持 pending 或进入 unfilled，不生成虚构成交。该账本只衡量模型建议的后续表现，不连接券商、不改变真实持仓。

## Product endpoints

- `GET /api/canonical/portfolio`：重新验证 current pointer 和完整组合后返回当前版本。
- `GET /api/canonical/portfolio/history`：返回所有通过完整校验的历史版本。
- `GET /api/canonical/portfolio/ledger`：返回并重新核对当前组合变化的模型账本；缺失、空账本或损坏时返回 `409`。
- `GET /api/canonical/portfolio/ledger/history`：返回与组合版本逐期对应的完整模型账本历史。

生成与独立验收：

```bash
python3 scripts/generate_canonical_portfolio.py
python3 scripts/verify_canonical_portfolio.py
python3 scripts/adversarial_verify_canonical_portfolio.py
python3 -m unittest product.tests.test_canonical_portfolio_v1 -v
```

生成器输出 JSON、HTML、桌面/移动长图和 PDF。独立验证器重新读取 runtime state，并自己启动浏览器重测 DOM 高度、重渲染两张 full-page PNG、比较像素文件哈希；它不把生成器回执当成独立事实来源。

## In scope / out of scope

In scope：固定 8 股研究范围、两个连续真实快照、确定性权重、组合版本差异、模拟调仓账本、API 和发布级视觉证据。

Out of scope：用户画像输入、全市场自动选股、券商账户、自动交易、真实持仓同步、公网部署、支付订阅和个性化适当性判断。

## Gotchas

- 组合总和为 100% 不代表组合合格；单股、行业、现金和报告身份必须同时通过。
- REAL snapshot 不代表模型在历史当日已经公开发布；历史补算必须标记 retrospective。
- `filled` 是模型账本的可复算模拟成交，不是真实交易回执。
- 自洽 hash 不能证明 diff 或 ledger 正确；独立验证器必须从两个组合重算 diff，从逐股漂移重建 expected orders，并把 filled 逐笔核对到 attested REAL source bar。
- 把 3 份 quantitative baseline 放进组合不等于把它们升级为 deep；研究深度必须逐股可见。
- HTML 中存在全部字段不代表移动端可读；验收必须检查真实 full-page 截图，而不是只检查 DOM。
