# Park Equity Research · Agent Instructions

This repository is the equity-research product repo for Park. It is no longer a
UZI-Skill repo. UZI-Skill is a historical/reference component only.

## Product Intent

Build a private-beta A-share investment research product for long-term capital.
The core user outcome is:

1. User enters a ticker.
2. Product returns a concise decision summary.
3. Product returns a standardized, evidence-backed 30-50 page equity research
   report when the evidence gate passes.

The product must feel complete from the user side, but it must not pretend that
mock data, fixture output, or AI prose is verified research evidence.

## Current Canonical Entry Points

Use these for product work:

```bash
python3 product/server.py --host 127.0.0.1 --port 8877
python3 scripts/verify_baseline.py
python3 -m unittest discover -s product/tests -q
```

Use these for current data/research contracts:

```bash
python3 product/refresh_engine.py --canonical --status
python3 scripts/verify_cross_company_research.py
python3 product/publication_pack.py 300750.SZ
```

Do not assume root `run.py` or `skills/deep-analysis/scripts/` is the product
entry point. Those belong to the inherited UZI capability and are reference
material unless the task explicitly asks to inspect or reuse UZI.

## Architecture Boundary

Think in product layers:

1. Data authority: immutable raw captures, source manifests, provenance,
   point-in-time market/fundamental/document/estimate/event records.
2. Evidence corpus: filings, announcements, research PDFs, news, events,
   broker estimates, and conflict/coverage gates.
3. Research engine: standardized report contract, valuation, thesis, risks,
   sell-side matrix, target price, position policy, and audit trail.
4. Product surface: ticker entry, status journey, one-page summary, report
   reader, evidence browser, exports, sharing, and private beta membership.
5. Reliability: auth/RLS, secrets, observability, backups, rollback, cost and
   cache budgets.

## Repo Composition Policy

Prefer reuse over rebuilding from scratch, but be explicit about what is reused:

- `datafeed` style repos can provide adapter/runtime patterns.
- `a-stock-data` style repos can provide source discovery and collector ideas.
- `UZI-Skill` can provide report/rendering and prior research-flow references.
- `equity-research-skill` style repos can provide research framework ideas.

Do not copy a repo wholesale into the product path unless the issue explicitly
approves that. Most integrations should be glue code around a canonical product
contract.

## Workflow Rules

Follow Park Operating System for execution:

- One user story = one GitHub issue = one branch = one PR.
- Chain PRs when milestones depend on each other: M2 bases on M1, M3 bases on
  M2, and so on.
- Do not merge execution PRs unless Park explicitly asks in this thread.
- Convert a completed PR to Ready for Review after the contract evidence is
  present.
- Keep parallel WIP at or below 3 PRs.
- Use `park-ai-bot` identity for GitHub work.
- Do not use `git add -A`; stage named files only.

PR bodies must include:

- What
- Why
- Validation
- `Closes #N`

## Decision Log

Material decisions must be recorded in `decision-log.md`.

Every material entry must include:

- Decision
- Why
- Evidence
- Gotchas

Gotchas are required. They are where we preserve the operational traps that
would otherwise be rediscovered later.

## Testing Policy

Scale testing to risk:

- Documentation-only or instruction-only changes: readback and diff-scope check.
- Local UI or copy changes: targeted product tests and, when visual, screenshot
  evidence.
- Shared data contracts, schema, auth, provenance, report compiler, or
  publication gates: focused tests plus one full relevant suite.
- Database/storage changes: test clean installs and idempotent re-runs when
  possible.

Avoid over-testing small changes. Do not skip focused tests on critical data,
identity, provenance, permission, billing, or report-output paths.

## Review Policy

Use adversarial or architecture review only for high-risk changes:

- database schema
- raw storage and provenance
- auth, RLS, billing, secrets
- research compiler and recommendation logic
- publication gates and evidence identity

Do not run multi-agent review for small documentation, copy, or local UI-only
changes unless Park asks for it.

## Data and Secret Boundaries

- Product runtime state belongs under `product/runtime/` and must not be
  committed.
- Do not commit databases, sessions, cookies, API keys, Telegram tokens,
  DeepSeek keys, payment references, or user credentials.
- Secrets must live outside the repository or in platform secret storage.
- AI-generated text is not a source of fact. It may only explain frozen evidence
  and must keep evidence identity intact.
- Any conclusion that an item is unavailable, indeterminate, or unsupported by
  extraction must include the bounded raw text excerpt around that location.
  A truthful observation without that source snippet is not enough to claim a
  causal explanation for the extraction failure.

## Source-Unavailability Rule

- Never conclude that a source is blocked, empty, unavailable, or rate-limited
  from a classifier result alone. Before recording that conclusion, preserve one
  manually issued raw request and its complete response (URL, method, payload,
  status, and body or a safe body hash) as evidence. A failed or empty adapter
  result is a debugging signal, not source evidence.

## UZI Reference Boundary

The inherited UZI instructions and skills may be read only when useful for:

- historical report design
- prior collector behavior
- rendering patterns
- research framework comparison

When using UZI, label whether the output is mock, fixture, cached, or live.
Never present UZI mock preview output as production research evidence.
