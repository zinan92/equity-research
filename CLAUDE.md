# Park Equity Research · Claude Context

This repository is the Park Equity Research product repo, not the UZI-Skill
plugin repo. Read `AGENTS.md` first and treat it as the canonical project
contract.

## Product Goal

Build a private-beta A-share research product where a user can enter any
supported ticker and receive:

1. a concise decision summary
2. a standardized, evidence-backed deep equity research report

The product must distinguish live evidence, frozen snapshots, fixtures, cached
outputs, and mock UI previews.

## Correct Product Entry Points

```bash
python3 product/server.py --host 127.0.0.1 --port 8877
python3 scripts/verify_baseline.py
python3 -m unittest discover -s product/tests -q
```

Canonical research and publication commands:

```bash
python3 product/refresh_engine.py --canonical --status
python3 scripts/verify_cross_company_research.py
python3 product/publication_pack.py 300750.SZ
```

## Review Expectations

For product, architecture, or research-quality review, judge the work against
the user outcome:

- Can a user understand the decision?
- Is the report structure standardized?
- Is every claim grounded in frozen evidence?
- Does the product fail honestly when data is missing?
- Are private-beta access, exports, and runtime data boundaries respected?

Use adversarial review only for high-risk changes such as schema, provenance,
auth, billing, publication gates, or recommendation logic. Small docs/copy/UI
changes do not need a heavy review loop unless Park asks.

## UZI Boundary

UZI-Skill remains useful reference material for historical report generation and
collector ideas, but it is not the root project identity. Do not default to
`run.py <ticker>` or the UZI deep-analysis workflow unless the task explicitly
asks to inspect or reuse UZI.
