#!/usr/bin/env python3
"""Compile page-bound sell-side evidence from an E4 runtime batch receipt."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.e4_sell_side_page_evidence import write_sell_side_page_evidence  # noqa: E402
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("batch_receipt", type=Path); parser.add_argument("--runtime-root", type=Path, required=True); args = parser.parse_args()
    result = write_sell_side_page_evidence(args.batch_receipt, args.runtime_root)
    print(json.dumps({"path": result["path"], "counts": result["receipt"]["counts"], "truth_boundary": result["receipt"]["truth_boundary"]}, ensure_ascii=False, sort_keys=True, indent=2))
if __name__ == "__main__": main()
