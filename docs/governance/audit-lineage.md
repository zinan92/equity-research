# Historical audit-lineage repair

## What happened

The `main` history contained milestone commits whose subjects referenced `#79` through `#89`, but GitHub had no corresponding Issue or Pull Request objects. GitHub's commit-to-pull-request API also returned no associated PRs for those commits. The implementation is intact; the missing part was the review and contract trail.

The retained evidence cannot prove which low-level write path produced every commit, so this repository does not claim that historical PRs existed. Rewriting Git history or inventing PR objects would make the audit trail less trustworthy.

## Repair

- Reconstructed, explicitly labelled Issues [#90](https://github.com/zinan92/equity-research/issues/90) through [#100](https://github.com/zinan92/equity-research/issues/100) bind the milestones to immutable commits.
- [`audit-lineage-v1.json`](audit-lineage-v1.json) provides the machine-readable mapping from each missing reference to its reconstructed Issue and evidence commits.
- `python3 scripts/verify_audit_lineage.py` checks the mapping, the referenced commit subjects, and ancestry from the checked-out `HEAD`.
- Issue [#101](https://github.com/zinan92/equity-research/issues/101) and its PR are the first new governance change following the truthful Issue → branch → PR path.

## Future rule

The `main` branch must require a pull request, including for administrators, while requiring zero human approvals. This preserves Park OS auto-merge and prevents direct implementation pushes. Commit text such as `(#123)` is not evidence that PR `#123` exists; GitHub's PR object and commit association are authoritative.
