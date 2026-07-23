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
- C3 now compiles page-cited broker viewpoints into per-report rows, robust consensus/outlier separation, immutable rating/target/forecast revisions, visible bull/bear topic evidence and evidence-strength-bounded summary language.
- The private research site now includes a code-first Industry Intelligence library: 38 archived segment three-high nodes, 94 materials-company nodes and 489 on-demand company dossiers. Single-use access codes collect no visitor identity; the source snapshot is explicitly separated from live/canonical research.
- N1-1 now adds a machine-readable and human-readable 83-field attribution register for the archived benchmark. It separates direct provenance labels (Eastmoney F10 578 and earnings-calendar 583) from candidate sources and classifies industry labels, grades and narratives as research judgment/AI inference rather than product facts.
- N1-2 now adds polite, provenance-preserving Eastmoney F10 business-composition and paginated appointment-calendar adapters. Every calendar page retains its own source URL and raw hash; a broken page yields a failed run and no partial complete-calendar result. Fixtures are isolated from optional live probes, and the 30-company runtime-only audit reached 93.46% segment-name coverage with a complete 11-page calendar and no missing validation tickers.
- GitHub audit lineage for missing references #79–#89 is truthfully reconstructed as Issues #90–#100 and bound to immutable main commits by `docs/governance/audit-lineage-v1.json`; future main changes require real Pull Request objects.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.

## 下一步

- Start N1-3 / Issue #113 from latest `main`: add A/HK/US/JP price and valuation snapshots with source fallback and historical 2026-06-30–07-02 reconstruction comparison.
- Reuse N1-2's runtime-only validation-input pattern; do not commit benchmark originals, ratings, scores, or dossier text into product outputs.
- Resume L2-C4 industry profiles only after the N1 queue has established the reusable source and research-production contracts; do not auto-map archived three-high segments to dossiers.
