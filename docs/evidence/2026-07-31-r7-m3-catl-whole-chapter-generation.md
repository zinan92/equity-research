# Round 7 M3 — CATL whole-chapter dossier

## Outcome

CATL (`300750.SZ`) now has a persistent Round 7 dossier at
`artifacts/round7-dossiers/300750.SZ.md` and `.html`. The verifier receipt is
`artifacts/evidence/round7-m3-catl-verification.json`.

- Run: `round7-run:03ab66a964f60a6d47300c97`
- Receipt hash: `a4848db654be998a8475f30daaf4867ee9f806145986467584df087cd05df8cd`
- Structure signature: `1c25130d38341372cbd96308c57e48553175764178e2e38c6ac645852f975ea5`
- Generated research text: 5,146 characters; chapter body: 8,993; full file: 12,401.
- Eight research chapters were generated one chapter per real `call_structured_deepseek` run; all are `partial / pending_judgment_review`. The production record is `full`.
- Tier remains B with `target_price`, `position_range`, and `action` blocked.

## Reused versus new

Reused: the existing `call_structured_deepseek` transport, Round 7 north-star
layout and structure signature, C1 exact-nine section contract, immutable
official narrative receipt, page-level financial evidence materializer, B6
evidence gate, research-degradation tiering, decision policy, and the existing
fact/judgment safety rules. The official narrative receipt and financial page
evidence are referenced by their receipt hashes in the dossier receipt; no
aggregator, fixture, archive, or proxy fact was added.

New: `round7_chapter_generator.py` (whole-chapter row generation and
deterministic normalization/audit), `run_round7_dossier.py` (checkpointed
runner), `verify_round7_generated_dossier.py` (replay verifier), and the
focused generator tests. The conclusion input is compacted to the first eight
high-signal evidence items to stay inside the provider's structured-response
envelope; this does not alter source identity or page bindings.

The former field/paragraph path was not reused because it emitted the wrong
shape, failed the canonical Round 7 structure signature, and conflated
chapter-boundary text with research text. Those outputs remain only as local
historical artifacts until the M4 retirement removes the obsolete path.

## Evidence and rejection trail

The final receipt contains the accepted model request IDs, rejected attempts,
semantic-auditor receipts, exact evidence IDs, document IDs, pages, anchors,
raw hashes, and source URLs. The final verifier replayed all eight chapters,
the exact structure signature, page bindings, action-safety grammar, section
status semantics, Tier B policy, and production counts with zero problems.

