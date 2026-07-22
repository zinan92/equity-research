# Deterministic Financial & Valuation Engine v1

## Product outcome

Users can reproduce the financial bridge, Bull/Base/Bear DCF, reverse DCF, peer multiple, historical multiple and sensitivity outputs from one frozen numeric input. The model never asks an LLM to calculate or repair a number.

## Reused methods

- `rollingSirius/equity-research-skill`: scenario DCF, reverse DCF, WACC × terminal-growth sensitivity, relative valuation and historical-range cross-check discipline.
- Existing UZI `fin_models.py`: explicit NOPAT/FCF bridge and deterministic sensitivity-table pattern.
- Park A4/C1: point-in-time financial inputs, canonical CNY/reporting unit semantics and the typed valuation section contract.

The shipped implementation is a new typed pure-function boundary. It does not reuse UZI defaults that infer shares from market cap, silently use 1 billion shares, or invent missing assumptions.

## Input contract

`ValuationEngineInput` requires:

- one ticker, currency, allowed financial unit scale, current price, market cap and absolute diluted shares;
- at least two ascending historical financial periods;
- exactly one audited Bear/Base/Bull assumption set whose probabilities sum to 1;
- peer EV/EBITDA anchors and historical P/E anchors.

Each historical period must balance `assets = liabilities + equity`, use the declared currency, contain positive revenue/assets/shares and explain any share-count jump above 50% with an explicit share event. Price × shares must match market cap within 2%.

## Calculations

1. Historical bridge: NOPAT, unlevered FCF, reported FCF, cash conversion, net debt and balance check.
2. Scenario DCF: revenue path → EBIT margin → NOPAT + D&A − capex − NWC investment → enterprise/equity/per-share value.
3. Probability-weighted DCF: exact Bear/Base/Bull probability weighting.
4. Reverse DCF: bisection solves the constant revenue growth implied by the current price while holding Base margins and capital intensity fixed.
5. Peer cross-check: median EV/EBITDA × latest EBITDA − net debt, converted using the same absolute shares.
6. Historical cross-check: median historical P/E × latest EPS using the same unit scale and shares.
7. Sensitivity: deterministic 5×5 WACC/terminal-growth grid; higher terminal growth increases value and higher WACC decreases it.

## Identity and failure boundary

- every scenario has an `assumption_hash`;
- the entire typed input has an `input_hash`;
- all bridges, scenarios, methods, reverse DCF and sensitivity values produce one `output_hash`.

Invalid currency, unit, market-cap/share identity, statement balance, unmarked share jump, probability, WACC/growth or scenario ordering fails closed. No target price or position recommendation is emitted in C2.
