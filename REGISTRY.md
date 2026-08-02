# REGISTRY

## Operating documents (2026-08-02)

- Stable intent and completion evidence: [`NORTH_STAR.md`](NORTH_STAR.md).
- Current handoff snapshot: this file (`REGISTRY.md`); do not duplicate its
  history in the North Star.
- Material daily deltas: [`daily/`](daily/), using
  [`daily/YYYY-MM-DD.md`](daily/YYYY-MM-DD.md) as the format template.
- Durable rationale and traps: [`decision-log.md`](decision-log.md).

## 2026-08-02 · V4/Ainiu reader contract is the active product path

Now: the approved Ainiu/Round 7 reader shape is implemented as the V4
whole-dossier contract and single writer. M1 froze the reader contract, M2
proved the same shape across three replay samples (汽车制造、光模块、AI 芯片),
M3 bound CATL and Moutai outputs to official CNINFO narrative/financial
receipts, M4 quarantined the old field-shaped writer path, and M5 published
the persistent reader index at
[`artifacts/v4-reports/index.html`](artifacts/v4-reports/index.html).

The current visible V4 dossiers are 300750.SZ and 600519.SH. Both are
`pending_human_review`, with no Tier/action credit; the three additional
samples remain replay-only and are not live research. The old 18-section
completion numbers are void after the authorized contract replacement and
must not be copied into #218.

M6's honest expansion receipt is
[`artifacts/evidence/v4-m6-acceptance.json`](artifacts/evidence/v4-m6-acceptance.json):
the real 100-ticker corpus has 100 identities, 0 Report Models, 0 Tier A/B,
and 0 completed page audits. The first 20 sorted tickers are retained with
explicit blockers; no V4 dossier is fabricated. The independent audit state
remains 7 pending assignments + 13 coverage gaps.

Next: acquire and bind official evidence for additional issuers through the
same whole-dossier entry point. Do not reintroduce field-level generation,
reuse the old 18-section counts, or treat replay samples as live evidence.

## 2026-07-31 · Frozen research archive publicly readable

