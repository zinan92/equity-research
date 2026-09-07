# Issue #1057 Market Regime redeploy verification

Date: 2026-09-08 (Asia/Shanghai)

## Contract and pre-deploy audit

The old app was compared with the repository checkout using:

```text
diff -rq --exclude=__pycache__ --exclude=.pytest_cache --exclude=.git \
  "$HOME/Library/Application Support/ParkMarketRegime/app" \
  "$PWD"
```

The complete output is in the Issue #1057 pre-deploy comment:
https://github.com/zinan92/equity-research/issues/1057#issuecomment-5573456947

The old `.git` contained:

```text
gitdir: /Users/wendy/Documents/投研面板/.git/worktrees/app
```

The old directory was retained as `app.retired-20260908`. No runtime data was
deleted or moved.

## Deployment commands and evidence

Before changing launchd configuration, the following backups were made:

```text
mkdir -p "$HOME/park-data/launchd-backup-2026-09-08"
cp -p "$HOME/Library/LaunchAgents/com.park.market-regime.scheduler.plist" \
  "$HOME/park-data/launchd-backup-2026-09-08/"
cp -p "$HOME/Library/LaunchAgents/com.park.market-regime.intraday-scheduler.plist" \
  "$HOME/park-data/launchd-backup-2026-09-08/"
cp -p "$HOME/Library/LaunchAgents/com.park.market-regime.web.plist" \
  "$HOME/park-data/launchd-backup-2026-09-08/"
```

The valid checkout is a git worktree created from `origin/main`:

```text
git worktree add -b deploy/market-regime-20260908 \
  "$HOME/Library/Application Support/ParkMarketRegime/app.redeploy-20260908" \
  origin/main
git pull --ff-only
HEAD ca5d3dc340209e75ebc7c62ee3343e759fb8622d
Already up to date.
```

The three plists now use `app.redeploy-20260908` for `WorkingDirectory` and
their script path. `PARK_MARKET_REGIME_ROOT` and `--root` remain
`/Users/wendy/Library/Application Support/ParkMarketRegime/runtime`; that path
resolves through the existing external-SSD symlink. `plutil -lint` returned
`OK` for all three files.

Immediately before restart, intraday status was `busy=false`. The recorded
restart sequence was bootout of scheduler, intraday-scheduler and web; rename
of the old app; then bootstrap of the three updated plist paths.

Post-bootstrap `launchctl print` showed all three services `state = running`
with working directory `.../app.redeploy-20260908`. The new code contains the
#1054 retry (`EDEADLK` at `product/market_regime_runtime.py:278-290`).

## Runtime acceptance

The web process owns TCP `127.0.0.1:8896` and a subsequent request returned:

```text
http_code=200
```

The first intraday cycle after deployment reached `publish`, but retention's
full runtime scan remained active for more than seven minutes. During that
scan status remained `busy=true`, `cycle_failure_streak=0`, and
`last_error=null`; therefore the required completed next-cycle receipt is not
yet verified. The process was not restarted while busy.

The runtime contains about 81,519 files and about 10 GiB under `intraday`.
`df -h` reported 822 GiB available on the SSD. Earlier `Errno 28` status-write
errors were observed in the pre-existing log; no deletion was performed to
address them.

The focused repository checks passed:

```text
PYTHONPATH=src python3 -m unittest -q \
  product.tests.test_market_regime_retention \
  product.tests.test_market_regime_runtime \
  product.tests.test_market_regime_lock
Ran 36 tests in 2.900s
OK
```

## Retention gate

The required `scripts/prune_market_regime_runtime.py` dry-run was not started
while the active cycle was still `busy=true`. No manual `--execute` prune and
no runtime deletion was performed. The owner must run and review the dry-run
after the cycle returns to `busy=false`, then decide whether to perform the
formal prune.

