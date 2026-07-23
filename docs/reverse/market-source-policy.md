# N1-3 跨市场行情与估值来源策略

## 结论

行情与估值必须被拆成两类记录：**可按交易日复查的历史价格**，以及只对采集时刻有效的**估值快照**。前者不能被用来倒推后者。

| 字段 | A 股主 / 备 | 港股、美股、日本主 / 备 | 历史复建资格 | 当前状态 |
| --- | --- | --- | --- | --- |
| price / chg | 腾讯行情 / 东方财富行情 | Yahoo Chart / 新浪（港股） | 是 | 已接入 Yahoo Chart（HK/US/JP）；A 股沿用腾讯日线 |
| mcap | 东方财富行情 / 腾讯行情 | Yahoo Snapshot / 官方交易所或公司披露 | 否，需历史快照 | 已接入当前 Yahoo Snapshot；历史缺档显式保留 |
| mcap_usd | 行情市值 + 冻结 FX | Yahoo Snapshot（USD）或行情市值 + 冻结 FX | 否，需同日 FX | USD 已接入；非 USD 在没有冻结 FX 时留空 |
| PE / PB | 东方财富行情 / 腾讯行情 | Yahoo Snapshot / 公司财报重算 | 否，需历史估值或 TTM 输入 | 已接入当前 Yahoo Snapshot；历史缺档显式保留 |
| PEG | PE + 版本化增长率 | Yahoo Snapshot / PE + 版本化增长率 | 否，需同口径增长率 | 只采集提供方当前值；不可得时留空 |

## 记录与降级规则

1. 每条事实记录必须保存 source URL、原始/规范化载荷哈希、采集时刻、币种、单位与来源 manifest。
2. Yahoo 直接匿名 quote 接口在此环境返回 401；`yfinance` 可完成提供方握手。它输出的为**客户端规范化载荷**，不是伪造的原始 HTTP 响应，manifest 已标记 `client_normalized_capture`。
3. 当前快照统一带 `historical_reconstruction_eligible=false`。报告生成器不得将它作为过去任一交易日的 PE、PB、市值或 PEG。
4. 非美元市值转美元前，必须有同一 `as_of` 的已冻结 FX 记录；没有则输出空值与 gap，不用当天汇率替代。
5. `scripts/validate_market_snapshot.py` 只把外部归档作为运行时 benchmark；它的输出不得提交，归档原文和原评分不得进入产品库。

## 验证口径

- 价格：在归档快照所覆盖的交易日窗口内匹配单证券实际交易日，日收盘相对误差不超过 ±0.5%。不得把所有证券误设为同一个收盘日。
- 市值：同日、同币种、同口径的快照相对误差不超过 ±2%。
- PE/PB：同日、同口径的快照相对误差不超过 ±5%。
- 没有同日历史估值来源时，结果必须为 `missing_historical_source`，不是通过日 K 线计算出来的“通过”。
