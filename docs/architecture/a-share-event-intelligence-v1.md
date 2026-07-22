# A-Share News & Event Intelligence v1

## User outcome

For a supported A-share ticker, the product can discover material news from several source types, group duplicate coverage into one event, and show exactly which source coverage is missing. News remains evidence; model interpretation remains a separately versioned inference.

## Reused building blocks

- `zinan92/intel`: source registry/collector boundary, RSS, Google News, Yahoo Finance and webpage-monitor collection patterns, plus source-status degradation and 48-hour event grouping.
- Park A3 ingestion core: immutable raw capture, `SourceManifest`, canonical event records, quality gates and authority-sink boundary.
- Park A4 security master: canonical A-share ticker, instrument identity, company name and aliases.

Only the collector interface and event-topology patterns are adapted. Intel's SQLite authority, gold/US ticker aliases, general tech feeds, delivery credentials and trading-opinion prompts are not imported.

## Flow

1. Configure an `IntelSourceSpec` for RSS, Google News, Yahoo Finance or an official-site monitor.
2. Wrap its collector with `IntelCollectorAdapter`, producing an EVENT-scoped `SourceManifest` and immutable raw batch.
3. Resolve every article against the A-share security master using source tickers, six-digit codes, names and explicit aliases; ambiguous aliases fail closed.
4. Store normalized article evidence with canonical URL, timestamps, source identity and raw hash. Tracking parameters are removed.
5. Group same-ticker, similar-title observations inside a 48-hour window; retain every evidence ID and distinct source key.
6. Attach analysis only through `InferenceEnvelope`, which requires provider, model, prompt ID, prompt version, generation time and evidence IDs.
7. Return one `CoverageGap` for every configured source that times out, fails or produces no publishable A-share evidence.

## Trust boundary

All discovery feeds are `supplementary_only`. An official-site monitor must remain on its configured host, but discovering a page still does not upgrade a news item into an official fact. Official claims must continue through B1 filing/document evidence and page-level citation gates.

## Deliberately deferred

- Production source configuration, scheduler and full-market backfill
- Social-media sentiment or trading actions
- Automated materiality scoring and portfolio impact
- LLM synthesis beyond the versioned inference envelope
