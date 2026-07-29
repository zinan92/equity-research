# L3-M1 · 源与管线可观测性

既有 A5 refresh receipt 继续是唯一输入。`source_observability` 现在输出：

- 每源 availability、freshness、data_kind、coverage impact 与连续失败起点；
- 关键 selected source 的 `alert_due_at`（首次连续失败后 15 分钟）；
- 交易日 `19:00 Asia/Shanghai` 日快照 deadline 及 `met/not_due/overdue` 状态；
- identity-only run trace 与去重的 open/recovered 告警生命周期。

非选中 fallback 的失败仍可见但不伪造覆盖影响。fixture/cached 不会让
production health 变绿；19:00 后没有 canonical snapshot 的交易日会出现
`daily_snapshot_deadline_missed`。该层不采集数据、不改变 last-good、Tier、
目标、仓位或行动。
