# R7-M1 · Round 7 north-star baseline

Issue: #641

## Outcome

The accepted Round 7 reader contract is now machine-frozen before the report
system is refactored. The north star is the template, five blind-evaluation
samples, NVDA structural replay, external-reader 5/5 receipt, and Park's
explicit Round 7 approval receipt.

The nine reader units are:

1. one-line positioning
2. industry coordinates
3. founder and team
4. development timeline
5. technology, products and business model
6. financials and valuation
7. why it can win
8. core risks
9. plain-language verdict

Production record and Sources remain mandatory publication appendices, rather
than research-completeness sections.

## Evidence

- Accepted structure signature:
  `bb6e0c1399cb75c4433eb0692168dfa90aaaff7ef1b0eb57788b1091ed7e0add`.
- Five blind samples share that signature.
- NVDA source and replay share that signature and the replay receipt records
  `structure_match=true`.
- External-reader receipt records self-produced dossiers winning 5/5.
- Park approval receipt records explicit approval of Round 7 without
  fabricating five Park pairwise choices.
- `artifacts/evidence/round7-north-star-baseline.json` binds the exact samples,
  approvals, quality gates, Tier field permissions, blocked fields, and source
  hashes of the B6/Tier/decision-policy safety boundary.

The existing CATL and Moutai Markdown samples are explicitly classified as
`legacy_product_sample`: they were additional product samples, not members of
the Round 7 blind canonical set, and do not share its structure signature.

## Quality gates for new output

Page citations, numeric traceability, name-swap specificity and concrete
sentences must each remain 100%. Uncited factual sentences, cross-company
leakage and ticker-specific generator branches must remain zero. Each dossier
must contain at least one falsifier and one typed evidence gap. The 4,000–5,500
body-character target is a smoke check only; it cannot make a section FULL.

## Safety boundary

This milestone does not alter the section contract, Tier policy, B6 evidence
gate or decision policy. It freezes their current identities so later
milestones must prove intentional section migration while preserving:

- B6 publishability before section completeness can affect Tier;
- all canonical sections FULL before Tier A;
- `action`, `target_price`, and `position_range` blocked below Tier A;
- unreviewed AI judgment never completing a section.

## Reuse / new-build answer

- Reused: Round 7 template, five blind samples, verifier/replay artifacts,
  preference receipts, and current safety state machine.
- New: one small canonical north-star module, focused tests, and a reproducible
  baseline receipt.
- Why existing output was insufficient: the accepted structure and the legacy
  CATL/Moutai pilot shape were both accepted by the old verifier, so a later
  system could point at the wrong artifact while still claiming “Round 7”.
