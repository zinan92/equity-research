#!/usr/bin/env python3
"""Verify the immutable repair ledger for missing GitHub milestone objects."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


EXPECTED_MISSING = list(range(79, 90))
EXPECTED_RECONSTRUCTED = list(range(90, 101))
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def validate(payload: dict[str, Any], repo: Path | None = None) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "audit-lineage-v1":
        errors.append("schema_version must be audit-lineage-v1")
    if payload.get("repository") != "zinan92/equity-research":
        errors.append("repository identity mismatch")

    entries = payload.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]

    missing = [entry.get("missing_reference") for entry in entries if isinstance(entry, dict)]
    reconstructed = [entry.get("reconstructed_issue") for entry in entries if isinstance(entry, dict)]
    if missing != EXPECTED_MISSING:
        errors.append(f"missing_reference sequence must be {EXPECTED_MISSING}")
    if reconstructed != EXPECTED_RECONSTRUCTED:
        errors.append(f"reconstructed_issue sequence must be {EXPECTED_RECONSTRUCTED}")
    if len(set(missing)) != len(missing):
        errors.append("missing_reference values must be unique")
    if len(set(reconstructed)) != len(reconstructed):
        errors.append("reconstructed_issue values must be unique")

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index} must be an object")
            continue
        label = f"entry #{entry.get('missing_reference', index)}"
        reference = entry.get("reference_commit")
        evidence = entry.get("evidence_commits")
        if not isinstance(entry.get("milestone"), str) or not entry["milestone"].strip():
            errors.append(f"{label}: milestone is required")
        if not isinstance(reference, str) or not SHA_RE.fullmatch(reference):
            errors.append(f"{label}: reference_commit must be a full lowercase SHA")
            continue
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{label}: evidence_commits must be non-empty")
            continue
        if reference not in evidence:
            errors.append(f"{label}: reference_commit must appear in evidence_commits")
        for commit in evidence:
            if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
                errors.append(f"{label}: invalid evidence commit {commit!r}")

        if repo is not None:
            try:
                subject = _git(repo, "show", "-s", "--format=%s", reference)
                if f"#{entry['missing_reference']}" not in subject:
                    errors.append(f"{label}: reference commit subject does not contain the missing number")
                for commit in evidence:
                    _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
                    _git(repo, "merge-base", "--is-ancestor", commit, "HEAD")
            except RuntimeError as exc:
                errors.append(f"{label}: git verification failed: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("docs/governance/audit-lineage-v1.json"),
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--no-git", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.ledger.read_text(encoding="utf-8"))
    errors = validate(payload, None if args.no_git else args.repo.resolve())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: verified {len(payload['entries'])} reconstructed audit entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
