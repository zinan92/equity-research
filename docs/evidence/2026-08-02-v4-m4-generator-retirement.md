# V4-M4 · Whole-dossier generator and field-path retirement

**Historical note (superseded by the canonical Round 7 publication gate):**
the earlier M4 text described a complete Markdown/evidence-manifest and
official-sample adapter route. Those inputs are now explicitly retired; the
only production packaging route is a canonical Round 7 receipt/Markdown/profile
validated by `v4_quality_gate`.

The V4 production-facing packaging entry point is
`scripts/publish_v4_round7_dossier.py`, backed by
`product/v4_quality_gate.py:evaluate_round7_quality`. The whole-dossier
generator accepts only canonical Round 7 receipt/Markdown/profile inputs and
refuses to write a package unless that gate is already `passed`.

The old field-shaped judgment material is quarantined as historical evidence;
the V4 entry point does not import or call it. Existing Round 7/e4 receipts are
preserved for audit history, but no longer define the V4 writer path.

The old seven-section mapper and official-sample regrouping remain review-only
failure samples. Receipt: `docs/evidence/v4-m4-generator-retirement.json`.

This milestone changes no Tier ladder, blocked-field semantics, B6 evidence
gate, or decision policy. It makes no model calls and does not claim live
research.
