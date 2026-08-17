# Research：板块 K 线与资金流 canonical 数据合同（#811）

- 正式合同：[K 线与资金流 canonical 数据合同 #811](https://github.com/zinan92/equity-research/issues/811)
- 研究状态：`partial`，足以锁定 V1 数据合同与 fail-closed 边界；不足以宣称三个示例板块都已具备完整双流数据
- 探测窗口：2026-08-17（Asia/Shanghai）
- 范围：只验证数据身份、字段、时间语义、可回放性和降级边界；不输出板块强弱、买卖或轮动判断
- 东财访问纪律：全程串行、每次请求间隔至少 1 秒并加抖动；只做有界探测，无并发、无重试风暴

## 1. 结论先行

1. **板块的精确 canonical 主键应是东财 `market=90 + BK code + board_class`，不能是中文名。** 同一 `90.BKxxxx` 可连接板块 K 线与板块资金流，名称只作受版本控制的显示属性。
2. **东财官网当前的“行业”资金流清单使用 `m:90+s:4`，概念使用 `m:90+t:3`。** 本地 `a-stock-data` v3.5.1 中行业仍写成 `m:90+t:2`；实测后者是更宽的 496 项集合，不应直接当作官网行业 canonical universe。
3. **当日/5 日/10 日字段是“当前横截面上的重叠滚动窗口”，不是可按历史日期查询的时间序列。** 想回放过去某日的榜单、占比或排名，必须从启用日起每日保存原始快照。
4. **`stock/fflow/daykline/get` 是另一条按日期返回的日级资金流序列。** 已验证 `BK1036` 可取 100 个交易日，但它不能无条件重建历史 `5d/10d` 占比；窗口占比分母、成分漂移与供应商修订均未被官方定义。
5. **板块 K 线 canonical 采用东财 `fqt=0`（不复权）板块指数。** 日线 `klt=101`，周线 `klt=102`；周线会包含尚未结束的当周，必须显式标记并排除未完成 bar。
6. **同源备用不等于独立 fallback。** `push2delay.eastmoney.com` 在本次窗口可读清单和精确快照，但 K 线只返回身份元数据及空数组，历史资金流只返回当日一行；它只能作为同源降级/诊断路由，不能证明完整历史可用。
7. **精确 BK 板块目前没有验证通过的独立 K 线或资金流 fallback。** ETF 可有腾讯/同花顺 K 线作为独立数据源，但 ETF 是另一种交易工具身份，不能与 BK 板块历史静默拼接，也不能替代东财板块资金流。
8. **三个示例并非都已 complete：** 若把“芯片”明确绑定为行业“半导体” `BK1036`，K 线与资金流均已实证；“AI应用” `BK1629` 的资金流已实证但 K 线未合格；“发电”没有同名板块，候选“电力” `BK0428` 还需要语义签收，且本窗口未完成其主路由 K 线实证。

因此，V1 可以落数据合同，但在进入轮动模型前必须维持：`stale / missing / identity_mismatch / proxy_only => unknown`。

## 2. 证据等级

本文只使用三种标签：

- `verified`：第一方页面/前端源码与本次只读响应可相互支持。
- `inference`：可由响应结构或算术推导，但没有供应商正式定义。
- `unknown`：本次无法验证，不能以空响应或适配器失败推断永久不可用。

| 项目 | 状态 | 证据摘要 |
|---|---|---|
| 官网行业/概念 universe filter | `verified` | 东财资金流页面 source map 明示行业 `m:90+s:4`、概念 `m:90+t:3` |
| 行业/概念 BK 身份及分页 | `verified` | 行业 128、概念 504；响应 `total` 可用；`pz=500` 实际最多返回 100 行，必须翻页 |
| 今日/5d/10d 字段及单位 | `verified` | 第一方列表源码字段映射与三块板 `ulist` 响应一致；金额为元、比例为百分点 |
| `BK1036` 日/周 K 线 | `verified` | 日线 1,327 行、周线 280 行；周线含当前未完成周 |
| `BK1036` 日级历史资金流 | `verified` | `fflow/daykline` 返回 100 行 dated rows |
| `BK1629`、`BK0428` 当前资金流 | `verified` | 精确 ID 快照均返回今日/5d/10d 字段 |
| `BK1629`、`BK0428` 主路由 K 线 | `unknown` | `push2his` 在本窗口 TLS/空响应；同源 delay 路由只回身份与空 `klines`，不能视作永久无历史 |
| 东财公开更新时刻、正式 quota | `unknown` | 第一方前端未声明 SLA/quota；响应未观察到 `RateLimit-*` 或 `Retry-After` |
| 精确 BK 独立 fallback | `unknown` | 未验证到与 `90.BKxxxx` 同构、同成分、同历史的独立源 |
| 数据再分发/商业使用权 | `unknown` | 本研究仅支持本地评估，不构成数据授权证明 |

## 3. Canonical identity：逻辑板块与供应商身份分开

### 3.1 最小身份模型

内部逻辑板块不能只存一个中文字符串，应至少包含：

```json
{
  "sector_id": "chip",
  "display_label": "芯片",
  "taxonomy_version": "sector-rotation-v1",
  "kline_identity": {
    "provider": "eastmoney",
    "instrument_kind": "board_index",
    "market": 90,
    "symbol": "BK1036",
    "provider_name": "半导体",
    "board_class": "industry",
    "relation_to_sector": "accepted_alias"
  },
  "flow_identity": {
    "provider": "eastmoney",
    "instrument_kind": "board",
    "market": 90,
    "symbol": "BK1036",
    "provider_name": "半导体",
    "board_class": "industry",
    "relation_to_sector": "accepted_alias"
  },
  "mapping_valid_from": "2026-08-17",
  "mapping_valid_to": null
}
```

`sector_id` 是产品层身份；`kline_identity` 与 `flow_identity` 是可审计的数据流身份。只有二者的 `market + symbol + board_class` 相同，才可标为 `exact_same_board`。ETF 映射必须写成 `proxy_etf`，不可伪装为精确板块。

### 3.2 名称歧义、重复、缺失与漂移

- canonical key：`provider / market / symbol / board_class`。
- 中文名不唯一时保留所有候选，由 mapping version 明确选择；不得“取第一个”。
- 同名不同 BK、同 BK 改名或行业/概念重分类都触发 `identity_review`，旧映射保留 `valid_to`，不覆盖历史。
- universe 中缺失已注册 BK 时，该板块为 `unavailable`；不得按相似名称自动换板。
- 分页结果若出现重复 BK、`total` 在同一次采集内变化，或各页 `f124` 跨越不同快照，则整次 universe 为 `partial`。

## 4. 东财板块 universe 与资金流合同

### 4.1 第一方入口和分类

东财[行业板块资金流页面](https://data.eastmoney.com/bkzj/hy.html)加载 [`bkzj/list.js.map`](https://data.eastmoney.com/newstatic/js/bkzj/list.js.map)，其中 `jssrc/bkzj/list.ts` 指向 `api/qt/clist/get`，并定义：

| 官网标签 | `fs` | 本次 `data.total` | 说明 |
|---|---:|---:|---|
| 行业 | `m:90+s:4` | 128 | 官网当前行业资金流 universe |
| 概念 | `m:90+t:3` | 504 | 官网当前概念 universe |
| 地域 | `m:90+t:1` | 未纳入本票 | 不在 #811 示例范围 |
| 旧适配器“行业” | `m:90+t:2` | 496 | 更宽的层级/混合集合；不是官网当前“行业”按钮所用 filter |

`clist` 使用 `pn`、`pz` 分页，`data.total` 是当次总数。本次对概念请求 `pz=500` 仍只返回 100 行；逐页 6 次获得 504 个唯一 BK。行业同样 `pz=500` 只回 100/128，因此不能把首屏行数当总量。

V1 规则：

1. universe discovery 以官网 `clist` filter 为 canonical；每页最多请求 100。
2. 同一轮分页必须串行，并保存每页 receipt；完成后按 BK 去重并核对 `total`。
3. 20 板块日常快照可在经过同 session parity 校验后，用 `ulist.np/get` 按精确 `90.BKxxxx` 取数；在 parity 尚未固化前，`clist` 仍是 canonical，`ulist` 只是精确 ID 探针/优化候选。
4. 本地 `a-stock-data` 的 `m:90+t:2` 只作 discovery 参考，不能覆盖第一方 universe 定义。

### 4.2 今日、5 日、10 日字段

| 窗口 | 涨跌幅 | 主力净额 / 占比 | 超大单 | 大单 | 中单 | 小单 |
|---|---|---|---|---|---|---|
| today | `f3` | `f62` / `f184` | `f66` / `f69` | `f72` / `f75` | `f78` / `f81` | `f84` / `f87` |
| 5d | `f109` | `f164` / `f165` | `f166` / `f167` | `f168` / `f169` | `f170` / `f171` | `f172` / `f173` |
| 10d | `f160` | `f174` / `f175` | `f176` / `f177` | `f178` / `f179` | `f180` / `f181` | `f182` / `f183` |

共同身份字段：`f12=BK code`、`f14=name`、`f124=provider timestamp`（Unix seconds，规范化为带时区 ISO-8601）。

单位合同：

- 所有净额原始值统一规范化为 `*_net_yuan`，单位人民币元；第一方图表只是把原值除以 `1e8` 后显示“亿元”。
- 所有 `*_pct` 是百分点，例如原值 `4.98` 规范化仍为 `4.98`，不是 `0.0498`。
- `main = super_large + large` 在三块样本的三个窗口上算术一致，标为 `verified sample invariant`；是否永远成立仍需运行期校验。
- 四档之和不强制为零；不能把 today、5d、10d 相加，因为三个窗口重叠。
- 原始 `null`、`-`、字段缺失或非有限数一律是 missing，不能填 0。只有供应商明确返回数值 0 才是有效零。

### 4.3 历史日级资金流

东财第一方 [`quotemoneyflowchart0715.js`](https://quote.eastmoney.com/newstatic/js/libs/quotemoneyflowchart0715.js)调用：

`/api/qt/stock/fflow/daykline/get?lmt=100&klt=101&secid=90.BKxxxx&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56`

其行格式为：

| 字段 | 规范化名称 | 单位 |
|---|---|---|
| `f51` | `trade_date` | Asia/Shanghai 交易日 |
| `f52` | `main_net_yuan` | 元 |
| `f53` | `small_net_yuan` | 元 |
| `f54` | `medium_net_yuan` | 元 |
| `f55` | `large_net_yuan` | 元 |
| `f56` | `super_large_net_yuan` | 元 |

`BK1036` 主路由实测返回 100 行，范围 2026-03-24 至 2026-08-17。这个结果只证明“至少 100 个交易日可取”，不证明更深历史或不可变历史。

同源 delay 路由对 `BK1629`、`BK0428` 各只回 2026-08-17 一行。由于主路由本次失败，不能据此推断两块板永久只有一日历史；应记录 `partial / endpoint_route=delay`。

## 5. 板块 K 线合同

### 5.1 接口、周期和字段

东财第一方 [`quotekchart/1.0.6.js`](https://quote.eastmoney.com/newstatic/libs/quotekchart/1.0.6.js)调用 `push2his.eastmoney.com/api/qt/stock/kline/get`，默认 `beg=0`、`end=20500101`、`lmt=1000000`，并定义：

- `klt=101`：日线；`klt=102`：周线；`klt=103`：月线。
- `fqt=0`：不复权（Bfq）；`fqt=1`：前复权；`fqt=2`：后复权。
- `fields2=f51..f61` 的行序：日期、开、收、高、低、成交量、成交额、振幅%、涨跌幅%、涨跌额、换手率%。

板块指数不是上市公司的公司行为价格序列，V1 canonical 固定 `fqt=0`。如果未来模型另外需要供应商的 `fqt=1/2` 结果，必须建立不同 `series_id`，不得与不复权历史拼接。

### 5.2 历史深度和连续性实证

`90.BK1036`（半导体）本次结果：

| 周期 | 行数 | 首日 | 末行 | 语义 |
|---|---:|---|---|---|
| day | 1,327 | 2021-03-01 | 2026-08-17 | 完整返回窗口；`dktotal=1327` |
| week | 280 | 2021-03-05 | 2026-08-17 | 2026-08-14 为最近完成周，2026-08-17 是正在形成的当周行 |

接收校验至少包括：

- 日期严格递增且不重复；日线日期属于交易日历。
- `low <= min(open, close) <= max(open, close) <= high`。
- `volume >= 0`，`amount >= 0`，价格和比例均为有限数。
- 周线的当前周在交易周结束前标 `is_complete=false`；模型只消费最近完成周。
- 首个供应商 bar 就是该 series 的可证起点；不能自行向前补值。
- 相同 BK 的名称或 class 改变时先隔离，不能把新旧定义自动串接。

### 5.3 ETF K 线只能是显式 proxy

以 `512480` 为独立 ETF 身份的有界探测：

- 腾讯 `day`：1,000 行，2022-07-05 至 2026-08-17，行内为日期/OHLC/成交量；请求数量限制可能静默截断更早历史。
- 腾讯 `week`：369 行，2019-06-14 至 2026-08-17，同样包含当前未完成周。
- 腾讯 `qfqday`：641 行，2023-12-22 至 2026-08-17；它与 `day` 是不同 adjustment identity，不能混用。
- 同花顺 `hs_512480/01/all.js` 元数据显示日线 1,742 行、起点 2019-06-12；`/11/all.js` 周线 369 行、起点 2019-06-14。响应是压缩 JSONP，生产使用前必须对解码器做固定样本 parity 测试。

ETF V1 也固定以不复权 `day/week` 作为 raw canonical series；`qfqday` 只能建立成另一条显式 series。分红、拆并份额等造成的不复权跳变不能由 adapter 擅自“修复”。腾讯样本只含 OHLCV、不含成交额，因此 `amount_yuan=null` 是有效缺省，不得拿成交量代填。

对于 ETF 自身，腾讯可作 canonical K 线源、同花顺作独立 fallback 候选；但二者都不能成为 `90.BK1036` 的“同一 instrument” fallback。逻辑板块若选择 ETF K 线，必须记录：

```text
relation_to_sector=proxy_etf
kline_identity != flow_identity
quality=proxy_partial
```

## 6. 三个示例的双身份资格

| 产品标签 | 东财候选 | class | K 线资格 | 资金流资格 | V1 状态 |
|---|---|---|---|---|---|
| 芯片 | 半导体 `90.BK1036` | industry | `verified`：日/周均有历史 | `verified`：当前三窗口 + 100 日日流 | `conditional_complete`：须明确接受“芯片→半导体”别名 |
| AI应用 | AI应用 `90.BK1629` | concept | `unknown`：主路由失败，delay 回 `dktotal=0/klines=[]` | `verified current`：三窗口齐；delay 历史路由仅一日 | `partial`，不能进入要求双流完整的轮动计算 |
| 发电 | 电力 `90.BK0428` | industry | `unknown`：主路由失败，delay 回 `dktotal=0/klines=[]` | `verified current`：三窗口齐；delay 历史路由仅一日 | `partial + needs_mapping_acceptance` |

歧义说明：

- “芯片”没有唯一同名板。概念候选还包括“国产芯片” `BK0891`、“半导体概念” `BK0917`、“AI芯片” `BK1127`、“存储芯片” `BK1137`。选择哪一个是产品 taxonomy 决定，不是数据适配器决定。
- “发电”没有本次验证到的同名板。“电力” `BK0428` 是行业候选；“发电机概念” `BK1014` 更接近设备概念，不能自动等同于发电运营。
- “AI应用”是精确同名概念 `BK1629`，但“身份存在”不等于“历史 K 线已合格”。

## 7. 横截面与可回放时间序列

| 数据 | 当前可读 | 供应商历史查询 | 回放条件 |
|---|---|---|---|
| 板块日/周 OHLCV | 是 | 是，`stock/kline/get` | 保存每次 raw；只消费 complete bars；防供应商回修 |
| 当前 today/5d/10d 资金流 | 是 | 未发现历史日期参数 | 必须每日保存完整横截面快照，才能回放当日值、占比和排名 |
| 日级五档资金流 | 是 | 是，`fflow/daykline/get`；本次主路由验证 100 日 | 保存 raw 与 normalized dated rows；更深历史仍 unknown |
| 历史 5d/10d 净额 | 当前字段有 | 不能直接按历史日查询 | 从日流求和只能算待验证的派生值，不能冒充供应商当日 snapshot |
| 历史 5d/10d 占比/排名 | 当前字段有 | 未验证 | 只能回放已保存的当日横截面快照 |

`today`、`5d`、`10d` 是重叠窗口，不是三个互斥期间。任何轮动模型都不得把三者直接相加。

## 8. 时间对齐、freshness 与 `known_at`

统一使用 `Asia/Shanghai` 交易日历，并保留四个不同时间：

| 字段 | 定义 |
|---|---|
| `trade_date` / `as_of_trade_date` | bar 或资金流所属交易日 |
| `provider_ts` | 东财 `f124` 等供应商时间戳；不能替代知识时间 |
| `received_at` | 客户端完整收到响应的 UTC 时间 |
| `known_at` | 数据首次通过 adapter 校验并可供系统使用的时间；V1 取该次 `received_at`，历史导入不得回填成 `trade_date` |

Freshness 规则：

1. 不依赖未经证实的固定“几点更新”；以交易日历、响应 `provider_ts`、K 线末日和 flow `as_of_trade_date` 联合判断。
2. 日终计算只接收最近已完成交易日；盘中日 bar 和当前周 bar 均为 `incomplete`。
3. K 线和资金流必须映射到同一个 `as_of_trade_date`。日期不一致、供应商时间倒退或一个源仍停在前一交易日时，结果是 `identity_mismatch/stale => unknown`。
4. delay 路由必须带 `route=push2delay` 与独立 freshness 状态；不能因 HTTP 200 就标为 fresh/full。
5. 不 carry-forward 旧值冒充今日值。可展示最近成功日期，但模型输入状态仍是 `stale`。

## 9. Canonical source、fallback 与失败语义

| 数据流 | Canonical | 同源降级 | 独立 fallback | 失败规则 |
|---|---|---|---|---|
| BK universe/当前资金流 | 东财第一方 `clist` | `push2delay`，必须标 delayed；`ulist` 需 parity 后才能作精确采集优化 | 未验证 | 失败或分页不一致即 partial/unavailable |
| BK 日/周 K 线 | 东财 `push2his stock/kline`，`fqt=0` | 本次 `push2delay` 不合格：只回身份与空 bars | 未验证到 exact BK fallback | 不用 ETF 或同名板静默补洞 |
| BK 日级历史资金流 | 东财 `push2his stock/fflow/daykline` | delay 本次只回当日，不能冒充 100 日历史 | 未验证 | 历史不足则缩短显式窗口或 unknown |
| ETF 日/周 K 线 | 腾讯，身份为交易所+ticker+adjustment | 腾讯自身重试/缓存不算独立 | 同花顺同 ticker；需解码 parity | 只服务 ETF identity，不改变 BK 状态 |

状态定义：

- `complete`：所需 exact identities、完成日/周 bar、当前 flow 与日期对齐全部通过。
- `partial`：至少一个组件有效，但存在缺行、分页不完整、delay-only、历史不足或部分板块失败。
- `unavailable`：该数据流没有任何可接受的新鲜响应。
- `proxy_partial`：只有 ETF 等代理身份可用。
- `unknown`：下游判断状态；任何 `partial/unavailable/stale/mismatch/proxy_only` 在要求 exact 双流的模型中都必须落此状态。

HTTP 200 但 `data=null`、`diff=[]`、`klines=[]` 仍是失败证据，不是永久无数据证明。HTTP 403/429/502、TLS、timeout、HTML 伪 JSON、schema drift 都先保存 receipt，再按上表 fail closed。

## 10. 最小规范化 schema

### 10.1 K 线 bar

```text
contract_version
sector_id
series_id
provider, route, instrument_kind
market, symbol, provider_name, board_class
relation_to_sector
interval: day | week
adjustment: none | qfq | hfq
trade_date
open, high, low, close
volume
amount_yuan: decimal | null
is_complete
provider_ts, received_at, known_at
raw_sha256, receipt_id, adapter_version
quality_status, rejection_reasons[]
```

### 10.2 当前资金流 snapshot

```text
sector_id, flow_identity_id
as_of_trade_date
provider_ts, received_at, known_at
window: today | 5d | 10d
price_change_pct
main_net_yuan, main_net_pct
super_large_net_yuan, super_large_net_pct
large_net_yuan, large_net_pct
medium_net_yuan, medium_net_pct
small_net_yuan, small_net_pct
snapshot_kind: current_cross_section
raw_sha256, receipt_id
quality_status, missing_fields[]
```

### 10.3 日级历史资金流

```text
sector_id, flow_identity_id, trade_date
main_net_yuan, super_large_net_yuan, large_net_yuan
medium_net_yuan, small_net_yuan
provider_ts: null | timestamp
received_at, known_at
replayability: provider_dated_series
raw_sha256, receipt_id
quality_status
```

所有数值使用 decimal 或有界整数；不要用二进制 float 作为持久化 canonical 值。

### 10.4 样例记录（只展示身份与证据，不展示市场判断）

```json
{
  "contract_version": "sector-data-v1",
  "sector_id": "chip",
  "as_of_trade_date": "2026-08-17",
  "kline_identity_id": "eastmoney:90.BK1036:industry:day:none",
  "flow_identity_id": "eastmoney:90.BK1036:industry",
  "flow_windows_present": ["today", "5d", "10d"],
  "kline_raw_sha256": "c67a3e73224d7a13ba0b80ebd89d519edb95cec52e7c37b9e4f8ea43ff0852f3",
  "flow_raw_sha256": "e4aafdd5beae4b30f2aab2ead81a8891aecd6042de193f22840d9f0f0e09ac29",
  "quality_status": "conditional_complete",
  "quality_reasons": ["sector_alias_requires_acceptance"],
  "market_judgment": null
}
```

## 11. Raw receipt 与可追溯要求

每次 attempt，无论成功或失败，至少保存：

```text
attempt_id
provider, endpoint_class, route
method
requested_url_sanitized, final_url_sanitized
query_params_sanitized
started_at, received_at, elapsed_ms
http_status
safe_response_headers
content_type, byte_count, sha256
raw_object_path | bounded_error_excerpt
adapter_version
parse_status, schema_status
accepted_record_count, rejected_record_count
error_class, error_message_sanitized
```

Raw response 与 receipt 不可变；normalized 记录引用其 hash。失败响应若不适合保存全文，至少保存安全 hash、字节数、content type、状态码及有界脱敏片段。本次 `push2` 502 的完整 157-byte body 为普通 nginx HTML，SHA-256 为 `24fe03fdb26088bfff8b1363911c29c79a19614bca42cdcdb9fefdf52917aeb1`：

```html
<html>
<head><title>502 Bad Gateway</title></head>
<body>
<center><h1>502 Bad Gateway</h1></center>
<hr><center>nginx/1.26.2</center>
</body>
</html>
```

## 12. 节流、缓存和运行期验收

东财未在所查第一方源码或响应头中给出公开 quota。V1 采用保守的内部限制，而不是伪造一个“官方 QPS”：

- 单进程、单 session 串行；请求间隔 `>=1s + jitter`。
- universe 每 session 缓存，分页只抓到 `ceil(total/100)`；不为每个板块重复抓全市场。
- 失败最多做一次有抖动的有界重试；403/429/连续 502/TLS 立即停止本轮，不切并发。
- 同一原始响应 fan-out 到 20 个注册板块，避免 20 次相同 universe 调用。
- 缓存键必须含 provider、route、endpoint、完整参数、observed session 和 adapter version。
- schema、字段单位、ID/name/class、主力拆分恒等式与日期连续性均进入运行期 contract test。

每次日终批次通过以下最小门：

1. universe 完整且分页一致；20 个注册 BK 均能精确命中。
2. 当日 K 线为 complete，周线只取最近 complete week。
3. 三个 flow window 的必填字段均为有限数，单位转换只发生一次。
4. K 线与 flow `as_of_trade_date` 一致。
5. receipt/raw hash 可读回，normalized 行可追溯到唯一 attempt。
6. 任何一项失败都保留局部数据，但总体模型输入不升级为 complete。

## 13. 本次有界探测 receipts

以下只记录结构和可复验性，不作市场解释。

| 请求/资产 | HTTP/结果 | bytes / rows | SHA-256 | 关键观察 |
|---|---|---:|---|---|
| 东财行业资金流页面 | 200 HTML | 218,726 B | `66199a7ea350a919fa73bd6faaa41787b4d2c5c09c07c23a0d545dd5260b9b94` | 第一方页面入口 |
| `bkzj/list.js.map` | 200 JSON | 101,254 B | `e21ea6975f3a1604131fee74a81580ce1f402b5a95ac6e5b5a0adaee39046f1c` | filter、分页、字段来源 |
| `quotekchart/1.0.6.js` | 200 JS | 164,135 B | `d42e0e371575f7046b47cbffee12a1de2f6f9376082f64d99ec708eb099e57f6` | K 线 endpoint、周期、复权枚举 |
| `quotemoneyflowchart0715.js` | 200 JS | 81,526 B | `5752bdae1f01a5c0ad0bbaf630074ba419f897199a615e26619f7d35836fcb70` | 日级资金流 endpoint 与 f51..f56 |
| `BK1036` 日 K | 200 JSON | 1,327 rows | `c67a3e73224d7a13ba0b80ebd89d519edb95cec52e7c37b9e4f8ea43ff0852f3` | 2021-03-01..2026-08-17 |
| `BK1036` 周 K | 200 JSON | 280 rows | `614e10d8210a9a40327a0a65aff156c64af3a2c6735e3e04f6e1f89ec4d93727` | 包含当前未完成周 |
| 三块板精确 flow snapshot | 200 JSON | 1,864 B / 3 rows | `e4aafdd5beae4b30f2aab2ead81a8891aecd6042de193f22840d9f0f0e09ac29` | 三行均有 today/5d/10d；`f124=2026-08-17 15:39:32+08:00` |
| `BK1036` 日级 flow | 200 JSON | 100 rows | `bc2ebec764e4a133b9feefade6596a331b52ef6bbe073b99e158285ef343bf47` | 2026-03-24..2026-08-17 |
| `BK1629` 官方 quote page | 200 HTML | 45,649 B | `0e25e4225b81a0e1c570da79d5e247609c5207a0809623dd4359afbebba9223c` | 标题确认 `AI应用(BK1629)` |
| `BK0428` 官方 quote page | 200 HTML | 45,619 B | `4198e34e9bcf3c8430505ffc21f6b512a075d2fcb94f153d5bae6b81440cce6b` | 标题确认 `电力(BK0428)` |
| delay `BK1629` 日 K | 200 JSON | 0 rows | `38107b3839776fb83580bb2410cfe34770929f55d4cf9200285e5a83dda265b3` | 身份存在，`dktotal=0`；不证明永久无历史 |
| delay `BK1629` 周 K | 200 JSON | 0 rows | `24222e839dfb29df204aa719706c4c5c98d283d4724cc7df441cb0f4ec1aeecf` | 同上 |
| delay `BK0428` 日 K（含官网 `ut`） | 200 JSON | 0 rows | `ac615e7b43181ecda3d35ad5b7f0f025e8b08cb258fb875c9d79e5712bf3e836` | delay 路由不具备完整 K 线 fallback 资格 |
| delay `BK1629` / `BK0428` 日级 flow | 200 JSON | 各 1 row | `86e7c5bf6681ba44f0bbfffd3826158410d592c6ae117f644408519156e2bc51` / `a52c80b183643218add5f2d79d1d8d525bfb12779e83d40f50416db761c0e173` | 只证明 delay 当日可读 |
| 腾讯 `512480` day/week | 200 JSON-as-text/html | 1,000 / 369 rows | `4aefc28ca50dabb9714694a01dbf0e38323c3f48a1a711fd91478d423f08bb4c` / `14e7646d73067b3fbf3f5c4837d49d945dcd6082dcb446c6ceb052da0a6dd451` | ETF 独立身份；source-specific parser 必需 |
| 同花顺 `512480` day/week | 200 JS | 1,742 / 369 metadata rows | `e82cf513fe7798f2d2cdc6dfaed1d60b88c5da515ab9911a66c8db351c55d46d` / `0fd00f6516de35faaf83bc9ae137e246eca51ee0560fd273f52638d075c7f16e` | 压缩 JSONP；需 decoder parity |

主路由失败证据包括 502 HTML、`RemoteDisconnected`、`DECRYPTION_FAILED_OR_BAD_RECORD_MAC` 和 empty reply。它们说明本次采集路径不稳定，不说明供应商永久不可用。

## 14. 尚未解决的缺口

1. 待在另一独立采集窗口重试 `BK1629`、`BK0428` 的主 `push2his` 日/周 K 线，并保存成功 raw 或有界失败 receipt；本票不能把 delay 空数组升级为结论。
2. 待验证 `fflow/daykline` 超过 100 日的真实最大深度、修订行为，以及逐日净额与当日 5d/10d 净额的长期 parity。
3. 待 Park/产品 taxonomy 明确签收“芯片→半导体 `BK1036`”与“发电→电力 `BK0428`”；否则两者保持 ambiguous。
4. 待对 20 个最终 BK 做同 session `clist` vs `ulist` 字段 parity，之后才能把精确 ID 批量接口提升为 canonical 优化。
5. 待找到或否定精确 BK 的独立 fallback；ETF 只能维持 `proxy_partial`。
6. 待法务/数据权利流程确认存储、再分发和商业使用边界。
7. 供应商未公布 quota 和稳定更新时间；只能以保守节流、日期校验和 raw receipts 管理风险。

## 15. 采用的仓内合同

本研究沿用仓内既有原则：

- [Market regime data contract](../../market-regime/data-contract.md)：source-specific 解析、严格 OHLC 校验、不可静默换 proxy、raw/normalized/receipt 可追溯。
- [Live data contract](../../market-regime/live-data-contract.md)：`observed_at/received_at/provider timestamp` 分离、未完成 bar、`complete/partial/unavailable`。
- [Canonical data contract ADR](../../architecture/adr/0001-canonical-data-contract-v1.md)：adapter accepted/rejected、raw hash、`known_at` 与 fail-closed。

这些规则锁定的是身份、证据和失败语义，不是对任何板块当前走势的判断。
