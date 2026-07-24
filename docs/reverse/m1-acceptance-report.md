# M1 / N1 验收报告

状态：**GO（带明确覆盖边界）**
验收日期：2026-07-24
合同：[#116](https://github.com/zinan92/equity-research/issues/116)

## 结论

N1 已从“爱牛归档的字段观察”推进到可复核的自有来源合同：30 家黄金验证集固定了跨行业、跨市场的最小回归面；快数据与可再生成财务字段的高/中置信度覆盖为 **84/90（93.33%）**；已披露评分公式在可计算样本上达到合同的 95% 门槛；五份自产档案经过外部盲评并获 Park 对 Round 7 的整体批准。

这不是“任意 ticker 已具备完整实时财务”的结论。港股和日股的点时财务增长字段仍是明确 gap，历史估值也仍受 PIT 股本、披露时点与 PEG 定义限制。后续 E1/N2 必须把这些 gap 变为 canonical 的缺失状态，而不能补成估计值。

## 30 家验证集

完整名单、行业理由、市场和可再生成字段矩阵在 [`m1/golden-validation-set.json`](m1/golden-validation-set.json)。

| 维度 | 结果 | 合同 |
| --- | ---: | --- |
| 公司数 | 30 | 30 |
| 市场 | A 股 21；港股 3；美股 3；日股 3 | 每市场 ≥3 |
| 行业 | AI芯片 5；半导体设备材料 5；光模块 5；PCB 4；机器人 6；电力 5 | 每行业 ≥3 |
| 高/中置信度字段 | 84 / 90（93.33%） | ≥80% |
| 显式缺口 | 港股/日股 6 个 `revenue_growth` 单元 | 必须显式，不得伪造来源 |

字段包括 `price`、`change_pct`、`revenue_growth`。每个高/中置信度单元都映射到本仓可执行的来源契约测试：A 股行情/财务使用腾讯与东财交叉核验，港美日行情使用 Yahoo 历史价格及冻结 FX，美国财务使用 SEC filed-before-as-of Company Facts。验收器会拒绝任何没有本地再生成证据路径的高/中置信度单元。

## 已复现的 N1 证据

| 能力 | 已验证结果 | 证据 |
| --- | --- | --- |
| 字段归因 | 83/83 字段分类；判断、AI 推断与原始/派生事实分开 | [`field-attribution.md`](field-attribution.md) |
| A 股业务/预约披露 | 30 家运行时审计：主营分部名称覆盖 93.46%，预约披露 11 页完整，0 缺失 ticker | [`decision-log.md`](../../decision-log.md) |
| 跨市场价格 | 30/30 有可解释结果：22 个严格窗口通过、8 个窗口外精确 residual、0 未解释价格异常/缺失 | [`market-source-policy.md`](market-source-policy.md) |
| 历史估值 | 106 个字段：52 通过、3 outlier、39 PIT 输入缺失、12 PEG 定义不匹配；全部保留状态 | [`market-source-policy.md`](market-source-policy.md) |
| 评分 | 综合分 453/453；机会分 575/578（99.48%）；PEG 分档 276/276 | [`scoring-formulas.md`](scoring-formulas.md) |
| 档案生产 | 5 家（含 NVIDIA）；数字有来源 ID；NVIDIA 结构复跑一致；外部盲评自产 5/5 | [`dossier-production`](../dossier-production/) |
| Park 批准 | Park 明确整体批准 Round 7；未提交 P1–P5，收据不伪造选择 | [`round7-park-approval-receipt.json`](../dossier-production/round7-park-approval-receipt.json) |

## 评分与判断边界

复现的是已披露的算术：综合分、机会分和 PEG 分档。S/A/B 不能从现有字段唯一推导，仍标记为人工/AI 研究判断；`summary`、产业角色、三高标签、路线图等也同样属于研究判断或 AI 推断。报告中没有“来源待查”的模糊状态：要么有来源契约，要么显示为 gap/人工或 AI 研究判断。

## Go / No-go

**GO：** 进入 E1/N2 的 canonical 对象、crosswalk 和 evidence corpus 建设。允许以这 30 家作为回归集验证新增来源或数据模型。

**NO-GO：** 不允许据此宣称所有市场都已具备点时财务、完整历史估值或可自动化 S/A/B 判断；不允许把本地归档正文、评分结果或盲评 key 放进产品输出。

## 验证命令

```bash
python3 scripts/verify_m1_acceptance.py docs/reverse/m1/golden-validation-set.json
python3 -m unittest product.tests.test_verify_m1_acceptance \
  product.tests.test_a_share_pit_fundamentals \
  product.tests.test_eastmoney_periodic \
  product.tests.test_market_snapshot \
  product.tests.test_validate_market_snapshot \
  product.tests.test_disclosed_scoring -q
```

`verify_m1_acceptance.py` 只验证已提交的来源合同、名单覆盖和缺口显式性；它不读取、不复制也不依赖本地归档正文或评分输出。
