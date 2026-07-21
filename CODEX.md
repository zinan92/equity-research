# UZI-Skill · Codex 专属指引

> 本文件供 **OpenAI Codex CLI / codex-rescue agent** 读取.
> 作用：在短上下文场景下给 codex 一份浓缩的项目地图 · 避免走错目录 / 误报结构问题.
> 长版本见 [AGENTS.md](./AGENTS.md).

---

## 🚨 必读前 60 秒

1. **`run.py` 在 repo root · 不在 `scripts/` 下**
   - ✅ `python run.py <ticker>`（从 UZI-Skill/ 目录）
   - ❌ `python scripts/run.py`（不存在 · 别找）
   - ❌ `python skills/deep-analysis/scripts/run.py`（也不存在）

2. **所有 Python 业务代码在 `skills/deep-analysis/scripts/`**
   - `fetch_*.py` (22 个 fetcher)
   - `run_real_test.py` (stage1/stage2 入口 · 简称 rrt)
   - `assemble_report.py` (HTML shell 组装)
   - `lib/pipeline/` (v3.0 管道架构)
   - `lib/report/` (v3.2 拆分的渲染子模块)

3. **Python 环境**：任意装了 `akshare` / `pytest` 的 Python 3.10+ 都行（macOS 系统自带的 `/usr/bin/python3` 通常没装这些 · 用 `pip install -r requirements.txt` 装一下；conda / venv / pyenv 都可以）

4. **pytest 必须 `cd skills/deep-analysis/scripts` 再跑** · 相对 import 要求 cwd 在 scripts/

---

## v3.0+ 架构关键约定

### 默认路径 vs Legacy Fallback

```
python run.py <ticker>                # 走 pipeline.run_pipeline (v3.0 默认)
UZI_LEGACY=1 python run.py <ticker>   # 强制走老 stage1/stage2 (保险绳)
```

**不要删 `rrt.collect_raw_data` / `rrt.stage1` / `rrt.stage2`** · 它们是 UZI_LEGACY 的 fallback 路径 · 删了就是破坏保险.

### Pipeline 数据流

```
pipeline.run_pipeline(ticker)
  ├─ _preflight_guards(ticker)    # 中文名/ETF/LOF/可转债 → ValueError → fallback legacy
  ├─ pipeline.collect()           # 22 BaseFetcher adapter · max_workers=6
  │                                 → 写 .cache/<ticker>/raw_data.json
  ├─ pipeline.score.score_from_cache(ticker)   # 调 rrt 纯函数 (不是调 stage1)
  │   ├─ rrt._autofill_qualitative_via_mx      # 实际来自 lib.pipeline.score_fns
  │   ├─ rrt.score_dimensions
  │   ├─ rrt.generate_panel
  │   └─ rrt.generate_synthesis
  │                                 → 写 dimensions/panel/synthesis.json
  └─ pipeline.synthesize_and_render(ticker)    # 调 rrt.stage2 · stage2 只读 cache 安全
                                    → 生成 reports/<ticker>_<date>/full-report-standalone.html
```

### 重构历史快照

| 版本 | 物理迁移 | 向后兼容 |
|---|---|---|
| v3.1.0 | rrt 1228 行纯函数 → `lib/pipeline/score_fns.py` | rrt 仍 re-export · `rrt.score_dimensions` 调用不变 |
| v3.1.0 | rrt.stage1 preflight 166 行 → `lib/pipeline/preflight_helpers.py` | stage1 内部调用 · 外部无感 |
| v3.2.0 | assemble_report 2377 行 → 5 个 `lib/report/*.py` | assemble_report 全部 re-export · 历史调用不变 |

**重要**：grep 式测试（搜字符串）在搬迁后需要拼接多文件读 · 已在 tests/ 里修好.

---

## 审视任务清单模板（给你参考）

如果被要求审视 v3 重构 · 按此流程查（`<repo-root>` 替换为你 clone 的目录）：

```bash
cd <repo-root>          # 例如 ~/code/UZI-Skill 或 git clone 到的任意路径

# 1. 确认入口位置（不要找 scripts/run.py）
ls run.py                          # ✅ 应该存在
ls skills/deep-analysis/scripts/run.py  # ❌ 应该不存在（正常）

# 2. Python 环境（任意装了 akshare/pytest 的 Python 3.10+ 都行）
python3 --version

# 3. cd 到 scripts 跑 pytest
cd skills/deep-analysis/scripts
python3 -m pytest tests/ -q --ignore=tests/test_v2_13_playwright_strategy.py

# 4. 验证 import 链
python3 -c "
import sys; sys.path.insert(0, '.')
import run_real_test as rrt
import assemble_report as ar
# 检查关键 re-export
for n in ['score_dimensions', 'generate_panel', 'generate_synthesis',
          '_is_junk_autofill', 'collect_raw_data', 'stage1', 'stage2']:
    assert hasattr(rrt, n), f'缺 {n}'
for n in ['svg_sparkline', '_viz_financials', 'render_fund_managers',
          'render_school_scores', 'trap_color_emoji', 'DIM_VIZ_RENDERERS',
          'render_dim_card', 'assemble']:
    assert hasattr(ar, n), f'缺 {n}'
print('re-export complete')
"

# 5. 真机 e2e (已 cached 的股 · resume)
python3 -c "
import sys, os; sys.path.insert(0, '.')
os.environ['UZI_NO_AUTO_OPEN'] = '1'
from lib.pipeline.run import run_pipeline
p = run_pipeline('002217.SZ', resume=True)
print(f'e2e ok: {p}')
"
```

---

## 常见 codex 误判避坑

| 误判 | 真相 |
|---|---|
| "scripts/run.py 缺失" | run.py 在 repo root · README/AGENTS.md 所有示例都是 `python run.py` |
| "fetch_*.py 没被 adapter 用 · 可删" | 它们仍是独立 CLI 工具 (`python fetch_basic.py <ticker>`) · 不能删 |
| "rrt.collect_raw_data 是死代码" | 是 `UZI_LEGACY=1` 的 fallback · 保留 |
| "renderer/ 21 个 stub 未被 assemble 用 · 可删" | 是 v3.x 未来方向的占位 · 留给后续迭代升级用 |
| "循环 import" | 每个 lib/report/*.py 都定义自己的 `_safe` · 避免 import assemble_report 才切断循环 · 这是故意的 |

---

## 文件大小红线（v3.2.0 基线）

| 文件 | 当前 | 上限（触发 refactor 信号）|
|---|---|---|
| `run_real_test.py` | 735 行 | > 1000 |
| `assemble_report.py` | 587 行 | > 900 |
| `lib/pipeline/score_fns.py` | 1271 行 | > 1500 (再拆) |
| 任意 `lib/report/*.py` | < 750 行 | > 1000 (再拆) |

如果某文件突破红线 · 说明又开始堆屎山 · 该开新 refactor PR.

---

## 有疑问先做什么

1. 读 `AGENTS.md` 完整版
2. 读 `RELEASE-NOTES.md` 最近 3 版（了解最新架构变化）
3. 读 `docs/BUGS-LOG.md` 最近几条（了解已知 bug 和修复）
4. 看 `skills/deep-analysis/scripts/lib/pipeline/MIGRATION.md`（v3 迁移文档）

**别瞎猜** · 所有答案都在上面 4 个文档里.
