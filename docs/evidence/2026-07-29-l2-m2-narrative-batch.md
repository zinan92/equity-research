# L2-M2 · 100 家官方 PDF 叙述抽取收据

运行收据：`e4-l2-narrative-batch-v1:b3afef60ddc186c83a36fd073a749a6f10e738cab4f080eb450d8034aeb60ab6`。
其运行态文件位于 `/private/tmp/e4-l2-m2-narratives/narrative-batch-b3afef60ddc186c8.json`；提交的验证摘要为 `artifacts/evidence/e4-l2-m2-narrative-batch-verification.json`，验证哈希为 `5c38f5a7b35511f459c9b064268d306f6818677da99dda04e4438b401f676b51`。

## 覆盖结果

| 项目 | 结果 |
| --- | ---: |
| 冻结身份池 | 100 ticker |
| 可用官方 PDF | 98 |
| 缺失 | 2 |
| 最新年度报告选择 | 95 |
| 最新可用中报回退 | 3 |
| 页级叙述块 | 41,340 |
| 目标章节已解析块 | 13,215 |
| 仍无目标章节上下文的块 | 28,125 |
| 已解析页面 | 4,634 |

每个可用行重新拉取其 L2-M1 已登记的 CNINFO 官方 PDF；只有 HTTP 200、PDF
魔数和重新计算的 SHA-256 均与冻结文件身份相同，才会解析。每个块保留
`document_id`、`raw_hash`、`page_number`、`section_path`、原文及官方 URL。L2-M1
收据仅用于冻结 ticker/文件选择，不是叙述事实来源。

## 缺失和失败分类

| 分类 | ticker | 处理 |
| --- | --- | --- |
| `no_available_official_report` | `600000.SH`, `600030.SH` | L2-M1 的全部六个时期均为官方收集超时，故本次无可复抓、可哈希匹配的官方 PDF；保留 MISSING。 |

三个北交所 ticker 没有可用年度报告但有 `2026Q1` 官方 PDF，因此明确标为
`latest_available_interim_fallback`；这不是年度报告的代理，也不会被标作年度覆盖。
未能归属目标章节的 28,125 段保留 `unresolved` 和原文片段，不会被强行接入研究章节。

## 边界

本批为官方 PDF 的页级叙述证据，`data_kind=real`，单并发、可检查点续跑。
它不生成 AI 判断、估值、Tier、目标价、仓位或行动建议。
