# REGISTRY

## 现在在哪里

- Product: Park Equity Research private-beta A-share research platform.
- Current main includes L2-A1 Canonical Data Contract v1, L2-A2 Supabase Canonical Schema & Raw Storage, L2-A3 Generalized Ingestion Core, and completed L2-A4 A-Share Market, Identity & PIT Fundamentals.
- A4 now covers validated ticker identity/aliases, Tencent quote/qfq bars, Eastmoney financial highlights and three statements, financial component revision identity, Tencent/Eastmoney valuation comparison, Tencent/Sina recent bar/calendar comparison, CNINFO official corporate-action anchors, raw provenance, and typed blocking conflicts.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.

## 下一步

- Start L2-A5 issue #32 from latest `main`: scheduler/backfill/gap detection, complete run/quality receipts, immutable raw-bound snapshot manifest, refresh locking/idempotency, failure isolation, and replay.
- Reuse the existing refresh/snapshot foundation where it already satisfies the contract; do not build a second orchestrator.
- Keep historical intraday PIT replay, full-market aliases, official exchange adjustment factors, and real A2 Supabase replay explicit until separately evidenced.
