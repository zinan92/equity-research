#!/usr/bin/env python3
"""Build persistent V4 reader HTML for the official-bound CATL/Moutai outputs."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from v4_publication import build_v4_publication  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=ROOT / "docs/evidence/v4-m3-official")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/v4-reports")
    args = parser.parse_args()
    result = build_v4_publication(source_root=args.source_root, output_root=args.output_root)
    print(result["index_path"])
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
