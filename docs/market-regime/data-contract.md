# Market Regime Radar · daily OHLC data contract

Status: M1 data authority only. This contract does not produce a market
verdict, recommendation, target price, position size, or trading action.

## Fixed instrument registry

The product has exactly nine primary chart instruments and three visible
evidence probes. Unknown symbols are rejected before any network request.

| Key | Display | Role | Provider symbol | Currency | Session timezone | Price basis |
| --- | --- | --- | --- | --- | --- | --- |
| `sp500` | S&P 500 | chart | `^GSPC` | USD | America/New_York | unadjusted index level |
| `nasdaq` | Nasdaq Composite | chart | `^IXIC` | USD | America/New_York | unadjusted index level |
| `shanghai` | 上证指数 | chart | `sh000001` | CNY | Asia/Shanghai | unadjusted index level |
| `star50` | 科创 50 | chart | `sh000688` | CNY | Asia/Shanghai | unadjusted index level |
| `wti` | WTI 原油 | chart | `CL=F` | USD | America/New_York | provider continuous front month |
| `gold` | 黄金 | chart | `GC=F` | USD | America/New_York | provider continuous front month |
| `silver` | 白银 | chart | `SI=F` | USD | America/New_York | provider continuous front month |
| `kospi` | KOSPI | chart | `^KS11` | KRW | Asia/Seoul | unadjusted index level |
| `nikkei` | Nikkei 225 | chart | `^N225` | JPY | Asia/Tokyo | unadjusted index level |
| `vix` | VIX | evidence | `^VIX` | USD | America/Chicago | unadjusted index level |
| `china_dividend` | 上证红利 | evidence | `sh000015` | CNY | Asia/Shanghai | unadjusted index level |
| `us_dividend` | SCHD | evidence | `SCHD` | USD | America/New_York | unadjusted ETF trade price |

WTI, gold, and silver use the provider's rolling continuous-future history;
they are not a frozen exchange contract series and must be labelled as such.

## Acceptance and failure policy

Every source attempt records method, requested/final URL, redirects, status,
safe response headers, declared Content-Type, byte length, SHA-256, fetch time,
and the runtime raw-capture path. Full raw bodies and run state stay under the
gitignored runtime root.

For Yahoo instruments the collector tries `query2.finance.yahoo.com` first and
then `query1.finance.yahoo.com` for the same symbol, interval and completed
session. These are endpoint retries for one unchanged instrument identity, not
semantic proxy substitution. The accepted artifact records the selected
endpoint and every rejected/accepted attempt. A non-Yahoo provider has only the
candidate explicitly declared by its provider contract; it is never silently
replaced by a different index or adjusted series.

The normalizer requires strictly ascending, unique ISO dates; complete and
finite OHLC; valid high/low containment; the expected response symbol and
currency; at least 120 completed daily bars; and a completed local-market
session. An all-null Yahoo holiday row is dropped and counted. A partially
null row is rejected. An in-progress current-session row is excluded and
listed in `dropped_unfinished_sessions`.

Tencent's K-line endpoint currently declares `text/html` while returning a
JSON object. The exception is source-specific: it is accepted only for the
fixed Tencent provider, only when the body starts as JSON, and only after JSON
parsing plus the expected symbol/row contract pass. The snapshot records
`provider_declares_text_html_for_json`. The same MIME from Yahoo or an HTML
error page remains a hard failure. The request explicitly leaves the
adjustment argument empty and accepts only `day`; a returned `qfqday` series is
rejected rather than mislabeled as an unadjusted index level.

Every accepted asset first writes an immutable normalized artifact. Its path
and SHA-256 are bound into the immutable completion receipt. Only after that
receipt exists does the product atomically advance `latest-good.json`; a crash
can therefore leave an unreferenced artifact, but never an unreceipted good
pointer. A rejected attempt never overwrites the pointer. If all same-day
candidates fail, the current snapshot contains an explicit
`quality=unavailable` item with the attempt receipt and no normalized-artifact
reference. The older `latest-good.json` remains historical recovery only and is
never projected into that current snapshot. A successful alternate endpoint
therefore keeps the current item accepted; only exhaustion produces an
unavailable slot.

Freshness uses provider session evidence, not elapsed wall time alone. Yahoo's
`regularMarketTime` and current regular-session end, or Tencent's quote
timestamp, must confirm whether a newer session should have completed. A
completed expected session without a daily bar is `partial`; a provider that
has been silent beyond the bounded source-retry window becomes `stale`.

## License gate

Yahoo Chart and Tencent K-line are classified `supplementary_only`, not
official exchange feeds and not verified commercial data. The default
`local_evaluation_only` mode is usable only in Park's local prototype and
always sets `publication_eligible=false`.

Private-beta and public modes remain disabled in M1, including when an operator
sets `commercial_rights_approved`: an arbitrary string is not a rights receipt.
The status/reference pair is retained only as an operator attestation and never
sets `publication_eligible=true`. A future deployment must verify a
provider/scope/deployment-bound external approval receipt before this gate can
change. This is not a legal opinion.

## One-shot local refresh

```bash
python3 scripts/refresh_market_regime_data.py \
  --deployment-mode local_prototype \
  --license-status local_evaluation_only
```

The default runtime root is `product/runtime/market-regime/`. It is ignored by
Git. M3 will own the independent 4h/12h scheduler; importing this module has no
network or scheduling side effect.
