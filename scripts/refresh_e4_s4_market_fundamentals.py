#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.e4_market_fundamentals_batch import run_market_fundamentals_batch  # noqa: E402
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("identity_receipt", type=Path); parser.add_argument("official_receipt", type=Path)
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "e4-s4-market-fundamentals")
    parser.add_argument("--max-tickers", type=int, default=100); parser.add_argument("--delay", type=float, default=1.0); parser.add_argument("--collector-timeout", type=float, default=30.0); parser.add_argument("--max-component-attempts", type=int, default=2)
    args=parser.parse_args()
    result=run_market_fundamentals_batch(args.identity_receipt,args.official_receipt,args.runtime_root,max_tickers=args.max_tickers,inter_ticker_delay_seconds=args.delay,collector_timeout_seconds=args.collector_timeout,max_component_attempts=args.max_component_attempts)
    print(json.dumps({"path":result["path"],"counts":result["receipt"]["counts"],"truth_boundary":result["receipt"]["truth_boundary"]},ensure_ascii=False,sort_keys=True,indent=2))
if __name__ == "__main__": main()
