---
schema_version: dossier-template-v1
status: "structural-replay"
company: "NVIDIA Corporation"
ticker: "NVDA"
market: "NASDAQ"
as_of: "2026-07-23"
prepared_by: "dossier-pilot/manual-v1"
evidence_cutoff: "2026-07-23"
replayed_from_sha256: "32338c07e78aafc4c91470a1fd899be1b16d65db9f25410cc967f8b987f6e268"
---

# NVIDIA｜公司档案（样例）

> **用途**：这是对模板的首个自有证据样例，不复制任何第三方档案正文，也不是投资建议。事实编号均能追溯到末尾来源；研究判断与公司披露分开。

## 1. 一句话定位

`[F-01]` NVIDIA 把自己描述为以 GPU 为基础、面向加速计算与 AI 基础设施的公司，其客户覆盖云服务商、模型开发者、企业与公共部门。[S-01]
**研究判断**：它的核心不是单一芯片销量，而是把计算、网络与软件生态交付为数据中心平台；这使客户采用深度与供应链/出口限制同样重要。

## 2. 身份、创始人与治理

| 主题 | 已核验事实 | 来源 |
| --- | --- | --- |
| 公司/证券身份 | NVIDIA Corporation 在美国 SEC 以 CIK 0001045810 披露，FY2026 年结为 2026-01-25。 | [S-01] |
| 创始人/关键管理者 | Jensen Huang 于 1993 年创立 NVIDIA，并自创立起担任 President、CEO 和董事会成员。 | [S-02] |
| 治理观察 | 本样例未对投票权、激励或继任安排作独立判断；需读取 proxy 后补充。 | 待核验 |

## 3. 技术来源与发展史

| 日期 | 已核验事件 | 研究含义（明确标注） | 来源 |
| --- | --- | --- | --- |
| 1993 | NVIDIA 创立。 | 公司的创始人连续性是治理研究起点，不等于未来执行保证。 | [S-02] |
| 1999 | 公司称 GPU 的发明推动 PC gaming、计算机图形和现代 AI 的发展。 | GPU 架构与开发者工具的长期积累是平台叙事的事实基础；护城河强度仍需客户迁移成本证据。 | [S-02] |
| FY2026 | 公司披露 NVLink Fusion，用于让 hyperscaler 与 custom ASIC 设计者接入其平台。 | 互联开放可能扩大平台边界，也可能降低封闭生态控制力；需持续跟踪采用。 | [S-01] |

## 4. 商业模式与业务线

| 业务线/平台 | 客户与交付物 | 收入或经营证据 | 关键依赖 | 来源 |
| --- | --- | --- | --- | --- |
| Data Center | 云厂商、模型开发者、企业和公共部门使用的 AI/HPC 计算与网络平台。 | FY2026 Data Center 收入同比增长 68%。 | 需求、供应、客户资本开支及贸易政策。 | [S-01] |
| Gaming | 面向 PC gaming 的图形计算产品。 | FY2026 Gaming 收入同比增长 41%，公司称 Blackwell 需求推动增长。 | 消费级需求及供给约束。 | [S-01] |
| Professional Visualization / Automotive | 专业可视化与汽车相关平台。 | FY2026 Professional Visualization 收入同比增长 70%；Automotive 收入同比增长 39%。 | 各终端产品周期与客户采用。 | [S-01] |

## 5. 财务与经营时间序列

| 期间 | 指标 | 数值/单位 | 同比/环比 | 口径 | 来源 |
| --- | --- | --- | --- | --- | --- |
| FY2026 | 收入 | 2,159.38 亿美元 | +65% | GAAP | [S-03] |
| FY2026 | 毛利率 | 71.1% | -3.9 个百分点 | GAAP | [S-03] |
| FY2026 | 净利润 | 1,200.67 亿美元 | +65% | GAAP | [S-03] |
| Q4 FY2026 | Data Center 收入 | 623 亿美元 | +75% | 公司新闻稿 | [S-03] |

