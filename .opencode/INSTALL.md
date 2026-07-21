# UZI-Skill · OpenCode 安装指南

## 安装

```bash
git clone https://github.com/wbh604/UZI-Skill.git
cd UZI-Skill
pip install -r requirements.txt
```

## 使用

对 OpenCode 说：

> 分析 贵州茅台

或直接执行：

```bash
python run.py 贵州茅台 --no-browser
```

## 两段式深度分析

```bash
cd skills/deep-analysis/scripts

# Stage 1: 数据采集 + 骨架分
python -c "from run_real_test import stage1; stage1('600519.SH')"

# Agent 分析（读 .cache/600519.SH/panel.json，逐组分析 51 评委）

# Stage 2: 生成报告
python -c "from run_real_test import stage2; stage2('600519.SH')"
```

## 远程查看

```bash
python run.py 贵州茅台 --remote
```

## 更多信息

- `AGENTS.md` — Agent 指令
- `skills/deep-analysis/SKILL.md` — 完整分析师手册
- `README.md` — 项目介绍
