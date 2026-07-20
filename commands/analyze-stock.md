---
description: 完整深度分析一只股票（22 维数据 + 65 位大佬量化评委 + 17 种机构分析方法 + 杀猪盘检测 + Bloomberg 风格 HTML 报告）
argument-hint: "[股票名称或代码，例如 华工科技 / 002273 / AAPL / 00700.HK]"
---

# 深度分析任务

用户输入: $ARGUMENTS

## 执行流程（两段式 · 你必须在中间介入）

### 第一段 · 数据采集 + 骨架分（脚本完成）

```bash
cd <plugin_root>
pip install -r requirements.txt 2>/dev/null
cd skills/deep-analysis/scripts
python -c "from run_real_test import stage1; stage1('$ARGUMENTS')"
```

这会跑完 Task 1 → 1.5 → 2 → 3（规则引擎骨架分），输出到 `.cache/{ticker}/` 下。

### 第二段 · 你来分析（核心！不能跳过！）

Stage 1 跑完后，**你必须做以下事情**：

**0. v2.13.5 · Playwright 兜底前置（必走）**

```python
import json, os
from pathlib import Path
net = json.loads(Path(".cache/_global/network_profile.json").read_text(encoding="utf-8"))
issues = json.loads(Path(f".cache/{ticker}/_review_issues.json").read_text(encoding="utf-8"))
low_quality_dims = [
    i["dim"] for i in issues.get("issues", [])
    if i.get("category") == "data" and i.get("severity") in ("critical", "warning")
]
if low_quality_dims:
    os.environ["UZI_PLAYWRIGHT_FORCE"] = "1"
    from lib.playwright_fallback import autofill_via_playwright
    autofill_via_playwright(raw, ticker)  # 主动强制再跑一次 · 补数据
```

**1. 读取评委骨架分**

读 `.cache/{ticker}/panel.json`，看 65 人各自打了多少分。特别关注：
- Top 5 看多和 Top 5 看空分别是谁？他们的 headline 有没有说服力？
- 有多少人 skip 了？（非 A 股时游资会 skip）
- 有没有明显不合理的分数？

**2. 逐组分析（spawn 4 个并行 sub-agent）**

对每组投资者，spawn 一个 Agent：

**Agent 1 · 价值 + 成长派（10 人）**
```
你要扮演巴菲特/格雷厄姆/费雪/芒格/邓普顿/卡拉曼/林奇/欧奈尔/蒂尔/木头姐，
逐一对 {stock_name} ({ticker}) 给出判断。

公司数据：{从 raw_data.json 摘取关键数据}
规则引擎参考分：{从 panel.json 摘取这 10 人的 score/headline}
真实持仓：{巴菲特持有苹果/BYD, 段永平持有苹果/茅台/腾讯 等}

对每人输出: investor_id, signal, score(0-100), headline(引用数字), reasoning(2-3句)
你可以覆盖规则引擎的分数——你是在模拟这个人的判断，不是跑公式。
```

**Agent 2 · 宏观 + 技术派（9 人）**
**Agent 3 · 中国价投 + 量化（9 人）**
**Agent 4 · 游资（23 人）** — 非 A 股直接全部 skip

**3. 合并 agent 结果**

把 4 个 agent 返回的 {signal, score, headline, reasoning} 覆盖到 `.cache/{ticker}/panel.json` 的对应投资者上。

**4. 写 agent_analysis.json（闭环关键！）**

对关键维度（财报/估值/护城河/行业）写 1-2 句定性评语（≥20 字，引用具体数字）。如果需要，web search 补充信息。

**⚠️ 必读：agent_analysis.json 完整 schema（缺字段 stage2 会报 schema warning/error）**

