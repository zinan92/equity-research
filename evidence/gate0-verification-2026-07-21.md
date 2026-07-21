# Gate 0 verification receipt · 2026-07-21

Objective: prove that the private-beta repository baseline is recoverable, does not require user-specific paths, and does not include known secrets or runtime state.

## Automated baseline

Command:

```bash
python3 scripts/verify_baseline.py --receipt evidence/gate0-baseline-receipt.json
```

Result:

- 79 product tests passed.
- Temporary-database server smoke passed.
- `/api/health` returned `status=ok`, `data_mode=DEMO`, no errors.
- `/api/dashboard` returned all 8 positions.
- No forbidden runtime or secret-like file was found among versioned or pending files.

This smoke test intentionally verifies only a fresh-clone `DEMO` baseline. It does not recreate the historical verified CATL narrative, approval, or publication pack because all runtime state is excluded from Git.

Machine-readable receipt: [gate0-baseline-receipt.json](gate0-baseline-receipt.json).

## Secret scanning

Commands:

```bash
gitleaks git --redact --no-banner --verbose
gitleaks dir . --redact --no-banner --verbose
```

Result at Gate 0 review: no leaks found in Git history or the current directory scan.

## Static validation

Commands:

```bash
git diff --check
python3 -m py_compile product/*.py scripts/verify_baseline.py
node --check product/render_publication.mjs
plutil -lint product/automation/*.plist
cd product && npm audit --omit=dev
```

Result: all passed; npm reported 0 vulnerabilities.

## Visual evidence selected for the repository landing page

- [Committee dashboard](m3-committee-home-desktop-2026-07-18.jpg)
- [CATL report PDF page 1](m4-publication-pdf-final-page1.png)
- [Private-beta login](m5-private-beta-login-2026-07-18.png)

These images prove the previously rendered UI state only. They do not prove current external-data connectivity, production deployment, payment, or a live user account.
