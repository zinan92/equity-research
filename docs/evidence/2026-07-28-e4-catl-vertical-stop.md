# E4 CATL official-fact-to-decision vertical: hard stop

Issue: #490  
Scope: `300750.SZ` only.

## Step 1 — official multi-period financial history

The runtime collector fetched and parsed only the eight declared CNINFO PDFs:
five complete annual reports (2021FY–2025FY), 2025Q3, 2026Q1 and 2026H1.
Every admitted fact is from a consolidated statement page and preserves its
CNINFO document ID, raw SHA-256, one-based page, label/anchor, unit, currency,
period and URL.  PDFs are runtime-only.

| report | page-bound facts admitted | explicit missing metrics |
|---|---:|---|
| 2021FY | 14 | capital_expenditure, parent_equity |
| 2022FY | 15 | capital_expenditure |
| 2023FY | 14 | capital_expenditure, parent_equity |
| 2024FY | 12 | capital_expenditure, current_liabilities, parent_equity, total_liabilities |
| 2025FY | 12 | capital_expenditure, current_liabilities, parent_equity, total_liabilities |
| 2025Q3 | 15 | capital_expenditure |
| 2026Q1 | 15 | capital_expenditure |
| 2026H1 | 15 | capital_expenditure |

The required annual coverage exists for revenue, operating cost, parent net
profit, operating cash flow, assets, liabilities/equity where stated, and the
other detected statement rows.  It does **not** yet exist for the required
capital-expenditure field: the official reports express the relevant cash-flow
line across layout boundaries, and this narrow extractor will not concatenate
adjacent lines/pages or infer a value.

### Example a human can verify

`300750.SZ` / revenue / `2025FY` / `423,701,834 千元` / consolidated / document
`1225002214` / page `116` / anchor:

> 一、营业总收入 423,701,834 362,012,554

Official PDF: <https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF>

Raw SHA-256:
`c15272977147dee7e6935a38ea0e4fd6855370aabb106f54cfe20f7cf6048ec9`.

## Hard stop — C2 valuation cannot receive a truthful input

The existing C2 `ValuationEngineInput` requires `capital_expenditure` in each
historical period.  It also requires `peer_ev_ebitda` and `historical_pe`
anchors.  The first is missing from every extracted official-PDF period; the
latter two cannot be truthfully represented from a single issuer's official
PDFs.  Supplying zero, copying an adjacent row, treating CATL as its own peer,
or importing a vendor multiple would change the semantics or violate #490.

Therefore this story stops before Step 2–5:

- no market/current snapshot was attached to C1;
- no C2 valuation, assumptions, target price, scoring or DecisionReceipt was
  produced;
- no C1/Tier status or #218 metric was changed.

This is a data-shape/input-authority stop, not a change request for C2, C1,
B6, Tier or decision policy.