## 6. 护城河的证据链

| 假设 | 支持证据 | 可证伪条件 | 当前判断 |
| --- | --- | --- | --- |
| 加速计算平台拥有生态与系统级黏性 | 公司披露其平台涵盖 GPU、网络，并服务多类客户；FY2026 提出 NVLink Fusion。[F-01][S-01] | 若大客户将训练/推理工作负载稳定迁移到替代平台、且不再需要其软硬件栈。 | **中等置信度的研究判断**：证据支持平台范围，不足以单独量化客户转换成本。 |
| Data Center 是增长引擎 | FY2026 Data Center 收入同比 +68%。[S-01] | 若后续报告显示 Data Center 增长显著低于总收入或出现持续客户集中度恶化。 | **事实支持强，持续性判断待更新**。 |

## 7. 风险、反题材与观察触发器

| 风险/反题材 | 已知事实 | 触发器 | 下一次核验 | 来源 |
| --- | --- | --- | --- | --- |
| 中国 Data Center compute 暴露 | 公司 FY2027 Q1 outlook 未假设中国 Data Center compute 收入。 | 后续业绩披露调整中国假设或出现新的出口/许可变化。 | 下一份 10-Q / earnings release。 | [S-03] |
| 组合复杂度与毛利率 | FY2026 GAAP 毛利率为 71.1%，公司称向 Blackwell 全规模数据中心方案转换以及 H20 相关费用影响毛利率。 | 毛利率持续低于公司指引区间，或库存/采购义务费用扩大。 | 下一份 10-Q / earnings release。 | [S-01] |
| Gaming 供给约束 | 公司预计 FY2027 Q1 及之后 Gaming 供给约束可能构成逆风。 | 供给约束延长或 Gaming 增长显著放缓。 | 下一份 earnings release。 | [S-01] |

## 8. 研究结论与待补问题

- **事实结论**：FY2026 的收入、Data Center 增长和利润率显示公司规模及增长处于高位；这些都是截至各披露期的历史事实。[S-01][S-03]
- **研究判断**：平台深度与增长持续性应视为待证假设，而不是“永久垄断”结论；最关键的反例是客户工作负载迁移和政策/供给冲击。
- **待补问题**：客户集中度、供应商依赖、回购/股权激励、区域收入与竞争对手替代，需要从 10-K 注释、proxy 和后续 10-Q 再建证据包。[S-01]

## 9. 生产记录

| 字段 | 值 |
| --- | --- |
| 运行 ID | `nvda-dossier-pilot-2026-07-24-structural-replay` |
| 采集/写作耗时 | 约 20 分钟初稿 + 约 8 分钟官方页面重开与数字回读。 |
| 模型/人工介入 | Codex 选择 SEC、IR 与公司 Newsroom 来源；2026-07-24 重新打开三项官方来源核验；未使用第三方档案文本。 |
| token 记录 | 见 `pilot-production-manifest.json`；历史初稿无独立计数，重验区间使用 Goal 级计数器记录并显式标注范围。 |
| 已用来源数 | 3 |
| 复跑策略 | 固定模板 + 固定事实 ID；以新的 evidence cutoff 重跑，并对事实、判断与待补问题生成 diff。 |

## Sources

| ID | 发布者 | 文档/页面 | 发布或报告日期 | URL | 用途 |
| --- | --- | --- | --- | --- | --- |
| S-01 | NVIDIA / SEC | FY2026 Form 10-K | 2026-02-25 | https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm | 业务、客户、平台、分部增长与风险 |
| S-02 | NVIDIA Newsroom | Jensen Huang bio | accessed 2026-07-24 | https://nvidianews.nvidia.com/bios/jensen-huang | 创立年份、CEO 角色、GPU 历史表述 |
| S-03 | NVIDIA Investor Relations | Q4 and FY2026 financial results | 2026-02-25 | https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Fourth-Quarter-and-Fiscal-2026/ | FY2026 GAAP 财务数字、Q4 Data Center、指引 |
