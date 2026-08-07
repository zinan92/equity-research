# 个人持仓风险卡 · M1.0 准入合同

Status: **`BLOCKED`**

Contract: `personal-holdings-risk-card-entry-v1` / `1.0.0`

Canonical receipt: `evidence/market-regime-m1/entry-readiness.json`

本文冻结 08:45 A 股开盘前个人持仓风险卡在接触第一位测试用户之前必须满足的准入条件。它是产品和工程的 fail-closed 合同，不是法律意见、数据授权、收费批准或发布批准。

## 1. 当前结论

当前不得联系 M1 测试用户、收集真实持仓、发送卡片、安装外部通知、收费或公开发布。原因不是模型或网页不可用，而是以下五份范围绑定的批准收据均不存在：

1. `market_data_rights`：数据提供方对目标字段、衍生输出、20 人私域发送、30 天保存及收费范围的许可；
2. `securities_service_boundary`：专项法律意见或持牌合作路径，明确允许与禁止输出；
3. `personal_information_processing`：持仓数据的最小必要、同意、人工访问、导出、删除和事故响应方案；
4. `notification_channel`：具体发送渠道、人数、内容、退订和停止开关的批准；
5. `park_owner_approval`：Park 对完全相同 scope 的明确准入确认。

Canonical receipt 因此必须保持：

```json
{
  "readiness_status": "blocked",
  "blocked_by": [
    "market_data_rights",
    "securities_service_boundary",
    "personal_information_processing",
    "notification_channel",
    "park_owner_approval"
  ]
}
```

`python3 scripts/verify_personal_holdings_risk_card_entry.py` 返回 0 只表示这份 blocked 合同真实、完整、未被篡改；只有增加 `--require-go` 也通过，才表示 M1-S2 可以接触测试用户。

## 2. 冻结的目标范围

| 项目 | M1 target |
| --- | --- |
| 产品 | A 股开盘前个人持仓风险卡 |
| 使用场景 | 每个 A 股交易日 08:45 的 90 秒风险卡 |
| 地区 | 中国大陆（`CN`） |
| 用户 | 最多 20 名受邀私域会员 |
| 发送 | 一对一获批私信渠道；禁止群发和公开链接 |
| 数据保存 | 30 天；用户可撤回、导出和删除 |
| 最小持仓输入 | ticker、组合权重、持有周期、用户自定义风险规则 |
| 明确不收 | 券商密码/session、账户余额、成本价、完整交易历史 |
| 收费 | 目标 scope 为 paid；在批准 receipt 缺失时不得收费 |
| 市场数据 | 当前 Yahoo Chart / Tencent K-line 仅 `local_evaluation_only`，M1 外发权利未证明 |

批准 receipt 必须覆盖上述完整范围。批准“本地研究”“非商业”“仅截图”或其他较窄范围，不得被解释为 M1 target 已获批准。

## 3. 08:45 point-in-time 合同

- 时区：`Asia/Shanghai`；
- 卡片计划时间：`08:45:00`；
- 最晚可用事实：`08:44:59` 已知的信息；
- A 股价格与内部结构：只使用上一已完成交易日，不能用当天开盘后信息补写；
- replay：任何 known-at 晚于 cutoff 的观察都不能进入原卡；
- `fresh`：只支持有证据的依赖结论；
- `partial`：只降级受影响结论；
- `stale` / `unknown`：阻断受影响结论，不用上次文案或 AI 推测补齐。

原始 morning card 一旦冻结不可重写。后续纠错只能追加 correction receipt，盘后结果只能追加 outcome observation。

## 4. 允许和禁止的产品能力

M1 允许的能力：

- 解释市场状态、风险偏好、攻防和风格；
- 把已经有证据的行业/风格暴露映射到用户组合；
- 给出观察条件、失效条件和用户自己定义的规则；
- 展示来源身份、新鲜度、冲突和长期校准。

