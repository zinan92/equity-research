# UZI-Skill · Codex 安装指南

## 自动安装（推荐）

在 Codex 环境中执行：

```bash
git clone https://github.com/wbh604/UZI-Skill.git
cd UZI-Skill
pip install -r requirements.txt
```

安装完成。直接对 Codex 说"分析 贵州茅台"即可。

## 工作原理

Codex 会自动读取仓库根目录的 `AGENTS.md`，了解可用命令：

| 你说的话 | Codex 执行的命令 |
|---|---|
| 分析 贵州茅台 | `python run.py 贵州茅台 --no-browser` |
| 分析 AAPL | `python run.py AAPL --no-browser` |
| 远程分析 002273 | `python run.py 002273 --remote` |

## 两段式深度分析（推荐）

Codex 作为 agent 应该分两步执行，中间自己做分析：

```bash
# Stage 1: 数据采集 + 规则引擎骨架分
cd skills/deep-analysis/scripts
python -c "from run_real_test import stage1; stage1('贵州茅台')"

# 此时 Codex 应该：
# 1. 读 .cache/{ticker}/panel.json 中 51 人骨架分
# 2. 对每组投资者做 role-play 分析
# 3. 更新 panel.json

# Stage 2: 生成报告
python -c "from run_real_test import stage2; stage2('600519.SH')"
```

## 快速模式

不需要 agent 介入，一把跑完：

```bash
python run.py 贵州茅台 --no-browser
```

## 远程查看

不在电脑前时：

```bash
python run.py 贵州茅台 --remote
```

会生成 `https://xxx.trycloudflare.com` 公网链接。

## 依赖

- Python 3.9+
- 零 API key
- requirements.txt 自动安装缺失依赖

## 目录结构

```
UZI-Skill/
├── run.py                    ← 一键入口
├── AGENTS.md                 ← Codex 自动读取
├── skills/deep-analysis/     ← 核心分析工作流
│   ├── SKILL.md              ← 分析师手册
│   └── scripts/              ← Python 脚本
└── requirements.txt
```

## 常见问题

**Q: 跑完看不到报告？**
A: 报告在 `skills/deep-analysis/scripts/reports/{ticker}_{date}/full-report-standalone.html`，用 `--remote` 可以生成公网链接。

**Q: 依赖安装失败？**
A: 确保 Python 3.9+ 和 pip 可用。`run.py` 会自动检测并尝试安装缺失依赖。

**Q: 中文名识别不了？**
A: 直接用代码：`600519.SH`（上海）、`002273.SZ`（深圳）、`00700.HK`（港股）、`AAPL`（美股）。
