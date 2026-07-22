# REGISTRY

## 现在在哪里

- Product: Park Equity Research private-beta A-share research platform.
- Current main includes the completed L1-A data-foundation chain: A1 Canonical Data Contract, A2 Supabase Canonical Schema & Raw Storage, A3 Generalized Ingestion Core, A4 A-Share Market/Identity/PIT Fundamentals, and A5 Orchestration/Quality/Immutable Snapshot.
- A4 now covers validated ticker identity/aliases, Tencent quote/qfq bars, Eastmoney financial highlights and three statements, financial component revision identity, Tencent/Eastmoney valuation comparison, Tencent/Sina recent bar/calendar comparison, CNINFO official corporate-action anchors, raw provenance, and typed blocking conflicts.
- A5 adds authoritative-calendar schedule/backfill planning, per-ticker/date gap detection, complete ingestion/quality receipts, explicit raw-hash-bound snapshot manifests, offline replay verification, serialized/idempotent refreshes, and fail-closed preservation of the previous active version.
- L1-B evidence ingestion has started: B1 now incrementally discovers CNINFO filings and captures CNINFO/SSE/SZSE/BSE official PDFs with raw hashes, HTTP metadata, classification, and official-primary role enforcement.
- B2 now incrementally syncs the Eastmoney sell-side catalog, archives validated PDFs behind controlled rate limits/retries, deduplicates by canonical URL and SHA-256, and keeps unavailable PDFs visible as queryable metadata-only evidence.
- B3 now extracts native PDF text with page-scoped OCR fallback, emits parser-versioned page/chunk identities, measures page-map/OCR coverage, and blocks claims whose citations do not match document ID, one-based page, and raw hash.
- B4 now normalizes Eastmoney/THS broker estimates by forecast year, binds enriched fields to report/date/raw provenance, builds replayable point-in-time consensus snapshots, and quarantines superseded or robust-outlier values before aggregation.
- B5 now adapts Intel RSS/Google News/Yahoo/official-monitor collectors behind canonical SourceManifest ingestion, resolves A-share entities against the security master, groups cross-source duplicate events, separates evidence from versioned model inference, and exposes per-source coverage gaps.
- B6 now freezes canonical records into deterministic evidence-set/gate identities, machine-checks primary/independent/lead roles, recomputes PIT/freshness/conflict/coverage, and exposes only accepted evidence through a read-only Research Context Pack.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.

## 下一步

- Start L2-C1 issue #39 from latest `main`: define one typed 15–18-section report contract for every company.
- Freeze required/optional inputs plus full/partial/missing semantics and bind section/profile/version hashes into report identity.
- Keep concrete company prose and live evidence acceptance out of C1; later real-data acceptance must pass the B6 Evidence Gate.
