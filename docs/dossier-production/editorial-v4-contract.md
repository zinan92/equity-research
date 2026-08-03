# Editorial V4 contract（review-only）

状态：`active / review_only_unpublished`
Issue：[#692](https://github.com/zinan92/equity-research/issues/692)
版本：`park-editorial-v4-v1`

这份合同冻结的是爱牛式 V4 的可读输出，不替换 Round 7 的 canonical 九章
契约，也不改变 Tier、B6 evidence gate、decision policy 或 blocked-fields。
V4 editorial 的输出只能进入 `artifacts/editorial-v4/`，在独立 QA 和真人
复核前不得进入 `artifacts/round7-dossiers/`、`artifacts/v4-reports/` 或公开
index。

## 读者结构

每篇报告按以下顺序输出：

1. 最新数据卡（只显示有页级证据的最新期次；没有就写 `输入未提供`）
2. `一句话定位`
3. `创始人与团队`
4. `发展时间线`
5. `技术与产品`
6. `财务与估值`
7. `风险与点评`
8. `大白话结论`
9. `Sources / 生产记录`

每个章节必须同时保留：

- `事实`：带 `[F-xx]`，映射到 `evidence_id → source_id → document_id →
  page_number → quoted_anchor → raw_sha256`；
- `研究判断`：带 `[J-xx]`，列出支持事实和可证伪条件；
- `公司自述`：带 `[C-xx]`，正文必须使用“公司披露/年报自述”等措辞，
  不得伪装成独立验证事实；
- `缺口`：带 `[G-xx]`，说明 `missing_page_anchor`、
  `insufficient_independent_evidence` 或其它具体原因。

### 锋利定位不是要被删掉的事实

“绝对龙头”“强定价权”“品牌护城河”“精密制造杂货铺”等是报告的
AI 研究判断，不要求年报存在一行逐字证明它们。它们必须保留其独特性，
但只能作为 `[J-xx]` 出现，并同时绑定相关底层 evidence 和 falsifier；
不得改写成无来源的 `[F-xx]` 或 `[C-xx]`。机器门禁只拦截未标记、无引用、
无证伪条件的锋利断言，不拦截有证据链的 aggressive synthesis。

## 内容门槛

- 一句话定位必须指出公司的资产角色、核心矛盾和当前兑现程度，禁止
  “公司专注于……”式空话。
- 创始人与团队、时间线、产品/商业模式、财务因果链、风险与大白话结论
  均须有公司特定细节；材料不足时显式写缺口，不得猜测。
- 财务比较必须写方向和幅度；方向/幅度只能来自输入包中的确定性计算，
  模型不得自行计算。
- 已披露的历史实际值不得放在 `如果……那么……` 的结论中；条件句只允许
  用于未来或待验证假设。
- 不生成目标价、仓位、买卖动作或无证据估值倍数。没有冻结预测/估值证据
  时，章节必须写 `估值证据缺失`。
- 最新数据卡若要展示股价、市值、PE/PB，必须有同一 `as_of` 的官方/授权
  行情 evidence；本次不从旧 M4 快照、fixture 或聚合器复用，缺失则只显示
  经营数据或写 `估值证据缺失`。
- 目标正文对齐冻结的 Round 7/Ainiu 参考样本（当前基线 2,429 个中文字符）；实际字数写入 receipt。低于目标不自动
  补写，必须列出证据覆盖或缺口原因。

## 输入与来源边界

生成请求只接收冻结的 `evidence_packet`，不联网、不搜索、不读取旧报告
正文。每个 evidence item 必须有：

`evidence_id, source_id, document_id, source_kind, evidence_class,
report_period, page_number, quoted_anchor, source_url, raw_sha256`。

允许的事实来源只包括 issuer/交易所官方页（本次为 CNINFO、CATL/招行/茅台
官方 IR 页面及已验收的官方页级 receipt）；不得将“已注册来源”泛化为任何
第三方网页。官方年报/季报是 `issuer_disclosure`，可证明公司披露了什么，但不能单独
证明护城河、同业领先、客户锁定、市场份额或订单兑现。旧 M4 包中的 NBD、
新华、SNE、CPNN 及 Eastmoney F10 仅记录为排除项，不进入模型输入。

## 机器 QA 与独立 QA

机器 QA 必须 fail-closed 检查身份、结构、字数、来源绑定、数字闭包、三条
推理规则、自述标记、未知项、禁止动作词、benchmark/ticker 泄漏和 receipt
哈希。DeepSeek 独立 QA 只返回问题清单，不得自审通过；任何 blocker 必须
通过带 request_id 的修复轮次，或保持 `blocked`。

QA receipt 必须绑定：输入包哈希、来源 manifest 哈希、模型 request/response
哈希、Markdown/HTML 哈希、每项 blocker、审阅状态和 `boundary`（不产生
Tier/B6/decision/publication credit）。即使 editorial QA `passed`，输出也只
能留在 `artifacts/editorial-v4/`；不得修改 Round 7 dossier 的
`review_status`/quality gate 或进入 canonical public index。

## 本次五家公司

原候选招商银行（`600036.SH`）只有业绩快报和一季报，没有冻结的官方年报
页级包；为避免用不完整输入制造“完整报告”，替换为已有官方页级包的
平安银行（`000001.SZ`）。最终候选：

- `600900.SH` 长江电力
- `000333.SZ` 美的集团
- `600519.SH` 贵州茅台
- `300750.SZ` 宁德时代
- `000001.SZ` 平安银行

前四家将重新抓取并绑定官方 PDF 页；平安银行复用已验收的官方页级 receipt，
仅复用证据，不复用旧报告正文。任一公司缺少页级材料时，该项保持缺失，
不以旧 M4 narrative/report.json 补齐。

## 复用与新建

复用：`product/deepseek_writer.py::call_structured_deepseek`、官方来源
身份/页级抽取器、`v4-contract.md` 的证据边界、`template-v1.md` 的读者
规格、blind review protocol 和确定性 HTML 渲染模式。

新建：独立 `editorial-v4` evidence packet、全报告生成 schema、机器/独立
QA、review-only renderer 和五家公司批量 receipt。原因是现有 Round 7 输出
是 canonical 九章表格型档案且当前公开门禁阻断，旧 M4 report/narrative
没有页级 claim registry，不能直接复用为爱牛式 V4 正文。
