# K-line World Context v1 · OHLC and relative-tape contract

Tracking: Issue #761. Parent: #758. Approved predecessor: #759 / PR #760.

## Outcome

Produce one immutable, replayable provider input containing the completed-daily
market tape required by the Global Market K-line Daily v2 world model. This
layer calculates facts and relationships only; it does not call an LLM, infer
capital flows or recommend trades.

## Fixed universe and roles

The context contains exactly 17 series in registry order:

1. S&P 500, Nasdaq Composite, Shanghai Composite, STAR 50, Nikkei 225 and KOSPI;
2. US Dividend ETF and SSE Dividend, which are canonical style inputs and must
   no longer remain hidden from the eventual reader;
3. WTI, gold and silver;
4. Bitcoin, explicitly labelled `supplemental` rather than silently entering
   the canonical deterministic dimensions;
5. VIX and DXY; and
6. US2Y, US10Y and 2s10s.

The 16 existing daily/macro evidence slots remain canonical. Bitcoin is the one
supplemental series. This contract does not change either upstream schema.

## History and feature semantics

- Price/index/commodity/ETF/Bitcoin/DXY series freeze the latest 120 accepted
  completed-daily OHLC rows and retain volume when supplied.
- US2Y and US10Y freeze 120 rate levels in percent. 2s10s freezes 120 spread
  levels in basis points. Their 5/20/60-session changes are basis points, never
  price returns.
- Price series expose deterministic 5/20/60-session returns, distance from
  MA20/MA60, 120-session drawdown, 20-session realized volatility and a bounded
  60-session direction label.
- Rate series expose 5/20/60-session bp changes, distance from the 120-session
  high/low in bp and a bounded 60-session direction label.

All calculations are identity-bound. The later LLM may explain them but cannot
replace their values.

## Relative relationship registry

The fixed registry compares:

- US growth vs US broad market;
- A-share technology vs A-share broad market;
- US dividend vs US growth;
- A-share dividend vs A-share technology;
- Korea vs Japan;
- US vs Japan and US vs China;
- equities vs gold;
- gold vs oil and silver vs gold;
- Bitcoin vs US equities; and
- dollar vs gold.

Rows align by common completed-session date. Each side is normalized to 100 at
the first aligned row, then the context stores a relative-performance index and
its 5/20/60-session percentage changes. The declared semantics are
`normalized_relative_performance_not_literal_fund_flow`.

## Identity, quality and publication

The context identity binds:

- exact daily run, macro run, S3 pack and Bitcoin identities;
- series registry/order, source artifact hashes, sessions, quality and units;
- all 120 points and deterministic features;
- pair registry/order, aligned points and relationship features; and
- the local-only, advice-allowed but no-auto-execution truth boundary.

The store writes the immutable context artifact, then its immutable completion
receipt, then atomically advances `latest.json`. A failed validation or write
does not advance the prior pointer. Hash/path/identity mismatch fails closed.
Content hashes prove internal integrity, not authenticity against a coherent
rewrite of every source and state object.

Real publication rejects fixture or unknown source kinds. Tests may opt into
fixture compilation explicitly but cannot publish their output as a real
runtime report. Stale/partial accepted inputs keep their declared quality and
degrade the overall context; unavailable or short-history inputs fail the new
context and preserve last-good.

## LLM projection

The stored context exposes one exact size-bounded provider projection. It keeps
the series/relationship identities, points, features, timing, deterministic
dimensions, contradictions and truth boundary. It omits raw paths, source
receipts and other storage metadata. It contains no Finance Daily Newsletter
input or generated prose.

## Boundaries

- No LLM call, prose, flow inference or advice in this layer.
- No changes to existing S3/S4 identity or the installed K-line Newsletter.
- No direct-fund-flow claim from relative price behavior.
- No public redistribution, broker call, order or portfolio mutation.
