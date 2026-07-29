# L3-M2 · Backup / restore objective drill

## What is protected

The private-preview runtime keeps the research release/storage tree and its
identity database as separate artifacts. `scripts/recovery_drill.py drill`
copies both into an external backup root, verifies the signed backup manifest,
clean-restores into another external runtime, and compares the restored auth
database hash plus the active release manifest.

The command writes a machine-readable
`recovery-objectives-receipt.json` beside the restored runtime. It evaluates,
rather than merely documents, these fixed objectives:

| Objective | Limit |
| --- | ---: |
| RPO | 24 hours |
| RTO | 4 hours |

A missing hash, a release that fails manifest validation, an auth hash mismatch,
a stale backup, or an over-limit restore makes the receipt `failed`. No Tier,
report-contract, B6, or decision-policy behavior is involved.

## 2026-07-29 clean drill

The currently installed private-preview runtime was backed up and restored to
separate external locations. The receipt is intentionally outside Git because
it contains a release identity and backup metadata:

`/Users/wendy/Library/Application Support/Park Equity Research Recovery Drills/2026-07-29/recovery-objectives-receipt.json`

| Check | Result |
| --- | --- |
| Backup manifest hash verification | passed |
| Separate auth database hash after restore | passed |
| Release/storage manifest after restore | passed |
| RPO | 0.419184 seconds, within 24 hours |
| RTO | 0.634650 seconds, within 4 hours |

The receipt's `production_runtime_observed` remains `false`: this proves the
installed private-preview recovery path, not an unconfigured production
deployment or a claim of multi-region disaster recovery. A production runtime
must execute the same command against its own external runtime and retain its
own receipt.

## Repeatable command

```bash
python3 scripts/recovery_drill.py \
  --runtime "/Users/wendy/Library/Application Support/Park Equity Research Preview" \
  drill \
  --backup-root "/Users/wendy/Library/Application Support/Park Equity Research Preview Backups" \
  --restored-runtime "/Users/wendy/Library/Application Support/Park Equity Research Recovery Drills/YYYY-MM-DD"
```
