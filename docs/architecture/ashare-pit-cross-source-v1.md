# A-Share PIT Cross-Source Validation v1

## Outcome

The CATL data path no longer treats one provider response as sufficient proof.
It resolves a security-master identity, preserves financial revision identity,
cross-checks valuation and recent daily/calendar facts across independent
providers, and anchors adjusted history to official CNINFO corporate-action
implementation announcements.

## Reused components

- A1 canonical `RecordEnvelope` and point-in-time provenance contract.
- A3 `IngestionRuntime`, source manifests, raw captures, quality decisions, and
  authority-sink boundary.
- A4 base packet from PR #79 for Tencent quote/qfq bars and Eastmoney financial
  highlights plus three statements.
- The existing product rule that adjusted series cannot be trusted without a
  corporate-action evidence version.

No parallel database or provider framework is introduced.

## Validation branches

| Fact | Primary | Independent check | Blocking rule |
|---|---|---|---|
| Security identity | Tencent quote | Eastmoney quote | code is validated by each adapter; normalized names must agree |
| Valuation | Tencent PE(TTM)/PB | Eastmoney PE(TTM)/PB | missing metric or relative difference above 10% |
| Recent daily bars | Tencent qfq OHLCV | Sina daily OHLCV | close difference above 0.5% on either of the latest two common dates |
| Trading dates | Tencent last two dates | Sina last two dates | dates must match exactly |
| Financial revision | Eastmoney row | row-content revision identity | every statement record keeps `provider_row_hash`, `revision_id`, and provider update time |
| Corporate action | qfq history requires an anchor | CNINFO implementation-announcement metadata and official PDF URL | no usable official announcement is blocking for the validated adjusted-history packet |

Every secondary provider response is a separate immutable raw capture. The
serialized validation summary retains source URL and raw hash. Provider ticker
identity mismatch fails inside the adapter before a canonical record can leave
it.

## Security master and aliases

The validated packet emits one canonical entry:

- instrument: `CN:300750.SZ`;
- ticker: `300750.SZ`;
- exchange/board from deterministic ticker rules;
- observed company name agreed by Tencent and Eastmoney;
- aliases: code, canonical ticker, provider symbol, instrument ID, and observed
  Chinese name.

An alias only resolves within its validated entry. The implementation does not
ship a hard-coded full-market name dictionary.

## Financial revision semantics

`REPORT_DATE` and `NOTICE_DATE` remain the PIT visibility fields. A provider row
also receives a content-addressed `revision_id`; if the provider changes any
field or update timestamp, a new record identity is produced rather than
overwriting the earlier receipt. The current packet aggregates the latest
capture and exposes all component statement revision IDs used for that report
period. Four component IDs mean four statement families, not four successive
revisions of one statement.

## Truth boundary

This closes the CATL-focused A4 contract and proves live source agreement at the
receipt timestamp. It is not a historical intraday PIT replay, a full-market
alias registry, or an official exchange adjustment-factor series. CNINFO is the
official corporate-action document authority; Tencent/Sina adjusted/recent
price agreement remains a provider cross-check. Production A2 Supabase replay
and broad-market coverage remain subsequent work.
