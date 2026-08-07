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

`python3 scripts/verify_personal_holdings_risk_card_entry.py` 返回 0 只表示这份 blocked 合同真实、完整、未被篡改；只有 canonical checkout 上增加 `--require-go` 也通过，才表示 M1-S2 可以接触测试用户。Production gate 禁止同时使用 test mode、历史 `--reference-time` 或 root/contract/schema path override，避免把 replay/fixture/旧文件冒充当前 go。

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
- 包含 approval key、`approved` 决定、批准机构的 safe identity/type/jurisdiction、允许的方法、独立复核身份与时间；
- 记录受控系统中原件或合同包的 SHA-256 和不泄密的 locator；市场数据合同包必须精确覆盖 canonical 中每个 `source_key`；
- 包含 issued-at、expires-at 和摘要自身的 canonical `receipt_hash`；
- authority 与 verifier 的 safe identity 必须已在 `trust-policy.json` 通过独立身份原件 hash/locator 登记，且 trust policy 为 `ready`；只在批准摘要里自称“律师”“数据商”“Park”或“合规复核人”无效；
- 同一个 approval key 的 authority 与 verifier 必须是不同 safe identity；身份在 receipt 的 `verified_at` 之后才登记，不能追溯验证旧 receipt；
- 每份 production 摘要还必须有 dual-control HMAC，覆盖除 HMAC/receipt hash 外的全部摘要字段；只复制受信 identity、伪造 underlying hash 再自算 receipt hash 仍无效；
- 以 `repo:` 相对路径指向仓库内的安全批准摘要；
- canonical entry 中记录该摘要文件的 SHA-256；
- 不是 `test_only`；
- 在 verifier reference time 未过期。

`verification_method` 与 `authority_type` 必须符合 approval key 的 schema 条件，例如通知渠道不能拿 Park 签字方法冒充渠道管理员确认。测试可以生成 `test_only=true` 的合成批准，但 contract、entry approval 和 safe summary 三层 test flag 必须一致；只要启用 `allow_test_only`，输出就固定 `production_eligible=false`。Production CLI 默认拒绝测试模式。任何 operator 字符串、环境变量、免责声明、口头同意、销售介绍页或测试通过都不能替代批准 receipt。

Hash 证明“摘要绑定哪一份原件”，不自动证明原件真实、签发人有权或法律判断正确。因此原件必须由授权复核人从受控 locator 打开核对；最终 Park owner receipt 还必须确认亲自检查另外四份批准。仓库不得保存合同正文、法律意见全文、个人信息或凭证。

当前 canonical `evidence/market-regime-m1/approval-requests/trust-policy.json` 为 `onboarding_required`，epoch `1`，有效至 `2027-08-07`，没有任何 production authority、verifier 或 production trust root 被信任。身份登记必须另有安全 identity-evidence hash、locator、登记人和时间；五个 key 均有相互独立的 authority/verifier 后，policy 才能改为 `ready`。Ready policy 还必须声明 epoch、签发/到期、`revokes_before_epoch` 和前序 policy hash；过期或被撤销 epoch 不能使用。

Production trust root 的 SHA-256 与当前 ready policy 的 exact receipt hash 必须由 Park 在独立、明确批准的代码合同中同时登记；当前两个 verifier 常量均为 `None`，所以任意 `ready` policy 都会 fail closed。Pin exact policy receipt 可阻止 operator 在 authority 撤销后重放旧的、曾合法签名的 policy。对应至少 32 bytes dual-control secret 只通过目标运行环境的 `PARK_RISK_CARD_TRUST_HMAC_KEY` 提供，不得进入仓库、日志或 request packet。Ready policy 本身和每份 production approval summary 都必须用该 secret 生成 HMAC。这意味着同一 repo operator 即使照抄已信任 identity、手写底层证据 hash 并重算普通 receipt hash，也不能解锁。

HMAC 是对称密钥：任何能读取该 secret 的人都能生成有效 HMAC。因此它只能由与施工/operator 权限隔离的 Park-controlled gate 在签发/验收时临时注入，不能放进普通 CLI shell、常驻网页服务或开发机通用环境。未来若要让多个独立机构自行签发，需迁移到 pinned public-key/Ed25519；在此之前 secret holder 就是 dual-control 审批边界。

五份当前 draft request 由以下命令确定性生成；`--check` 会在 scope 或输出漂移时失败：

```bash
python3 scripts/build_personal_holdings_risk_card_approval_packet.py
python3 scripts/build_personal_holdings_risk_card_approval_packet.py --check
```

- Forwardable Markdown：`docs/market-regime/approval-requests/`
- Machine-readable JSON：`evidence/market-regime-m1/approval-requests/`
- Provider 候选与权利缺口：`docs/market-regime/provider-rights-options.md`

## 8. 激活步骤

1. Park 明确授权发送对应 draft request；发送、签约、购买和接受条款不由 packet builder 自动授权；
2. 在独立 issue 中取得并保存每份安全批准摘要；
3. 确认五份摘要绑定同一个 scope hash；
4. 登记相互独立的 authority/verifier identity，签发带 epoch/有效期/撤销边界的 ready trust policy；
5. 由 Park 独立批准 production trust-root fingerprint 与当前 policy receipt pin，并把 HMAC secret 只注入隔离 gate；
6. 更新 data-source target rights 和 truth boundary；
7. 重新计算 canonical `receipt_hash`；
8. 在无 test/replay/path override 的 canonical checkout 运行：

```bash
python3 scripts/verify_personal_holdings_risk_card_entry.py --require-go
```

9. Park 查看 exact diff、四份外部批准摘要和 verifier 输出后，以 exact-scope owner receipt 明确批准；
10. 只有这时才建立 M1-S2 issue，先做 3–5 人 × 3 个交易日 smoke，再扩到 20 人 × 10 个交易日。

## 9. 停止条件

任何一份 receipt 缺失、过期、scope 不一致、hash 不一致、被拒绝或不允许目标收费/渠道时，readiness 必须回到 `blocked`。M1-S2 不得以“先试一下”“只有熟人”“不展示原始 K 线”或“有免责声明”为由绕过。
