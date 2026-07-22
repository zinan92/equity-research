# Sell-Side Viewpoint Matrix v1

## Outcome

C3 converts frozen B2–B4 broker-report evidence into one deterministic matrix that answers four different questions without collapsing them into “机构认为”:

1. What did each broker publish, and on which page?
2. What is the numeric consensus after superseded values and robust outliers are separated?
3. How did each broker revise its rating, target and forecasts?
4. Which bullish and bearish claims coexist, and how strong may the summary language be?

The compiler is `product.data_core.build_sell_side_viewpoint_matrix`. It performs no network or model calls.

## Input contract

Each immutable `SellSideViewpoint` binds one report to:

- ticker, broker, analyst, report date and report identity;
- document ID and exact PDF raw SHA-256;
- rating, target price, currency and normalized `BrokerEstimate` rows;
- typed claims with topic, stance, explicit/tentative strength and B3 page citations.

An estimate whose ticker, broker, analyst, report, date, target or raw hash disagrees with its report fails closed. A matrix cannot mix currencies.

## Output contract

`SellSideViewpointMatrix` contains:

- one row per historical report, with latest-for-broker and missing-field states;
- a B4 `ConsensusSnapshot`, including superseded and outlier quarantine;
- consecutive per-broker rating, target-price and forecast revisions;
- topic-level bullish, bearish and neutral evidence IDs;
- every blocked claim and its exact citation error;
- deterministic input and matrix identities;
- `to_report_inputs()` output for C1 section 11.

## Summary-strength gate

Only claims passing the document/page/raw-hash/quote gate contribute to topics.

| Evidence | Maximum summary language |
|---|---|
| tentative claims only | `tentative_report_language_only` |
| one broker with explicit evidence | `one_report_says` |
| at least two brokers, no bull/bear split | `multiple_reports_indicate` |
| at least two brokers with bull and bear evidence | `documented_disagreement` |
| at least four brokers and at least 80% explicit stance alignment | `broadly_shared_view` |

This is a language ceiling, not a judgment that the brokers are correct. Bull and bear claim IDs always remain separately visible.

## Boundary

- No LLM-authored estimates or claims.
- No automatic judgment of broker quality.
- No recommendation, target-price policy or position sizing; those remain C5.
- No fabricated report or fixture may be labelled REAL.
