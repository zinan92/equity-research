# v2.10.3 测试方案 · 给 Codex 执行

> **目的**：验证 v2.10.3 的 6 大改动在 Codex 环境下工作正常，特别是**三档深度 + 多源 failover + 网络韧性**。
>
> **执行者**：Codex agent（或任何能跑 bash + pytest 的环境）
>
> **时间预算**：完整跑 ~20-30 分钟，最小跑 ~5 分钟（只测 smoke + 回归）

---

## 第零步 · 环境准备

```bash
# 1. clone + checkout
git clone https://github.com/wbh604/UZI-Skill.git
cd UZI-Skill
git checkout main            # v2.10.3 已合到 main

# 2. 验证版本
cat package.json | grep version
# 期望输出: "version": "2.10.3",

# 3. 装依赖
pip install -r requirements.txt

# 4. 可选：装 efinance / tushare 做 provider 完整测试
pip install efinance tushare 2>&1 | tail -3
```

**成功标准**：版本号 `2.10.3`，依赖安装无报错。

---

## 第一步 · 回归测试套件（最快 · 必跑）

```bash
cd skills/deep-analysis/scripts
python -m pytest tests/test_no_regressions.py -v
```

**成功标准**：`68 passed`，**允许** `0 failed`。

**如果失败**：
- 记录第一个 FAILED 的测试名 + 具体 assert 错误
- 继续跑后续测试（某些失败是环境问题不阻塞整体）

---

## 第二步 · 基础 smoke · 模块加载 + parse_ticker

```bash
python -c "
from lib.market_router import parse_ticker, classify_security_type
from lib import providers
from lib.analysis_profile import get_profile, DEPTH_LITE, DEPTH_MEDIUM, DEPTH_DEEP
from lib import net_timeout_guard, network_preflight
from lib import self_review
print('所有模块加载 ✓')
"
```

**验证 ticker 识别**：

```bash
python -c "
from lib.market_router import parse_ticker
tests = [
    ('600519', 'A', '600519.SH'),
    ('512400', 'A', '512400.SH'),     # SH ETF
    ('159949', 'A', '159949.SZ'),     # SZ ETF
    ('113517', 'A', '113517.SH'),     # SH 可转债
    ('700', 'H', '00700.HK'),          # 3 位 HK（v2.10.2 修的）
    ('00700', 'H', '00700.HK'),
    ('AAPL', 'U', 'AAPL'),
]
for raw, m, expected in tests:
    r = parse_ticker(raw)
    ok = r.full == expected
    print(f'{\"✓\" if ok else \"✗\"} {raw:8} → {r.full:15} (want {expected})')
"
```

**成功标准**：7/7 全 ✓

---

## 第三步 · Providers 框架 health check

```bash
python -c "
from lib import providers
import json
hc = providers.health_check()
print(json.dumps(hc, ensure_ascii=False, indent=2))
"
```

**成功标准**：至少 `akshare` 和 `direct_http` 显示 `available: true`；其他 provider 可能 `available: false`（未装 efinance/tushare 正常）。

**provider chain 验证**：

```bash
python -c "
from lib import providers
chain = providers.get_provider_chain('financials', market='A')
for p in chain:
    print(f'{p.name} · markets={p.markets} · requires_key={p.requires_key}')
"
```

**成功标准**：至少返 1 个 provider；如果装了 efinance 和设置了 TUSHARE_TOKEN 则返更多。

---

## 第四步 · direct_http 实时行情（关键 · 证明脱离 akshare 能跑）

```bash
python -c "
import warnings; warnings.filterwarnings('ignore')
from lib.providers import get
dh = get('direct_http')
assert dh is not None, 'direct_http provider 不存在'

# 测 3 市场 × 4 ticker
tests = [
    ('600519', 'A', '贵州茅台'),
    ('000001', 'A', '平安银行'),
    ('00700', 'H', '腾讯控股'),
    ('AAPL', 'U', 'Apple'),
]
for code, market, expected_name in tests:
    try:
        r = dh.fetch_quote_tencent(code, market)
        price = r.get('price', 0)
        name = r.get('name', '')
        assert price > 0, f'{code} 价格异常 {price}'
        print(f'✓ {code:10} [{market}] price={price:<10} name={name[:15]}')
    except Exception as e:
        print(f'✗ {code:10} [{market}] ERROR: {type(e).__name__}: {e}')
"
```

