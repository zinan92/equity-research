# Research Section Contract v2

## Product outcome

Every company uses the same 18-section research skeleton, the same completion semantics and the same 32–50 page budget. Industry differences enter through typed optional inputs/profile modules; they do not fork the main report.

## Upstream frameworks used

- `rollingSirius/equity-research-skill` at `43965c972371e1945a1a1ed899eebe75db8d818c`: adopt the nine-chapter sequence, valuation/source discipline and industry appendix boundary.
- `star23/Day1Global-Skills` at `562c14b0c0bc84abff755181ead30ebea613d063`: rewrite the useful A–P modules as typed inputs for revenue quality, margins, cash flow, guidance, KPIs, executives, macro, ownership, R&D, accounting, risks and action triggers.
- Park B3–B6: page citations, consensus/event evidence and the immutable Evidence Gate become required inputs to the evidence/method section and the live acceptance boundary.

We do not import either upstream runtime, prompts, unavailable reference files, US-tech-only assumptions or position recommendations.

## Canonical structure

| # | Section | Required input groups | Important optional modules | Pages |
|---:|---|---|---|---:|
| 1 | 一页决策摘要 | market snapshot, decision summary | key chart | 2–3 |
| 2 | 投资逻辑与预期差 | thesis, variant view | strongest bear case | 2–3 |
| 3 | 业务模式与收入结构 | company profile, segment financials | customers, partner ecosystem | 2–3 |
| 4 | 行业空间与价值链 | industry profile, market size | value chain | 2–3 |
| 5 | 竞争格局与护城河 | peer matrix, moat assessment | competitive events | 2–3 |
| 6 | 管理层、治理与资本配置 | management record, governance events | ownership, capital allocation | 2–3 |
| 7 | 收入质量与经营 KPI | revenue history, operating KPIs | guidance, R&D efficiency | 2–3 |
| 8 | 盈利能力与利润质量 | income history, margin bridge | adjusted earnings bridge | 2–3 |
| 9 | 现金流与资产负债表 | cash-flow history, balance-sheet history | liquidity stress | 2–3 |
| 10 | 会计质量与审计检查 | accounting checks, audit opinions | restatements | 1–2 |
| 11 | 盈利预测、共识与修订 | broker estimates, consensus history | Park forecast, guidance bridge | 2–3 |
| 12 | 估值与市场隐含预期 | scenarios, assumptions, current market | reverse DCF, SOTP, EPV | 3–4 |
| 13 | 宏观、政策与成本传导 | macro exposures, policy events | commodity sensitivity | 1–2 |
| 14 | 事件、催化剂与时间表 | event timeline, catalyst calendar | versioned impact inference | 1–2 |
| 15 | 风险、反证与 Kill Conditions | risk register, falsification tests | bias check, ESG screen | 2–3 |
| 16 | 结论、目标价与仓位框架 | C5 policy output | committee explanation | 1–2 |
| 17 | 跟踪指标与行动触发器 | monitoring KPIs, action triggers | next-update calendar | 1–2 |
| 18 | 证据台账、方法与附录 | B6 receipt, citation index, methodology | gaps, industry appendix | 2–3 |

Total page budget: **32–50 pages**. It is a planning boundary, not a mandate to pad content.

## Completion semantics

- `full`: every required input for the section is present and type-valid. Optional inputs may still be absent.
- `partial`: at least one recognized required/optional input is present, but one or more required inputs are absent.
- `missing`: no recognized input is present.

Unknown sections, unknown input keys and wrong value types fail closed. `partial` and `missing` must remain visible to later renderers; they cannot be silently turned into generic prose.

## Identity

- `section_hash`: complete typed section schema, page budget and taxonomy origin.
- `profile_hash`: profile/version/modules plus all section hashes.
- `version_hash`: v2 schema and contract version.
- `contract_hash`: version + profile + ordered section schema identity.
- `input_hash`: supplied content identity for one section; changing facts changes this hash without changing the schema contract.

## B6 boundary

`structure_only=True` lets product and template work proceed without pretending there is live evidence. A live section contract (`structure_only=False`) requires a publishable B6 evidence set and freezes its `evidence_set_id` and manifest hash. C1 does not supply company prose or certify a real ticker's evidence.
