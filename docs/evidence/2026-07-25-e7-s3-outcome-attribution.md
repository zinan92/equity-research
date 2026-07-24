# E7-S3 outcome attribution evidence

`build_outcome_receipt()` reuses the published report identity: publication ID,
snapshot ID, ticker, report hash, `as_of`, and `known_at` are frozen into the
receipt. The report’s market price is the only company starting basis.

Later observations are separately labelled `outcome_window` rows. Each row
contains company, benchmark, optional industry and optional fundamental
observation components. It cannot mutate the frozen report and contains no
rating, target, position, recommendation or order.

The contract rejects a ticker/snapshot mismatch and observations at or before
the frozen `known_at` cutoff. This prevents later information from being
presented as available to the original research decision.

Verification:

```bash
python3 -m pytest product/tests/test_research_outcomes.py -q
python3 -m unittest product.tests.test_research_refresh_v1 product.tests.test_research_objects -q
```
