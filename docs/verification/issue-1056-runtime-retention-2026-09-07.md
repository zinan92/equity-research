# Issue #1056 runtime retention verification

## Scope

This branch adds a resolved-root, reference-aware prune for the Market Regime
runtime. The online runtime was inspected read-only; no live files were
deleted and no launchd service or plist was changed.

## Live dry-run

Command:

```bash
python3 scripts/prune_market_regime_runtime.py \
  --root "$HOME/Library/Application Support/ParkMarketRegime/runtime" \
  --retention-days 14 --summary
```

Observed 2026-09-07 (Asia/Shanghai):

```json
{
  "schema_version": "market-regime-prune-v1",
  "root": "/Volumes/Phone SSD/park-runtime/ParkMarketRegime/runtime",
  "retention_days": 14,
  "dry_run": true,
  "planned_delete_count": 44265,
  "planned_delete_bytes": 10868709236,
  "deleted_count": 0,
  "deleted_bytes": 0,
  "runtime_bytes_before": 15989793354
}
```

The root confirms that the configured symlink was resolved to the SSD target.
The `--summary` command did not write `prune-receipt.json`.

## Automated validation

```bash
python3 -m py_compile product/market_regime_retention.py \
  scripts/prune_market_regime_runtime.py product/market_regime_runtime.py
PYTHONPATH=src python3 -m unittest \
  product.tests.test_market_regime_retention \
  product.tests.test_market_regime_runtime -q
```

Result: `Ran 31 tests ... OK`.

Full discovery result: `Ran 1193 tests in 268.528s`, with 3 environment
errors and 1 skipped. The errors are the pre-existing missing
`/Users/wendy/Desktop/K线日报/SYSTEM-PROMPT-macro-analyst.md` fixture and two
Playwright tests whose Chromium executable is not installed. No retention test
failed. `python3 scripts/verify_baseline.py` completed without output, and
`gitleaks detect --source . --no-banner --redact` reported `no leaks found`.

## Owner follow-up

After merge, the owner should run the formal command with `--execute` while
the scheduler is stopped or otherwise lock-safe, inspect
`prune-receipt.json`, and verify the runtime size and the 8896 historical page
against the acceptance contract. This branch intentionally does not perform
that deletion.