Now: [`research.park-ai-intel.com`](https://research.park-ai-intel.com) serves
the frozen archive as anonymous read-only from merge
`d7cb781f67be6c0654497f537b03650bd9aa8ccb`, tag
`public-readonly-archive-v1`, and content-addressed runtime release
`preview_bf6198f4d8b65c96`. External acceptance verified eight current bound
reports, 38 industry segments, 94 materials nodes and 489 company dossiers;
13 protected GET routes and six anonymous write/auth routes remain denied, all
eight mutable auth/billing table counts remained unchanged, and the Owner
login/CSRF/logout regression passed.

Boundary: this deployment is the separate frozen
`release/public-readonly-archive-v1` line. It does not restore the archived
third-party dataset to `main`, supersede canonical E1--E4 research, or make the
2026-07-02 archive live/current evidence. Anonymous visitors receive no member
or session identity; member, audit, feedback, billing, invite, mutation,
export and download capabilities remain private. The prior private release
`preview_b71f46fcd0dbc965` and a verified pre-deployment auth/runtime backup
remain the rollback boundary.

Next: keep this archive immutable unless a separately reviewed source and
rights update is approved. New product research continues on canonical main;
do not copy archive scores, grades, prose or dossiers back into its serving
paths.

## 2026-07-31 · Round 7 refactor baseline (M3–M6)

Now: the canonical output is the exact CATL Round 7 nine-chapter dossier, not
the retired field/paragraph pipeline. CATL replay is verified at
`round7-run:03ab66a964f60a6d47300c97` (model text 5,146 chars, chapter body
8,993); Moutai replay is verified at
`round7-run:10bc8c41a6fc28e01ce771b4` (model text 3,928 chars, chapter body
6,467). Both have eight research chapters `PARTIAL / pending_judgment_review`,
production record `FULL`, Tier B, and blocked `target_price`, `position_range`,
`action`. Moutai has one official source document and an explicit partial
coverage warning; no missing source was fabricated.

The old 18-section/field statistics (including 4 FULL / 10 PARTIAL / 4
MISSING) are **void after the authorized C1 chapter-set replacement** and must
not be carried into #218. New baseline is the two exact-nine replay receipts
above. The 20 page-level numeric audit assignments remain independent of report
structure and retain their prior status; no audit or #218 credit is created by
these dossiers.

The obsolete E4 field generator, wiring, queue, compiler/verifier scripts and
tests were removed in PR #653. The read API now exposes persistent dossiers at
`/api/research/round7-dossier/{ticker}` without changing publication/Tier safety.

Next: extend the same evidence-bound whole-chapter path to additional issuers;
do not reintroduce field-level generation or use the old 18-section counts.

## 2026-07-31 · Round 7 exact-nine correction

Now: issue #648 corrects the canonical C1 identity to the exact nine numbered
chapters in `docs/dossier-production/samples/300750.SZ-v1.md`. The earlier
“产业坐标 / 创始人与团队 / 发展时间线 / 大白话点评” nine-part redesign is retired.
The nine chapter bodies target 3,080–4,620 characters around the accepted
sample's actual 3,443; the complete sample remains 4,249 characters. Sources
is the sole appendix and production record is chapter 9. B6, Tier escalation,
decision policy and blocked-field sources are byte-unchanged.

Next: rebuild CATL chapter-by-chapter against this exact contract. Narrative
facts must use clean page-bound spans; the stale redesigned checkpoint and
generated artifact are not valid progress.

## 2026-07-30 · Round 7 nine-section C1 contract active

Superseded on 2026-07-31: this entry described a redesigned nine-part taxonomy,
not the exact CATL Round 7 chapter set. Its 4,200–5,500 section-body target and
“production record outside Tier” statement are invalid.

Next: R7-M3 reuses the existing structured DeepSeek transport to generate one
complete chapter per call for CATL, retaining the three reasoning validators
and all page-level evidence identity.

## 2026-07-30 · Round 7 north star frozen

Corrected on 2026-07-31: the accepted CATL file
`docs/dossier-production/samples/300750.SZ-v1.md` is the canonical chapter
taxonomy and quality example. The five blind samples and NVDA replay remain
approved structure/repeatability references created before that exact taxonomy
was frozen; they do not override the CATL chapter identity.

Next: R7-M2 replaces C1's 18-section taxonomy with a nine-section machine
contract while preserving the frozen B6, Tier and blocked-field semantics.

## 2026-07-30 · Real model judgments recompiled for CATL and Moutai

Now: the issuer-generic DeepSeek judgment path is wired into both persistent
reports with receipt identity and directly reviewable page citations. CATL is
Tier B at 5 FULL / 10 PARTIAL / 3 MISSING with seven unreviewed judgments;
Moutai is Tier B at 4 FULL / 8 PARTIAL / 6 MISSING with eight. Every section
containing an unreviewed judgment remains PARTIAL with
`pending_judgment_review`; no approval, target price, position, action, Tier A
credit, or issue #218 credit was created.

Next: submit the two impact-sorted review queues to human reviewers. Preserve
the explicit generation gaps (`monitoring_kpis` for both issuers and
`margin_bridge` for CATL), plus all independent C1 coverage gaps, until real
receipt-bound inputs exist.

## 2026-07-29 · L1 first-report vertical complete

Now: L1-M1 through L1-M6 are merged as a bounded CATL vertical.  The CATL
report is Tier B at 5 FULL / 10 PARTIAL / 3 MISSING; nine AI judgments remain
pending human review, with page-linkable citations and no review writeback.
Only `risks_and_falsification` and `monitoring_and_action_triggers` lack only
the required human approvals.  Of the prior 20 spot-audit assignments, eight
still match current financial-sequence lineage, twelve are stale, and the
fresh conservative assignment receipt has seven pending tasks plus thirteen
coverage gaps.  None is a completed audit or issue #218 credit.

Next: L2-M1 extends the existing official financial sequence to the 100-ticker
acceptance cohort, retaining typed missing coverage rather than relaxing any
gate.

## 2026-07-29 · CATL first-report vertical (M1–M4)

Now: CATL and Moutai persistent, evidence-bound HTML reports are recompiled from receipt-identified inputs. CATL is 4 FULL / 10 PARTIAL / 4 MISSING with 10 explicitly unreviewed AI judgments; Moutai remains 4 FULL / 3 PARTIAL / 11 MISSING with none. Both are Tier B / `no_action`.

Next: a human may review the 10 CATL queue items against their page citations; approval can complete only the individually eligible C1 sections, while independent coverage gaps and the #218 audit gate remain unchanged.

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
- C1 now defines the exact accepted Round 7 nine-chapter contract with fixed full/partial/missing semantics, chapter/profile/version/input hashes, and the unchanged hard B6 boundary for live acceptance. `production_record` is chapter 9; `Sources` is the sole non-Tier appendix.
- C2 now reconciles historical statements and produces hashed Bear/Base/Bull DCF, reverse DCF, peer/history cross-checks and stable sensitivities while blocking currency, unit, balance and share-count anomalies.
- C3 now compiles page-cited broker viewpoints into per-report rows, robust consensus/outlier separation, immutable rating/target/forecast revisions, visible bull/bear topic evidence and evidence-strength-bounded summary language.
- The private research site now includes a code-first Industry Intelligence library: 38 archived segment three-high nodes, 94 materials-company nodes and 489 on-demand company dossiers. Single-use access codes collect no visitor identity; the source snapshot is explicitly separated from live/canonical research.
- N1-1 now adds a machine-readable and human-readable 83-field attribution register for the archived benchmark. It separates direct provenance labels (Eastmoney F10 578 and earnings-calendar 583) from candidate sources and classifies industry labels, grades and narratives as research judgment/AI inference rather than product facts.
- N1-2 now adds polite, provenance-preserving Eastmoney F10 business-composition and paginated appointment-calendar adapters. Every calendar page retains its own source URL and raw hash; a broken page yields a failed run and no partial complete-calendar result. Fixtures are isolated from optional live probes, and the 30-company runtime-only audit reached 93.46% segment-name coverage with a complete 11-page calendar and no missing validation tickers.
- N1-3 now reconstructs the 30-company A/HK/US/JP historical market snapshot with bounded source fallbacks and field-level provenance: 22 prices pass the declared window, eight exact matches are retained as outside-window residuals, and 28/30 changes pass with two explicit previous-close reference mismatches. SEC filed-before-as-of facts plus frozen historical FX reconstruct 52 valuation fields, while three outliers, 39 unavailable historical inputs and 12 undisclosed-definition PEG fields remain visible instead of being forced through tolerance. The source register reaches 24/28 high/medium-confidence market-field cells (85.7%).
- N1-4 now independently reproduces only the benchmark's disclosed arithmetic. In the 649-company main universe, composite matches 453/453 calculable rows and opportunity matches 575/578 (99.48%); 196 and 71 missing-input rows remain explicit. PEG grades match 276/276 calculable rows in the separate 661-company levels universe. S/A/B remains labeled manual/research judgment because visible score values map to multiple grades and the claimed qualitative inputs are mostly absent.
- N1-5 established the reader-first dossier evidence used in Round 7. On 2026-07-31 Park selected the CATL nine-chapter file as the exact canonical taxonomy: 一句话定位；身份、创始人与治理；技术来源与发展史；商业模式与业务线；财务与经营时间序列；护城河的证据链；风险、反题材与观察触发器；研究结论与待补问题；生产记录；plus Sources. Five blind samples and the NVIDIA replay remain supporting quality/repeatability evidence, not an alternate taxonomy.
- N1-6 now closes the M1/N1 acceptance package: a 30-company six-sector A/HK/US/JP golden set, 84/90 (93.33%) high/medium source-contract field coverage, six explicit HK/JP point-in-time financial-growth gaps, prior 30-company market reconstruction, disclosed-score validation, and five-dossier evidence. The resulting M1 report is a Go for E1/N2 canonical modeling, not a claim of all-market real-time financial coverage.
- N5 first slice now ships a fixture-driven Atlas frontend at `product/static/atlas/`: six deep-linkable hash routes covering overview, 22 industry-chain structures with segment→company navigation, a three-high bubble map linked to segment catalysts, a 649-company virtualized table with full-column sorting and chain/layer/market/grade/tag filters, a 661-stock S/A/B table with real header sorting, and a company workbench (position, five-factor scores, three-high verdict, quarterly drill, business segments, roadmap, supply chain, dossier). Dev fixtures derive from the 2026-07-02 archive, are gitignored and load per view (~240KB first screen); `js/data.js` is the single seam for the future N2 canonical API; every quote surface shows as_of + FIXTURE and archived dossier text is labeled as development sample only.
- GitHub audit lineage for missing references #79–#89 is truthfully reconstructed as Issues #90–#100 and bound to immutable main commits by `docs/governance/audit-lineage-v1.json`; future main changes require real Pull Request objects.
- Root `AGENTS.md` / `CLAUDE.md` are re-scoped from UZI-Skill to Park Equity Research.
- The prior stacked PR chain has been cleared; each completed story is now merged before the next branch starts under the 2026-07-22 Park Operating System manual.
- E1-S1 now supplies the canonical Company / Universe Crosswalk without creating a parallel identity schema: code + market resolve to explicit `matched`, `ambiguous`, or `unmapped` outcomes; every candidate carries source reference, known-at and data-kind. The local 649/661 archive audit remains runtime-only (1,058 matched, 252 unmapped), while all 30 M1 tickers parse and nine archive absences stay explicit.
- E1-S2 now supplies eight versioned research-object contracts on the existing A1/A2 authority path: Company, SectorPosition, Evidence, Catalyst, Roadmap, ScoreSnapshot, Falsifier and Dossier. SQLite and Postgres revisions are append-only; facts require evidence references, judgments require a model version, and each subsequent revision binds the immediately prior object hash.
- E1-S3 now binds each research-object revision to existing A2 raw hashes and an accepted A5 snapshot, rejects un-frozen evidence, preserves same-input idempotency, and produces deterministic identity-only replay receipts that expose any broken revision/provenance chain.
- E1-S4 now provides the single canonical write path for E1 objects: the A3-style publisher validates E1-S2/E1-S3 bindings and atomically writes revision plus identity-only evidence receipt, rolling back an invalid batch without changing last-good state.
- E1-S5 now exposes fixture-safe canonical read contracts for Company, SectorPosition, Dossier, ScoreSnapshot and Roadmap: accepted real-snapshot data retains object/evidence/snapshot identity, while unknown or fixture/non-real requests return structured gaps unless fixture access is explicitly enabled.
- E2-S1 now production-validates the existing A4 A-share identity contract: point-in-time alias resolution reuses A4 normalization across SH/SZ/BJ, returns explicit ambiguous/unmapped outcomes, exposes lifecycle state by as-of, and carries a deterministic 100-ticker identity-contract corpus (not a claim of live full-market coverage).
- E2-S2 now production-validates the existing A4/A5 market and PIT-financial authority path with an explicit fixture-only acceptance receipt: identical input is idempotent, PIT quality gates have no blockers, raw-bound snapshot replay is deterministic, and this remains separate from any claim of real-time/full-market coverage.
- E2-S3 now production-validates existing corporate-action, adjustment-factor and historical valuation/FX contracts: broken lineage, future-visible actions, valuation conflicts and inferred valuation history all fail closed; FX remains date-frozen and unavailable inputs remain gaps.
- E2-S4 now production-validates the existing B1/B3 official-filings corpus: incremental discovery preserves official PDF identity and raw receipt; parser page/OCR coverage is measured and unreadable pages remain gaps; document/page/hash citations can fail-closed return to the official HTTPS URL and immutable storage URI.
- E2-S5 now production-validates the existing B2/B4 sell-side path: catalog/PDF identity and metadata-only gaps remain explicit; broker estimates have point-in-time, stale/outlier-quarantine and replay semantics; viewpoint language stays constrained by page-bound evidence and documented disagreement.
- E2-S6 now production-validates B5/B6: event entity ambiguity, cross-source provenance and source failures are explicit; accepted-only Context Packs reject future, fixture, rejected or tampered evidence; coverage tiers remain recomputable.
- E3-S1 now defines the self-owned, versioned AI-compute ontology: 12 major nodes and 108 stable segments with identity, boundary and source strategy, explicitly separate from archive prose, scores and grades.
- E3-S2 now provides an evidence-bound industry graph: 30 source-scoped, direction/strength/as-of edges bind to raw hashes captured from three first-party sources; absent or rejected evidence cannot appear in traversal.
- E3-S5 now supplies declarative battery, consumer and bank Profiles over the single C1 report contract: shared section structure with sector KPI, valuation-focus and visible missing-input policy.

## 下一步

- 2026-07-28: M1–M3 vertical validation is complete. CATL reaches page-bound financial history, partial C2 and an explicit no_action receipt; Moutai exposes generic table-column validation gaps; Ping An Bank is correctly outside manufacturing DCF. Next: decide whether to build generic column validation and sector valuation profiles; do not promote these slices toward #218.

- 2026-07-28: PR #473 re-ran and recorded R2 as passed using five hash-bound runtime receipt lineages: 12 nodes, 108 segments, 30 accepted company positions, 20/20 evidence-bound dossiers and all five company evidence questions at 20/20. This closes only the R2 world-model evidence gate; all dossiers remain `no_action`. Next hard release gate is R3/#218: ≥95 Report Models, ≥80 Tier A/B and 20 independent numeric/page audits.

- 2026-07-28: PR #470 retired the benchmark-derived Industry Intelligence snapshot from product-serving paths. The product no longer ships `product/data/industry-intelligence-v1.json`; both historical endpoints fail closed with `410 industry_intelligence_unavailable` until canonical E1--E3 evidence is published. The archival builder rejects any output below `product/`. Next: replace the retired surface only through the canonical industry/evidence path and Claude-owned frontend work; do not restore an archive fallback.

- R0 approved on 2026-07-24: [Epic Execution Plan](docs/plans/2026-07-23-epic-execution-plan.md). Execute through existing #113–#116 first; only create missing child issues after current WIP clears.
- Continue E3-S3 / M3.1: produce 50–100 company industry positions from the M1 identity-only validation set; accept only official page-cited mappings and retain unverified/ambiguous mappings in an explicit review queue. In parallel start E3-S6: production-validate the existing C2 valuation engine and C3 viewpoint matrix against real accepted Context Packs.
- Reuse N1-2's runtime-only validation-input pattern; do not commit benchmark originals, ratings, scores, or dossier text into product outputs.
- N5 next slice: replace Atlas fixtures with the N2 canonical read API once it exists, run the three-minute five-question self-test with Park on real usage, and keep frontend ownership with Claude (Codex must not modify `product/static/**`).
- Resume L2-C4 industry profiles only after the N1 queue has established the reusable source and research-production contracts; do not auto-map archived three-high segments to dossiers.

- E4-S4o is merged: valuation and sell-side coverage can now be bound only through real, hash-bound receipts matching the same ticker, cutoff and accepted Context Pack as an E4 partial model; even with both sections present it remains Tier C / no_action.
- Next E4 step: produce source-compliant runtime valuation/sell-side receipt adapters for the canonical 100-ticker corpus, then evaluate #218 without treating partial models as Tier A/B coverage.
- E4-S4p is merged: the canonical real 100-ticker identity corpus can now run a bounded, checkpointed B2 sell-side catalog/PDF archive batch with per-ticker raw/source identities, metadata-only states and typed failures; it is input-only and grants no Tier, target, position, action or page-audit credit.
- Next E4 step: run the bounded sell-side batch against the full corpus, parse archived PDFs into C3 page citations, and bind only matching Context Pack receipts before re-evaluating #218.
- E4-S4q is merged: each successful E4 sell-side catalog/PDF ingestion attempt can now persist re-hashed, content-addressed bytes beneath ignored runtime raw storage; receipt paths appear only after local hash verification and remain non-canonical, input-only material.
- Next E4 step: rerun the bounded sell-side corpus using runtime raw persistence, then parse the archived PDFs through B3/C3 into page-cited viewpoints before the #218 coverage gate.
- E4-S4r is merged: re-hashed, runtime-local E4 sell-side PDFs can now be parsed through the existing B3 parser into document/page/chunk identities with parser version and typed blockers; this is page evidence only, not an analyst claim, matrix, Tier or decision.
- Next E4 step: rerun the 100-ticker sell-side batch on the raw-persistent path, then compile page-cited C3 viewpoints/estimate receipts against matching Context Packs.
- E4-S4s is merged: a catalog broker/rating can enter the existing C3 matrix only when the same report PDF has been re-hashed and page-verified; target, estimates and claims remain explicit missing fields rather than inferred prose, and output is still non-Tier/non-decision input.
- Next E4 step: finish the raw-persistent 100-ticker run, compile its page evidence and C3 matrices, then bind only matching Context Packs into partial Report Models before re-running #218.

## 2026-07-24 · E4-S4b strict coverage baseline

- E4-S4b is merged: the fixed 100 identity / 95 real Report Model / 80 Tier A/B / 20 numeric+page audit contract now has a deterministic, fail-closed receipt with per-ticker failure taxonomy.
- The live baseline is intentionally not accepted: 100 real A-share identities are present, while real Report Model, Tier A/B, and numeric/page-audit counts remain 0; all 100 tickers are classified `missing_canonical_evidence`.
- Parent #218 remains open. Next data work is canonical-evidence acquisition and explicit Report Model construction; identity directories and fixtures do not count toward that gate.
- E3-S4 is now merged: all 108 ontology segments have an evidence-gated six-section catalyst profile; current one-party captures anchor 24 segments and the remaining 84 remain explicit `missing_evidence`. Next: E3-S7 dossier generation from accepted evidence and E3-S3 positions.
- E3-S7 is now merged: deterministic dossiers compile only from an accepted Context Pack, accepted company position and matching catalyst profile; facts retain evidence identity and unavailable catalyst inputs remain gaps. Next research-engine step: E3-S8 decision/target/position policy.
- E3-S8 is now merged: decision receipts jointly bind valuation/quality/risk/liquidity/coverage and portfolio caps; insufficient evidence or breached constraints returns non-executable `no_action`. Next: E3-S9 offline research compiler.
- E3-S9 is now merged: an offline Report Model binds C1 section semantics to dossier and decision identities without fetches or model calls. E3 is structurally complete; next gate is E4 three-company vertical slices with real accepted evidence.
- E3-S1b is now merged: battery, consumer and bank sector identities live in a separate cross-sector taxonomy; AI-compute IDs remain unchanged and mismatched segments fail closed. E4-S1 can now build truthful cross-sector company positions.
- E3-S6 is now merged: C2 valuation and C3 sell-side matrix outputs are bound to B6 accepted Context Pack identity; unaccepted report raw hashes, missing components and fixture evidence fail closed. E3-S3 remains the active evidence-collection gate for page-cited company positions.
- E3-S3 is now merged: its A-share-first review queue contains 50 company positions, 30 independently page-cited to official CNINFO annual-report URLs and raw hashes; the remaining 20 are explicit `needs_evidence`. Next research-engine work is E3-S4: evidence-bound catalyst/falsifier content for all 108 ontology segments.
- Next active gate: E4-S1 three-company vertical slice. Populate cross-sector positions with official annual-report page citations for 宁德时代、贵州茅台和招商银行; do not promote existing fixtures as real evidence.
- E2-S4b is now merged: SH issuer filing discovery uses an independent official SSE bulletin index, captures raw index provenance, accepts only declared official PDF URLs, and routes exchanges without silent fallback. The first live SSE probe remains pending because this environment timed out against the official site.
- E4-S1 is now merged: one historic, evidence-bound pipeline spans 宁德时代、贵州茅台和招商银行. Each retains a public disclosure URL/page/SHA-256, context/dossier/report identities and a deterministic `no_action`; missing market, valuation, sell-side, quality/risk/liquidity and catalyst inputs stay explicit. This proves a shared partial pipeline, not a current complete report.
- Next active gate: E4-S2 must turn the historic anchor receipts into canonical persisted objects with immutable raw storage and re-auditability before any product surface calls them current research.
- Correction / E4-S2 completion: E4-S2 is the roadmap's batch/cache/resume story, now merged. It binds every reusable task artifact to ticker + snapshot + evidence manifest, persists each task for selective resume, and returns explicit completed/partial/failed/reused states. The prior raw-storage sentence remains a standing truth boundary for E4-S1 anchors, not a claim that E4-S2 changed their authority.
- Next active gate: E4-S3 Honest Degradation. Freeze A/B/C/Missing output policy over B6/C1, so any-ticker requests communicate exactly what can be concluded and never emit high-confidence position advice from low coverage.
- E4-S3 is now merged: B6 evidence and C1 sections compile into A/B/C/Missing receipts. Only Tier A may expose action, target price or position range; all lower tiers preserve coverage, blocked fields and source-specific next steps.
- Next active gate: E4-S4 100-ticker acceptance. Establish 100 identity resolutions, then measure real evidence/report-model coverage and classify every failure without treating fixtures as product evidence.
- E6-S1 is now merged: private-beta authentication retains server-side tier entitlements while adding owner-controlled editor/member roles, append-only SQLite audit events, credential-shaped detail redaction, and owner-only audit readback. Next reliability work may proceed independently as E6-S2 observability and cost controls; it must not claim that database triggers replace backup or host-level access controls.
- E6-S2 is now merged: existing A5 refresh receipts now derive local source-health, identity-only run-trace, coverage-impact and deduplicated alert-lifecycle receipts. Fallback recovery remains visible without false coverage alerting; fixture/cached sources cannot yield production health. Next reliability milestone is E6-S3 backup/restore/release rollback, while E4-S4 remains the product-data coverage gate.
- E6-S3 is now merged: the existing isolated release store now has an external-runtime-only backup/clean-restore drill. Its manifest rechecks release/snapshot identity and separate auth DB hash; a tampered backup cannot activate. Existing verified `current` pointer rollback remains the release mechanism. Next reliability story is E6-S4 performance/cache/cost; E4-S4 remains the actual 100-ticker coverage blocker.
- E6-S4 is now merged: identity-bound cache reads and offline task queues have local-harness p95 budgets, ten-task isolation evidence, and a receipt-backed cost ledger whose unknown provider costs stay unknown. These are not live SLA or billing claims. E6’s planned reliability stories are complete; the principal product gate remains E4-S4’s 100 real-ticker coverage.
- E4-S4a is now merged: a bounded runtime security-master capture replaced the synthetic prefix corpus with 120 real SH/SZ/BJ identities, URL/raw-hash provenance and fail-closed code/exchange checks. It meets only the identity sub-gate; it explicitly does not count toward evidence, Report Model or Tier A/B coverage. Next E4-S4 work is the real evidence/report coverage receipt and failure taxonomy.
- E4-S4c is now merged: a sequential, resumable runtime batch converts the real identity corpus into at most one current annual/semiannual/quarterly official PDF per ticker, retaining official URL, publication timestamp, raw hash and canonical storage URI. The batch is explicitly an input layer: a captured PDF does not count as Report Model, Tier A/B or numeric/page-audit coverage. Next: compile captured primary inputs into canonical evidence sets and Report Models without weakening #218’s 100/95/80/20 gate.
- E4-S4d is now merged: each valid E4-S4c official PDF can be revalidated into a primary-only B6 Context Pack and deterministic partial Report Model. It may establish real evidence-bound model coverage, but it is fixed at Tier C / `no_action`, with market, fundamentals, valuation, sell-side and industry-position gaps explicit; it cannot count toward Tier A/B or numeric/page-audit thresholds. Next: collect and bind those missing components before any upgrade.
- E4-S4e is now merged: financial-report collection now searches a bounded sequence of official CNINFO/SSE index pages and retains each inspected page receipt before saying no qualifying report exists. It retains the sequential one-PDF cap and all Tier/audit boundaries; a live 3-ticker check moved official-PDF capture and partial-model compilation from 1/3 to 3/3. Next: measure the same real pipeline across the 100-ticker E4 corpus.
- E4-S4g is now merged: each live official-filing ticker collection runs in a terminating child process, so a stalled SSL/PDF read becomes explicit `collector_timeout` and cannot block the sequential corpus. Timeouts contain no evidence/model/Tier/audit credit. Next: rerun the 100-ticker E4 baseline under this bounded failure behavior.
- E4-S4h is now merged: a companion batch reuses the A4 canonical packet to capture real market and point-in-time financial inputs with per-component source/raw/manifest/known-at provenance and the same terminating child-process boundary. It is input-only: a valid quote or financial statement cannot on its own promote a company above Tier C or produce an action. Next: bind those inputs to primary evidence, valuation and remaining independent evidence under the still-running 100-ticker E4 baseline.
- E4-S4i is now merged: the external official-evidence corpus atomically checkpoints each resolved ticker and marks its latest pointer as `in_progress` or `completed`. Resume is permitted only for the exact identity corpus and collection configuration; checkpoint rows remain runtime-only and confer no Report Model, Tier A/B or audit credit. Next: complete and measure the real checkpointed 100-ticker baseline.
- E4-S4i follow-up is now merged: completed receipts carry the same exact corpus configuration as in-progress checkpoints, and a configuration mismatch fails closed before captured rows can be reused. Next: complete and measure the real checkpointed 100-ticker baseline.
- E4-S4f is now merged: the real checkpointed baseline resolved 100 identities into 40 evidence-bound Tier C partial Report Models and 60 source-specific collection failures. It records 0 Tier A/B and 0 numeric/page audits, so #218 remains failed at 100/95/80/20 rather than being relaxed. Next: expand official-source coverage and bind market, PIT fundamentals, valuation, sell-side and industry-position inputs before any Tier upgrade.
- E4-S4j is now merged: the A4 market/PIT fundamentals companion batch atomically checkpoints each terminal ticker, resumes only when identity/official receipt/config hashes match, and remains strictly input-only. Next: finish the real 100-ticker companion receipt, then bind it with primary evidence before valuation, sell-side and industry-position upgrades.
- E4-S4j live baseline is now merged: the completed real companion receipt provides market and PIT fundamentals availability for 67/100 identities, with 33 typed failures. It is input-only and adds no Report Model, Tier, target, position or audit credit. Next: bind primary and companion identities into an upgraded model contract alongside valuation, sell-side and industry-position inputs.
- E4-S4l is now merged: partial Report Models may bind only a companion receipt whose official receipt bytes hash exactly matches the primary corpus. It exposes real market/PIT component availability but remains Tier C / `no_action`; valuation, sell-side, industry position and audits remain explicit gates. Next: publish the real dual-input replay, then add those remaining components.
- E4-S4m is now merged: the published real dual-input replay records 40 primary-evidence partial models and 60 typed blocks across 100 identities; 27 of the 40 bind both market and PIT-fundamentals components through exact receipt lineage. This is still Tier C / `no_action`, with zero valuation, sell-side, industry-position, Tier A/B or numeric/page-audit credit. Next: restore official SH/BJ coverage, then bind the remaining gated research components.
- N3-S1 is now merged: the AI-compute world model now has one deterministic company↔industry-segment index over the existing E3-S3 review queue. It exposes 30 page-cited company facts by default and retains 20 explicitly unverified positions only for review; it does not duplicate the position store or turn gaps into investment facts. Next: add evidence-gated industry relationships, catalysts and company-dossier production on this index.
- N3-S2 is now merged: a fresh, first-party-receipted AI-compute relationship baseline contains 12 nodes, 108 segments and 30 accepted segment edges. It describes structural value-chain relationships only, not company leadership, valuation or investment claims. Next: compile evidence-gated catalysts and company dossiers atop this index and graph.
- N3-S3 is now merged: the catalyst baseline covers all 108 segments, but only 24 carry one first-party current-state fact; the remaining 84 are explicit missing-evidence profiles, and driver/trigger/indicator/falsifier/time-horizon fields remain unfilled. Next: use only these bounded inputs to compile evidence-gated company dossiers.
- N3-S4 is now merged: 宁德时代、贵州茅台和招商银行 each run through the same evidence-bound Context Pack → dossier → report → decision loop with no fixture facts. All remain partial / `no_action`, with market, valuation, quality/risk/liquidity, sell-side and catalyst gaps explicit. Next: refresh those inputs and extend accepted industry/company evidence before any action upgrade.
- N3-S5 runner is now merged: 20 E3-S3 cited official PDFs are processed sequentially with per-row runtime checkpoints and exact selection-identity resume. Its first real baseline is 19 compiled / 1 `601138.SH` timeout / 19 `no_action`; the ≥20 contract remains open and must be recovered without relaxing the threshold or using a substitute source.
- N3-S5 recovery is now merged: the original `601138.SH` CNINFO citation was re-fetched with the exact expected raw hash, so the unchanged 20-company selection now completes 20 compiled filing-backed dossiers and 20 `no_action` receipts. This meets the R2 count gate only; valuation, sell-side, market, quality/risk/liquidity and catalyst evidence remain missing.
- N3-S6 is now merged: R2’s fail-closed audit confirms ontology, positions, graph, 20 dossiers and archive isolation, but R2 remains `partial`. Only the industry-layer question is 20/20; moat, financial delivery, market future and falsifier are each 0/20 and must gain company-specific evidence before R2 can pass.
- N3-S7 runner is now merged: an A4 PIT financial-delivery receipt binds period, announced-at and four real source identities to the same 20 companies. Its real baseline is 11/20 available and 9 packet-validation gaps, so financial delivery rises only to 11/20 and R2 remains `partial`; no valuation or action credit is created.
- N3-S7a is now merged: future-scheduled Eastmoney rows stay in raw captures but cannot enter PIT facts, and N3 financial delivery validates only its four declared financial sources with bounded same-source retries for transient transport failure. The unchanged 20-company selection now reaches 20/20 real financial inputs; R2 remains `partial` because moat, market-future and falsifier evidence are still 0/20. Next: bind those three company-specific evidence dimensions without converting financial-input coverage into a recommendation.
- N3-S8 is now merged: 20/20 selected companies have an issuer-disclosed, observable falsifier bound to the original official CNINFO URL, full raw hash, page and known-at. Large official PDFs are read in bounded ranges and only accepted after full-hash verification. R2 now has layer / financial-delivery / falsifier at 20/20 but remains `partial`: moat and market-future evidence are each 0/20 and no action, target or position credit exists. Next: collect those two independent company evidence dimensions.
- N3-S9 is now merged: the same 20 selected companies each have one page-bound issuer-disclosed capability observation, bound to the original CNINFO URL, full raw hash and known-at; generic advantage language is rejected. R2 now has layer / moat / financial-delivery / falsifier at 20/20 and remains `partial` solely because market-future evidence is 0/20. Next: collect a separately sourced, company-specific market-future evidence receipt without turning issuer disclosure into a forecast, valuation, target, position or action.
- N3-S10 is now merged: the same 20 selected companies each have a page-bound issuer-disclosed forward market-driver observation, bound to the original CNINFO URL, full raw hash, page and known-at; generic company aspiration is rejected. R2’s five evidence questions are each 20/20 and its evidence gate is `passed`. This is not a recommendation: every dossier remains `no_action`, and subsequent work must still separately meet valuation, sell-side, publication and product gates before any decision output.
- E4-S4k-a is now merged: failed official-filing discovery receipts distinguish TLS/SSL transport timeout, explicit official access denial, official-index empty and unclassified failure only when their captured attempt evidence supports it. Failure classification creates no evidence, Report Model, Tier, target, position or audit credit. Next: #274 must restore source-compliant SH/BJ coverage or retain these typed gaps; it may not bypass WAFs or substitute an aggregator.
- E4-S4k-b is now merged: an urllib TLS handshake failure may retry only the exact `query.sse.com.cn` official index URL and headers through bounded curl transport; off-host redirects, unavailable curl and curl errors fail closed. A real SSE index response is recoverable, but this does not solve PDF capture or BJ coverage and yields no Report Model, Tier, target, position or action credit. Next: #274 continues with source-compliant SSE document capture and BJ discovery only.
- E7-S1 is now merged: the existing A5 orchestration receipt now records a versioned slow/periodic/fast cadence policy. Only fast reads an actual canonical active `activated_at`; without source-specific successful receipts, slow and periodic are explicitly `missing`. No second scheduler, direct collector write path, fact, Tier or recommendation was introduced. Next: bind actual slow/periodic runners and retain A5 last-good behavior on their failures.
- E7-S2a is now merged: `thesis` is a first-class append-only research object with fresh SQLite, explicit legacy SQLite rebuild, and PostgreSQL constraint migrations. Legacy object rows and append-only triggers are retained; a thesis remains context, not a rating, target, position or action. Next: E7-S2 links versioned theses to catalysts, falsifiers and events.
- E7-S2 is now merged: B5 events can produce only an explicit, evidence-bound fulfilled/delayed/broken trigger-revision proposal. E1 remains the sole append-only write path; prior revisions are never silently changed, and the flow produces no action, target, position or order. Next: continue the E4 evidence-coverage gate, including source-compliant SH/BJ filing coverage and missing valuation/sell-side/industry inputs.
- E7-S3 is now merged: a read-only outcome receipt freezes publication/report identity and its `as_of`/`known_at` basis, then records separately labelled later company/benchmark/optional-industry/fundamental outcomes. Later inputs cannot rewrite the research basis and never yield an action, target, position or order. Next: E7-S4 aggregates coverage/freshness/citation/outcome quality into a controlled expansion gate.
- E7-S4 is now merged: a deterministic quality aggregate returns `no_go` whenever coverage, cadence, citation or outcome quality is not passed, or a manual correction issue is present. It reuses receipt status only and creates no source collection, action, target, position, recommendation or order. Next: R3 remains blocked on E4-S4 100-ticker evidence coverage.
- E4-S4n is now merged: partial Report Models expose valuation and sell-side states only as accepted/missing/blocked, retaining Tier C and `no_action` in every case. It does not collect a new source, relax #218, or create target/position/action output. Next: establish actual point-in-time valuation and sell-side availability across the 100-ticker corpus.

## 2026-07-25 · E4-S4t receipt-binding update

- 现在在哪里：PR #388 merged. E4 can now bind the existing B6 official-primary Context Pack identity, market/fundamentals source receipts, and C3 page-verified sell-side matrix into deterministic per-ticker Report Model inputs. Mismatched ticker, official lineage or exact cutoff is explicit blocked; all outputs remain Tier C / no_action.
- 下一步：run a synchronized real-input trial using these receipts, record its typed coverage/blockers on #218, then close the remaining E4-S4 acceptance gaps (valuation, explicit page-cited claims and numeric/page audit) without treating rating-only matrices as research conclusions.

## 2026-07-25 · E4-S4v research-cutoff update

- 现在在哪里：PR #393 merged. E4 C3 matrix runtime receipts now carry a caller-supplied, timezone-qualified `research_cutoff` alongside the unchanged date-level report-filter `as_of`; no provider timestamp or report date is rewritten.
- 下一步：make E4-S4u consume this explicit cutoff against official/market known-at evidence, then rerun the real 100-ticker Context Pack binding and retain every remaining acceptance gap on #218.

## 2026-07-25 · E4-S4u real Context Pack replay

- 现在在哪里：PR #396 merged. At the explicit `2026-07-25T23:59:59Z` research cutoff, the real 100-ticker replay compiled 40 official-primary Context Pack model inputs; 27 have market/fundamentals and 18 have page-verified C3 sell-side sections. Actual source `known_at` and official-context timestamps remain separately auditable.
- 下一步：E4-S4 acceptance remains failed: convert legitimate valuation inputs and page-cited analyst claims, perform the required numeric/page audit, and recover official coverage without counting rating-only matrices as Tier A/B, target, position or action evidence.

## 2026-07-25 · E4-S4w valuation receipt adapter

- 现在在哪里：PR #400 merged. C2 valuation can now be replayed only from explicit canonical source hashes, an explicit assumption receipt and matching E4 partial Context Pack identity; missing or future-known source inputs are blocked and every output remains Tier C/no_action.
- 下一步：produce governed, real assumption/source receipts for the corpus, then separately extract page-cited analyst claims and complete the required numeric/page audit. The adapter itself adds no valuation coverage until those real inputs exist.

## 2026-07-25 · E4-S4x page-cited claim candidates

- 现在在哪里：PR #404 merged. Page-verified sell-side PDFs can now yield deterministic sentence candidates retaining report/raw/parser/page/chunk identity. Every item is labelled an unreviewed broker assertion, not a verified company fact or accepted C3 claim.
- 下一步：run the candidate extractor over the runtime corpus, then define a separate accept/reject review gate before any candidate can enter C3 claims, Tier A/B or the required page audit.

## 2026-07-25 · E4-S4y candidate runtime receipt

- 现在在哪里：PR #408 merged. Candidate extraction now writes a content-addressed runtime-only receipt and latest pointer, preserving all input hashes and non-actionable truth boundaries.
- 下一步：execute the corpus in bounded/checkpointed slices and report actual candidate counts; candidates remain unreviewed until a separate accept/reject gate exists.
## 2026-07-25 · E4-S4z bounded candidate extraction

- 现在在哪里：PR #412 merged. The sell-side candidate extractor now resumes from a lineage-bound runtime checkpoint; the completed real corpus contains 71 compiled documents, 1 blocked document, and 1,047 unreviewed broker-assertion candidates.
- 下一步：add the separate accept/reject gate before any candidate can become a C3 research claim; candidates remain non-actionable and cannot affect Tier, audit, target, position, or action.

## 2026-07-25 · E4-S4aa governed claim admission

- 现在在哪里：PR #416 merged. The only admission path now requires an explicit, identity-bound human review decision; the real runtime corpus truthfully records 1,047 candidates and zero admitted claims because no reviewer decision was fabricated.
- 下一步：collect actual reviewer decisions for selected candidates, then execute the separately contracted numeric/page audit and governed valuation inputs; no admission alone changes Tier, target, position, or action.

## 2026-07-25 · E4-S4k official document taxonomy

- 现在在哪里：PR #419 merged. Official evidence receipts now distinguish non-PDF, access-denied, TLS and timeout document failures; the fresh SSE/BJ probes remain explicit source gaps rather than fabricated coverage.
- 下一步：#274 remains open. Expand only through a registered official source when it is actually reachable; do not bypass the official BSE/SSE access boundary or substitute an aggregator.

## 2026-07-25 · E4-S4ab persisted reviewer decisions

- 现在在哪里：PR #423 merged. An owner can append a hash-bound candidate review through the product backend and export it into the existing admission contract; duplicate, member and unauthenticated writes are rejected.
- 下一步：obtain real reviewer decisions for selected candidates, then perform the required independent numeric/page audit. No stored decision alone changes Tier, target, position or action.

## 2026-07-25 · E4-S4ac companion-bound partial models

- 现在在哪里：PR #427 merged. The real matching E4 lineage now compiles 40 official-input partial models, with 27 carrying available market and fundamentals sections; 60 rows retain their official-input blockers.
- 下一步：turn real reviewed sell-side claims, governed valuation inputs and page/numeric spot audits into acceptance evidence. Until then, all partial models remain Tier C/no_action rather than full reports.

## 2026-07-25 · E4-S4ad source-bound display facts

- 现在在哪里：PR #431 merged. E4 now retains a whitelisted, source-bound market and financial input projection rather than only availability flags. A fresh real `000001.SZ` receipt compiled into a partial model with both fact sections, while preserving Tier C/no_action.
- 下一步：scale this runtime capture only where real provider packets succeed; separately resolve official filing coverage, reviewer decisions, governed valuation inputs, and page/numeric audit before treating any partial model as a publishable research report.

## 2026-07-25 · E4-S4ae component failure taxonomy

- 现在在哪里：PR #434 merged. E4 market/fundamental collection now preserves source-component blockers and bounded same-plan retry history instead of collapsing all failures into one packet validation error.
- 下一步：run the new receipt contract against the remaining 100-ticker baseline, use only its typed source gaps to guide recovery, and retain every unavailable section as input-only / no_action.

## 2026-07-25 · E4-S4af source-bound partial-model API

- 现在在哪里：PR #437 merged. Deep-report members can read a source-bound partial model through a fail-closed endpoint that validates receipt identity, root containment and the Tier C/no_action boundary; unavailable tickers receive an explicit status rather than fallback prose or facts.
- 下一步：#218 remains failed at 40/95 report models, 0/80 Tier A/B and 0/20 page/numeric audits. Continue real official evidence coverage, governed valuation inputs, reviewed sell-side claims and auditable spot checks; the new read API cannot be used to claim a full report or recommendation.

## 2026-07-25 · E4-S4ag immutable spot-audit assignments

- 现在在哪里：PR #441 merged. A content-addressed, runtime-only list now freezes 20 real fact-bearing E4 partial models for numeric and page-citation review; it contains 20 pending human reviews and zero completed audits, with no raw paths or Tier/action escalation.
- 下一步：an independent reviewer must produce identity-bound numeric and page review records before #218 can count any spot audit. In parallel, #218 remains failed at 40/95 report models and 0/80 Tier A/B; official coverage, governed valuation inputs and reviewed sell-side claims remain separate gates.

## 2026-07-25 · E4-S4ah human spot-audit decision store

- 现在在哪里：PR #445 merged. Active owners can append and export identity-bound numeric/page audit decisions; duplicate writes, member access and silent updates are rejected. This is a record path only: no automated or empty record receives audit credit.
- 下一步：#218 remains at 0/20 completed spot audits until an independent reviewer records actual checks. Official evidence coverage (40/95), governed valuation inputs and reviewed sell-side claims remain separate acceptance gates.

## 2026-07-25 · E4-S4ai explicit valuation assumptions

- 现在在哪里：PR #449 merged. The valuation path now rejects omitted/default scenario values: every future assumption receipt must state its author, rationale, source identities, cutoff and complete bear/base/bull parameters.
- 下一步：this is only a governed input contract. #218 gets no valuation, Tier, target or action credit until real analysts author and independently review source-bound assumptions, while official evidence coverage and sell-side review stay separate gates.

## 2026-07-25 · E4-S4aj valuation-assumption store

- 现在在哪里：PR #453 merged. Explicit valuation assumptions can now be owner-authored through append-only storage and exported with their source identity; duplicate receipts are rejected.
- 下一步：the store does not create a real analyst judgment. #218 remains unchanged until real assumptions and review evidence are supplied, alongside its official-coverage, sell-side and spot-audit gates.

## 2026-07-25 · E5-S5a audit assignment read API

- 现在在哪里：PR #458 merged. The future review workstation can request one validated, owner-safe audit assignment without parsing runtime files or exposing raw paths/PDF bytes.
- 下一步：the read API does not make an assignment completed. Claude-owned frontend work in #456 remains required before Park can perform a usable source/page review.

## 2026-07-25 · E5-S5b private-preview audit route access

- 现在在哪里：PR #462 merged. Private preview now explicitly admits the existing owner-only assignment read/export routes; anonymous and member sessions remain rejected, while POST review retains CSRF and append-only guards.
- 下一步：complete Claude-owned #456 against this live allowlist, then verify the owner workbench can load an assignment and preserve failed form submissions without treating any assignment as complete.

## 2026-07-25 · E5-S5 evidence-first spot-audit workstation

- 现在在哪里：PR #464 merged. The private-preview Owner surface can load one signed E4 audit assignment, render numeric/page evidence identity and the raw-document boundary, and submit only a validated append-only decision after the backend accepts it. Browser smoke loaded the real `000001.SZ` assignment without submitting a fabricated review.
- 下一步：perform genuine independent source/page checks for the 20 assigned tickers. #218 remains at 0/20 completed audits until those actual reviewer records exist; the workbench itself adds no Tier, target, position or action credit.

## 2026-07-28 · Official filing coverage and issuer identity

- 现在在哪里：PR #467 merged. CNINFO structured discovery, reusable transport and failed-row replay raised real official-primary partial models from 40 to 100. Current issuer codes are used for document identity; legacy BJ codes remain E1-S1 aliases when official orgId evidence proves a same-market migration. The default gitleaks history gate is green.
- 下一步：perform the existing 20 genuine independent numeric/page audits. Do not treat 100/100 official-primary inputs as Tier A/B, valuation, target, position or a completed equity-research report.

## 2026-07-28 · E4 page-bound facts precede any human audit

- 现在在哪里：PR #476 merged. 宁德时代、贵州茅台和招商银行各有一条真实官方年报营业收入事实，均带同一 PDF 的 document_id、raw SHA-256、一基页码、原文锚点、报告期、合并口径、单位及币种；审计候选已改为“一个数字 + 它所在的一页”，不再把行情报价和年报页错误配对。
- 下一步：#218 仍未通过，且不得安排 reviewer。当前 3 条仅是可审对象和窄 Tier-C/no_action Report Model projection，不产生 numeric/page audit、Tier A/B、目标价、仓位或行动 credit；先扩大真实页级 primary facts，再由 Park 决定是否安排人工核验。

## 2026-07-28 · E4 20-ticker page-bound filing facts

- 现在在哪里：PR #479 merged. 来自现有池的 20 个 SH/SZ/BJ ticker 已形成 23 条官方 PDF 页级事实；每条含 document/raw SHA-256、同页锚点、合并口径、单位与币种，且不使用聚合器补位。市场分布为 SZ 6、SH 10、BJ 4。
- 下一步：#218 仍未达标，也不得邀请 reviewer。本批只补足“20 个可翻页审的 ticker”这一前置对象，未产生人工 audit、Tier A/B、目标价、仓位或 action credit；Park 决定何时开始独立人工核验。

## 2026-07-28 · E4 three vertical slices enter the canonical degradation path

- 现在在哪里：PR #482 merged. 宁德时代、贵州茅台、平安银行均用真实官方页级事实通过 B6（filings primary 1/1）并生成 manifest 对齐、live_eligible 的 C1 合同；现有策略自然输出 Tier B，三家 reasons 均为 `partial_or_missing_sections` 与 action-field block。
- 下一步：三家都只有 1 FULL、1 PARTIAL、16 MISSING；例如决策摘要仍缺市场快照和决策摘要输入。不得把这三家外推至其他 ticker，也不得以此宣称 #218 的 80 家 Tier A/B 门槛有进展；继续补真实章节证据前，不安排 reviewer。

## 2026-07-28 · E4 C1 completion inventory before any 80-ticker expansion

- 现在在哪里：PR #485 merged. 三家 Tier-B 合同逐章盘点确认 1 FULL、1 PARTIAL、16 MISSING；距 Tier A 尚缺 33 项独立 required inputs，其中 17 项有现成模块可接、16 项未建。
- 下一步：C1 v2 当前没有任何 required input 跨章节复用，所谓“输入杠杆”最高仅解锁 1 章。先由 Park 审核这份施工图，再决定补哪些真实能力；不得用机械扩到 80 家 Tier B 替代内容完成度。

## 2026-07-28 · E4 existing-module wiring readback

- 现在在哪里：PR #488 merged. 宁德时代、贵州茅台、平安银行的官方、页级营业收入事实现已接入 C1 的 `revenue_history`；三家均为 1 FULL / 2 PARTIAL / 15 MISSING，新增的只是 `revenue_quality_and_kpis` 从 MISSING 到 PARTIAL，`operating_kpis` 仍明确缺失。模块名不再被视作输入已可用的证据：市场/财务批次属聚合器包，估值、卖方、事件和催化模块均没有三家合格的运行收据。#112 东财 F10 虽结构上可形成 `segment_financials`，但因 `supplementary_only` / `vendor_f10` 不得作为本路径的真实输入。
- 下一步：停止在本票范围内扩展。先为剩余缺口取得真实、ticker-bound、provenance-bound 输出（而非仅接模块 API）；不得用 F10 或其他聚合器把 `business_model` 标成 FULL，也不得因此宣称 #218 的 Tier A/B 门槛有进展。

## 2026-07-29 · AGENTS.md 去重，流程只认 manual.md

- 现在在哪里：治理修订，非产品进展。根 `AGENTS.md` 的 `## Workflow Rules` 不再抄写全局流程，改为一行指向 `~/work/park-operating-system/manual.md`；与 manual.md 直接矛盾的两条（链式叠 PR、执行 PR 须 Park 批准后合并）已删——两条都停在旧版，而 Codex 实际按 manual.md 自行合并。`## Testing Policy` / `## Review Policy` 改挂 manual.md 的 S/M/L 尺度，只保留本仓特有的高风险路径清单。产品边界、数据与密钥边界、UZI 边界均未动。
- 下一步：manual.md 侧的配套修订（完整合同免代笔、REGISTRY 允许攒批更新）在 POS PR #17，属法律层，等 Park 亲合后生效；生效前本仓仍按现行 manual.md 走。另有两条只活在本文件里的全局规则（完工转 Ready、`park-ai-bot` 身份）暂留项目层，是否升进 manual.md 由 Park 定。

## 2026-07-29 · M1–M6 official-fact batch handoff

- 现在在哪里：M1–M6 收敛完成但未达 #218。M2 的 runtime receipt 有 20 ticker、52 份官方报告、951 条页级事实；M3 为 20 份 no-action；M4 仅有 7 份真实可审任务、13 个明确缺口。详见 `docs/evidence/2026-07-29-m1-m6-handoff.md`。
- 下一步：先修复 PDF worker 的硬墙钟隔离并重采集 13 个 M4 缺口；在有 20 个真实页级审计对象前不得邀请 reviewer 或声称 #218 达标。

## 2026-07-29 · M1–M6 recovery addendum

- 现在在哪里：PR #516 / #518 已合并。官方 CNINFO 传输的外层预算不再早于既有重试完成；短原生表格文本不再被空 OCR 回调抹掉。浦发与中石油已由官方直链恢复为页级事实。招行（600036.SH）和华东医药（000963.SZ）仍是明确的 parser/OCR 缺口，不能凑成审计任务。
- 下一步：为这两种已定位 PDF 形态构建页界 OCR/表格解析后，重新生成 20 个不同 ticker 的真实审计任务；在此之前 #218 仍未达标，且不得安排 reviewer。

## 2026-07-29 · M1–M6 final evidence handoff

- 现在在哪里：M4 已重切为 20/20 个不同 ticker 的官方 PDF 页级待审任务（5 条 cross_verified、15 条 unverified、0 条已知 disputed 入队）；M3 重跑产出 20 份 no_action receipt。完整样本、边界与交接见 `docs/evidence/2026-07-29-six-milestone-final-handoff.md`。
- 下一步：由 Park 决定是否把 20 个 pending task 送入现有 owner-only 审计工作台。#218 仍未达标；待审任务、no_action receipt 和页级事实都不等于人工 audit、Tier A/B 或投资建议。

## 2026-07-29 · Cross-page statement context repair

- 现在在哪里：官方 PDF 重放了 1,241 条既有页级事实；870 条以精确同页同值的方式刷新列身份，371 条仍显式 unresolved/invalid。宁德时代季报 p7 的流动负债已正确继承 p5 表头，报告数据时点为 2026Q1，内部矛盾为 0。
- 下一步：剩余 unresolved 必须以原始页片段逐项分类和修复；不得因报告已能显示最新期而降低事实身份或人工审计门槛。

## 2026-07-29 · L2 arbitrary-ticker layer complete

- 现在在哪里：L2-M1~M7 已合并。100 ticker 冻结身份池取得 14,483 条官方页级财务事实和 41,340 条官方页级叙述块；三行业估值 profile、输出降级矩阵、可恢复报告任务及 canonical 读 API 已落地。严格 #218 验收仍 failed：identity 100/100，Report Model 0/95，Tier A/B 0/80，spot audit 0/20。
- 下一步：不得把 L2 identity/财务/叙述收据当作 #218 canonical Report Model。进入 L3 前保留这些明确缺口；后续可观测性、备份、成本和发布工作均不得抬升 Tier 或绕过人工审计。

## 2026-07-29 · L3 reliability layer complete

- 现在在哪里：L3-M1~M10 已合并。可观测性、外部备份/恢复实测、性能/成本收据、回滚演练、三层 cadence、权限/私域交付、trigger/history、结果归因与受控扩张均有可复验边界记录。
- 下一步：生产 Supabase/RLS、slow/periodic 真实运行、纠错 SLA 与成员自助数据权利仍未完成；这些缺口不得被 L3 的本地或私域验收记录覆盖。
