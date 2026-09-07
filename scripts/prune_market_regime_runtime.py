#!/usr/bin/env python3
"""Plan or execute bounded Market Regime runtime retention."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from market_regime_retention import (  # noqa: E402
    DEFAULT_RETENTION_DAYS,
    MarketRegimeRetention,
)
from market_regime_runtime import market_regime_root  # noqa: E402
from market_regime_runtime import _write_atomic  # noqa: E402
from market_regime_runtime import _try_file_lock, _unlock_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=market_regime_root())
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--execute", action="store_true", help="delete the planned immutable objects")
    parser.add_argument("--summary", action="store_true", help="print counts and byte totals only")
    args = parser.parse_args()
    lock = None
    try:
        if args.execute:
            resolved_root = Path(args.root).expanduser().resolve()
            lock = _try_file_lock(resolved_root / "scheduler" / "pipeline.lock")
            if lock is None:
                parser.error("runtime pipeline lock is busy; retry after the active cycle finishes")
        result = MarketRegimeRetention(args.root, retention_days=args.retention_days).prune(
            dry_run=not args.execute
        )
        if args.execute:
            receipt_path = Path(result["root"]) / "prune-receipt.json"
            _write_atomic(receipt_path, result)
    finally:
        if lock is not None:
            _unlock_file(lock)
    if args.summary:
        print(json.dumps({key: result[key] for key in (
            "schema_version", "root", "retention_days", "cutoff_at",
            "dry_run", "planned_delete_count", "planned_delete_bytes",
            "deleted_count", "deleted_bytes", "runtime_bytes_before",
            "runtime_bytes_after",
        ) if key in result}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
