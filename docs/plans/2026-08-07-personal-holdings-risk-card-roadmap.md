# A 股开盘前个人持仓风险卡 · 产品路线图

> 状态：`Execution approved 2026-08-07 · M1 in progress`
>
> 已批准方向：以“08:45 A 股开盘前 90 秒个人持仓风险卡”为首个场景。
>
> Park 以“去做吧，直到做完”批准按 5 个 v1 milestone + 1 个有条件 post-v1 milestone 执行。该批准授权按“一 Story = 一 issue = 一 branch = 一 PR”开发，不替代 M1.0 所需的数据权利、专项合规、个人信息、通知渠道或收费批准。

## 1. 结论

现有 Market Regime Radar 作为 **M0 已完成底座**保留。第一版成熟产品需要 **5 个顺序 milestone、约 16 张独立 story issue/PR**；M5 通过后，再决定是否启动面向公共传播与规模化的 **M6 post-v1**。

三个可交付台阶：

- **M4 完成：可用产品**——用户能收到个人化开盘前卡，并在收盘后看到复盘。
- **M5 完成：第一版成熟付费私测**——真实用户、真实付费、真实留存，安全和合规边界可运行。
- **M6（有条件）：可规模化产品**——只有 M5 达标且公共传播权利获批后，才重新规划公共内容获客、自助 onboarding、分享和运行 SLA。

在单一主执行流、Milestone 顺序作业、WIP 不超过 3、预留 20% 工程缓冲的假设下：

- 到 M4：约 **7–9 周**；
- 到 M5：约 **12–15 周**，其中包含至少 20 个交易日的真实私测观察；
- M6 不在 v1 排期内，M5 的留存、获客和运行数据出来后再估算。

以上是容量假设，不是承诺日期。当前没有可用的近三 sprint velocity；用户招募、数据授权、合规意见和通知渠道审批是日历时间关键路径，不能靠增加 agent 线性压缩。

## 2. 最终用户结果

用户只提供最少必要信息：持仓代码、组合权重、持有周期和自定义风险规则，不要求券商密码、账户余额或成本价。

每天 08:45，用户在 90 秒内得到：

1. 隔夜全球市场发生的实质变化；
2. Risk On / Risk Off、进攻 / 防守、科技 / 红利状态；
3. 哪些个人持仓受到顺风、逆风或风格错配影响；
4. 当天需要观察的 2–3 个条件；
5. 当前判断的失效条件；
6. 与前一日相比“什么真正变了”；
7. 收盘后不可回写的判断复盘和长期校准记录。

未获得相应资质或持牌合作前，产品只提供研究解释、风险暴露、条件提醒和用户自定义规则，不输出具体买卖、目标价、仓位指令或自动交易。

## 3. 当前可复用底座与边界

### 3.1 直接复用

- `product/data_core/market_regime_data.py`：九个主图资产、三个证据 probe、immutable raw/normalized receipt、freshness 和 last-good 机制。
- `product/data_core/market_regime_model.py`：四维确定性市场状态、情景、置信度、背离和失效条件。
- `product/market_regime_runtime.py`：只读 API bundle、hash/schema/path 校验、失败时保留上一份 cohesive bundle。
- `product/static/market-regime.*`：专业雷达与证据下钻层。
- `product/auth_store.py`、Supabase RLS migration：身份与隔离模式的参考基线。
- `product/data_core/research_trigger_history.py`、outcome attribution contracts：不可回写历史、触发条件和结果观察的参考模式。
- `product/billing_store.py`、private-preview flow：会员与收费流程的参考模式。

### 3.2 不能误当成已完成

- 当前 Yahoo/Tencent 数据仅有 `local_evaluation_only` 权利边界，不能直接变成私测或公开商业数据源。
- 现有 canonical/model portfolio 不是用户真实持仓，不能直接改名复用。
- Supabase/RLS、billing、private preview 目前是代码与本地验收基线，不是生产部署证明。
- 现有 Market Regime 输出为 `model_generated_unreviewed`、`action_eligible=false`，不能静默升级为投资建议。
- 现有 4 小时 scheduler 是数据刷新节奏，不等于用户应该每 4 小时收到一次通知。

## 4. Module 与 Milestone

```text
Module A 需求与经营权验证
  M1 M1.0 准入闸 + 个性化需求 Go/No-Go
        ↓
Module B 个人上下文与决策产品
  M2 最小持仓身份与暴露图谱
        ↓
  M3 个人风险卡编译器
        ↓
Module C 每日习惯闭环
  M4 决策窗口送达与收盘复盘
        ↓
Module D 商业化与规模
  M5 付费私测和生产安全
        ↓ 条件：M5 达标 + 公共传播权利获批
  M6 post-v1 公共增长与规模化发布
```

