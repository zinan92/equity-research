# Market Regime 8907 QA Control

## Control identity

- URL: `http://127.0.0.1:8907/`
- JSON endpoint: `http://127.0.0.1:8907/api/weekly-report`
- Current control report: `market-regime-weekly-report:135b4ce71122ce61d0f6d5ca2bc0d8f722344bdd91154fbee5594f36ab5813ee`
- `week_end`: `2026-08-21`
- `sample_label`: `历史样本（非今日最新）`

This is a reader and analysis control, not a current-market data source. A
QA pass must never copy its prices, dates or conclusions into a Daily/Weekly
production edition.

## What the control demonstrates

### Overview surface

The market overview should make the first scan possible without opening every
asset:

1. grouped asset navigation;
2. one row per asset with display name and searchable ticker;
3. a readable mini K-line, latest value and unit;
4. latest candle tone (up/down), weekly change;
5. a compact position meter (high/middle/low);
6. a trend marker and label (up / down / disagreement);
7. explicit unavailable state instead of a fake neutral state.

The control report's acceptance baseline is `analysis_validated == assets.length`
for its historical sample. This is a completeness check, not a requirement
that a live report hide real provider failures.

### Single-asset surface

The detail view is the primary semantic control:

1. asset display name, ticker/instrument and as-of date;
2. position / structure / odds in one metric strip;
3. one card per eligible period, with the chart before the explanation;
4. a 0–100 period score with a direction conclusion and tone color;
5. one combined conclusion and one market-meaning explanation;
6. visible evidence/status footer without OPS fields in the main narrative.

The period contract remains edition-specific: Weekly uses weekly + daily +
eligible 4-hour context; Daily uses daily + only the declared intraday slots.
The QA sample defines the reading order and completeness expectation, not the
period universe or freshness policy.

## Pass/fail gate for future editions

| Layer | Pass condition |
|---|---|
| Data | Every requested slot is `ready` or visibly `unavailable`; no stale or implicit source switch |
| Asset reader | Every eligible asset has identity, observation time, chart, period text, position, structure and odds |
| Direction | Every validated period has a score/conclusion/tone; unavailable periods never become neutral |
| Synthesis | Every model-ready asset has combined conclusion + market meaning; dual failures are named |
| Surface parity | HTML, Markdown and article payload preserve asset → period image → period text → summary order |
| Truth boundary | `model_generated_unreviewed` is never labelled “已验证”; historical control data never enters live output |

## Current known difference

The 8907 control is a polished Weekly historical sample. The current Daily
runtime is the real-data path and may show deterministic-only cards or a
missing cross-asset thesis when both providers fail. That difference must be
visible in the report status; it is not permission to fill the gap with this
sample's text or prices.