**成功标准**：4/4 都拿到正数 price。**如果 3/4 及格也 OK**（说明腾讯某个市场临时挂）。

**失败报告**：记录哪个 ticker 失败 + 错误信息。

---

## 第五步 · 三档深度 · profile 差异验证

```bash
python -c "
from lib.analysis_profile import get_profile, DEPTH_LITE, DEPTH_MEDIUM, DEPTH_DEEP
lite = get_profile(DEPTH_LITE)
mid = get_profile(DEPTH_MEDIUM)
deep = get_profile(DEPTH_DEEP)

# 档位差异必须显著
assert len(lite.fetchers_enabled) < len(mid.fetchers_enabled), 'lite fetchers 应少于 medium'
assert lite.investors_count < mid.investors_count, 'lite 评委应少于 medium'
assert lite.ddg_budget < mid.ddg_budget < deep.ddg_budget, 'ddg 预算递增'
assert lite.fund_stats_top_n < mid.fund_stats_top_n < deep.fund_stats_top_n
assert not lite.enable_bull_bear_debate
assert not mid.enable_bull_bear_debate
assert deep.enable_bull_bear_debate  # deep 独享
assert not lite.enable_segmental_model
assert deep.enable_segmental_model

# 打印对比
print(f'lite:   fetchers={len(lite.fetchers_enabled)}  投资者={lite.investors_count}  ddg_budget={lite.ddg_budget}  fund_top={lite.fund_stats_top_n}')
print(f'medium: fetchers={len(mid.fetchers_enabled)}  投资者={mid.investors_count}  ddg_budget={mid.ddg_budget}  fund_top={mid.fund_stats_top_n}')
print(f'deep:   fetchers={len(deep.fetchers_enabled)}  投资者={deep.investors_count}  ddg_budget={deep.ddg_budget}  fund_top={deep.fund_stats_top_n}')
print('✓ 三档差异正确')
"
```

**成功标准**：所有 assert 过 + 3 行对比输出。

---

## 第六步 · 网络预检 · 验证本地可达性

```bash
python lib/network_preflight.py
```

**期望输出**（类似）：

```
🌐 网络预检 (X/5 通 · 均延迟 XXms)
  ✓ XXms  push2.eastmoney.com          · A 股行情 (akshare 主源)
  ✓ XXms  duckduckgo.com               · ddgs 定性查询
  ✓ XXms  www.cninfo.com.cn            · cninfo 行业 PE + 公告
  ✓ XXms  stock.xueqiu.com             · 雪球数据
  ✓ XXms  api.github.com               · 通用网络健康度
  ✓ 网络畅通
```

**成功标准**：至少 3/5 通。**如果 < 3 通**，记录不通的域名——说明 Codex 环境代理限制，正好验证了自动 lite 的价值。

---

## 第七步 · DDGS timeout 护栏

```bash
# 测 DDGS 硬 timeout（就算代理挂也不会卡 30+ 秒）
python -c "
import os, time
os.environ['UZI_DDG_TIMEOUT'] = '3'
from lib.web_search import _ddg_search

t0 = time.time()
r = _ddg_search('timeout_test_unique_probe_xyzzz', max_results=3)
dt = time.time() - t0

print(f'耗时: {dt:.1f}s')
print(f'返回: {r[:1]}')
assert dt < 8, f'timeout 护栏失效！耗时 {dt}s > 8s'
print('✓ DDGS timeout 护栏工作正常')
"
```

**成功标准**：耗时 < 8 秒。（护栏限 3s，加上线程收尾最多 5s 左右）

---

## 第八步 · lite 模式 stage1（最关键 · 端到端）

