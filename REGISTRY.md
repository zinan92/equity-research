# REGISTRY

## 现在在哪里

- Product: Park Equity Research private-beta A-share research platform.
- Current main includes the completed L1-A data-foundation chain: A1 Canonical Data Contract, A2 Supabase Canonical Schema & Raw Storage, A3 Generalized Ingestion Core, A4 A-Share Market/Identity/PIT Fundamentals, and A5 Orchestration/Quality/Immutable Snapshot.
- A4 now covers validated ticker identity/aliases, Tencent quote/qfq bars, Eastmoney financial highlights and three statements, financial component revision identity, Tencent/Eastmoney valuation comparison, Tencent/Sina recent bar/calendar comparison, CNINFO official corporate-action anchors, raw provenance, and typed blocking conflicts.
- A5 adds authoritative-calendar schedule/backfill planning, per-ticker/date gap detection, complete ingestion/quality receipts, explicit raw-hash-bound snapshot manifests, offline replay verification, serialized/idempotent refreshes, and fail-closed preservation of the previous active version.
- L1-B evidence ingestion has started: B1 now incrementally discovers CNINFO filings and captures CNINFO/SSE/SZSE/BSE official PDFs with raw hashes, HTTP metadata, classification, and official-primary role enforcement.
- B2 now incrementally syncs the Eastmoney sell-side catalog, archives validated PDFs behind controlled rate limits/retries, deduplicates by canonical URL and SHA-256, and keeps unavailable PDFs visible as queryable metadata-only evidence.
- B3 now extracts native PDF text with page-scoped OCR fallback, emits parser-versioned page/chunk identities, measures page-map/OCR coverage, and blocks claims whose citations do not match document ID, one-based page, and raw hash.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.

## 下一步

- Start L2-B4 issue #36 from latest `main`: normalize broker EPS/revenue/profit/target estimates by forecast year and bind every estimate to broker/report/date.
- Build replayable consensus snapshots and quarantine outliers before aggregate calculations.
- Keep Park-authored earnings forecasts outside B4.
