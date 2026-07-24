# Company / Universe Crosswalk v1

## Purpose

将 archive universe 的 code/name/market 观察转换成可审计的 canonical 候选身份。该 crosswalk 是读取与审计层，不是 collector，也不允许写入正式 authority。

## Identity rule

只接受 `code + market` 形成的候选 ticker：

- A 股六位代码按 6/68 → SH、0/3 → SZ、4/8 → BJ 解析；
- 港股五位代码、日股四位代码和美股 ticker 采用各自显式 market；
- 相同 code+market 但出现多个规范化名称 → `ambiguous`；
- 缺 code、缺 market、或不支持的格式 → `unmapped`；
- 名称、数组位置、模糊别名都不能独立产生 `matched`。

`matched` 行的 company ID 是由 canonical ticker 派生的稳定 v1 标识。A/H 双重上市、ADR、历史代码变更和一家公司多个证券目前不被自动合并；需要后续 canonical evidence 才可建立 company-level relationship。

## Read contract

`UniverseCrosswalk.resolve(query)` 只返回三种状态：

| 状态 | 含义 | 行为 |
| --- | --- | --- |
| `matched` | 候选都指向同一 company ID | 返回候选记录 |
| `ambiguous` | 别名碰撞或冲突名称 | 返回所有候选，不选择一个 |
| `unmapped` | 没有可信 identity | 返回空候选或未映射记录 |

## Runtime-only audit

```bash
python3 scripts/build_universe_crosswalk.py \
  --main /local/path/scores-and-ratings.json \
  --levels /local/path/levels-ratings.json \
  --out /tmp/company-universe-crosswalk.json
```

在 2026-07-24 的本地归档审计中，`main=649`、`levels=661`，输出 1,310 条记录：1,058 `matched`、252 `unmapped`、0 `ambiguous`。该 JSON 是 runtime-only audit output，不能提交或作为产品事实。

同一审计针对 M1 的 30 家黄金集产生独立 coverage receipt：30/30 ticker 可按其显式市场规范化；其中 21 家在 archive universe 中有 `matched` 候选，9 家为 `unmapped`。后者是 archive coverage 缺口，不是名称匹配或产品身份失败。该 receipt 同样只写到 `/tmp`。

## Boundary

该模块复用 A1/A2 的 canonical `instrument_id` 语义和 A4 的证券代码规则；它没有新建 authority schema，也不允许从 archive 回填证券身份。后续 E1-S2 才定义 Company、SectorPosition、Evidence 等正式对象的版本化写入。
