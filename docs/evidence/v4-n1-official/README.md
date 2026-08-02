# V4-N1 官方证据包

本包是 Issue #682 的证据层 milestone，不是研报正文。三家公司均走现有
CNINFO 官方 PDF 入口，输出只包含报告身份、raw hash、页级财务事实和页级
叙述块；没有模型调用、判断正文、Tier 或 action credit。

## 可重放收据

- 总包：`receipt.json`
- 总包 receipt hash：`638186bf104b3f291fb8ee066c869d9e097822800dae1f9b9a5ec756f20ca845`
- 物化脚本：`scripts/materialize_v4_n1_evidence.py`
- 单公司采集脚本：`scripts/capture_v4_n1_official_sequence.py`
- 分期合并脚本：`scripts/merge_v4_n1_financial_receipts.py`
- Round 7 输入校验：`data_core.round7_evidence.load_source_receipts`

| ticker | 官方财务报告 | 页级事实 | 叙述块 | 财务 receipt | 叙述 receipt |
|---|---:|---:|---:|---|---|
| 000001.SZ | 6 | 118 | 612 | `3a6574cceb6534eccc23921730a63c474ec1d870da565648a97d1e6046217eee` | `e4-official-narrative-evidence-v1:5d605a0c080ea5e65e7ad8cf2931b151bb9654c955fe269d0f307787f037e6e0` |
| 000002.SZ | 6 | 113 | 653 | `e8cda56f067be7e7ef9be941e3e8783a19063cb13946bc0e7f23c7f00ecd7a52` | `e4-official-narrative-evidence-v1:8fdc4021f96defc5cf05e369dfb4d3f5ff299ea9da3c9ca89c5b322df98ea40a` |
| 600000.SH | 6 | 24 | 976 | `173e9bcfe1260a353e2eb21da8562689f8c2c4e03f7a7ac87a8413598c29e1d7` | `e4-official-narrative-evidence-v1:538f49414f4f2a8a0a295247ca625ec5f8800606b5994cbcb7080d2301c10490` |

## 明确缺口

- 600000.SH 的 2022FY 和 2026Q1：官方 PDF、document_id、URL、raw hash
  均已捕获，但当前页级财务抽取没有形成合格 consolidated fact，保留为
  `page_facts_empty`，没有用零值或代理值填补。
- 600000.SH 的叙述 receipt 已按合并后的财务 receipt hash fresh 重抓，新的
  receipt 为 `e4-official-narrative-evidence-v1:538f49414f4f2a8a0a295247ca625ec5f8800606b5994cbcb7080d2301c10490`；
  旧 receipt 仍留在 runtime 作为历史尝试，不进入本包。
- 每个重试 receipt 保留了实际官方 index/document 请求的 method、参数、URL、
  HTTP 状态、响应 body hash 和时间。未把原始失败误报成“来源不可用”。

## 边界

这些文件只证明“官方材料已经绑定并可供下一 milestone 使用”。它们不产生
V4 章节、不触发 `pending_human_review` 之外的审批、不改变 Tier 阶梯、B6
evidence gate、decision policy 或 #218 审计计数。下一 milestone 才能用这些
receipt 进入单公司 whole-dossier 生成，并且仍需保持缺口可见。