Milestone 是硬门：前一环没有通过，不进入后一环；验收标准变化必须回到 issue 合同工序重写，不能在执行中悄悄降标。

## 5. Milestone 详细计划

### M1 · Right-to-operate 与需求证明

**Goal**：在写多用户产品代码前，证明用户每天会使用并愿意为明确边界内的结果付费，同时确认数据、内容和通知渠道可合法交付。

**预计周期**：2–3 周，其中必须覆盖 10 个真实交易日。

**Stories：2**

1. `M1-S1 产品/证据/权利合同`
   - 固定 08:45 卡片 schema、允许与禁止输出、证据与新鲜度要求。
   - 形成 provider × use scope × private/public/paid 的权利矩阵。
   - 取得证券服务边界、个人持仓数据、通知渠道的专项合规意见或明确的持牌合作路径。
2. `M1-S2 20 人 × 10 个交易日 concierge 验证`
   - M1-S1 形成 **M1.0 准入 receipt** 后，先做 3–5 人 × 3 个交易日运行冒烟，再招募 20 位目标用户；人工辅助履约，不先造完整前端。
   - 保存每天送达、09:15 前打开、计划确认/改变、缺失/投诉和续费证据。

**Exit criteria**：

1. 在联系测试用户或发送第一张卡片前，M1.0 已冻结 provider、字段、衍生输出、渠道、人数、地区、保存期、截图/导出和收费范围，并获得 Park 准入确认。
2. 3–5 人冒烟没有 P0 权利、隐私、错误关联、漏发或纠错流程缺陷，才扩大到 20 人。
3. 20 人完成 onboarding，至少 16 人完成 8 个以上交易日。
4. 至少 60% 的有效卡片在 09:15 前打开；至少 40% 用户一周使用 4 天以上，并能说出卡片帮助确认/改变计划或减少了什么冲动决策。
5. 在合规允许的产品边界内，至少 5 人真实付费继续使用；若 M1.0 不允许收费，只能记录付费意愿，不能冒充真实付费验证。
6. 数据权利、内容边界、人工访问、泄露响应、隐私同意、纠错 SLA、停止和删除方法有可审阅记录；同时记录卡片过期/漏发率、错误关联、投诉和每张卡人工分钟数。

**禁区**：不公开发布受限行情；不收券商密码；不输出个股买卖、目标价或仓位指令；不因用户口头喜欢就判定验证通过。

### M2 · 最小持仓身份与暴露图谱

**Goal**：让产品知道“用户持有什么以及暴露于什么”，同时从第一天保证数据最小化、租户隔离、导出和删除。

**预计周期**：1–2 周。

**Stories：4**

1. `M2-S1 用户、组合、规则与同意 schema`
   - 版本化 User / Portfolio / Position / Horizon / UserRule / Consent / DeletionReceipt。
   - 从存储层绑定 owner identity；禁止跨用户读取。
2. `M2-S2 三分钟内导入与数据权利`
   - 首版支持手工和 CSV；截图 OCR 只有在准确率达标后再开放。
   - 支持校验、纠错、版本历史、导出、撤回同意和彻底删除。
3. `M2-S3 持仓暴露图谱`
   - 把证券映射到行业、市场、科技/红利风格、周期/防御属性及可验证的商品/宏观关联。
   - 无证据的关联保持 unknown，不用 AI 猜测补齐。
4. `M2-S4 08:45 A 股确认数据合同`
   - 与持仓工作并行冻结市场宽度、成交结构、风格扩散和行业领导/背离的 point-in-time、来源、权利、完整性与 stale 语义。
   - 只做 contract 和 bounded live probe；正式 authority 在 M3 实现。

**Exit criteria**：

1. 20 位 beta 用户能在 3 分钟内完成代码与权重导入，不提交金额、成本价或券商凭证。
2. beta 持仓至少 95% 有稳定证券身份；暴露无法判断时明确显示 unknown。
3. tenant isolation、错误身份、重复导入、幂等更新、导出和删除专项测试通过。
4. 删除后业务存储不可读取，保留的最小审计信息不含持仓正文。
5. 暴露关系绑定来源、known_at、版本和置信度。
6. A 股确认数据合同通过来源原始响应、交易日/08:45 截点和 rights readback，不用盘中或收盘后信息补写开盘前状态。

**禁区**：不连接交易权限；不把模型组合当真实持仓；不保存不影响产品结果的个人财务信息。

### M3 · 确定性个人风险卡编译器

**Goal**：把 Market Regime、A 股内部确认、用户持仓暴露和用户规则编译为同输入可重放、缺证据会降级的 90 秒风险卡。

**预计周期**：2 周。

**Stories：3**

1. `M3-S1 A 股内部确认层`
   - 按 M2-S4 合同实现市场宽度、成交与风格扩散、行业领导/背离等必要 authority。
   - 每个来源先通过权利、时点、完整性与 last-good gate。
