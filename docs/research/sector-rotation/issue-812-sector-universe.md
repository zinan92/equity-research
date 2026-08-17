# #812：旧 a-share 分类映射为 20 板块候选池

> 合同：[GitHub issue #812](https://github.com/zinan92/equity-research/issues/812)（parent map #810）
>
> 研究时点：2026-08-17（Asia/Shanghai）
>
> 证据状态：**PARTIAL / decision-ready**
>
> 决策状态：**Research recommendation only — pending Park HITL approval；不是最终冻结的 20 板块。**

## 结论先行

旧 a-share 中存在的不是一套稳定、互斥的行业 taxonomy，而是三个用途和粒度不同的版本：

1. **16 个自定义个股组件**：369 只股票，每只股票只有一个 `stock_sectors.sector`；它们是人工篮子，不是同花顺或交易所指数。
2. **19 个 Dashboard 展示板块**：数据库 `available_sectors` 的后期快照；相较 16 个组件，删除、改名并补入了若干展示项。
3. **8 个重点主题**：为 Daily Review 建立的叙事/别名聚合层，允许一个主题吸收多个旧板块；它不是 8 个同级可交易指数。

因此，本研究建议把新 universe 定义成 **20 个稳定监控槽位（monitoring slots）**，每个槽位分别保存：稳定 slug、中文显示名、历史组件来源、当前 K 线主身份、身份类型和重叠组。它不是互斥行业树。尤其是 `芯片 → 半导体设备 / 存储`、`新能源 → 光伏 / 风电 / 储能` 这样的宽窄关系必须显式存在，不能用同级二字掩盖。

下面给出的 exactly-20 草案满足 #812 的 18–22 个候选要求，并覆盖 Park 明确提出的 `芯片`、`AI应用`、`发电`、`半导体设备`、`存储`、`机器人`、`创新药`、`新能源`、`白酒`、`银行`、`保险`。选择依据只有历史连续性、身份可取性、代表性和重叠控制，**没有使用 2026-08-17 的涨跌、资金流或任何当前表现来选板块**。

## 1. 证据边界与术语

### 1.1 四种身份不能混写

| 身份类型 | 本文含义 | 能否直接当作同一个东西 |
|---|---|---|
| 行业板块 | 数据商按经营行业组织的板块，例如东方财富 `银行Ⅱ` | 只能与同一数据商、同一代码和版本的历史序列连续使用 |
| 概念板块 | 数据商按主题维护的动态成分，例如 `存储芯片`、`机器人概念` | 不能静默等同于行业，也不能假定成分长期不变 |
| ETF / 指数代理 | 交易所基金或指数公司指数，拥有独立编制方案 | 只能作为另一个可交易/可回测代理，不能因简称相似就等同于板块 |
| 自定义篮子 | 旧 repo 的 CSV/SQLite 个股组件 | 是 Park 旧观察口径；没有指数编制、调样和复权合同 |

本文表格中的“主身份”表示后续取得板块 K 线时优先尝试的代码，不表示中文显示名与数据商名称完全相等。凡是代理关系都明确写为“代理”。

### 1.2 攻防标签不是层级，也不是当日结论

初步标签只是长期行为先验：

- `进攻`：通常具有较高风险偏好、产业催化或市场 beta。
- `偏防`：通常现金流/股息/必选或避险属性更强，但主题行情中仍可转为进攻。
- `周期/混合`：不能稳定塞进攻或防，需由当天宏观 regime、相对强弱和资金确认。

本议题不判断 2026-08-17 哪个板块正在进攻，也不实现轮动算法。

## 2. 旧 a-share 的三个真实版本

### 2.1 当前能直接读取的本地快照

本地路径：`/Users/wendy/work/trading-co/ashare`。

2026-08-17 回读时，该目录只保留部分文件，且**不存在 `.git` 元数据**，所以不能为它补造 Git commit。可复核版本证据如下：

| 文件 | SHA-256 | mtime（+08:00） | 证据用途 |
|---|---|---|---|
| `config/ashare_focus_themes.json` | `5f1cfa397092b8759594b2bb121d106c804c6d2a098cf533bcaf1125b99ce17e` | 2026-05-09 15:00:40 | 8 个 Primary 主题、Secondary 主题、别名和数据策略 |
| `docs/ashare_universe_and_focus_themes.md` | `537583eafacd599ef0e1516c195fe3724e7fd638a3e818799b888065ed01ee08` | 2026-05-09 15:01:13 | 旧板块复用与多主题映射说明 |
| `daily-review.skill` | `48c443db773e3bd4e99d67c870976a5b64be59074257018896e5faabdbbd2854` | 2026-01-27 20:11:58 | Daily Review 使用场景 |

2026-05-09 的原始 session 记录显示，当时这里仍是完整 repo，包含 `data/sectors/*.csv`、`data/market.db`、`docs/CATEGORIES_GUIDE.md`、`scripts/create_sectors_table.py` 等；同一 session 最后显示新增的 focus-theme JSON/说明文档仍为 untracked，因此本研究只把它们称为“本地快照”，不称为已提交版本。

历史证据位置：`/Users/wendy/.codex/sessions/2026/05/09/rollout-2026-05-09T12-37-11-019e0b06-707d-7d12-9772-ce13ac60776c.jsonl`。

### 2.2 版本 A：16 个自定义个股组件（369 只）

历史 `docs/CATEGORIES_GUIDE.md` 明确写为“16 个赛道、369 只”，并指向 `stock_sectors + available_sectors` 与 `data/sectors/*.csv`：

| 旧组件 | 股票数 | 旧组件 | 股票数 |
|---|---:|---|---:|
| AI应用 | 67 | 金属 | 58 |
| 军工 | 46 | 机器人 | 38 |
| 芯片 | 33 | 创新药 | 27 |
| 光伏 | 20 | 发电 | 19 |
| 新能源汽车 | 14 | 贵金属 | 12 |
| 其他 | 12 | 半导体 | 7 |
| PCB | 7 | 消费 | 4 |
| 可控核聚变 | 3 | 脑机接口 | 2 |

可确认的组合逻辑：

- `data/sectors/import_sectors.py` 遍历 `sectors_summary.json` 的 ticker 列表，将每个 ticker 写入 `stock_sectors(ticker, sector, ...)`。
- 历史表结构只有一个 `sector` 字段；后期数据库查询也得到 `COUNT(DISTINCT ticker)=COUNT(*)=1938`，即当时仍是一股一标签。
- `scripts/update_stock_sectors.py` 的 AI 应用示例对已有 ticker 执行 `UPDATE ... SET sector = ?`，再次证明它是覆盖式单标签，而不是多主题 membership。
- 因此，“个股组件 → 板块”的真实含义是**人工维护的一组股票被赋给一个展示标签**，不是从板块指数成分自动反推。

### 2.3 版本 B：19 个 Dashboard 展示板块

2026-05-09 对历史 SQLite `available_sectors` 的实际查询返回：

| display_order | 名称 | display_order | 名称 |
|---:|---|---:|---|
| 0 | AI应用 | 2 | PCB |
| 3 | 机器人 | 4 | 军工 |
| 5 | 储能锂电 | 6 | 可控核聚变 |
| 7 | 发电 | 8 | 金属 |
| 9 | 创新药 | 10 | 脑机接口 |
| 12 | 其他 | 13 | 半导体 |
| 14 | 光伏 | 15 | 贵金属 |
| 16 | 金融 | 17 | 算力/AI基建 |
| 18 | 传媒游戏 | 19 | 白酒 |
| 99 | 旅游 |  |  |

这不是 16 个组件的简单加三：

- 16 版中的 `芯片`、`新能源汽车`、`消费` 不在这张 19 项展示表中。
- 19 版新增 `储能锂电`、`金融`、`算力/AI基建`、`传媒游戏`、`白酒`、`旅游`。
- 同期 `stock_sectors` 已扩到 19 个自定义标签（另有 `指数成份股`），且不少成分数与 16 版不同。

所以 16 与 19 是两个时间切片，不能合并后声称它们同时是“原 repo 的唯一分类”。

### 2.4 版本 C：8 个 Primary focus themes

当前可读 JSON 的 8 个 Primary 是：

1. `算力/AI基建`：吸收芯片、半导体、PCB、CPO、光模块、5G、液冷、数据中心等别名。
2. `电力`：别名含发电、火电、水电、核电、光热发电；说明限定为发电侧，除非明确讨论电网/设备。
3. `存储`：存储芯片、DRAM、NAND、HBM；文件明确说明应与 broad chips 分开观察。
4. `新能源`：新能源汽车、储能锂电、光伏、风电、充电桩等上位主题。
5. `商业航天`：旧 CSV 不一定存在，但属于重点叙事。
6. `创新药`：保留独立主题。
7. `稀有金属`：聚合稀土、小金属、金属、贵金属及具体品种。
8. `人形机器人`：可用 broad robot board 作缺少窄板时的证据。

Secondary 列表为 `AI应用`、`军工`、`可控核聚变`、`脑机接口`、`传媒游戏`、`金融`、`白酒`、`旅游`、`消费`、`其他`。

这份配置的真实价值是别名和叙事聚合；它同时明确 `theme_membership_sources` 可来自 curated CSV、同花顺概念/行业映射，并要求不覆盖旧单标签表。它不是已经完成的 8 个指数序列。

### 2.5 事实与研究者推断分界

| 陈述 | 状态 |
|---|---|
| 旧文档存在 16 个组件、369 只股票及上述计数 | 历史命令输出验证 |
| 后期 `available_sectors` 存在上述 19 个展示项 | 历史 SQLite 查询验证 |
| 当前 focus 配置存在 8 个 Primary 和 Secondary 列表 | 当前文件 + SHA-256 验证 |
| 旧 `stock_sectors` 是一股一标签 | 表结构、导入脚本和计数共同验证 |
| 16 → 19 的每一项为何被增删 | **未知**；没有决策日志，不能反推作者动机 |
| 下面 20 个槽位是旧 repo 已经存在的最终 universe | **不是事实**；是本研究给 #812 的候选映射 |

## 3. 当前第一方身份核验

### 3.1 查询记录

遵循 A 股数据调用规范，本轮对东方财富接口串行调用，只取代码/名称字段 `f12,f14`，不取涨跌或资金字段：

| 时间（+08:00） | 来源身份 | 请求/结果 |
|---|---|---|
| 2026-08-17 18:38:16 | 东方财富 `push2` 行业目录 | `fs=m:90+t:2`、`fid=f12`；HTTP 200，响应称 total=496，但单页只返回 100 行 |
| 2026-08-17 18:38–18:41 | 东方财富 `79.push2` 概念目录 | `fs=m:90+t:3`；一次 HTTP 200，响应称 total=504、返回 100 行；后续分页遇到 502/代理中断 |
| 2026-08-17 18:41–18:50 | 东方财富板块详情页 | 逐项核对候选的板块代码与页面标题 |
| 2026-08-17 | 国证指数、上海证券交易所 | 核对少量指数/ETF 正式名称，未读取表现来筛选 |

实际 API：

```text
https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=600&po=0&np=1&fltt=2&invt=2&fid=f12&fs=m%3A90%2Bt%3A2&fields=f12%2Cf14
https://79.push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=0&np=1&fltt=2&invt=2&fid=f12&fs=m%3A90%2Bt%3A3&fields=f12%2Cf14
```

东方财富是**数据商第一方页面/API**，不是交易所或官方行业标准。目录分页不完整意味着不能声称“所有板块已经穷尽”，但不影响已逐页核对的代码/名称；也不能因为分页失败就声称某个未出现的板块不存在。

### 3.2 exactly-20 研究草案（pending Park HITL）

> 这 20 行是候选监控槽位，不是最终冻结，不赋权重，也不代表当前强弱排序。

| # | stable slug | 中文显示名 | 初步攻防 | 后续 K 线主身份（类型） | 旧来源组件 | 覆盖理由与重叠警告 |
|---:|---|---|---|---|---|---|
| 1 | `chips` | 芯片 | 进攻 | [半导体 BK1036](https://quote.eastmoney.com/bk/90.BK1036.html)（行业代理） | 16: 芯片 33；16/19: 半导体；8: 算力/AI基建别名 | 保留 Park 的 broad hardware 槽位；与 #2/#3 高重叠，`芯片 ≠ 半导体板块`，这里只是代理 |
| 2 | `semiconductor-equipment` | 半导体设备 | 进攻 | [半导体设备 BK1326](https://quote.eastmoney.com/bk/90.BK1326.html)（细分板块，目录类型待复核） | 原 repo 无独立组件；Park 明确补充 | 设备周期和整芯片不同；与 #1 同簇，不能合并计算 breadth |
| 3 | `memory` | 存储 | 进攻/周期 | [存储芯片 BK1137](https://quote.eastmoney.com/bk/90.BK1137.html)（概念） | 8: 存储；旧数据库概念曾匹配存储芯片 | DRAM/NAND/HBM 有独立周期；与 #1 重叠但有保留理由 |
| 4 | `pcb` | PCB | 进攻 | [PCB BK0877](https://quote.eastmoney.com/bk/90.BK0877.html)（概念） | 16: PCB 7；19: PCB | AI 硬件中游代表；与芯片、算力基础设施相关但不是父子关系 |
| 5 | `ai-applications` | AI应用 | 进攻 | [AI应用 BK1629](https://quote.eastmoney.com/bk/90.BK1629.html)（概念）；国证 AI 应用指数 980112 为指数备选 | 16: AI应用 67；19: AI应用；8: Secondary | 明确承担 software/application 槽位；与传媒/游戏可能重叠 |
| 6 | `robotics` | 机器人 | 进攻 | [机器人概念 BK1090](https://quote.eastmoney.com/bk/90.BK1090.html)（概念） | 16: 机器人 38；19: 机器人；8: 人形机器人上位映射 | broad 口径覆盖更稳；若 Park 只要人形，应整体替换为 BK1184 |
| 7 | `innovative-drugs` | 创新药 | 进攻/独立 | [创新药 BK1106](https://quote.eastmoney.com/bk/90.BK1106.html)（概念） | 16: 创新药 27；19/8: 创新药 | 与 AI/能源相关性较低，提供成长风格内部轮动对照 |
| 8 | `new-energy` | 新能源 | 进攻/周期 | [新能源 BK0493](https://quote.eastmoney.com/bk/90.BK0493.html)（概念） | 16: 光伏/新能源汽车；19: 光伏/储能锂电；8: 新能源 | 上位聚合槽；若保留，光伏/风电/储能只能作为 drill-down 或替换项 |
| 9 | `power-generation` | 发电 | 偏防/主题时可进攻 | [电力 BK0428](https://quote.eastmoney.com/bk/90.BK0428.html)（行业代理） | 16: 发电 19；19: 发电；8: 电力 | 发电侧现金流与 AI 电力需求叙事兼具；`发电 ≠ 全电力产业链` |
| 10 | `defense` | 军工 | 进攻/独立 | [国防军工 BK1204](https://quote.eastmoney.com/bk/90.BK1204.html)（行业）；[军工 BK0490](https://quote.eastmoney.com/bk/90.BK0490.html) 为概念备选 | 16: 军工 46；19: 军工；8: Secondary | 用行业身份减少概念漂移；与商业航天有成分重叠 |
| 11 | `commercial-space` | 商业航天 | 进攻 | [商业航天 BK0963](https://quote.eastmoney.com/bk/90.BK0963.html)（概念） | 8: 商业航天；旧数据库概念曾命中 | 补足独立重点叙事；与军工、卫星 ETF 高重叠 |
| 12 | `controlled-fusion` | 可控核聚变 | 进攻 | [可控核聚变 BK1163](https://quote.eastmoney.com/bk/90.BK1163.html)（概念） | 16: 3；19: 可控核聚变；8: Secondary | 历史连续，但旧篮子极窄；是 20 行中最应接受 HITL 质疑的槽位之一 |
| 13 | `rare-metals` | 稀有金属 | 周期/进攻 | [小金属 BK1027](https://quote.eastmoney.com/bk/90.BK1027.html)（行业代理） | 16/19: 金属；8: 稀有金属 | 比旧“金属”更可解释；`稀有金属 ≠ 小金属`，仍需最终指数合同 |
| 14 | `precious-metals` | 贵金属 | 偏防/避险 | [贵金属 BK0732](https://quote.eastmoney.com/bk/90.BK0732.html)（行业） | 16: 贵金属 12；19: 贵金属；8 中曾被稀有金属聚合 | 必须与 #13 分开，否则周期资源和避险属性被混掉 |
| 15 | `media-gaming` | 传媒（含游戏观察） | 进攻/消费 | [传媒 BK0486](https://quote.eastmoney.com/bk/90.BK0486.html)（行业代理）；[游戏Ⅱ BK1046](https://quote.eastmoney.com/bk/90.BK1046.html) 为窄口径 | 19: 传媒游戏；8: Secondary | 旧项是自定义合并名，不能声称等于传媒行业；与 AI 应用有内容侧重叠 |
| 16 | `baijiu` | 白酒 | 偏防/消费 | [白酒 BK0896](https://quote.eastmoney.com/bk/90.BK0896.html)（行业） | 19: 白酒；8: Secondary；16 中仅由“消费”覆盖 | 代表消费核心资产和相对防守风格；不等于整个消费板块 |
| 17 | `banks` | 银行 | 防守 | [银行Ⅱ BK0475](https://quote.eastmoney.com/bk/90.BK0475.html)（行业） | 19: 金融；8: Secondary 金融 | 将旧“金融”拆成可观察 peer；不可沿用旧金融篮子假装纯银行 |
| 18 | `insurance` | 保险 | 防守 | [保险Ⅱ BK0474](https://quote.eastmoney.com/bk/90.BK0474.html)（行业） | 19: 金融；Park 明确补充 | 利率敏感度与银行、证券不同；旧 repo 无独立保险组件 |
| 19 | `securities` | 证券 | 进攻/高 beta | [证券Ⅱ BK0473](https://quote.eastmoney.com/bk/90.BK0473.html)（行业） | 19: 金融 | 承担风险偏好/成交活跃度代理；不能与银行、保险合并判定攻防 |
| 20 | `tourism` | 旅游 | 周期/消费 | [旅游及景区 BK1272](https://quote.eastmoney.com/bk/90.BK1272.html)（行业） | 19: 旅游；8: Secondary | 提供可选消费/线下景气轮动观察；19 版同期标签查询为 10 股，当前身份应换成板块序列 |

### 3.3 为什么这 20 个，而不是按当前行情挑

选择规则按顺序是：

1. 覆盖 #812 和 Park 已明确点名的 11 个板块。
2. 优先保留在 16/19 版本中重复出现的旧观察习惯。
3. 对 `金融`、`金属` 等过宽标签拆成行为差异足够大的 peer sectors。
4. 删除 `其他`：它不是稳定经济含义，无法形成可解释 K 线。
5. 避免同时把 `新能源 + 光伏 + 风电 + 储能`、`机器人 + 人形机器人` 全塞进 20 行；需要时用替换或 drill-down。
6. 要求至少有一个当前可识别的 provider board 或官方指数候选；身份仍不够精确的地方保留缺口。

没有用涨幅、成交额、资金净流入、热度或 2026 年主题表现作为入选条件。

### 3.4 原 repo 支持与需要补充的边界

- **旧组件/展示项直接支持（12）**：`chips`、`ai-applications`、`pcb`、`robotics`、`innovative-drugs`、`power-generation`、`defense`、`controlled-fusion`、`precious-metals`、`media-gaming`、`baijiu`、`tourism`。这里的“支持”只证明旧名字/篮子存在，不证明当前 provider 身份与旧成分相等。
- **后期 focus 配置支持、但没有独立旧组件（4）**：`memory`、`new-energy`、`commercial-space`、`rare-metals`。它们有别名/聚合设计，仍需为 K 线冻结精确指数或板块。
- **本研究明确补充或拆分（4）**：`semiconductor-equipment` 是 Park 新增要求；`banks`、`insurance`、`securities` 是从旧 `金融` 拆出的三个 peer sectors。旧 repo 没有这四个独立个股组件。

这三组刚好覆盖 20 行，避免把研究者补充伪装成“旧 repo 原本就有”。

## 4. 主要重叠冲突

| 重叠组 | 冲突 | 建议处理 |
|---|---|---|
| 芯片硬件 | 芯片、半导体设备、存储、PCB 不是互斥行业；同一公司可能跨槽 | 四个槽可同时保留，但加 `overlap_group=chip-hardware`，轮动统计不能把它们当四份独立 breadth |
| AI 软件/内容 | AI应用与传媒/游戏可能共享软件、广告、游戏公司 | 主身份分开；个股 breadth 或资金合计时去重 |
| 电力/新能源 | 发电是供给侧行业，新能源是能源转型概念；新能源又覆盖光伏、风电、储能 | 保留发电 + broad 新能源；子赛道默认 drill-down，不默认加到 20 |
| 军工/航天 | 商业航天常被军工概念吸收 | 保留两个叙事槽，但必须标注相关性；不能把军工上涨自动解释成航天轮动 |
| 金属 | 旧“金属”、稀有金属、小金属、贵金属边界不同 | 新草案只留稀有金属与贵金属；放弃无边界的 broad 金属 |
| 金融 | 旧“金融”混合银行、保险、证券，三者攻防行为不同 | 拆成三个行业身份；旧金融组件只作 provenance，不直接续 K 线 |
| 自定义篮子 vs provider | 中文同名不代表成分、权重、调样和复权一致 | 不拼接历史序列；每个槽位记录 `identity_type/provider/code/as_of` |

## 5. 替代项（只能换入，不应无条件加总）

| 替代项 | 当前身份/旧证据 | 建议替换谁 | 采用条件 |
|---|---|---|---|
| 人形机器人 | [人形机器人 BK1184](https://quote.eastmoney.com/bk/90.BK1184.html)（概念）；8 Primary | `robotics` | Park 明确只看人形链，接受更窄、更易漂移的成分 |
| AI芯片 | [AI芯片 BK1127](https://quote.eastmoney.com/bk/90.BK1127.html)（概念） | `chips` | 只想观察 AI 芯片而不是 broad 半导体 |
| 光伏设备 | [光伏设备 BK1031](https://quote.eastmoney.com/bk/90.BK1031.html)（行业） | `new-energy` 或 `controlled-fusion` | Park 决定新能源必须拆细，且保证总数不增加 |
| 风电设备 | [风电设备 BK1032](https://quote.eastmoney.com/bk/90.BK1032.html)（行业） | `new-energy` 或其他能源窄项 | 与光伏相同，只在拆分方案使用 |
| 新能源车 | [新能源汽车 BK0900](https://quote.eastmoney.com/bk/90.BK0900.html)（概念） | `new-energy` | 希望恢复 16 版汽车组件口径 |
| 储能锂电 | 19 版真实展示项；当前精确 provider 代码本轮未完成核验 | `new-energy` | Park 更关心储能/锂电，且先补完身份核验 |
| 游戏 | [游戏Ⅱ BK1046](https://quote.eastmoney.com/bk/90.BK1046.html)（行业，代码由行业目录核对） | `media-gaming` | 不接受“传媒含游戏”的合并显示名 |
| 消费电子 | [消费电子 BK1037](https://quote.eastmoney.com/bk/90.BK1037.html)（行业） | `tourism` 或其他消费槽 | 需要补一条硬件消费链，并接受与 AI 硬件相关 |
| 脑机接口 | 16 版仅 2 股、19 版有展示项 | `controlled-fusion` | Park 明确要保留；先核验当前概念板块身份和最小广度 |
| 消费 | 16 版仅 4 股的自定义篮子 | `tourism` | 先定义可取的 broad-consumer 指数，不能直接续旧 4 股篮子 |
| 算力/AI基建 | 19 版展示项、8 Primary umbrella | 不建议与芯片/PCB/AI应用并列增加 | 只有在 Park 选择“大叙事视图”并删除多个窄槽时才换入 |

## 6. 指数与 ETF 代理：存在，但本议题不冻结

当前第一方资料证明部分槽位有正式指数或 ETF 身份，但“有产品”不等于“它就是该槽位的 canonical K 线”：

- 国证指数的[国证 AI 应用指数编制方案](https://www.cnindex.com.cn/docs/gz_980112.pdf)给出名称与代码 `980112`；[2025 年修订公告](https://www.cnindex.com.cn/zh_information/notices_news/2025/202508/P020250804548075580061.pdf)同时列出 `AI应用 980112` 与 `AI应用软件 980107`。两者是不同口径，后续只能选一个或并列比较，不能混接。
- 上交所资料中的 `561980` 场内简称含“芯片设备”，但基金全名是“招商中证半导体产业 ETF”；[基金正式报告](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2026-01-21/561980_20260121_7V9P.pdf)显示其并非凭简称即可认定为纯半导体设备指数。这是名称误导风险的直接例子。
- 上交所[2026 年第二季度融资融券标的通知](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/specific/margin/c/c_20260710_10825136.shtml)可核对若干现有产品身份，例如 `512480 半导体`、`512570 中证证券`、`512980 传媒ETF`、`515020 银行指数`、`561980 芯片设备`、`562510 旅游ETF`、`563230 卫星ETF`。本文只使用名称/代码存在性，没有用它们的规模、流动性或收益排名选板块。
- 上交所[基金动态](https://etf.sse.com.cn/fundtrends/)记录 `561050 易方达中证稀有金属主题 ETF` 于 2026-05-13 成立，可作为稀有金属代理候选；是否适合长历史 K 线仍需另行评估。

ETF 最终选择至少还要比较：跟踪指数定义、成立日/历史长度、复权、停牌/折溢价、规模与流动性、是否跨市场。它属于后续数据合同，不在 #812 冻结。

## 7. Park HITL 必须决定的事项

1. **芯片簇是否允许宽窄并存**：接受 `芯片 + 半导体设备 + 存储 + PCB` 四槽，还是用一个 broad 槽换取更多宏观行业覆盖。
2. **新能源粒度**：保留 broad `新能源`，还是固定拆成光伏、风电、储能/锂电、新能源车中的若干项。
3. **机器人粒度**：broad `机器人` 还是 narrow `人形机器人`；两者不应同时占槽。
4. **传媒口径**：用 `传媒` 行业，还是 `游戏Ⅱ`，或另建一个有明确成分规则的自定义合成序列。
5. **窄主题取舍**：`可控核聚变`、`脑机接口`、`商业航天` 中最多保留几个；当前草案保留前者与商业航天。
6. **攻防是否允许第三态**：本研究建议允许 `周期/混合`，避免把发电、贵金属、创新药等永久二值化。
7. **K 线 canonical identity 优先级**：provider board、官方指数、ETF、旧自定义等权篮子之间要冻结一条不可静默切换的优先顺序。

## 8. 证据状态与未解决缺口

### 已验证

- #812 的 Outcome、验收标准、范围和禁区（2026-08-17 只读打开）。
- 16 个旧自定义组件的名称、计数、总数和单标签写入方式（历史原始命令输出）。
- 后期 19 个 Dashboard 展示项（历史 SQLite 查询原始输出）。
- 8 个 focus themes、别名和不覆盖旧单标签表的策略（当前文件 + SHA-256）。
- exactly-20 草案中各主身份的 provider 页面代码/名称；部分正式指数/ETF 名称由国证/上交所资料交叉核对。
- 选择过程没有读取当前表现字段。

### Partial / unresolved

- 旧 a-share 当前目录没有 `.git`，原 repo 的 remote 与 HEAD commit 未保留；只能给出 2026-05-09 session 时点和当前残存文件哈希。
- 东方财富目录分页在本轮出现 502/代理中断，完整目录、分类层级和所有替代项没有一次性快照；`半导体设备 BK1326` 的目录类型仍待复核。
- 本议题不读取个股成分，因此只揭示语义重叠，没有量化 Jaccard overlap、重复市值权重或 breadth 去重影响。
- provider 概念板块可能调样；尚未取得其历史成分版本和重构规则。
- 没有为 20 个槽逐一冻结指数/ETF，也没有评估可用历史长度、流动性与复权质量。
- `发电 → 电力 BK0428`、`芯片 → 半导体 BK1036`、`稀有金属 → 小金属 BK1027`、`传媒游戏 → 传媒 BK0486` 都只是显式代理，不是身份相等。

整体判断为 **PARTIAL / decision-ready**：足以让 Park 对 20 个候选及 7 个关键分歧做 HITL，但不足以宣称最终 universe 或 K 线数据合同已经冻结。

## 9. 可复查命令与证据位置

本轮使用的关键只读命令：

```bash
# 当前残存文件和版本指纹
find /Users/wendy/work/trading-co/ashare -maxdepth 3 -type f | sort
shasum -a 256 \
  /Users/wendy/work/trading-co/ashare/config/ashare_focus_themes.json \
  /Users/wendy/work/trading-co/ashare/docs/ashare_universe_and_focus_themes.md
python3 -m json.tool \
  /Users/wendy/work/trading-co/ashare/config/ashare_focus_themes.json

# 从 2026-05-09 原始 session 定向提取当时执行的命令与输出
jq -r 'select(.type=="response_item" and .payload.type=="function_call")' \
  /Users/wendy/.codex/sessions/2026/05/09/rollout-2026-05-09T12-37-11-019e0b06-707d-7d12-9772-ce13ac60776c.jsonl

# 原 session 中的关键命令（此处仅记录，不在缺失 DB 上重跑）
sed -n '1,260p' docs/CATEGORIES_GUIDE.md
sed -n '1,240p' data/sectors/import_sectors.py
sed -n '1,220p' scripts/create_sectors_table.py
sqlite3 data/market.db \
  'SELECT name, display_order FROM available_sectors ORDER BY display_order, name;'
sqlite3 data/market.db \
  'PRAGMA table_info(stock_sectors); SELECT sector, COUNT(*) FROM stock_sectors GROUP BY sector; SELECT COUNT(DISTINCT ticker), COUNT(*) FROM stock_sectors;'
```

研究仓库基线：`/Users/wendy/.codex/worktrees/equity-research-sector-universe-803`，研究开始时 HEAD `4516b36`；本地分支后由主 agent 改名为 `research/sector-universe-812`。本文件是本议题唯一写入路径。
