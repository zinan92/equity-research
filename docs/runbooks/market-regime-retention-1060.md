# Market Regime retention cutover runbook

This runbook is for the owner after the PR is merged. It does not change the
runtime data format, port 8100, or any LaunchAgent plist.

## Preflight and enablement

Keep the current symlink and runtime untouched while validating the new
checkout. Update the retained deployment checkout to the merged SHA and run:

```bash
DEPLOY="$HOME/Library/Application Support/ParkMarketRegime/app.redeploy-20260908"
git -C "$DEPLOY" fetch origin
git -C "$DEPLOY" checkout --detach <MERGED_SHA>
git -C "$DEPLOY" status --short --branch
PARK_MARKET_REGIME_ROOT="$HOME/Library/Application Support/ParkMarketRegime/runtime" \
  PYTHONPATH="$DEPLOY/product" \
  python3 "$DEPLOY/scripts/prune_market_regime_runtime.py" --summary
```

The first command is only a hold-point: do not switch the live symlink until
the owner has reviewed the dry-run output. To enable bounded cycle retention,
write `retention.json` under the runtime root:

```json
{"enabled": true, "max_candidates": 2000, "max_seconds": 30}
```

The default is `enabled: false`. The cycle writes `prune-receipt.json` only
after a successful publish and enabled prune. Verify its `candidate_scan_truncated`,
`deleted_count`, `completed_at`, and `runtime_bytes_after` fields, plus the
`stage_timings.publish` and `stage_timings.prune` fields in the intraday
scheduler status/run receipt.

## Cutover, verification, and rollback

After owner approval, back up the three existing plists, update their existing
checkout/script paths from `app.retired-20260908` to
`app.redeploy-20260908`, and use the existing labels to bootout/bootstrap the
three agents. The approved owner command sequence is:

```bash
BACKUP="$HOME/park-data/launchd-backup-2026-09-08-issue-1060"
mkdir -p "$BACKUP"
for p in \
  com.park.market-regime.scheduler.plist \
  com.park.market-regime.intraday-scheduler.plist \
  com.park.market-regime.web.plist; do
  cp -p "$HOME/Library/LaunchAgents/$p" "$BACKUP/"
done
# Edit only the existing checkout/script path fields in the three plists.
for p in "$HOME/Library/LaunchAgents/"com.park.market-regime.{scheduler,intraday-scheduler,web}.plist; do
  sed -i '' 's#ParkMarketRegime/app#ParkMarketRegime/app.redeploy-20260908#g' "$p"
done
for label in com.park.market-regime.scheduler com.park.market-regime.intraday-scheduler com.park.market-regime.web; do
  launchctl bootout "gui/$(id -u)/$label"
done
for plist in "$HOME/Library/LaunchAgents/"com.park.market-regime.{scheduler,intraday-scheduler,web}.plist; do
  launchctl bootstrap "gui/$(id -u)" "$plist"
done
```

Verify `launchctl print`, the original live URL, `busy=false`, and the next
run receipt. No plist edit or service restart is performed by this PR; the
owner performs the approved cutover.

If the cycle remains busy, publish exceeds 60 seconds, or the complete cycle
exceeds 3 minutes, set `app` back to `app.retired-20260908`, leave
`retention.json` disabled, and restore the three plist files from `BACKUP`
before bootstrapping the same labels. Do not delete `app.redeploy-20260908` or
runtime data.
