# V4-M4 · Whole-dossier generator and field-path retirement

The V4 production-facing entry point is now `scripts/generate_v4_dossier.py`,
backed by `product/v4_dossier_generator.py:generate_v4_dossier`. It accepts a
complete Markdown dossier plus an evidence manifest, or the deterministic
official-source adapter inputs used by M3, then validates and writes one V4
document and receipt.

The old field-shaped judgment material is quarantined as historical evidence;
the V4 entry point does not import or call it. Existing Round 7/e4 receipts are
preserved for audit history, but no longer define the V4 writer path.

Receipt: `docs/evidence/v4-m4-generator-retirement.json`.

This milestone changes no Tier ladder, blocked-field semantics, B6 evidence
gate, or decision policy. It makes no model calls and does not claim live
research.
