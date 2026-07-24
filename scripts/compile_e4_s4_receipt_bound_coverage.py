"""Write a replayable E4 valuation/sell-side coverage receipt from frozen inputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "product") not in sys.path:
    sys.path.insert(0, str(ROOT / "product"))

from data_core.e4_valuation_sellside_coverage import compile_receipt_bound_coverage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("partial_receipt", type=Path)
    parser.add_argument("valuation_receipt", type=Path)
    parser.add_argument("sell_side_receipt", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = compile_receipt_bound_coverage(args.partial_receipt, args.valuation_receipt, args.sell_side_receipt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(args.out), "receipt_hash": receipt["receipt_hash"], "counts": receipt["counts"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
