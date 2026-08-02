# V4-M5 · Persistent reader publication (superseded by V4-P1 gate)

The publication directory is persistent, but it is fail-closed: the canonical
Round 7 receipts for 000001.SZ, 300750.SZ and 600519.SH are evaluated by
`product/v4_quality_gate.py` and held in `review-queue.json`. The current
publication status is `blocked`, and the index is intentionally empty (zero
company/mobile links):

`artifacts/v4-reports/index.html`

`publication-receipt.json`, `review-queue.json` and the per-ticker quality-gate
receipts sit under the same directory. The receipts record canonical source
paths, run IDs, file hashes and blocker details. Historical mapped company
directories were moved to `artifacts/v4-reports-legacy/` as failure samples;
they are not inside or linked by the publication output.

No new model calls or official documents were made. Passing the reader
structure alone does not unlock Tier/action fields; human review and the
independent evidence gate are still required. The change does not touch
`product/static/**`.
