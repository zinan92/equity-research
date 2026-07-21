# Private Preview v1

## Product contract

M6 turns the canonical A-share research product into an invite-only preview for Park, a few friends and the future paid community. The first screen answers one job: **what the model portfolio owns, at what target weight, what changed, and why**.

Known product configuration:

- Market: A shares only.
- Reference user: RMB 10 million+ assets and a long holding period.
- Delivery group: Park, invited friends and a small paid community.
- Product output: one canonical 8-stock model allocation, cash, actions, observation ranges, research depth, primary risks and linked standardized reports.
- User input: none in v1; no risk questionnaire or personalized holdings.
- Execution: model recommendations only; no broker connection and no claim of real positions or fills.

Deliberately unresolved until M7:

- price and billing interval;
- payment provider, refund handling and subscription webhooks;
- which report/download rights are part of a paid plan.

## Product configuration

This section is the Gate A configuration record for the private preview. Unknown commercial fields stay explicitly pending rather than being invented.

- Product: Park Equity Research Private Preview.
- Owner: Park.
- Domain: `research.park-ai-intel.com`.
- One-line job: turn one traceable A-share model portfolio and its bound company reports into a decision-first, invite-only research product.
- Initial users: Park and a small number of invited long-horizon investors with an assumed RMB 10 million+ asset base; the need comes from Park's stated requirement to provide market development, long-term allocation, named stocks and suggested weights.
- Initial region/language: invited Chinese-speaking users; Chinese UI and RMB references. The current Cloudflare-to-local-Mac route is only the preview deployment, not the final regional hosting decision.
- Core flow: receive invite → register/login → read canonical allocation → member opens exact company report → submit feedback → owner reviews feedback or suspends access.
- Required functions: canonical decision first screen; entitlement-bound reports; structured feedback/member control.
- Explicit exclusions: user holdings/risk input, personalization, broker connection, payment, public signup, MFA, multi-region hosting and full-market screening.
- Acceptance: the seven Issue #22 criteria plus the commands in this document must pass against the external URL; anonymous leakage, identity mismatch or rollback failure blocks the gate.
- User data: email, display name, password hash, session/CSRF hashes, tier/status, invite audit and feedback. Secrets and research data are stored separately outside Git.
- Retention/export/deletion: owner feedback export and immediate suspension exist; member self-export/deletion and a fixed retention period are pending M7/Scale design and must be verified before that gate.
- Maintenance budget: target at most two hours per week during the private pilot; verify from four consecutive weekly operating logs before Scale decisions.
- Price, paid rights, provider, refund, unit-cost ceiling, margin, distribution attribution and shutdown economics: pending M7, verified only through the Paid Pilot contract and real provider/account evidence. M6 accepts no payment.
- Preview validation window: 30 days after the first invited external user; success means at least three invited users complete the core flow and at least two submit actionable feedback. Otherwise Park decides whether to revise or stop the preview.

## Runtime architecture

```text
External browser
  -> dedicated HTTPS Cloudflare Tunnel
  -> loopback-only Python origin
  -> packaged, content-addressed product release
       -> immutable research.db + canonical portfolio state
       -> separate mutable auth.db for members, sessions and feedback
```

The runtime lives outside the repository. A release identity binds the research database attestation, current portfolio, recomputed diff, ledger history, the exact eight-report bundle and packaged product-code hash. `current` changes atomically only after the complete release verifies. The installer copies the minimal service runner into the external runtime, so the installed origin does not execute application code from the working tree. That runner validates the manifest, release identity, every packaged file hash and all external paths before every server start. Member and feedback state remain in a separate database and survive release changes.

## Entitlements

| Tier | Canonical first screen | Deep reports | Downloads | Member/feedback administration |
|---|---:|---:|---:|---:|
| `preview` | yes | no | no | no |
| `member` | yes | yes | no | no |
| `paid` (reserved for M7) | yes | yes | no in M6 | no |
| `owner` | yes | yes | yes | yes |

