# R7-M2 · Nine-section contract evidence

Issue: https://github.com/zinan92/equity-research/issues/644

## Outcome

C1 now uses the nine Round 7 reader units directly. The old 18-section
identifiers and v2 builder are absent from executable product and script code.
The old contract document is a tombstone pointing to Git history.

The contract target is 4,200–5,500 Chinese characters. Production record and
Sources are publication appendices and do not count toward Tier.

## New versus reused

New:

- nine chapter specs, required inputs, annual-report origins and character
  targets;
- v3 contract builder and verifier;
- direct-consumer migration inventory and machine receipt.

Reused:

- `ResearchSectionContract`, `ResearchSectionSpec`, hashing and type checks;
- the B6 evidence-set boundary;
- `research_degradation.assess_any_ticker`;
- `_TIER_ALLOWED` and `_BLOCKED_FIELDS`;
- existing official page-fact, R2 industry, governance and decision receipts.

The existing 18-section artifact could not be retained as the production
contract because its unit of delivery is a fragmented field rather than a
reader chapter. It remains in Git history only. The existing field-generated
judgments are not discarded yet, but are downgraded to optional legacy chapter
materials; they cannot satisfy `chapter_draft` and will leave the runtime path
in R7-M4.

## Direct consumers migrated

1. `product/report_contract.py`
2. `product/data_core/e4_vertical_degradation.py`
3. `product/data_core/e4_r2_industry_wiring.py`
4. `product/data_core/e4_judgment_wiring.py`
5. `product/data_core/e4_judgment_review_queue.py`
6. `scripts/run_e4_m2_research_wiring.py`
7. `scripts/build_e4_l1_m5_reassessment.py`
8. `scripts/inventory_e4_section_completion.py`
9. `scripts/compile_e4_m4_report.py`
10. `scripts/verify_e4_wired_reports.py`
11. `product/data_core/research_degradation.py` (generic interface; source
    unchanged)
12. Contract, Tier, wiring, renderer, inventory and queue tests.

The separate public report-v1 surface is explicitly deferred to R7-M6; it did
not consume C1 section identifiers and is not silently represented as migrated.

## Safety proof

Frozen source hashes remain:

- `research_degradation.py`:
  `98fc7820019a9f10b91d4533c17de38f4db9b178e3d33c1e5ed57ce98890fed1`
- `evidence_gate.py`:
  `bddf93d9268633532efce4ba3ae9b5069217f08ba5d8353e846bf452ef28e805`
- `decision_policy.py`:
  `34ace569be831712af1bd1c3cf7bdd42ba2c63a6e3b19935c29058a02e28f4b9`

The verifier proves:

- a reviewed all-nine-FULL contract still reaches Tier A;
- one unreviewed chapter becomes PARTIAL with
  `pending_judgment_review`, produces Tier B, and blocks `action`,
  `target_price`, and `position_range`;
- a chapter with no explicit review identity, no complete text, or no page-level
  evidence binding is rejected instead of defaulting to FULL;
- a retired section ID is rejected;
- the B6 live-evidence boundary remains active.

Receipt:
`artifacts/evidence/round7-m2-section-contract-verification.json`

Receipt hash:
`3a68bbd47c65d2d9198797fba296e3b0ef7fbbf0a43635ff4c6c20dd6782bc3f`

## Persistent report reassessment

The committed CATL and Moutai report receipts were reassessed under v3; the
18-section statuses were not copied. The migration carries forward only
committed page facts, receipt-valid legacy judgment material, and CATL's
committed governance receipt. Market/decision and R2 inputs that existed only
as old assessment hashes are typed as not carried forward.

- migration receipt:
  `artifacts/e4-reports/e4-m4-model-wiring.json`
- migration receipt hash:
  `6a84b44ec9b4af714ca2902a19ff24c15a7ba1073fab90124e175cfcc8b60381`
- CATL: 0 FULL / 6 PARTIAL / 3 MISSING, Tier B
- Moutai: 0 FULL / 5 PARTIAL / 4 MISSING, Tier B
- current report verification:
  `artifacts/e4-reports/e4-m4-wired-report-verification.json`
  (`round7-wired-report-verification-v1`, passed)

The report verifier independently validates the migration receipt hash, binds
each report's `input_hashes.m2` to that exact wiring object, and requires the
report section array to equal the matching ticker's reassessed section array.
The migration itself accepts only the pinned parent file SHA
`db27e157a0a2e3d50c43846940dfd81beea589c7869cbac16084f40e2c2bbca9`,
recomputes its legacy receipt hash, and rejects non-official filing URLs.

These HTML files are explicitly
`transitional_evidence_status_not_round7_chapter_dossier`. They prove the
contract and renderer no longer disagree; they are not the complete Round 7
chapter dossiers promised by R7-M3 and R7-M5.

## Validation

- `python3 -m unittest discover -s product/tests -q`
  - 647 passed, 1 skipped.
- `python3 scripts/verify_round7_north_star.py --out <runtime path>`
  - passed; receipt hash unchanged at
    `38222aebba14738d1f66dc33b828acb4dfc02e4d17a391e7e9806401a1f43f5a`.
- `python3 scripts/verify_round7_section_contract.py --out artifacts/evidence/round7-m2-section-contract-verification.json`
  - passed.
