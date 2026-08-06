# Market Regime Radar · deterministic model contract

Status: M2 analysis only. Model version: `market-regime-model-v1`.

This compiler reads M1 immutable normalized artifacts and writes a separate,
immutable analysis artifact. It does not fetch data, call an LLM, publish a
report, recommend a position, or place an order.

## Per-asset feature

Each usable asset needs at least 80 accepted closes (M1 normally supplies at
least 120). The feature receipt contains:

- 1d / 5d / 20d / 60d returns;
- MA20 and MA60;
- 20d and 60d annualized realized volatility;
- a bounded trend score from -100 to +100;
- the last completed session and normalized artifact SHA-256.

The trend score is deterministic:

```text
30 × tanh(5d return / 20d-vol scaled 5d)
+ 35 × tanh(20d return / 60d-vol scaled 20d)
+ 20 × tanh((close / MA20 - 1) / 20d-vol scaled 20d)
+ 15 × tanh((MA20 / MA60 - 1) / 60d-vol scaled 20d)
```

Daily volatility has a 0.3% floor to stop a flat/short fixture from creating
an infinite standardized signal. Scores are explanatory state, not expected
returns.

## Four verdict dimensions

### Risk On / Risk Off

Weighted trend basket:

| Asset | Weight |
| --- | ---: |
| S&P 500 | +0.20 |
| Nasdaq | +0.22 |
| Shanghai | +0.11 |
| STAR 50 | +0.12 |
| KOSPI | +0.08 |
| Nikkei | +0.08 |
| US dividend proxy | +0.05 |
| VIX | -0.14 |

Thresholds: `>=30 risk_on`, `>=10 leaning_risk_on`, `(-10,10) mixed`,
`<=-10 leaning_risk_off`, `<=-30 risk_off`. S&P, Nasdaq, Shanghai, STAR 50,
and VIX are critical. Missing any of them makes only this dimension `unknown`.

Gold and oil are deliberately not mechanical Risk inputs. Their meaning is
conditioned in the scenario layer.

### Offense / defense

Offense is Nasdaq + STAR 50 + KOSPI. Defense is US dividend + China dividend +
gold. Score is `(offense average - defense average) / 2`, bounded to ±100.
Two members on each side are required; missing members produce `partial`, and
fewer than two on either side produces `unknown`.

Thresholds: `>=25 offense`, `>=8 leaning_offense`, `(-8,8) balanced`,
`<=-8 leaning_defense`, `<=-25 defense`.

### Technology / dividend

Technology edges are Nasdaq minus S&P and STAR 50 minus Shanghai. Dividend
edges are SCHD minus S&P and Shanghai Dividend minus Shanghai. Style score is
`(average technology edge - average dividend edge) / 2`.

All six assets are required because a missing dividend proxy cannot support a
technology-versus-dividend claim. Thresholds are ±20 for a full style label
and ±7 for a leaning label.

### Leadership

The ranking contains US equities, A equities, Asia ex-China, energy, and
precious metals. Each member score is 55% trend score plus 45% bounded 20d
momentum. A group is unavailable if any required member is missing.

A leader is named only when its score is at least +10 and its gap over second
place is at least 8 points. Otherwise the state is `none` or `contested`. If
any group is unavailable, the available groups remain ranked for diagnosis but
the global leader is `unknown`; an incomplete universe cannot crown a winner.

## Cross-asset scenarios

The deterministic scenario layer distinguishes:

- `supply_shock_risk_off`: WTI 20d return >=12%, WTI trend >=35, gold
  trend >=20, and aggregate risk <=-10;
- `reflation_risk_on`: WTI 20d return >=8%, WTI trend >=30, risk >=10;
- `flight_to_safety`: gold trend >=30 and VIX trend >=20 while risk <=-10;
- `growth_led_risk_on`: Nasdaq trend >=25, risk >=15, posture non-defensive,
  and style >=7 toward technology;
- `broad_deleveraging`: risk <=-15;
- otherwise `cross_asset_rotation`.

This prevents an oil or gold rally from being called Risk On without the
equity/volatility context, and prevents a strong Nasdaq tape from masking a
broader defensive/dividend rotation.

Scenario classification is three-valued. Risk, posture, style, WTI, gold, VIX
and Nasdaq inputs must all be available before the default rotation label can
be `full`; otherwise the scenario is `unknown` with an explicit missing list.

## Completeness and replay

`verdict_as_of` is the earliest completed close in the cross-market evidence;
the latest close and skew are also retained. More than 30 hours of close skew
forces the overall result to `partial`. Missing inputs degrade only their
dependent dimension.

The analysis identity hashes the model version and the input fingerprint. The
fingerprint binds snapshot quality/generated time plus every usable
instrument's session, close time, quality, evidence kind and M1 normalized
artifact hash. Recompiling the same input produces identical JSON. The
immutable analysis artifact is written under `analysis/artifacts/`; only its
verified pointer may advance. Consumers read through
`MarketRegimeAnalysisStore.latest`, which checks path containment, content
hash, schema, analysis identity and input fingerprint before returning it.

Every artifact and CLI output propagates `data_kind` and is labelled
`model_generated_unreviewed`, `read_only`, `not_investment_advice=true`,
`action_eligible=false`, and `publication_eligible=false`.

## One-shot compile

```bash
python3 scripts/compile_market_regime.py
```

M3 owns scheduling and HTTP exposure. Importing or compiling M2 has no network
or trading side effect.
