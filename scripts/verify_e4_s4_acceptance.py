#!/usr/bin/env python3
"""Run the strict E4-S4 acceptance gate over a runtime identity receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "product") not in sys.path:
    sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_acceptance import evaluate_e4_s4  # noqa: E402


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate strict E4-S4 real coverage acceptance")
    parser.add_argument("security_master_receipt", type=Path)
    parser.add_argument("--coverage", type=Path, help="runtime canonical coverage JSON keyed by ticker")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    coverage = load(args.coverage) if args.coverage else {}
    result = evaluate_e4_s4(load(args.security_master_receipt), coverage_rows=coverage)
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if result["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
