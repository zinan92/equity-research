# Paid Community Pilot v1

状态：M7 人工履约合同；**不是 Product OS Gate B / Paid Pilot Ready**。

## 用户结果

Park 可以继续使用已经审核通过的外部收款方式服务少量社群成员：款项在平台外发生，Owner 核验后记录付款，成员立即获得与当前 canonical portfolio 精确绑定的 8 股研究包；退款会撤回权益并注销旧会话。平台不提供 checkout、自动续费或支付商 webhook。

## 第一性原理边界

付费权益的可信来源不是 `members.tier`，而是不可回写的账单事件：

```text
外部付款凭据
  → Owner + CSRF 人工核验
  → payment_confirmed append-only event
  → effective entitlement = paid
  → exact content-addressed research-pack.zip

外部退款凭据
  → refund_confirmed append-only event
  → paid entitlement removed
  → all prior member sessions revoked
```

- `manual_external`：Owner 记录真实外部凭据。它仍只是内部人工记录，不是支付商回调或银行对账证明。
- `acceptance_test`：机器验收专用。事件永久带 `test_mode=true`，不进入 `realized_revenue_minor`。
- 数据库中遗留的 `tier=paid`、前端按钮或邀请码都不能产生 Paid 权益。
- 当前产品明确返回 `paid_pilot_ready=false`、`online_checkout=false`、`payment_provider_connected=false`。

## 数据合同

`billing_events` 只允许追加：

- `payment_confirmed` 绑定 member、provider event、外部 reference、CNY 金额、发生时间、当前 portfolio identity 与 research-pack hash。
- `refund_confirmed` 绑定原付款事件，并继承原付款的 portfolio 与 research-pack identity。
- `(provider, provider_event_id)` 与同类 `(provider, payment_reference)` 均唯一；金额必须是整数分，退款不得早于付款。
- 完全相同的重放返回原事件及原 release identity，即使当前 release、停止新付款开关或 366 日录入窗口已经变化；内容不同的重放拒绝。
- 退款只读取原付款事件，不依赖当前 portfolio 或研究包可用，因此内容故障时仍可撤权和退款。
- exact-SQL trigger 禁止 update/delete；trigger 缺失或被同名 no-op 替换时初始化失败。

`billing_settings` 是唯一可变控制面，只控制是否允许新的人工付款确认。每次变化另写入 append-only `billing_control_events`；停止新付款不阻止退款。

账单、会员/会话和反馈保存在仓库外的 `PARK_AUTH_DB`。研究库与 release 保持只读；任何账单表出现在 research DB 都属于部署错误。

## 研究包合同

每个 release 构建一个 `canonical-research-pack-v1`：

- 当前 `portfolio.json`、`diff.json`、当前/历史 ledger；
- 精确 8 份 canonical report JSON；
- `pack-manifest.json` 和 deterministic ZIP；
- 文件哈希、portfolio/snapshot/report-bundle identity 与 release identity 全部绑定。

runner 在每次启动前重新验证 release manifest、源码、8 份报告、pack manifest、所有成员文件和 ZIP 内容，并逐个比较包内 portfolio/diff/ledger/history/report 与 canonical release 原件。Paid/Owner 下载时服务端重复同一绑定验证；路径固定为 `/downloads/private-preview/research-pack.zip`，不接受用户提供文件名。

## API 与权限

| 路由 | 权限 | 语义 |
|---|---|---|
| `GET /api/billing/me` | 登录成员 | 自己的派生账单状态与研究包身份 |
| `GET /api/billing` | Owner | 全量账单与对账摘要 |
| `GET /api/billing/export` | Owner | 内容寻址 JSON 导出 |
| `GET /api/billing/settings` | Owner | 新付款总开关 |
| `POST /api/billing/payment` | Owner + CSRF | 人工确认付款，幂等追加 |
| `POST /api/billing/refund` | Owner + CSRF | 人工确认退款、撤权、注销会话 |
| `POST /api/billing/settings` | Owner + CSRF | 停止/恢复新的人工确认 |
| `GET /downloads/private-preview/research-pack.zip` | 派生 Paid 或 Owner | 精确研究包下载 |

匿名请求返回 401；普通成员访问 Owner 路由返回 403；M7 未启用时所有 billing/pack 路由保持 M6 的 404 private-preview surface。

## Owner 履约步骤

1. 在外部渠道核对付款人、金额、币种和不可重复 reference。
2. 在 Owner 面板填写成员邮箱、分金额、付款 reference 和事件 reference。
3. 确认成员页面显示 Paid，并让成员下载当前 8 股研究包。
4. 发生退款时，用原 `payment_event_id` 记录退款；系统立即撤权并注销其旧会话。
5. 每次运营结束导出 `/api/billing/export`，核对真实事件、测试事件和 `realized_revenue_minor`。

不要把 `acceptance_test`、截图、Owner 权限或 self-reported reference 当作真实收入证明。

## 停止收费与恢复

- 紧急停止：Owner 面板关闭“允许新的人工付款确认”。已有 Paid 权益继续可用，退款仍可执行。
- 对账：导出 billing JSON；测试事件必须与真实事件分列，测试事件净收入永远为零。
- 产品关闭：停止新付款 → 处理全部应退款/履约 → 导出 billing/feedback → 归档仓库外 auth DB → 下线 tunnel。
- release 回滚只能回到同样包含 M7 billing schema 与 pack 验证的安全版本，不能回到缺少研究包的 M6 release 后继续声明人工付费履约可用。

## 验收

```bash
python3 -m unittest product.tests.test_paid_community_pilot_v1 -q
python3 scripts/verify_paid_community_pilot.py
python3 scripts/adversarial_verify_paid_community_pilot.py
python3 scripts/verify_baseline.py
```

外部验收只使用 `acceptance_test`：开通 → 现有 session 获权 → 下载 exact pack → 幂等/冲突重放 → 停止新付款 → 退款 → session 失效 → 重登无权。验收前后 `realized_revenue_minor` 必须相同。

## In scope / Out of scope

In scope：少量成员、人工外部付款确认、退款撤权、账单导出、停止新付款、exact 8 股研究包、外部 HTTPS 验收。

Out of scope：在线 checkout、支付商 SDK/webhook/签名、正式商户审核、自动续费、价格/优惠券/税务、分销佣金、真实生产小额支付、Gate B / Scale Ready。

进入 Product OS Gate B 仍必须补齐并实际验证：正式支付账户和类目批准、沙箱与真实小额支付/退款/对账、webhook 验签重试、合规页面、客服、告警、成本限流与一级归因。
