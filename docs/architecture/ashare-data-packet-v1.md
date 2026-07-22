# A-Share Data Packet v1

## User outcome

Given a supported mainland ticker, the research pipeline receives one typed,
point-in-time packet containing identity, current quote, adjusted daily bars,
financial highlights, balance sheet, income statement, cash flow, source
outcomes, and explicit gaps. Downstream report code does not call providers
directly.

## Flow

```text
ticker
  -> normalize_ashare_ticker
  -> six provider adapters (concurrent)
     -> Tencent quote
     -> Tencent qfq daily bars
     -> Eastmoney financial highlights
     -> Eastmoney balance sheet
     -> Eastmoney income statement
     -> Eastmoney cash flow
  -> L2-A3 IngestionRuntime
     -> immutable RawCapture
     -> canonical RecordEnvelope
     -> quality/publishability decision
     -> authority sink + optional non-authoritative cache
  -> AShareDataPacket
     -> summary/report research context
```

The adapters are glue around the existing ingestion runtime. They do not create
a second data store or bypass the A1 canonical contract and A2 authority sink.

## Identity and ticker policy

- Canonical ticker forms are `600519.SH`, `300750.SZ`, and `8xxxxx.BJ`.
- Common prefix/suffix forms are normalized; conflicting, exchange-mismatched,
  B-share, or ambiguous input raises `AShareTickerError`.
- Canonical instrument identity is `CN:{ticker}`.
- Exchange, board, and provider-observed name are retained. Listing state is
  explicitly `unknown` until a listing-status authority is added.
  Industry remains `null` when the selected identity source does not provide it;
  the adapter does not invent a classification.

## Point-in-time fundamentals

Every fundamental record carries both `report_period` and provider
`NOTICE_DATE` as `announced_at`. The packet includes, where present:

- financial highlights: revenue, parent net profit, growth, margins, ROE,
  leverage, operating cash per share;
- balance sheet: assets, liabilities, equity, cash, receivables, inventory,
  fixed assets;
- income statement: operating income/cost, operating profit, total profit,
  parent and deducted parent profit;
- cash flow: operating, investing, and financing net cash flow plus cash paid
  for long-term assets.

Statement requests are separate captures, so each provider response retains its
own raw hash, source URL, retrieval time, and manifest identity.

## Publication boundary

`AShareDataPacket.publishable` is true only when quote, daily bars, highlights,
balance sheet, income statement, and cash flow all pass the ingestion quality
gate as live data. The packet-level gate additionally requires provider identity,
last/high/low quote fields, at least two complete OHLCV rows, and a latest
report period containing a minimum highlights + three-statement field set.
Fixture and local-cache outcomes remain non-publishable.
Any unavailable required source produces an `AShareDataGap`; missing values are
never filled with sample data.

Each summary source entry retains manifest hash, capture ID, raw hash, source
URL, and `known_at`, so downstream consumers do not lose provenance when they
serialize the typed packet.

This milestone establishes real inputs for supported A-share tickers. It does
not yet claim full-market historical backfill, a production Supabase deployment,
historical intraday PIT replay, or a complete 30–50 page report for every ticker.

## Reuse decisions

- Reuse the product's L2-A3 port/adapter runtime and L2-A1 record contracts.
- Adapt the already-proven Tencent/Eastmoney source choices used by
  `product/real_pipeline.py`.
- Do not copy an external repository or create another provider framework.
