# L2-M5 · 多 ticker 报告任务批处理

`report_task_runtime` 已复用 A5 的不可变 snapshot / evidence-manifest
身份、原子检查点和 `SQLiteReportTaskCache`。本次把运行收据补为明确的
`runtime_only`：缓存不是权威来源，且不能改变 Tier、目标价、仓位或行动。

每个任务的缓存键绑定 `ticker + snapshot_id + evidence_manifest_hash`；改变任一
身份必定重新构建。队列按 ticker 串行，逐行原子保存，已完成行可复用；
`partial`/`failed` 行带原因并在下一次运行重试，绝不会拖垮其他 ticker 或被
伪装成报告成功。

验证覆盖：缓存身份隔离、一次失败后的断点续跑、队列顺序与限流、跨 ticker
写入拒绝，以及 runtime/cache 的非权威边界。