| 字段 | 要求 | 触发校验 |
|---|---|---|
| `agent_reviewed` | 必须 `true` | ⚠️ 缺 → warning |
| `dim_commentary` | 覆盖全部 22 维，**每条 ≥20 字**（引用具体数字，禁止空泛） | ⚠️ <20 字 → warning |
| `panel_insights` | **≥30 字**，评委投票分布 + 多空分歧分析 | ⚠️ <30 字 → warning |
| `great_divide_override` | punchline(≥10 字) + bull_say_rounds(≥3 条) + bear_say_rounds(≥3 条) | 🔴 缺字段 → error |
| `narrative_override.core_conclusion` | **≥20 字**综合定论 | ⚠️ <20 字 → warning |
| `narrative_override.risks` | **≥3 条**风险 | ⚠️ <3 条 → warning |
| `narrative_override.buy_zones` | **必须含 value/growth/technical/youzi 四个 key**，每个 key 内含 `price`(数值, youzi 可为 0) + `rationale`(≥5 字解释) | 🔴 缺 key → error / ⚠️ 缺子字段 → warning |
| `qualitative_deep_dive` | 覆盖 3_macro/7_industry/8_materials/9_futures/13_policy/15_events 共 6 维。每维含：`evidence` 数组（≥2 条）、`associations` 跨域因果链（6 维合计 ≥3 条）、`conclusion`（1-2 句） | 🔴 evidence 非 list → error |
| `data_gap_acknowledged` | dict 格式 `{"dim_key": "已尝试 X 但失败的原因"}`，标记数据采集失败但 agent 已知晓的维度 | 🔴 类型非 dict → error |

把所有 agent 产出写入 `.cache/{ticker}/agent_analysis.json`：
```python
from lib.cache import write_task_output
write_task_output(ticker, "agent_analysis", {
    "agent_reviewed": True,
    "dim_commentary": {
        "0_basic": "公司全称+成立/上市时间+市值+行业地位，≥20字",
        "1_financials": "ROE/营收增速/净利率/毛利率/FCF等核心数据+质量判断，≥20字",
        # ... 覆盖全部 22 维，每条 ≥20 字，引用具体数字
    },
    "panel_insights": "评委投票分布(看多X/中性X/看空X)+多空分歧核心逻辑，≥30字",
    "great_divide_override": {
        "punchline": "多空对决一句话金句，≥10字",
        "bull_say_rounds": ["R1: 看多论点+引用数字", "R2: ...", "R3: ..."],
        "bear_say_rounds": ["R1: 看空论点+引用数字", "R2: ...", "R3: ..."]
    },
    "narrative_override": {
        "core_conclusion": "综合定论+评分+建仓建议，≥20字",
        "risks": ["风险1", "风险2", "风险3", ...],  # ≥3条
        "buy_zones": {
            "value":     {"price": 140, "rationale": "DCF安全边际>60%，等待极端低估"},
            "growth":    {"price": 160, "rationale": "PEG<0.1极度低估，当前即可建仓"},
            "technical": {"price": 180, "rationale": "等待Stage 2突破确认后右侧入场"},
            "youzi":     {"price": 0, "rationale": "非A股不适用游资打板策略"}
        }
    },
    "qualitative_deep_dive": {
        "3_macro": {
            "evidence": [{"source": "...", "url": "...", "finding": "...", "retrieved_at": "2026-04-27"}],
            "associations": [{"link_to": "7_industry", "chain_id": "macro->industry", "causal_chain": "...", "estimated_impact": "medium"}],
            "conclusion": "宏观结论1-2句"
        },
        # ... 7_industry, 8_materials, 9_futures, 13_policy, 15_events 同上格式
        # 重要：associations 跨所有 6 维合计 ≥3 条
    },
    "data_gap_acknowledged": {
        "10_valuation.pe_quantile": "Lixinger API 对该港股不支持历史分位查询"
    }
})
```

> 详细说明见 `skills/deep-analysis/SKILL.md` 第 464 行 schema 表，以及 `references/task2.5-qualitative-deep-dive.md` 第 5 节。

### 第三段 · 生成报告（脚本完成）

```bash
python -c "from run_real_test import stage2; stage2('$ARGUMENTS')"
```

stage2 会自动读取 panel.json + agent_analysis.json，合并生成最终报告。
agent_analysis.json 中的字段优先级高于脚本 stub。

### 第四段 · 向用户汇报

1. 综合评分 + 定调
2. 65 评委投票分布
3. DCF 内在价值 vs 当前价
4. Top 3 看多理由 + Top 3 看空理由
5. Great Divide 金句
6. 杀猪盘等级
7. 报告文件路径

## 快速模式（跳过 agent 介入）

如果用户说"快速分析"或"不用那么详细"：
```bash
cd <plugin_root>
python run.py $ARGUMENTS --no-browser
```
这会 stage1 + stage2 一把跑完，不做 agent 分析。

## 禁止

- 不跑脚本就编造数据
- 跳过 agent 分析直接出报告（除非用户明确要快速模式）
- 用"基本面良好"等模板话术
