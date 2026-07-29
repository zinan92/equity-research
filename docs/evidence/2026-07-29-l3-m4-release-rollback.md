# L3-M4 · Release and rollback rehearsal

On 2026-07-29 the installed private-preview runtime completed a machine-observed
rollback, roll-forward, and dedicated-tunnel restart rehearsal. The current
release was restored in the script's `finally` path.

| Step | Verified release | External health |
| --- | --- | ---: |
| Before / final | `preview_b71f46fcd0dbc965` | 200 |
| Rollback target | `preview_76e74a7aa8a14266` | 200 |
| Tunnel restart | dedicated tunnel remained active | 200 |

The receipt is [restart-rollback-receipt.json](../../evidence/m6-private-preview/restart-rollback-receipt.json)
(`verified_at`: `2026-07-29T10:02:58.399096+00:00`). Both releases were
verified from their content-addressed manifests before the pointer transition;
corrupt or unknown releases are rejected by `point_current` / `verify_release`.
The packaged runner rechecks the manifest and release identity before starting,
and the release store's immutable `current` pointer supplies the rollback path.

This proves the current isolated private-preview release boundary. It does not
claim that dev, staging, and production deployments exist: production deployment
and migration rollout remain absent, so no production-isolation or production
migration-compatibility claim is made here.
