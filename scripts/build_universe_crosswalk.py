#!/usr/bin/env python3
"""Build an audit-only 649/661 universe crosswalk from local snapshot inputs."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.universe_crosswalk import build_crosswalk  # noqa: E402


def _records(path: Path, *, main_only: bool = False) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"{path} must contain an object with records")
    selected = [row for row in records if isinstance(row, dict)]
    if main_only:
        selected = [row for row in selected if row.get("universe") == "main"]
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--levels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    main_records = _records(args.main, main_only=True)
    level_records = _records(args.levels)
    records = build_crosswalk(main_records, level_records)
    statuses = Counter(row.status for row in records)
    payload = {
        "schema_version": "company-universe-crosswalk-v1",
        "boundary": "Runtime-only audit output. Do not commit archive-derived rows or use them as product facts.",
        "input_counts": {"main": len(main_records), "levels": len(level_records)},
        "status_counts": dict(sorted(statuses.items())),
        "records": [row.to_dict() for row in records],
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("input_counts", "status_counts")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
