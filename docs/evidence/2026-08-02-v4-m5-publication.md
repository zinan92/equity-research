# V4-M5 · Persistent reader publication

The two official-bound V4 dossiers are compiled through the unified entry
point and rendered into persistent HTML. The index is:

`artifacts/v4-reports/index.html`

The per-company Markdown/HTML files and `publication-receipt.json` sit under
the same directory. The receipt records input/output hashes, source URLs,
reader character counts, and the pending-human-review boundary.

No new model calls or official documents were made. The renderer does not
unlock Tier/action fields and does not touch `product/static/**`.
