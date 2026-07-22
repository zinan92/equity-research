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
- C1 now defines one typed 18-section report contract with fixed full/partial/missing semantics, a 32–50 page budget, section/profile/version/input hashes, and a hard B6 boundary for live acceptance.
- C2 now reconciles historical statements and produces hashed Bear/Base/Bull DCF, reverse DCF, peer/history cross-checks and stable sensitivities while blocking currency, unit, balance and share-count anomalies.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.

## 下一步

- Start L2-C3 issue #41 from latest `main`: turn individual sell-side reports into an evidence-bound viewpoint matrix.
- Separate consensus from outliers, preserve revision timelines and keep both bull and bear evidence visible.
- Prevent summaries from claiming more certainty than the source reports; do not auto-judge which broker is correct.
