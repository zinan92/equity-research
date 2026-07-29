#!/usr/bin/env python3
"""Freeze a real 100-ticker identity input for L2 financial collection.

The security master supplies canonical ticker identity only.  Financial facts
remain exclusively extracted from the later official CNINFO PDF captures.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.ashare_security_master import collect_security_master, write_runtime_capture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "e4-l2-identity")
    args = parser.parse_args()
    # 34 x 3 gives at least 100 real identities while preserving SH/SZ/BJ.
    result = write_runtime_capture(collect_security_master(per_market=34), args.runtime_root)
    receipt = result["receipt"]
    print(json.dumps({"path": result["path"], "record_count": receipt["record_count"], "exchanges": receipt["exchanges"], "truth_boundary": receipt["truth_boundary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
