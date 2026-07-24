# N3-S6 · R2 AI-compute world-model acceptance audit

## Result

The R2 audit is **`partial`**. It confirms that the structural and filing-backed
coverage gates are real, but it prevents a count-only release because four of
the five required company questions have no company-specific evidence yet.

| Gate | Result | Evidence |
| --- | --- | --- |
| Ontology | Pass | 12 nodes, 108 canonical segments |
| Company positions | Pass | 50 reviewed A-share positions; 30 accepted page-cited positions |
| Relationship graph | Pass | 30 accepted first-party evidence-bound segment edges |
| 20-company dossiers | Pass | Exact N3-S5 receipt: 20 requested / 20 compiled / 0 failed / 20 `no_action` |
| Archive isolation | Pass | N3 production path contains no 爱牛 archive dependency |
| Five company questions | **Fail** | Only `layer` is covered for 20 companies |

## Five-question coverage

| Required question | Covered / 20 | Current boundary |
| --- | --- | --- |
| 产业链哪一层 | 20 | Accepted E3-S3 company position, with page citation |
| 凭什么有壁垒 | 0 | No company-specific moat evidence object |
| 财务兑现到哪 | 0 | No parsed, point-in-time financial delivery object |
| 市场在交易什么未来 | 0 | No evidence-bound market-expectation object |
| 什么信号应推翻判断 | 0 | No company-specific falsifier section; segment catalyst profile does not supply it |

The audit therefore rejects an R2 pass even though counts are satisfied. It
does not invent a moat, financial conclusion, market narrative, or falsifier
from a filing’s existence, an industry edge, or an AI-generated explanation.

## Archive isolation

The audit statically checks the modules that produce N3 company outputs:
company positions/index, graph, catalyst profile, dossier batch/compiler,
decision policy and offline report model. None references the archived 爱牛
dataset. This is a non-dependency check only; archive material is not loaded
or used as a source of fact.

## Reproduction

```bash
python3 scripts/verify_r2_ai_compute_world_model.py \
  /Users/wendy/Documents/equity-research-n3-s5a-runtime/n3-dossier-batch-10dd875e32907e14.json
```

The audit may pass only after each missing company-question coverage reaches
20 with its own accepted evidence identity. A `no_action` dossier is not a
substitute for those evidence gates.
