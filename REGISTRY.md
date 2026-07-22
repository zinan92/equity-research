# REGISTRY

## 现在在哪里

- Product: Park Equity Research private-beta A-share research platform.
- Current main includes the completed L1-A data-foundation chain: A1 Canonical Data Contract, A2 Supabase Canonical Schema & Raw Storage, A3 Generalized Ingestion Core, A4 A-Share Market/Identity/PIT Fundamentals, and A5 Orchestration/Quality/Immutable Snapshot.
- A4 now covers validated ticker identity/aliases, Tencent quote/qfq bars, Eastmoney financial highlights and three statements, financial component revision identity, Tencent/Eastmoney valuation comparison, Tencent/Sina recent bar/calendar comparison, CNINFO official corporate-action anchors, raw provenance, and typed blocking conflicts.
- A5 adds authoritative-calendar schedule/backfill planning, per-ticker/date gap detection, complete ingestion/quality receipts, explicit raw-hash-bound snapshot manifests, offline replay verification, serialized/idempotent refreshes, and fail-closed preservation of the previous active version.
- L1-B evidence ingestion has started: B1 now incrementally discovers CNINFO filings and captures CNINFO/SSE/SZSE/BSE official PDFs with raw hashes, HTTP metadata, classification, and official-primary role enforcement.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.

## 下一步

- Start L2-B2 issue #34 from latest `main`: incrementally sync the Eastmoney sell-side catalog, archive available PDFs with controlled retry/rate limits, deduplicate by SHA/canonical URL, and expose broker/analyst/date/rating/page metadata.
- Reuse A2 private raw storage, A3 ingestion runtime, a-stock PDF patterns, and Vibe metadata patterns; keep metadata-only reports explicit when no PDF is available.
- Keep viewpoint synthesis and full-text OCR outside B2.
