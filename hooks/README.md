# Hooks · v2.6

## 文件清单

| 文件 | 用途 |
|---|---|
| `hooks.json` | Claude Code 的 SessionStart hook 配置（直接调 session-start，不走 polyglot） |
| `session-start` | bash 脚本 · 在 SessionStart 时打印 skill 列表 + 工作流提醒，输出到 Claude additionalContext |
| `hooks-cursor.json` | Cursor IDE 用的 hook 配置（保留兼容） |
| `run-hook.cmd` | 历史 polyglot bash/batch 调度器（v2.6 起 hooks.json 已不再用，仅保留供外部调用） |

## 安装

`session-start` 需要可执行权限。`setup.sh` 自动做了：

```bash
chmod +x hooks/session-start hooks/run-hook.cmd
```

如果手动 clone：

```bash
chmod +x hooks/session-start
```

## v2.6 论坛 bug 修复说明

论坛反馈 "Claude plugin 执行不了"，原因是旧版 `hooks.json` 调用
`run-hook.cmd` 中转脚本，而 `.cmd` 在 macOS Claude Code 安全策略下：
1. 权限检查未通过（Claude Code 可能拒绝执行 `.cmd` 后缀脚本）
2. polyglot bash/batch 用 `: <<'BATCH_SCRIPT'` heredoc 体操，对解释器有要求

v2.6 修复：`hooks.json` 改为**直接调** `session-start`（标准 sh 脚本，已有 shebang），
跳过 `run-hook.cmd` 中间层。Windows 用户若依赖该中转，仍可手动调用。

## 调试

若 SessionStart 没有触发：

1. 确认 `session-start` 有 `+x` 权限：`ls -l hooks/session-start`
2. 手动测试输出：`./hooks/session-start | head -5`（应看到 JSON 含 `additionalContext`）
3. 检查 Claude Code 日志（`Cmd+Shift+P → Developer: Open Logs`）
4. 若 Claude Code 报路径错误，确认 `${CLAUDE_PLUGIN_ROOT}` 正确解析
