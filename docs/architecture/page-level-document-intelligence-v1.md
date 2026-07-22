# Page-Level Document Intelligence v1

## User outcome

Every report claim that reaches publication can jump back to the exact source document and PDF page. A citation with the wrong document ID, page, raw hash, quote, or chunk is blocked together with its claim.

## Reused products

- `pypdf` handles native PDF text extraction.
- Poppler `pdftoppm` rasterizes only pages that lack sufficient native text.
- Tesseract handles local OCR fallback; Chinese plus English is selected when `chi_sim` is installed, otherwise the available English model is used.
- Existing B1/B2 document IDs, PDF raw hashes, and content-addressed storage identities remain authoritative.

No new database or document framework is introduced.

## Canonical chain

`raw PDF -> document -> one-based page -> page-bound chunk -> report citation -> claim publication gate`

Every page and chunk carries:

- document ID
- one-based source page
- source PDF SHA-256
- parser version
- extraction method (`native_text`, `ocr`, or `unreadable`)
- deterministic text/chunk identity

Chunks never cross a page. Re-running the same raw PDF with the same parser version is deterministic; a parser-version change produces a distinct parse identity.

## Quality and failure policy

- Default corpus page-marker accuracy gate: at least 95%.
- Default scanned-page searchable-text coverage gate: at least 90%.
- Sparse/failed OCR pages are `unreadable`; the parser does not invent text.
- Text that looks tabular but lacks verified coordinates is marked `possible_unlocated` and emits a warning.
- Publication is fail-closed per claim: every citation must resolve against document ID, page, and raw hash. Optional quote and chunk locators are also verified when provided.

## Deferred

- automatic investment conclusions
- table-cell coordinate reconstruction
- managed OCR workers and Chinese language-pack deployment
- persistence/query API for the parsed corpus
