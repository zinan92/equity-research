# Sell-Side Report Catalog & PDF Archive v1

## User outcome

For an A-share ticker, the product can enumerate the sell-side reports supporting a conclusion and distinguish an archived source PDF from a metadata-only catalog entry.

## Reused building blocks

- `simonlin1212/a-stock-data`: Eastmoney catalog contract, PDF URL convention, serialized request pacing, and retry pattern.
- `HKUDS/Vibe-Trading`: normalized broker, analyst, publication date, rating, and valuation-metadata concepts.
- Existing Park A2/A3: content-addressed raw storage identity, immutable fetch receipts, adapter registry, quality gate, and authority sink.

The repos supply source-specific patterns only. Park keeps its existing canonical ingestion/storage architecture and adds a thin adapter and archive orchestrator.

## Flow

1. Page through Eastmoney's ticker-scoped report catalog within an explicit date window.
2. Normalize report ID, title, broker, analyst, publication date, rating, page count, and canonical PDF URL.
3. Skip known report IDs or canonical URLs before fetching a PDF.
4. Fetch remaining PDFs through the configurable serialized rate-limit/retry transport.
5. Validate PDF bytes and preserve raw hash plus content-addressed storage URI.
6. Deduplicate identical PDF bytes by SHA-256.
7. Return every catalog record as `archived_pdf`, `duplicate_url`, `duplicate_sha`, or `metadata_only`.

## Failure boundary

A missing, blocked, or invalid PDF does not erase its catalog metadata and does not stop other reports. It becomes `metadata_only` with an error. Sell-side evidence remains supplementary and cannot claim an official-primary role.

## Deliberately deferred

- PDF OCR and table extraction
- viewpoint synthesis or consensus calculation
- a production scheduler and full-market SLA
- licensing expansion beyond internal research use
