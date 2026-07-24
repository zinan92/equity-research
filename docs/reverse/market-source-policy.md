# N1-3 跨市场行情与估值来源策略

## 结论

行情与估值必须被拆成两类记录：**可按交易日复查的历史价格**，以及只对采集时刻有效的**估值快照**。前者不能被用来倒推后者。

| 字段 | A 股主 / 备 | 港股、美股、日本主 / 备 | 历史复建资格 | 当前状态 |
| --- | --- | --- | --- | --- |
| price / chg | 腾讯行情 / 东方财富行情 | Yahoo Chart / 新浪（港股） | 是 | 已接入 Yahoo Chart（HK/US/JP）；A 股沿用腾讯日线 |
| mcap | 东方财富行情 / 腾讯行情 | SEC companyfacts + Yahoo 同日收盘（美国）；交易所/公司 PIT 股本 + 同日收盘（港日） | 仅在同日价格与披露日前已知股本齐全时 | 美国已接入 SEC 官方重算；多类别股份、ADR 比率或港日 PIT 股本不全时显式留 gap |
| mcap_usd | 行情市值 + 冻结 FX | 同日本币市值 + Yahoo 历史 FX | 仅在本币市值与同日 FX 都冻结时 | 已接入 `USD/local currency` 同日 FX；不拿今日 FX 替代历史 |
| PE / PB | 东方财富行情 / 腾讯行情 | 同日市值 + SEC/公司披露的 TTM 净利或净资产 | 仅在 filing `known_at <= as_of` 且口径明确时 | 美国 SEC GAAP 重算已接入；adjusted/GAAP、股份范围不一致时标 residual |
| PEG | PE + 版本化增长率 | PE + SEC TTM 同比（仅为另一种明示定义） | 需同口径增长率 | benchmark 未披露增长率基础；SEC TTM 同比结果标 `definition_mismatch`，不能冒充 benchmark PEG |

## 记录与降级规则

1. 每条事实记录必须保存 source URL、原始/规范化载荷哈希、采集时刻、币种、单位与来源 manifest。
2. Yahoo 直接匿名 quote 接口在此环境返回 401；`yfinance` 可完成提供方握手。它输出的为**客户端规范化载荷**，不是伪造的原始 HTTP 响应，manifest 已标记 `client_normalized_capture`。
3. 当前快照统一带 `historical_reconstruction_eligible=false`。报告生成器不得将它作为过去任一交易日的 PE、PB、市值或 PEG。
4. 非美元市值转美元前，必须有同一 `as_of` 的已冻结 FX 记录；没有则输出空值与 gap，不用当天汇率替代。
5. `scripts/validate_market_snapshot.py` 只把外部归档作为运行时 benchmark；它的输出不得提交，归档原文和原评分不得进入产品库。
6. SEC companyfacts 只使用 `filed <= as_of` 的事实。TTM 使用最新年报加本期 YTD 减上年同期 YTD；年报、季度和 proxy 重复值按期间与 filing form 分开，不能让 proxy 覆盖正式 10-K。
7. SEC cover-page shares 可能只覆盖一个股份类别；外国发行人还可能缺 ADR 比率。无法证明总股本与交易证券一致时，市值必须留 gap。

## 30 公司运行时验证结论

- 价格：22 家在 2026-06-30～07-02 窗口内通过；其余 8 家港股/日股都在 **2026-06-22** 找到误差 ≤0.5% 的精确对应值，因此分类为 `benchmark_as_of_outside_declared_window`，不是放宽容差。
- 涨跌幅：28 家在 ±0.1 个百分点内通过；6594.T 与 RRX 的 benchmark previous-close 基础与 Yahoo 日线不同，保留为 2 个 `reference_mismatch`，不放宽容差。
- 估值：106 个可比较字段中 52 个通过、3 个保留 source-definition/share-scope outlier、39 个缺可靠历史输入、12 个 PEG 标 `definition_mismatch`。美国公司使用 Yahoo 同日收盘与 SEC filed-before-as-of companyfacts 重算；港股/日股在缺 PIT 股本或财报 normalizer 时保持 `missing_historical_source`。
- FX：JPY、HKD 及需要的财务币种按匹配交易日冻结，并保留 source URL/raw hash。
- 字段口径：`HISTORICAL_MARKET_FIELD_POLICY` 对 A/HK/US/JP 的 7 个字段共 28 个单元逐一登记 primary/fallback/gap；其中 24/28 为高/中置信度候选归因（85.7%），4 个 PEG 单元因增长率定义未披露保持低置信度。
- 完整 30 家 JSON/Markdown 差异包只在运行时生成，不进入 Git；仓库只保存可复跑验证器、来源合同和汇总结论。

## 验证口径

- 价格：在归档快照所覆盖的交易日窗口内匹配单证券实际交易日，日收盘相对误差不超过 ±0.5%。不得把所有证券误设为同一个收盘日。
- 若窗口外搜索到误差 ≤±0.5% 的精确值，只能标记为 explained residual，并同时保留声明窗口内的最近值；不能把窗口外日期改写成“窗口通过”。
- 市值：同日、同币种、同口径的快照相对误差不超过 ±2%。
- PE/PB：同日、同口径的快照相对误差不超过 ±5%。
- PEG：只有增长率定义一致时才允许按 ±5% 判定；定义未披露时固定标 `definition_mismatch`。
- 没有同日历史估值来源时，结果必须为 `missing_historical_source`，不是通过日 K 线计算出来的“通过”。
