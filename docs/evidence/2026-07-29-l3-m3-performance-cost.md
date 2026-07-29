# L3-M3 · Performance and cost budget harness

`scripts/verify_performance_budget.py` persists a bounded receipt outside the
repository. It exercises 10x the ten-task baseline (100 tasks), warms the
identity-bound report cache, measures cached summary reads and cached report
payload reads, and records the existing fresh-report queue contract.

The 2026-07-29 receipt is at:

`/Users/wendy/Library/Application Support/Park Equity Research Performance Receipts/2026-07-29/performance-budget-receipt.json`

| Measurement | Result | Budget |
| --- | ---: | ---: |
| Cached summary read p95 | 0.0000642205s | < 2s |
| Cached report payload p95 | 0.0000670355s | < 3s |
| Fresh report queue builder p95 | 0.0000098003s | < 3s |
| Queue isolation | 100 ordered tasks, no cross-write | 10x baseline |

The receipt records `parse`, `model_tokens`, and `storage` as **unknown** when
there is no provider bill. Unknown cost is never converted to zero, and a
known amount over a caller-supplied budget remains an alert.

This is deliberately a local contract harness: its task identities are
synthetic, it does not measure network/API latency, and it does not claim a
provider invoice or production p95. New report work is recorded as the existing
`queued_async_contract`; product API wiring is a separate delivery surface.

```bash
python3 scripts/verify_performance_budget.py \
  --runtime "/Users/wendy/Library/Application Support/Park Equity Research Performance Receipts/YYYY-MM-DD" \
  --task-count 100
```