```bash
# A 股测试：茅台 lite 模式
python run.py 600519 --depth lite --no-browser 2>&1 | tee /tmp/uzi_test_600519_lite.log | tail -50
```

**观察点**：

1. **启动 banner** 显示：
   ```
   ⚡ 速判模式 · depth=lite · 预计 1-2 分钟
     · fetchers: 7/20 维
     · 评委: 10 位
     ...
   ```

2. **网络预检** 跑完（3 秒内）

3. **stage1** 跑：
   - 期望 < 3 分钟
   - `[wave 2] done in <time>` 应该 < 60s

4. **生成报告**：
   - `reports/600519.SH_<YYYYMMDD>/full-report.html` 存在
   - 文件大小 > 300KB

5. **self-review** 通过：
   ```
   → passed: true (critical=0)
   ```

**成功标准**：
- ✓ 用时 < 4 分钟
- ✓ HTML 报告生成
- ✓ self-review critical_count = 0

**如果失败** 记录：
- 哪一步报错
- 具体 traceback 首 10 行
- `.cache/600519.SH/_review_issues.json` 内容（如存在）

---

## 第九步 · ETF 早退交互式引导（用户体验关键）

```bash
python run.py 512400 --no-browser 2>&1 | tee /tmp/uzi_test_etf.log | head -30
```

**期望输出**：

```
🔴 非个股标的: 512400.SH (ETF)
   本插件是个股深度分析引擎，...

   📊 不过我可以帮你识别 512400.SH 的前 10 大持仓，请选一只分析：

       1. 紫金矿业     (601899.SH  ) · 占比 XX.XX%
       2. 洛阳钼业     (603993.SH  ) · 占比 XX.XX%
       ...

   👉 请选择要分析的成分股（告诉我编号或代码）
```

**成功标准**：
- ✓ 识别为 ETF 而不是硬跑
- ✓ 输出 >= 5 条前十大持仓
- ✓ `.cache/512400.SH/_resolve_error.json` 存在且含 `top_holdings` 数组

**失败报告**：截全部输出，特别是 `🔴` 行和持仓列表。

---

## 第十步 · HK 股验证（3 位数字 + kline fallback）

```bash
# 3 位数字输入（修复验证）
python -c "
from lib.market_router import parse_ticker
r = parse_ticker('700')
assert r.full == '00700.HK', f'700 应为 00700.HK，实际 {r.full}'
print('✓ HK 3 位数字修复 OK')
"

# 完整 HK stage1（短 lite 跑）
python run.py 00700.HK --depth lite --no-browser 2>&1 | tail -30
```

**成功标准**：
- ✓ 3 位数字正确识别
- ✓ HK kline_count > 100（证明 fallback 链至少一条路活）
- ✓ HTML 生成

---

## 第十一步 · Fund holders 双层策略

```bash
# 快速测 fund_holders 返回形状
python -c "
import warnings; warnings.filterwarnings('ignore')
import os
os.environ['UZI_FUND_STATS_TOP'] = '5'  # 只算 5 家 full，其他 lite
import fetch_fund_holders
r = fetch_fund_holders.main('600519.SH', limit=None)
data = r.get('data', {})
mgrs = data.get('fund_managers', [])
print(f'总基金数: {data.get(\"total_funds_holding\", 0)}')
print(f'full 业绩行: {data.get(\"full_stats_count\", 0)}')
print(f'lite 清单行: {data.get(\"lite_count\", 0)}')
print(f'实际返回 rows: {len(mgrs)}')
# 前 5 应该有 return_5y, 其余应该 None
for i, m in enumerate(mgrs[:7]):
    has_5y = m.get('return_5y') is not None
    mark = '(full)' if has_5y else '(lite)'
    print(f'  row {i+1}: {m.get(\"fund_name\", \"\")[:20]:20} {mark}')
" 2>&1 | tail -20
```

**成功标准**：
- 前 5 行 = `(full)` · 带 `return_5y`
- 第 6 行以后 = `(lite)` · `return_5y=None`
- 总行数 > 5（证明 lite 清单也返回了）

