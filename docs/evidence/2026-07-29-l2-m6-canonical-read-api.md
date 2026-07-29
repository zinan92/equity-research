# L2-M6 · Canonical 读 API

新增只读端点：`/api/canonical/{company|sector|dossier|score|roadmap|report}/{ticker}`。
每个端点只读取完整性校验后的 canonical active report；无 active report 时返回
显式错误与 `fallback: none`，不会调用普通 report、cache 或 fixture 路径。

响应固定包含 `source_state`（`live` / `fixture` / `unknown`）和
`truth_boundary`，前端可据此拒绝把 fixture 或未知状态渲染为实时研究。
