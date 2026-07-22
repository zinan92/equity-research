# Cross-company research v1

## User outcome

同一条生产线覆盖首批五个行业：公司适配器只定义研究问题、价值链和可比范围；冻结证据门决定能说什么；`research-report-v1` 决定如何呈现。任何公司都不能通过复制模板获得例外。

## Production boundary

```text
quality-passed canonical snapshot + normalized-row content attestation
            +
captured company documents → frozen evidence manifest
            +
company adapter (questions only)
            ↓
production input identity
            ↓
DeepSeek frozen input (network forbidden)
            ↓
claim/source validation + evidence-editor revision
            ↓
independent sentence-level entailment approval
            ↓
research-report-v1 → desktop / mobile / PDF
```

`production_input_identity` 绑定 snapshot、证据 manifest、adapter、模板、模型和 prompt 版本。legacy REAL snapshot 在 draft/publish 前必须在同一 SQLite read transaction 内读取 normalized rows 并重算 `snapshot_content_attestations`；attestation 表由 exact-SQL append-only trigger 保护，trigger 缺失、删除或替换均 fail closed。因此业务行或 attestation 被原地改写后，即使旧 manifest 和 snapshot ID 仍在，也不能进入模型边界。模型请求只接收冻结包；不接收数据库连接、文件路径、API key 或实时 URL locator。修改冻结包后 hash 不一致，生成会失败。

## Adapter boundary

首批适配器为贵州茅台、招商银行、长江电力、美的集团和宁德时代，分别覆盖消费品牌、商业银行、公用事业、全球制造和新能源制造。适配器只包含：

- 公司与上市身份；
- 行业语义、价值链、可比公司；
- 必须回答的证据问题。

模块顺序、状态语义、引用规则、币种规则和格式不在 adapter 内，全部由 `research-report-v1` 管理。

## Fail-closed rules

- 至少两个 primary/company document 与一个 independent cross-check；
- 每个 document 必须有 HTTPS allowlisted URL、时间、raw/content SHA-256；
- 每个 fact/inference/risk 只能引用当前 manifest 的 source ID；
- risk 必须有 trigger；
- unknown citation、private URL、未来证据、identity mismatch、post-freeze mutation 均阻断；
- 模型 schema 通过不代表引用蕴含句子；evidence-editor 必须保留原模型 hash、修订 hash、修订原因，修订后重新审批；
- 审批 manifest 与独立终审回执预先绑定 exact narrative/evidence/artifact provenance hash，以及 input/provider/model/prompt identity；审批前伪造 editor/revision、审批后篡改模型或正文均阻断发布；
- 缺证据时保持 `Missing evidence`，估值零值只表示空状态；
- `ACCEPTANCE_FIXTURE` 的 contract 永远标记 `is_live_research=false`。

## Acceptance evidence

`scripts/verify_cross_company_research.py` 生成五家公司相同八模块的 JSON、standalone HTML、1440px full-page 长 PNG、390px full-page 移动图和多页 PDF。验收器读取 DOM `scrollHeight` 并要求截图像素高度完全一致，固定视口截图不能冒充长图。样例只证明生产线与格式，不证明任何实时投资结论；生产使用必须替换为 REAL snapshot 与实际捕获的冻结文档。

`evidence/m4-cross-company-research/live/` 记录五家公司真实发布证明：同一 REAL snapshot、每家公司至少两个 primary/company document 与一个 independent cross-check、DeepSeek 冻结输入、provenance-preserving evidence edit、逐句语义审查以及 exact-hash approval。新证据重绑后的最终审查为 P0=0、P1=0；一项全局 P2 明示记录在 editorial receipt：本批早期重试没有永久保留全部原始 base artifacts，因此无法从留档独立重算 base provenance。它不影响当前 revision validator 和内容批准；生成器已改为后续逐公司保存 base artifact 与完整 receipts。原始文档、数据库和密钥不进入仓库。