---

## 第十二步 · Tushare provider opt-in（可选 · 仅当用户有 TUSHARE_TOKEN）

```bash
# 如果有 token
if [ -n "$TUSHARE_TOKEN" ]; then
    python -c "
import warnings; warnings.filterwarnings('ignore')
from lib.providers import get
ts = get('tushare')
print(f'tushare available: {ts.is_available()}')
if ts.is_available():
    r = ts.fetch_basic_a('600519')
    print(r.get('raw', {}))
"
fi
```

**成功标准**（仅当 TUSHARE_TOKEN 设置时）：is_available=True + 返回 stock_basic 记录。

---

## 第十三步 · 深度模式（可选 · 耗时长）

```bash
# 如果时间充足，跑一次 medium 对比
time python run.py 002273 --depth medium --no-browser 2>&1 | tail -20

# deep 模式（15-20 分钟，仅在明确需要时跑）
# time python run.py 002273 --depth deep --no-browser 2>&1 | tail -20
```

**成功标准**：medium 完整跑完，生成 HTML，时间 < 10 分钟。

---

## 报告格式

请把测试结果按这个模板回：

```markdown
# v2.10.3 测试报告 · Codex 环境

**环境**: [Codex / CI / local] · Python [版本] · OS [...]
**执行时间**: [总耗时]
**网络状况**: [根据第六步 preflight 结果]

## 逐步结果

| # | 测试 | 状态 | 耗时 | 备注 |
|---|---|---|---|---|
| 0 | 环境准备 | ✓/✗ | Xs | |
| 1 | 回归 68 条 | ✓/✗ (实际 N passed) | Xs | |
| 2 | 模块加载 + ticker | ✓/✗ | Xs | |
| 3 | Providers health check | ✓/✗ | Xs | 装了哪些 |
| 4 | direct_http 4 ticker | ✓/4 | Xs | 哪个失败 |
| 5 | 三档差异 | ✓/✗ | Xs | |
| 6 | 网络预检 | X/5 通 | Xs | 哪些不通 |
| 7 | DDGS timeout | ✓/✗ (Xs 耗时) | Xs | |
| 8 | lite 模式 end-to-end | ✓/✗ | Xmin | 报告大小 XXK |
| 9 | ETF 早退 | ✓/✗ | Xs | |
| 10 | HK 股 | ✓/✗ | Xmin | |
| 11 | Fund holders 双层 | ✓/✗ | Xs | |
| 12 | Tushare | 跳过/✓/✗ | — | |
| 13 | medium 模式 | 跳过/✓/✗ | Xmin | |

## 发现的问题

1. [具体描述 · 完整 traceback · 复现步骤]
2. ...

## 额外观察

- 三档模式对 Codex token 消耗的实际对比
- 网络挂时自动 lite 触发是否符合预期
- 任何用户体验层面的 feedback
```

---

## 调试辅助

**如果某个 fetcher 一直挂**：
```bash
export UZI_HTTP_TIMEOUT=10     # 短超时快速 fail
export UZI_DDG_TIMEOUT=5
python run.py <ticker> --depth lite --no-browser
```

**如果自动 lite 没触发但应该触发**：
```bash
rm -rf skills/deep-analysis/scripts/.cache/_global
# 重跑，观察 banner 是否打印 "⚡ LITE MODE: 首次安装..."
```

**如果想强制某个 provider**：
```bash
export UZI_PROVIDERS_FINANCIALS=tushare,akshare
python run.py <ticker>
```

**如果想关掉预检（对比有无）**：
```bash
export UZI_SKIP_PREFLIGHT=1
python run.py <ticker>
```

---

## 不在本次测试范围

- Playwright 登录态（XueQiu contests）— 需账号
- 远程模式 (`--remote` Cloudflare Tunnel) — 需 cloudflared
- prewarm_cache.py 实际打包 — 需手动 tar
- deep 模式完整流程（15-20 分钟，耗费 Codex token 太多）
