# E4-S4m · real dual-input partial-Report-Model replay

## Result

The real replay joined the completed official-primary corpus with the completed
market/PIT companion only through their exact official-receipt lineage. Of the
100 requested identities, 40 compiled into evidence-bound partial Report
Models and 60 remained typed blocks. Within those 40 partial models, 27 have
both real market and PIT-fundamentals components available.

## Immutable runtime inputs

The runtime payloads remain ignored; this note records only the reproducible
handles and aggregate result.

| Input | Runtime receipt handle | Receipt bytes SHA-256 |
| --- | --- | --- |
| Official-primary corpus | `official-evidence-batch-115bdd8d6ac1f5c5.json` | `60f5dc8a35790c480498474ce4f64b386761c3177fa78b4645379c9fc7272871` |
| Market/PIT companion | `market-fundamentals-batch-99177f8d263adbcd.json` | `52f34bca7bbd808b5c2dd66bbbd155153d50e38420dc2d8ae592eb65c4064606` |

The companion receipt declares the official receipt bytes hash above. The
compiler rejects a companion whose lineage differs, even when ticker symbols
overlap.

## Replay and counts

Run from the worktree that owns the official runtime root, because captured
PDF paths in that receipt are relative to that root:

```bash
cd /Users/wendy/Documents/equity-research-e4-s4i
PYTHONPATH=/Users/wendy/Documents/equity-research-e4-s4m/product python3 - <<'PY'
from pathlib import Path
from data_core.e4_partial_report_models import compile_partial_report_models

root = Path("product/runtime/e4-s4-official-evidence-checkpointed")
receipt = compile_partial_report_models(
    root / "official-evidence-batch-115bdd8d6ac1f5c5.json",
    root,
    Path("/Users/wendy/Documents/equity-research-e4-s4j/product/runtime/"
         "e4-s4-market-fundamentals-100/"
         "market-fundamentals-batch-99177f8d263adbcd.json"),
)
print(receipt["counts"])
print(sum(
    row["status"] == "compiled"
    and row["model"]["sections"]["market"] == "available"
    and row["model"]["sections"]["fundamentals"] == "available"
    for row in receipt["models"]
))
PY
```

Observed result: `{'compiled_partial_models': 40, 'blocked': 60}` and `27`.
The official corpus baseline requested 100 identities, so the complete
aggregate is 100 requested / 40 primary partial models / 60 typed blocks / 27
with both bound companion components.

## Truth boundary

Every replayed output remains **Tier C** and **`no_action`**. It earns zero
Tier A/B, valuation, sell-side, industry-position, target-price, position, or
numeric/page-audit credit. The 27 is component availability, not coverage of a
complete research report or an investment recommendation.

For the individual baselines, see
[official evidence baseline](2026-07-24-e4-s4f-100-ticker-baseline.md) and
[market/PIT baseline](2026-07-24-e4-s4j-market-pit-baseline.md).
