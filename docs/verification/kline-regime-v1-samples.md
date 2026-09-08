# kline-regime-v1 live validation

- Captured: 2026-09-08 Asia/Shanghai.
- Source: read-only `GET` from `http://127.0.0.1:8100`; `cache_policy=bypass`, `quality=strict`, `fallback_policy=none`.
- Watchlist: 16 shared assets; each row was fetched at both `1d` and `4h`.
- `unavailable` is a source observation, not a fallback or synthetic result.

| Asset | 1d bars | 4h bars | Regime | Range | Confidence | as_of | Schema | Reason |
|---|---:|---:|---|---|---:|---|---|---|
| UUP | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 502 upstream_error: No complete 4H buckets returned for UUP |
| SPY | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_etf does not serve SPY at 4h |
| QQQ | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_etf does not serve QQQ at 4h |
| SCHD | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_etf does not serve SCHD at 4h |
| ^VIX | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve ^VIX at 4h |
| BTC | 600 | 600 | trend_up | 76108.8–80900.6 | 0.818484139209 | 2026-09-08T00:00:00+00:00 | PASS | — |
| ETH | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source binance_spot_public does not serve ETH at 4h |
| HYPE | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source binance_spot_public does not serve HYPE at 4h |
| sh000001 | — | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 1d: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve sh000001 at 1d; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve sh000001 at 4h |
| sh000688 | — | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 1d: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve sh000688 at 1d; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve sh000688 at 4h |
| sh000015 | — | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 1d: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve sh000015 at 1d; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve sh000015 at 4h |
| ^N225 | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve ^N225 at 4h |
| ^KS11 | 600 | — | unavailable | — | 0.0 | — | PASS | 8100 source unavailable; 4h: HTTP 400 timeframe_not_supported: Source yahoo_finance_index does not serve ^KS11 at 4h |
| CL=F | 600 | 523 | trend_up | 80.698–91.21 | 1.0 | 2026-09-07 | PASS | — |
| GC=F | 600 | 520 | range | 4330.38–4617.06 | 0.704013870866 | 2026-09-07 | PASS | — |
| SI=F | 600 | 522 | range | 64.598–69.3658 | 0.911924948529 | 2026-09-07 | PASS | — |

## Unavailable source evidence

The following complete HTTP response bodies were captured from the corresponding read-only requests:

### `UUP`

- `4h` URL: `http://127.0.0.1:8100/api/candles/etf/UUP?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"upstream_error","detail":"No complete 4H buckets returned for UUP","suggestions":[],"provider":"yahoo_finance","source_mode":"yahoo_finance_etf","provider_symbol":"UUP","timeframe":"4h","raw_timeframe":"1h","timeframe_origin":"aggregated","aggregation":{"kind":"ohlc_resample","rule":"fixed_4h","input_timeframe":"1h","bucket_timezone":"UTC","anchor_hour":0,"anchor_minute":0},"source_identity":{"provider_symbol":"UUP","repair_policy":"yfinance_repair_on_invalid_ohlc","repair_attempted":false,"repaired_row_count":0,"repaired_timestamps":[],"quality_flags":[],"exclusion_applied":false,"excluded_row_count":0,"excluded_timestamps":[],"excluded_rows":[],"provider":"yahoo_finance","source_mode":"yahoo_finance_etf","timeframe":"4h","raw_timeframe":"1h","timeframe_origin":"aggregated","aggregation":{"kind":"ohlc_resample","rule":"fixed_4h","input_timeframe":"1h","bucket_timezone":"UTC","anchor_hour":0,"anchor_minute":0},"served_from":"legacy_upstream","query_served_from":"legacy_upstream","market_data_miss_reason":"timeframe_not_persisted"},"requested_source":"auto","selected_source":"yahoo_finance_etf","attempted_sources":["yahoo_finance_etf"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"upstream_error","access_issues":["yahoo_finance_etf: No complete 4H buckets returned for UUP"]}}
```

### `SPY`

- `4h` URL: `http://127.0.0.1:8100/api/candles/etf/SPY?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_etf does not serve SPY at 4h","suggestions":["Supported timeframes for SPY: 1d, 1w"],"provider":"yahoo_finance","source_mode":"yahoo_finance_etf","provider_symbol":"SPY","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"SPY","provider":"yahoo_finance","source_mode":"yahoo_finance_etf","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_etf","attempted_sources":["yahoo_finance_etf"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: SPY/4h"]}}
```

### `QQQ`

- `4h` URL: `http://127.0.0.1:8100/api/candles/etf/QQQ?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_etf does not serve QQQ at 4h","suggestions":["Supported timeframes for QQQ: 1d, 1w"],"provider":"yahoo_finance","source_mode":"yahoo_finance_etf","provider_symbol":"QQQ","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"QQQ","provider":"yahoo_finance","source_mode":"yahoo_finance_etf","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_etf","attempted_sources":["yahoo_finance_etf"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: QQQ/4h"]}}
```

### `SCHD`

