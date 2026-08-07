# M1 市场数据权利路线 · provider options

Status: **CANDIDATE RESEARCH / NO PROVIDER APPROVED / OUTBOUND NOT AUTHORIZED**

As of: `2026-08-07`

Target approval scope hash: `fbd101f1933bbc3603d4e35f4093d9bddede2520cd903a97b57d8aa6d71746bd`

这份矩阵只回答“下一步该向谁问、必须问什么”，不证明任何数据商已经允许 M1 使用。没有覆盖 exact provider、字段、衍生输出、最多 20 人、一对一外发、30 天保存、用户导出和 paid 的书面许可，就一律是 `unknown/blocked`。

## 1. 当前 source 结论

| Source | 本地研究 | 20 人私域外发 | Paid | 衍生输出展示 | 当前结论 |
| --- | --- | --- | --- | --- | --- |
| Yahoo Chart | 仓库仅按 `local_evaluation_only` 使用 | 未取得书面权利 | 未证明 | 未证明 | `blocked_pending_rights` |
| Tencent K-line | 仓库仅按 `local_evaluation_only` 使用 | 未取得书面权利 | 未证明 | 未证明 | `blocked_pending_rights` |

当前 scope 同时含两个 source key。一个真实的 `market_data_rights` receipt 必须由覆盖两者的合同包证明，并在安全摘要中把 `covered_source_keys` 精确写成 `yahoo_chart + tencent_kline`。任何只覆盖其中一个 source 的许可不能解锁。

## 2. 可替换 provider 候选

| 候选 | 官方公开信息能证明什么 | 仍不能证明什么 | Target-use status | 联系入口 |
| --- | --- | --- | --- | --- |
| Twelve Data | 官方条款区分 internal、external display/redistribution 和 derived data；商业展示取决于订阅层级、Redistribution Rights Add-On 或单独协议。官方支持页还说明美国以外商业使用需要额外批准，redistribution 需要单独协议。 | 未证明其当前合同覆盖本产品的中国大陆 20 人 paid 私信、全部目标交易所、字段、30 天缓存、CSV/JSON 导出和衍生 risk labels。第三方交易所许可/费用也可能另需处理。 | `candidate_requires_written_scope_addendum` | [Terms](https://twelvedata.com/terms) · [Commercial and personal usage](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage) · [EOD market-data pricing](https://support.twelvedata.com/en/articles/12682324-end-of-day-eod-pricing-market-data) |
| Wind | 官网展示股票、债券、基金、衍生品、指数、宏观等覆盖，以及 API、文件同步和网页组件等交付能力。 | 官网能力说明不是外部商业分发许可；未证明 20 人 paid 私信、衍生标签、缓存、导出及目标交易所权利。 | `candidate_sales_confirmation_required` | [Wind 官方产品与申请试用](https://www.wind.com.cn/portal/zh/Home/) |
| Choice 数据 | 官网展示终端/API 等产品能力并提供企业联系入口。标准用户协议只证明一般终端使用合同存在。 | 未找到公开页面明确允许把目标字段或衍生风险卡向 20 名付费会员外发；不能把终端账号许可解释成 redistribution 权利。 | `candidate_sales_confirmation_required` | [Choice 下载与联系](https://choice.eastmoney.com/product/download_center.html) · [产品能力](https://choiceweb.eastmoney.com/choiceh5contact/Intelligent) · [用户协议](https://choice.eastmoney.com/html/userprotocol/userprotocol.html) |

公开页面会变化，也不能替代签约文件。最终 receipt 必须记录原件 SHA-256、受控 locator、签发/到期日和独立复核身份。

## 3. 推荐采购路径

推荐先比较一个 A 股权威 provider（Wind 或 Choice）与一个全球/跨资产 provider（Twelve Data）的组合报价，并要求数据商在同一附录里逐项回答 `market_data_rights.request.md`。选择 provider 后，必须先回到合同工序：

1. 用拟签约 provider、source key、字段和衍生输出更新 canonical entry；
2. 重算 scope hash；
3. 重新生成五份批准请求；
4. 取得 provider/交易所覆盖完整范围的书面许可或已执行合同包；
5. 原件留在受控系统，仓库只提交安全摘要及 hash；
6. verifier `--require-go` 通过前，不外发、不收真实持仓、不收费。

不建议把“现有抓取 endpoint 能返回数据”当作生产采购路线。HTTP 可用性、SDK 安装或付费订阅本身都不等于外部商业分发权。

## 4. 数据商必须逐项确认

- exact instrument/exchange coverage：S&P、Nasdaq、上证、科创 50、WTI、黄金、白银、KOSPI、Nikkei 及对应 A 股研究字段；
- exact fields：日线 OHLC、市场时间戳、session metadata、A 股指数行情；
- derived outputs：risk state、posture、style、cross-asset leadership 与 A 股风格/风险标签；
- audience/channel：最多 20 名中国大陆受邀会员，一对一私信，禁止群发和公开链接；
- commercial/display：paid concierge、external display、人工复核访问、署名要求；
- storage/export：30 天缓存、用户 JSON/CSV 导出、不得原始行情再分发；
- exchange dependencies：所需交易所批准、报告、费用和地域限制；
- term：生效、到期、终止、scope 变化、事故与删除后的处理。

## 5. 立即停止条件

以下任何一种回答都保持 `market_data_rights=blocked`：

- “按一般订阅条款应该可以”，但不写 exact target scope；
- 只允许 internal/local/non-commercial；
- 只覆盖一个 source key 或部分交易所；
- 不允许 paid、外部展示、衍生输出、缓存或用户导出中的任一 target use；
- 需要交易所单独许可但该许可尚未取得；
- 只有销售口头承诺、网页功能页、API 成功响应或测试账号。