2. `M3-S2 个人影响与条件树编译器`
   - 输出持仓顺风/逆风/错配、变化原因、观察条件和失效条件。
   - 用户规则与产品研究判断分开标识；无证据时不产生确定性结论。
3. `M3-S3 风险卡 API 与 mobile-first reader`
   - 首屏先回答“今天对我有什么变化”；市场雷达和证据链作为下钻层。
   - 每句话可回到输入 snapshot、暴露映射和规则版本。

**Exit criteria**：

1. 同一输入完全离线重放得到相同卡片 identity 和正文。
2. stale、partial、冲突或缺失输入只降级依赖它的结论，不静默 fallback。
3. 100% 数字和事实绑定 evidence identity；AI 文案不能创建事实或动作。
4. 20 个真实 beta 组合通过人工盲审；关键持仓影响没有无来源的肯定判断。
5. 移动端用户中位阅读完成时间不超过 90 秒。

**禁区**：不输出 expected return、目标价、具体交易量或自动下单；不把相关性写成因果；不因界面需要而隐藏 unknown。

### M4 · 决策窗口送达与不可回写复盘

**Goal**：让用户不需要主动想起产品，并让产品每天公开检验自己的早盘判断。

**预计周期**：1–2 周。

**Stories：2**

1. `M4-S1 决策窗口 orchestrator 与变化提醒`
   - 08:45 发送完整卡；午间/盘中只在状态跨阈值或持仓影响发生实质变化时提醒。
   - 先落 immutable delivery receipt，再发送；支持幂等、去重、重试、退订和总停止开关。
2. `M4-S2 15:15 收盘复盘与长期校准`
   - 冻结早盘卡片，追加条件 fulfilled/delayed/broken 和市场结果观察。
   - 展示按市场情景分类的准确度与常见错误，不用收盘信息改写上午结论。

**Exit criteria**：

1. 交易日、节假日、跨市场时区和夏令时测试通过；08:45 卡不重复、不漏发。
2. 盘中只有定义明确的 material change 触发提醒，用户可查看触发原因。
3. 收盘复盘绑定原卡 identity，历史不可覆盖或删除后伪造更高准确率。
4. 通知渠道拥有明确授权；退订和停止开关即时生效。
5. 运行健康、失败原因和最后成功送达可查询。

**禁区**：不把 4 小时刷新等同于 4 小时推送；不在未冻结 morning card 时计算“命中”；不自动发到外部群。

### M5 · 付费私测与生产安全

**Goal**：证明这不是 demo，而是可以安全服务真实付费会员、持续运行一个月的私有 beta。

**预计周期**：3–4 周，必须覆盖至少 20 个交易日。

**Stories：5**

1. `M5-S1 生产身份与租户隔离`
   - 在目标部署环境完成 auth/RLS、session/entitlement、密钥边界和跨租户攻击测试。
2. `M5-S2 数据主体权利与事故响应`
   - 完成同意、人工访问审计、导出、删除、纠错 SLA、泄露响应和 owner 操作留痕。
3. `M5-S3 Rights、备份恢复与运行可靠性`
   - provider 与通知渠道的批准 receipt 绑定产品范围和部署环境；完成备份恢复、回滚、可观测与故障演练。
4. `M5-S4 订阅、退款、反馈和运营面板`
   - 支持受邀 onboarding、权益、收费/取消、退款状态、反馈和人工纠错。
   - 只使用测试支付环境完成技术验收；真实收费需单独授权并满足 M1 合规 gate。
5. `M5-S5 50 人付费私测验收`
   - 运行 20 个交易日，记录 delivery、使用、留存、付费、纠错和支持成本。

**Exit criteria**：

1. 至少 50 人受邀、30 人完成 onboarding、20 人完成完整观察窗口。
2. 第四周至少 12 人仍每周使用 4 天以上，至少 8 位真实付费续订。
3. 无 P0 数据泄露、跨租户访问或未授权通知；纠错和删除 SLA 可兑现。
4. 备份恢复、回滚、gitleaks、相关全套测试和移动端 E2E 全部通过。
5. 每次卡片、通知、复盘和收费均可追到用户授权、输入身份和版本。

**禁区**：没有 rights receipt 不开放；没有真实留存和付费不宣称 PMF；支付测试通过不等于真实收费已获授权。

### M6 · Post-v1 公共增长与规模化发布

**状态**：不属于 v1 完工条件。只有 M5 达标且公共传播 rights receipt 获批后，才建立新的 milestone/issue 合同。

**Goal**：把“公共市场天气”变成内容获客入口，把“私人持仓风险卡”变成自助付费结果，同时保持隐私和质量边界。

**预拆方向，不是执行 Story**：