- `4h` URL: `http://127.0.0.1:8100/api/candles/etf/SCHD?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_etf does not serve SCHD at 4h","suggestions":["Supported timeframes for SCHD: 1d, 1w"],"provider":"yahoo_finance","source_mode":"yahoo_finance_etf","provider_symbol":"SCHD","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"SCHD","provider":"yahoo_finance","source_mode":"yahoo_finance_etf","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_etf","attempted_sources":["yahoo_finance_etf"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: SCHD/4h"]}}
```

### `^VIX`

- `4h` URL: `http://127.0.0.1:8100/api/candles/index/%5EVIX?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve ^VIX at 4h","suggestions":["Supported timeframes for ^VIX: 1d, 1w"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"^VIX","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"^VIX","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: ^VIX/4h"]}}
```

### `ETH`

- `4h` URL: `http://127.0.0.1:8100/api/candles/crypto/ETH?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source binance_spot_public does not serve ETH at 4h","suggestions":["Supported timeframes for ETH: none"],"provider":"binance_spot","source_mode":"binance_spot_public","provider_symbol":"ETH","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"ETH","provider":"binance_spot","source_mode":"binance_spot_public","timeframe":"4h"},"requested_source":"auto","selected_source":"binance_spot_public","attempted_sources":["binance_spot_public"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["public_api","spot","research_only","not_execution_venue"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: ETH/4h"]}}
```

### `HYPE`

- `4h` URL: `http://127.0.0.1:8100/api/candles/crypto/HYPE?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source binance_spot_public does not serve HYPE at 4h","suggestions":["Supported timeframes for HYPE: none"],"provider":"binance_spot","source_mode":"binance_spot_public","provider_symbol":"HYPE","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"HYPE","provider":"binance_spot","source_mode":"binance_spot_public","timeframe":"4h"},"requested_source":"auto","selected_source":"binance_spot_public","attempted_sources":["binance_spot_public"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["public_api","spot","research_only","not_execution_venue"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: HYPE/4h"]}}
```

### `sh000001`

- `1d` URL: `http://127.0.0.1:8100/api/candles/index/sh000001?timeframe=1d&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve sh000001 at 1d","suggestions":["Supported timeframes for sh000001: none"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"sh000001","timeframe":"1d","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"sh000001","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"1d"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: sh000001/1d"]}}
```
- `4h` URL: `http://127.0.0.1:8100/api/candles/index/sh000001?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve sh000001 at 4h","suggestions":["Supported timeframes for sh000001: none"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"sh000001","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"sh000001","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: sh000001/4h"]}}
```

### `sh000688`

- `1d` URL: `http://127.0.0.1:8100/api/candles/index/sh000688?timeframe=1d&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve sh000688 at 1d","suggestions":["Supported timeframes for sh000688: none"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"sh000688","timeframe":"1d","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"sh000688","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"1d"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: sh000688/1d"]}}
```
- `4h` URL: `http://127.0.0.1:8100/api/candles/index/sh000688?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve sh000688 at 4h","suggestions":["Supported timeframes for sh000688: none"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"sh000688","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"sh000688","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: sh000688/4h"]}}
```

### `sh000015`

- `1d` URL: `http://127.0.0.1:8100/api/candles/index/sh000015?timeframe=1d&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve sh000015 at 1d","suggestions":["Supported timeframes for sh000015: none"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"sh000015","timeframe":"1d","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"sh000015","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"1d"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: sh000015/1d"]}}
```
- `4h` URL: `http://127.0.0.1:8100/api/candles/index/sh000015?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve sh000015 at 4h","suggestions":["Supported timeframes for sh000015: none"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"sh000015","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"sh000015","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: sh000015/4h"]}}
```

### `^N225`

- `4h` URL: `http://127.0.0.1:8100/api/candles/index/%5EN225?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve ^N225 at 4h","suggestions":["Supported timeframes for ^N225: 1d, 1w"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"^N225","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"^N225","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: ^N225/4h"]}}
```

### `^KS11`

- `4h` URL: `http://127.0.0.1:8100/api/candles/index/%5EKS11?timeframe=4h&limit=600&cache_policy=bypass&quality=strict&fallback_policy=none`

```json
{"detail":{"error":"timeframe_not_supported","detail":"Source yahoo_finance_index does not serve ^KS11 at 4h","suggestions":["Supported timeframes for ^KS11: 1d, 1w"],"provider":"yahoo_finance","source_mode":"yahoo_finance_index","provider_symbol":"^KS11","timeframe":"4h","raw_timeframe":null,"timeframe_origin":null,"aggregation":{},"source_identity":{"provider_symbol":"^KS11","provider":"yahoo_finance","source_mode":"yahoo_finance_index","timeframe":"4h"},"requested_source":"auto","selected_source":"yahoo_finance_index","attempted_sources":["yahoo_finance_index"],"cache_policy":"bypass","quality_policy":"strict","fallback_policy":"none","require_execution_venue":false,"served_from":"upstream","is_synthetic":false,"fresh":null,"latest_timestamp":null,"age_seconds":null,"max_age_seconds":null,"quality_flags":["delayed_possible","market_hours","research_only"],"execution_venue":false,"reject_reason":"timeframe_not_supported","access_issues":["unsupported symbol/timeframe: ^KS11/4h"]}}
```
