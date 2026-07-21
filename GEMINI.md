# UZI-Skill · Gemini CLI 指令

## 安装

```bash
gemini extensions install https://github.com/wbh604/UZI-Skill
```

更新：

```bash
gemini extensions update stock-deep-analyzer
```

## 使用

对 Gemini 说"分析 贵州茅台"，或直接执行：

```bash
pip install -r requirements.txt
python run.py 贵州茅台 --no-browser
```

## 完整流程

参考 `AGENTS.md` 和 `skills/deep-analysis/SKILL.md`。

核心是两段式：
1. `stage1()` — 数据采集 + 规则引擎骨架分
2. Agent 分析 — 读 panel.json，逐组 role-play 66 评委
3. `stage2()` — 生成 Bloomberg 风格 HTML 报告