Every protected endpoint checks its entitlement on the server. Front-end visibility is not an authorization control. Anonymous access receives only the login shell and a minimal health response.

Private-preview mode deliberately exposes only `GET /api/private-preview`, exact `GET /api/reports/{ticker}`, owner member/feedback reads and the authentication/feedback/member-administration writes needed for the pilot. Legacy dashboard, refresh, approval, publication, download and research mutation routes return `private_preview_route_unavailable`, including for an owner. This keeps the externally reachable service read-only with respect to the packaged research release.

## Security and truth boundary

- Invite-only registration; invites are limited by time and uses.
- Passwords use PBKDF2-SHA256 with a random salt; session and CSRF values are stored only as hashes.
- Public sessions use `__Host-` + `Secure` + `HttpOnly` + `SameSite=Strict`; writes require the bound CSRF token.
- Suspended members lose every active session immediately.
- Failed login work is bounded per identity and per trusted client IP, so rotating email addresses cannot force unbounded PBKDF2 work.
- Feedback is rate-limited, deduplicated and protected by exact-SQL append-only triggers.
- Research, portfolio and ledger corruption fails closed. All eight report hashes are recomputed and must match their position bindings; there is no fallback to DEMO, an unbound report or a legacy portfolio in private-preview mode.
- The page is explicitly labelled `PRIVATE PREVIEW`, does not accept payment, does not connect a broker and does not represent user holdings.

## Prepare and deploy

From the repository root:

```bash
python3 scripts/prepare_private_preview.py prepare
python3 scripts/prepare_private_preview.py sanitize-auth  # one-time cleanup after upgrading an older preview
python3 product/member_admin.py --db <external-runtime>/auth.db \
  create-owner --email <owner-email> --name Park
python3 product/deployment/install_private_preview.py install \
  --tunnel-id <dedicated-tunnel-id> \
  --credential-file </path/outside/repository/tunnel-credential.json>
```

The installed origin and tunnel are separate LaunchAgents. The tunnel credential, acceptance credentials, auth database and generated environment file must remain outside Git and owner-readable only.

Rollback is content-addressed:

```bash
python3 scripts/prepare_private_preview.py rollback <verified-release-id>
launchctl kickstart -k gui/$(id -u)/com.park.equity-research-preview
```

The command refuses an unknown, corrupted or repository-local release.

A complete machine-observed rollback, roll-forward and tunnel-restart rehearsal is:

```bash
python3 scripts/verify_private_preview.py --rehearse-ops \
  --rollback-release <different-verified-release-id>
```

The rehearsal restores the original current release in a `finally` path, waits for external HTTPS health after every transition, compares the identity and active connector state of every other Cloudflare tunnel before/after the dedicated restart, and writes `evidence/m6-private-preview/restart-rollback-receipt.json`. A manually written receipt is not acceptance evidence. The rollback target must itself contain the current minimum security contract; a known-vulnerable historical release is never an acceptable rehearsal target.

## Acceptance

```bash
python3 -m unittest product.tests.test_private_preview_v1 -v
python3 scripts/verify_private_preview.py
python3 scripts/adversarial_verify_private_preview.py
```

Acceptance covers the complete anonymous and legacy-route matrix, preview/member/owner entitlements, registration/login/logout, suspension, cookies, CSRF, feedback audit, exact canonical identity and all eight report bindings, external HTTPS, dedicated service/tunnel health, actual rollback/roll-forward/restart and authenticated desktop/mobile full-page screenshots. Mobile acceptance also checks readable body text and 44px-or-larger primary interaction targets.

## Operating limits

This is **Private Preview Ready**, not Production Ready or Paid Pilot Ready. The current origin is a single Mac and is unavailable if that Mac sleeps, loses network access or stops both LaunchAgents. It has no multi-region failover, email recovery, MFA, online PostgreSQL/Supabase authority, payment or refund flow. Those limits are visible product truth, not implied future capability.
