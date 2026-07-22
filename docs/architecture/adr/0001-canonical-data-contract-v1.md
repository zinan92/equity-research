# ADR-0001 · Canonical Data Contract v1

状态：Accepted
日期：2026-07-22
合同：`canonical-data-contract-v1`

## Context

现有产品已经有可回放的本地 market/fundamental baseline，但后续会同时接入公告、卖方预测和事件。若每个上游 repo 直接把自己的 payload 写入正式表，来源、时点、失败语义和版本会分裂，任何研报数字都无法稳定复算。

## Decision

1. Canonical ingestion 边界固定五个域：`market`、`fundamental`、`document`、`estimate`、`event`。
2. 每个域拥有独立 `*-record-v1` schema；字段扩展必须发布新 schema version，不能原地改变旧版本语义。
3. adapter 只能产生带 provenance 的 RecordEnvelope。合法 provenance 必须同时绑定 `SourceManifest` 与不可变 `RawCapture`，至少保留 source、manifest hash、provider/schema version、raw hash 和 UTC `known_at`。
4. adapter 输出状态只有 `accepted` 或 `rejected`。Accepted record 必须通过逐域非空、类型、时间、hash、JSON 与 PIT 校验；Rejected record 保存原 provider payload、reason 和结构化 violations，不要求无效 payload 先满足 canonical schema。
5. `SourceManifest.domain_scope` 是 source 的能力白名单。市场 adapter 不能借同一 manifest 输出 event 或 document。
6. `active=false` 的 source 不能产生 accepted output；停用后的异常响应仍可作为 rejected receipt 留档。
7. `product/data_core/schemas/canonical-data-contract-v1.json` 冻结 v1 descriptor；required fields 变化必须升级对应 record version。
8. Envelope 内部只保存 canonical `payload_json`；`payload` accessor 返回 detached copy，阻止 boundary 验证后、sink 写入前的 TOCTOU 修改。
9. 此合同只定义逻辑边界；Supabase DDL、Storage、RLS 和具体 provider adapters 分别由 A2/A3 交付。

## Consequences

- datafeed、a-stock-data、Vibe、Intel 的复用代码必须先包装成这个边界，不能直写 canonical 表。
- 每条 accepted record 都能确定性计算 record hash，并可由 raw bytes 与 source manifest 复核。
- 新增 record domain 或改动 required fields 属于 breaking change，需要 ADR、version 和 contract tests。
- 本地 SQLite 仍可作为 acceptance adapter，但不是 production authority。

## Rejected alternatives

- 直接复用每个 repo 的 SQLite/schema：无法形成单一 identity、PIT 和 provenance。
- 只保存 normalized JSON：丢失原始证据后无法复核 parser 或 provider 变化。
- 用 `degraded` 作为 adapter 接受状态：会让“不可信但可用”静默进入 authority；降级应由后续 quality gate 显式判断。
