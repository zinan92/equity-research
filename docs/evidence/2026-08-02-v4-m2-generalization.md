# V4-M2 · 三家公司 Ainiu reader contract 泛化

> 历史回放收据：本文件记录的是 canonical Round 7 九章替换前的旧 reader
> replay（当时使用“产业坐标/财务与估值/风险与点评”映射）。它不再是当前
> V4 发布合同，也不提供公共/mobile 链接；当前合同见 `v4-contract.md`。

状态：**通过（reader replay）**<br>
合同：[#670](https://github.com/zinan92/equity-research/issues/670)<br>
机器收据：[`v4-m2-generalization-receipt.json`](v4-m2-generalization-receipt.json)<br>
可读交付：[`v4-m2-reader-index.html`](v4-m2-reader-index.html)

## 结果

三个不同行业的既有 Round 7 档案通过同一个 `park-v4-dossier-v1` 验证入口：

| ticker | 行业 | reader 字符 | source rows | 结构校验 |
| --- | --- | ---: | ---: | --- |
| 002594.SZ | 汽车制造 | 3,463 | 4 | passed |
| 300308.SZ | 光模块 | 3,499 | 4 | passed |
| NVDA | AI 芯片 | 3,870 | 6 | passed |

三个样本沿用同一可见顺序：一句话定位 → 产业坐标 → 创始人与团队 → 发展时间线 → 技术、产品与商业模式 → 财务与估值 → 风险与点评 → 生产记录 → Sources。没有 ticker-specific chapter branch。

## 诚实边界

本 milestone 的 `generation_mode` 是 `replay_existing_round7`，新模型调用为 0、新官方文件为 0，`is_live_research=false`。它证明的是 reader contract 的跨公司兼容性，不是本次新写作，也不把 Ainiu 归档或本地 fixture 变成证据。M3 才会从冻结的官方页级输入生成新的公司档案。
