#!/usr/bin/env python3
"""Build an honest V4 expansion/coverage acceptance receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_contract import validate_v4_dossier  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(*, acceptance_path: Path, official_root: Path, replay_receipt_path: Path, audit_path: Path) -> dict[str, object]:
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    rows = list(acceptance.get("ticker_coverage") or [])
    if len(rows) != 100:
        raise ValueError(f"expected the real 100-ticker acceptance corpus, got {len(rows)}")
    rows.sort(key=lambda row: str(row.get("ticker")))
    sample = rows[:20]
    official_rows = []
    for ticker in ("300750.SZ", "600519.SH"):
        path = official_root / f"{ticker}.md"
        text = path.read_text(encoding="utf-8")
        errors = validate_v4_dossier(text)
        official_rows.append({"ticker": ticker, "path": str(path), "sha256": _sha(path), "validation": "passed" if not errors else "failed", "errors": errors})
    replay = json.loads(replay_receipt_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    actual = {
        "identity": len(rows),
        "report_models": sum(1 for row in rows if row.get("report_model_hash")),
        "tier_a_or_b": sum(1 for row in rows if row.get("tier") in {"A", "B"}),
        "numeric_page_audits": sum(1 for row in rows if row.get("numeric_spot_audit") and row.get("page_citation_spot_audit")),
    }
    return {
        "schema_version": "park-v4-expansion-acceptance-v1",
        "status": "honest_baseline_not_ready",
        "contract": "park-v4-dossier-v1",
        "old_18_section_statistics": {"status": "void_after_contract_replacement", "values_must_not_be_reused": True},
        "v4_baseline": {
            "official_bound_dossiers": official_rows,
            "official_bound_count": len(official_rows),
            "replay_only_count": int(replay.get("sample_count", 0)),
            "publication_index": "artifacts/v4-reports/index.html",
            "human_review": "pending_human_review",
            "tier_credit": "none",
        },
        "real_100_ticker_gate": {
            "thresholds": acceptance.get("thresholds"),
            "actual": actual,
            "gap": {key: int((acceptance.get("thresholds") or {}).get(key, 0) - value) for key, value in actual.items() if key in (acceptance.get("thresholds") or {})},
            "source_receipt": str(acceptance_path),
            "source_receipt_sha256": _sha(acceptance_path),
            "failure_taxonomy": acceptance.get("failure_taxonomy"),
        },
        "twenty_ticker_slice": {
            "selection": "first 20 sorted tickers from the real 100-ticker acceptance receipt",
            "count": len(sample),
            "rows": [{"ticker": row.get("ticker"), "data_kind": row.get("data_kind"), "tier": row.get("tier"), "blockers": row.get("blockers"), "report_model_hash": row.get("report_model_hash")} for row in sample],
            "all_have_explicit_blocker": all(row.get("blockers") for row in sample),
        },
        "independent_page_audit_state": {
            "assigned": len(audit.get("assignments") or []),
            "coverage_gaps": len(audit.get("coverage_gaps") or []),
            "completed_human_audits": 0,
            "counts_as_issue_218_credit": False,
            "receipt": str(audit_path),
        },
        "truth_boundary": {
            "no_fabricated_v4_dossiers": True,
            "no_threshold_relaxation": True,
            "no_unreviewed_approval": True,
            "no_tier_a_credit": True,
            "is_live_research": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance", type=Path, default=ROOT / "artifacts/evidence/e4-l2-m7-acceptance.json")
    parser.add_argument("--official-root", type=Path, default=ROOT / "docs/evidence/v4-m3-official")
    parser.add_argument("--replay-receipt", type=Path, default=ROOT / "docs/evidence/v4-m2-generalization-receipt.json")
    parser.add_argument("--audits", type=Path, default=ROOT / "artifacts/e4-reports/e4-l1-m6-spot-audit-assignments.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build(acceptance_path=args.acceptance, official_root=args.official_root, replay_receipt_path=args.replay_receipt, audit_path=args.audits)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    result["receipt_hash"] = hashlib.sha256(payload).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
