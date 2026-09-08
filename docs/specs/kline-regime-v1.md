# `kline-regime-v1`

## Purpose and boundary

This is a deterministic, research-only classification contract. It accepts
fixed-length, already-closed 1d and 4h OHLC bars from Datafeed 8100 and emits
a machine-readable regime. It does not place, recommend, size, or control an
order; `action_eligible` is always `false`.

The CLI is read-only and uses only `GET
http://127.0.0.1:8100/api/candles/commodity/{ticker}` with
`cache_policy=bypass`, `quality=strict`, and `fallback_policy=none`. `XAU` is
mapped to the 8100 alias `GOLD`. No other source or fallback is used.

## Input gate

The calculation requires at least 20 1d bars and 30 4h bars and uses the most
recent fixed windows. A bar is forming when `is_forming=true`, `forming=true`,
`status` is `forming` or `open`, or `quality_flags` contains `forming`. Any
forming bar, insufficient history, or malformed OHLC value returns
`regime=unavailable` with a non-empty `reason`.

## Deterministic formula

For each timeframe, fit the ordinary least-squares slope of `ln(close)` over
the bar index. Normalize it as `slope * window_length / ATR14 / mean(close14)`.
The final score is `0.7 * score_1d + 0.3 * score_4h`.

- `trend_up` when score >= 0.35; `trend_down` when score <= -0.35.
- Otherwise the result is `range`.
- Trend confidence is `min(1, abs(score) / 1.5)`.
- Range confidence is `1 - abs(score) / 0.35`, clipped to [0, 1].
- `range_low` and `range_high` are the linear-interpolated 20th percentile
  of the last 20 daily lows and 80th percentile of the last 20 daily highs.

`inputs_digest` is SHA-256 of canonical JSON for the supplied 1d and 4h
arrays (`sort_keys=true`, compact separators). `as_of` is the lexicographically
latest timestamp in the used windows. JSON output uses sorted keys and compact
separators, so identical inputs produce byte-identical output.

## CLI

```bash
python3 -m product.kline_regime XAU --from-8100
```

The JSON Schema beside the implementation is the v1 validator contract.