1. `M6A 公共卡与获批分享`：无持仓、延迟或聚合、权利已清理的公共卡片。
2. `M6B 自助身份与付费`：自助同意、开户、组合导入、付款、退款、导出和删除。
3. `M6C 容量与运营`：负载、缓存、成本、故障降级、客服/纠错和增长漏斗。

**Exit criteria**：

1. 公共卡与私人卡在数据、缓存、日志和分享权限上完全隔离。
2. 至少 80% 成功 onboarding 用户在 3 分钟内获得第一张有效私人卡。
3. 100+ 用户负载下达到 M5 后另行冻结的可用性、延迟、成本和错误预算。
4. 第四周留存、真实付费转化和推荐率达到 M5 后由 Park 冻结的门槛。
5. 数据 rights、合规、隐私政策、支持和停止开关覆盖公开发布范围。

**禁区**：不泄露私人卡；不靠夸大收益或“荐股神器”获客；不以注册数、群人数或页面浏览量冒充产品价值。

## 6. 关键路径与 Go/No-Go

```text
M0 existing radar
  → M1.0 right-to-operate gate
  → M1 smoke + 20×10 personalized concierge
  → M2 holdings identity
  → M3 personalized compiler
  → M4 daily habit loop
  → M5 paid private beta
  → [conditional] M6 scale/public release
```

硬停止条件：

- M1 未证明真实使用与付费：停止，不进入 M2。
- 数据 rights 或合规路线不成立：保留本地研究工具，不做对外产品。
- M2 无法保证租户隔离和删除：不得导入真实持仓。
- M3 人工盲审出现无来源的高影响判断：不得自动送达。
- M4 无法保证 immutable morning card：不得展示准确率。
- M5 没有真实留存：不得进入 M6 扩张。

## 7. Capacity、测试与执行纪律

### Capacity 假设

- 1 条主执行链；可并行准备不相互改代码的研究/验收材料，但 milestone 顺序合并。
- WIP ≤ 3；v1 共约 16 张 story issue/PR，M6 在 M5 后重新估算，不把当前预拆当硬上限。
- 以 20% buffer 覆盖数据源失败、用户反馈、bug 和 tech debt。
- 每个 milestone 完成后更新 `decision-log.md`（含 Gotchas）和 `REGISTRY.md`，再从最新 `main` 开下一环。

### 测试深度

- M1：M1.0 准入 readback、3–5 人冒烟、真实 delivery/usage/payment receipt、rights/compliance review。
- M2：schema、clean install、migration idempotency、tenant isolation、export/delete、identity collision。
- M3：deterministic replay、PIT/no-lookahead、missing/stale/conflict、evidence identity、人工盲审。
- M4：时区/节假日、幂等/去重/重试、不可回写历史、停止开关和故障演练。
- M5：auth/RLS、secret scan、backup/restore、rollback、billing sandbox、完整相关 suite 与 E2E。
- M6：公共/私人隔离、mobile onboarding、load/performance/cost、真实 cohort acceptance。

每张 Story 在开工前另写 GitHub issue，必须包含 Outcome、3–7 条可复验验收标准、In/Out scope、禁区、Allowed Files 和 Verification Commands。计划本身不能替代 issue。

## 8. 主要风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 市场数据没有商业/公开发布权 | 产品无法私测或公开 | M1 先做 provider × scope rights gate；无 receipt 不进入对外运行 |
| 个性化输出跨入投顾业务 | 收费与营销受限 | 固定研究/风险提醒边界；专项合规意见或持牌合作；机器规则禁止动作语言 |
| 用户不愿提交真实持仓 | 个性化价值无法成立 | 只收 ticker + 权重；支持 watchlist 模式；本地/租户隔离、导出和删除 |
| 相关性被写成因果或建议 | 误导用户、损害信任 | 暴露关系保留来源与置信度；unknown fail closed；人工盲审高影响样本 |
| 推送太多形成噪音 | 留存下降 | 数据可 4h 更新，但用户只收决策窗口和 material-change 通知 |
| 用 hindsight 美化准确率 | 产品信任失真 | morning card immutable；结果只追加；按情景公开错误而非只报胜率 |
| 过早做公开增长 | 放大隐私、权利和质量问题 | M5 真实付费留存通过后才启动 M6 |

## 9. 已记录的 Park 决定

1. 批准 **5 个 v1 milestone + 1 个有条件 post-v1 milestone** 作为产品 finish line；
2. 接受 **M1 是硬 Go/No-Go**，未通过就停止对外验证和后续 milestone；
3. 以 **M5 成熟付费私测** 作为第一版完成，M6 保持为公开规模化版本；
4. 以上是产品执行批准，不是 M1.0 外部经营权批准；canonical readiness verifier 仍决定是否可以接触用户、收集持仓、发送、收费或公开发布。
