# Round 7 M4 — legacy field pipeline retirement

The obsolete E4 field-based judgment path is retired. Removed production code
and directly dependent runners/verifiers/tests include `e4_model_judgments`,
`e4_judgment_wiring`, `e4_judgment_review_queue`, the E4 wiring/queue/compile
scripts, and their unit tests. No current production module imports those
paths; `scripts/run_round7_dossier.py` is now the sole AI dossier generation
entry point.

Historical evidence notes and prior receipts remain for audit history and are
not treated as current production inputs. The exact-nine C1 contract, evidence
gate, Tier ladder, blocked fields, and decision policy were not changed.

The issuer narrative extraction helper keeps its official-PDF receipt
validation locally so that narrative capture does not depend on the retired
judgment generator.
