# V4-M3 · 官方页级证据绑定

状态：**通过（官方证据适配，待人工审阅）**<br>
合同：[#672](https://github.com/zinan92/equity-research/issues/672)<br>
机器收据：[`v4-m3-official/receipt.json`](v4-m3-official/receipt.json)

## 产出

| ticker | 输出 | reader 字符 | 官方 PDF URL | 状态 |
| --- | --- | ---: | --- | --- |
| 300750.SZ | [`300750.SZ.md`](v4-m3-official/300750.SZ.md) | 4,184 | CATL 2025 年报 + 2026Q1 | pending_human_review |
| 600519.SH | [`600519.SH.md`](v4-m3-official/600519.SH.md) | 4,046 | 茅台 2025 年报 + 2026Q1 | pending_human_review |

两份档案都通过 `park-v4-dossier-v1` 的结构、来源表、HTTPS 与证据标记校验；每份输出的 production record 绑定 narrative receipt、financial receipt、输入样本 hash 和输出 hash。数字与判断没有新增来源，仍按 `[F-xx] / [S-xx]` 回溯到原官方页级样本。

## 边界

这是官方证据适配，不是新的模型生成：`fresh_model_calls=0`、`new_official_documents=0`、`tier_credit=none`。输出明确标记 `pending_human_review`，不解锁 Tier A、目标价、仓位或 action。第三家公司没有可绑定的官方页级 receipt，本 milestone 不强行填补；M4 才接入新生成器。
