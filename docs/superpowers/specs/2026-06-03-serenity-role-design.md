# 重磅角色 Serenity 接入 UZI-Skill 评审团 — 设计文档

- 日期：2026-06-03
- 状态：待用户审阅
- 参考：[serenity-alpha skill](https://github.com/haskaomni/serenity-skill/tree/main/serenity-alpha)、X @aleabitoreddit

## 1. 背景与目标

Serenity（X @aleabitoreddit）是 2026 年爆火的海外散户/研究员，前 AI 研究科学家、前 RISC-V
基金会成员、光通信工程师。核心方法论是 **「AI 产业链卡脖子/瓶颈点」投资法**：不直接买 AI 龙头，
而是拆解供应链、找到**最难被替代、最容易出现供给瓶颈的二三线上游小盘**，抢在市场定价之前埋伏。
代表战是提前一年押中 InP 衬底瓶颈股 AXTI（$12 → $70+，10 倍+）。

目标：把 Serenity 作为**重磅角色**接入 UZI-Skill 的投资大佬评审团，覆盖 4 件事：
1. 新增一位评委（独立流派）；
2. 实现「卡位决定态度」的打分逻辑；
3. 提供独立的「瓶颈点投资法」分析模块；
4. 模仿其真实语气 + 沉淀其底层知识库；
并额外交付一份**全网研究方法评价档案**。

## 2. 现状架构（接入点）

评审团是**双层架构**：
- **规则引擎层**（确定性）：`skills/deep-analysis/scripts/lib/`
  - `investor_db.py` — 每位评委元数据（id/name/group/fields/avatar_seed），`assert_count` 现为 51。
  - `investor_criteria.py` — `INVESTOR_RULES[id]` = `Rule(check=lambda features)` 列表，出「骨架分」。
  - `investor_evaluator.py` — 跑规则 → score/signal/confidence；`SCHOOL_LABELS` 现为 A–G；
    `--school` 可锁单一流派；F 组有射程检查。
  - `investor_personas.py` — `PERSONAS[id]` = bullish/bearish/neutral 的 signature lines（拟人台词）。
- **LLM agent 层**（拟人）：`agents/investor-panel.md` — 按 Group Profile 复盘，**可覆盖**规则骨架分，
  产出最终 `{signal, score, headline, reasoning}` JSON。
- **展示层**：`skills/investor-panel/assets/investor-cards.json`（HTML 渲染卡片）、
  `skills/investor-panel/references/group-{a..g}.md`（方法论）、`quotes-knowledge-base.md`（语料）。
- 特征来源：`stock_features.py`，已有 `5_chain`（供应链）、`14_moat`（护城河 4 维）等维度。

现状注意点：
- 无 `build_cards.py`（`_meta` 注释提到但不存在）；`investor-cards.json` 现有 50 条 vs db 51 条，
  **已存在漂移**。本次手动同步，把 Serenity 补成第 52 条。
- `fin-methods/` 目录现仅 `README.md`。

## 3. 设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 卡位判断放哪层 | **双层都做** | 规则引擎出 `ai_chokepoint_score` 骨架分（可追溯），LLM agent 层用人设做最终裁决，与现有哲学一致 |
| 流派归属 | **新建 H 组**「AI 卡位/瓶颈猎手」 | 方法论独特，塞进 A–G 任一组都失真；独立组可被 `--school H` 单独锁定 |
| 显示名 | **Serenity** + 中文 tagline「AI 卡脖子猎手」 | 保留推特 ID 辨识度 |
| 票权 | **仅高亮置顶，不加票权**（一人一票） | 不破坏现有共识分公平性；重磅感由高亮卡片 + 独立方法论专栏体现 |
| 语气来源 | 爬 @aleabitoreddit X 原帖 + Tracker/Substack/媒体直接引用 | 真实语料，避免编造 |

## 4. 实现方案（5 块）

### 块 1 · 新增第 52 位评委（H 组）
- `investor_db.py`：在末尾新增 H 组与条目：
  ```python
  {"id": "serenity", "name": "Serenity", "en": "Serenity (@aleabitoreddit)",
   "group": "H", "tier": "flagship",
   "fields": ["5_chain", "7_industry", "14_moat", "13_policy", "15_events"],
   "source": "serenity-alpha skill / X @aleabitoreddit", "avatar_seed": "Serenity-Chip"}
  ```
  `assert_count` 51 → 52；`__main__` 自检按组计数保持通过。
- `investor_evaluator.py`：`SCHOOL_LABELS["H"] = "AI 卡位/瓶颈猎手"`（使 `--school H` 生效）。
- `investor_personas.py`：新增 `PERSONAS["serenity"]`（见块 5）。
- `skills/investor-panel/references/group-h-serenity.md`：H 组方法论文档。
- `skills/investor-panel/assets/investor-cards.json`：手动新增 Serenity 卡片，`_meta.count`/groups 同步，
  `tier:"flagship"` 字段用于前端置顶高亮。

### 块 2 · 卡位打分逻辑（核心）
新增派生特征 `ai_chokepoint_score`（0–100），在 `stock_features.py` 计算，四因子合成：
1. **AI 链命中**：行业/`5_chain` 文本命中关键词库（光模块/CPO/光芯片/HBM/CoWoS/先进封装/InP 衬底/
   PCB/液冷/铜连接/电源/交换机/AI-ASIC/RISC-V/铜缆/PCB 载板…）。
2. **不可替代性**：`14_moat` 的 switching（切换成本）+ scale 分位高 → 上游卡点。
3. **弹性**：中小市值（市值越小弹性越大）。
4. **需求拐点**：`13_policy` / `15_events` 出现需求/扩产/缺货信号。

`SERENITY_RULES`（全部 weight 5，体现强信念）：
- 看多：`ai_chokepoint_score ≥ 70` 且不可替代性达标 → bullish。
- 中性：在 AI 链但卡位不明确（score 40–70）→ neutral，列出待验证项。
- **看空/skip：`ai_chokepoint_score < 40`（产品在 AI 浪潮里没卡到位）→ 他直接不碰**
  （= 用户强调的「卡位决定态度」）。
- LLM agent 层（块 4）H 组 profile 一句话定调：
  *「我只看一件事——这家的产品在当前 AI 浪潮里卡没卡住脖子。卡住=重仓，没卡=不看。」*

### 块 3 · 独立「瓶颈点投资法」分析模块
- 新增 `skills/deep-analysis/references/fin-methods/serenity-bottleneck.md`，落地 serenity-alpha 六步法：
  ① 信号去噪 ② 映射财务科目 ③ 猎misclassified 小盘 ④ 验证错误定价 ⑤ 建验证链 ⑥ alpha 评分。
  alpha 5 维评分：**确定性 / 清晰度 / 纯度 / 弹性 / 时间窗**。
- 报告输出**独立专栏**：供应链瓶颈地图 → 卡位评级 → 验证链（财报/backlog/ASP/产能/客户 roadmap）
  → 仓位建议。挂到 `task2.5-qualitative-deep-dive.md` 与 `task3-investor-panel.md` 流程。

### 块 4 · LLM agent 接入
- `agents/investor-panel.md` 增加 `### Group H · AI 卡位/瓶颈猎手 (Serenity)` profile：
  焦点 = 供应链不可替代性、二三线上游、需求拐点；忽略 EPS/估值传统指标；
  卡位裁决规则 + 上面那句定调；可覆盖规则骨架分。
- `task3-investor-panel.md` / `task3-agent-evaluation.md`：H 组纳入分派与 schema。

### 块 5 · 语气模拟 + 底层知识库
- 实现阶段爬取/汇总 @aleabitoreddit 原帖 + Tracker(semiconstocks.com)/Substack/PANews/Futu 等直接引用，
  产出：
  - `skills/investor-panel/references/serenity-voice.md` — 底层知识库（方法论 + 典型案例 AXTI 等 +
    口头禅/术语表）。
  - 并入 `quotes-knowledge-base.md` — 全局语料复用。
- `PERSONAS["serenity"]` signature lines 用其真实口吻，示例：
  - bullish：「别盯着 EPS——问这家在 AI 基建里可不可被替代。不可替代，就是印钞机。」
  - bearish：「{name} 在供应链里没有卡点，对我没意义。」
  - neutral：「卡位还没被验证，等客户 roadmap / 缺货信号坐实再说。」
  风格标签：技术流、供应链偏执、鄙视盯短期 EPS、断言式、点名具体节点、略带战斗性。

### 交付物 · 全网研究方法评价档案
- 新增 `docs/serenity-research-dossier.md`：汇总知乎/雪球/PANews/区块周刊/东方财富/腾讯/网易/
  Futu/KuCoin/HTX/Substack/semiconstocks 等所有帖子与评价。
- 每条 = 来源 + 核心观点摘要 + 对其方法的评价（正面/质疑，含「从不公开认错」「选择性展示」
  「收益不可审计」等批评）+ 原文链接。实现阶段再扩一轮搜索做全。

## 5. 测试与验收
- `investor_db.assert_count()` → 52 通过；`python investor_db.py` 分组计数含 H=1。
- 新增 `test_serenity_rules.py`：
  - AI 卡点小盘（如模拟 AXTI 类）→ Serenity bullish 且 score 高；
  - 非 AI/无卡位标的（如白酒/银行）→ skip 或 bearish；
  - `--school H` 锁定时仅 Serenity 参与、其余 skip。
- 现有 `test_v2_13_3_investor_rules.py` 等回归不破。
- 报告渲染：卡片置顶高亮 + 瓶颈点投资法专栏正常出现。

## 6. 影响文件清单
- 改：`investor_db.py`、`investor_evaluator.py`、`investor_criteria.py`、`investor_personas.py`、
  `stock_features.py`、`agents/investor-panel.md`、`investor-cards.json`、
  `task2.5/task3` 两个 reference、`quotes-knowledge-base.md`。
- 增：`references/group-h-serenity.md`、`fin-methods/serenity-bottleneck.md`、
  `references/serenity-voice.md`、`docs/serenity-research-dossier.md`、`tests/test_serenity_rules.py`。

## 7. 非目标（YAGNI）
- 不做实时抓取 X API（用静态汇总语料）。
- 不改共识分聚合算法（不加票权）。
- 不重构现有 build_cards 缺失问题（仅手动同步本次卡片）。