M1 永久禁区：

- 具体买入、卖出、加仓、减仓或择时指令；
- 目标价、预期收益和仓位指令；
- 承诺或暗示保证收益；
- 券商连接、账户操作和自动交易。

“非投资建议”免责声明不能把被禁止的能力变成允许。证监会现行规则把有偿提供证券品种选择、投资组合等建议纳入证券投资顾问业务边界；利用软件提供选股、择时等建议也有专门监管要求。最终范围必须由专项法律意见或持牌合作确认，而不是由本文自行判断：

- [证券投资顾问业务暂行规定（证监会法规库）](https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?navbarId=1&secFutrsLawId=3636153f028c44e9a00de8ed06494385)
- [证监会规范利用“荐股软件”从事证券投资咨询业务行为](https://www.csrc.gov.cn/csrc/c100028/c1002385/content.shtml)

## 5. 持仓隐私合同

每个用户必须有 scope-bound、可撤回的显式同意。人工访问只允许 owner 授权、最小必要且有审计记录。

- 导出 SLA：24 小时；
- 删除 SLA：24 小时；
- 删除后只保留不含持仓正文的最小删除 receipt；
- 错误组合身份：立即停止受影响发送，通知 owner，纠正后才能恢复；
- 未授权披露：停止全部发送、保留最小审计并升级处理；
- 第一张外发卡之前必须证明总停止开关可用。

个人信息处理范围还需要专项审阅。《个人信息保护法》官方文本：[全国人大](https://www.npc.gov.cn/WZWSREL25wYy9jMi9jMzA4MzQvMjAyMTA4L3QyMDIxMDgyMF8zMTMwODguaHRtbD9yZWY9aW1i)。

## 6. 人工复核与纠错

M1 concierge 的每张卡在送达前必须由获授权的人完成：

1. 数据新鲜度和质量状态；
2. 证券身份；
3. 事实与 evidence identity；
4. 卡片与收件人组合的 owner match；
5. 不含禁止动作语言；
6. 存在可检查的失效条件；
7. 私密发送目的地正确。

普通事实纠错 SLA 为 4 小时；隐私或身份错误按事故流程立即停止。纠错不得覆盖原卡。

## 7. 批准 receipt 规则

每项 approved receipt 必须：

- 使用 `personal-holdings-risk-card-approval-v1`；
- 绑定 canonical approval scope 的 SHA-256；该 scope 同时包含产品、provider/字段/衍生输出、08:45 截点、语言边界、个人数据、人工复核和事故响应合同；
- 包含 approval key、authority、issued-at、expires-at 和 `approved` 决定；
- 以 `repo:` 相对路径指向仓库内的安全批准摘要；
- canonical entry 中记录该摘要文件的 SHA-256；
- 不是 `test_only`；
- 在 verifier reference time 未过期。

测试可以生成 `test_only=true` 的合成批准，但 production CLI 默认拒绝。任何 operator 字符串、环境变量、免责声明、口头同意或测试通过都不能替代批准 receipt。

## 8. 激活步骤

1. 在独立 issue 中取得并保存每份安全批准摘要；
2. 确认五份摘要绑定同一个 scope hash；
3. 更新 data-source target rights 和 truth boundary；
4. 重新计算 canonical `receipt_hash`；
5. 运行：

```bash
python3 scripts/verify_personal_holdings_risk_card_entry.py --require-go
```

6. Park 查看 exact diff 和 verifier 输出后明确批准；
7. 只有这时才建立 M1-S2 issue，先做 3–5 人 × 3 个交易日 smoke，再扩到 20 人 × 10 个交易日。

## 9. 停止条件

任何一份 receipt 缺失、过期、scope 不一致、hash 不一致、被拒绝或不允许目标收费/渠道时，readiness 必须回到 `blocked`。M1-S2 不得以“先试一下”“只有熟人”“不展示原始 K 线”或“有免责声明”为由绕过。
