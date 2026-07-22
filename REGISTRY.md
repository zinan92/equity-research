# REGISTRY

## 现在在哪里

- Product: Park Equity Research private-beta A-share research platform.
- Current main includes the completed L1-A data-foundation chain: A1 Canonical Data Contract, A2 Supabase Canonical Schema & Raw Storage, A3 Generalized Ingestion Core, A4 A-Share Market/Identity/PIT Fundamentals, and A5 Orchestration/Quality/Immutable Snapshot.
- A4 now covers validated ticker identity/aliases, Tencent quote/qfq bars, Eastmoney financial highlights and three statements, financial component revision identity, Tencent/Eastmoney valuation comparison, Tencent/Sina recent bar/calendar comparison, CNINFO official corporate-action anchors, raw provenance, and typed blocking conflicts.
- A5 adds authoritative-calendar schedule/backfill planning, per-ticker/date gap detection, complete ingestion/quality receipts, explicit raw-hash-bound snapshot manifests, offline replay verification, serialized/idempotent refreshes, and fail-closed preservation of the previous active version.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.

## 下一步

- Start L2-B1 issue #33 from latest `main`: incrementally ingest CNINFO/exchange filings with complete raw bytes/hash/MIME/HTTP metadata, correct filing classification, and official-source role enforcement.
- Reuse A2 private raw storage and A3 ingestion runtime; extend the existing CNINFO adapter instead of creating a second document pipeline.
- Keep seller research, OCR/deep parsing, live-provider SLA, official full-history exchange calendar, and real Supabase deployment explicit until separately evidenced.
