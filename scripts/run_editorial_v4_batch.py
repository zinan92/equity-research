#!/usr/bin/env python3
"""Generate the five fresh review-only Ainiu/V4 dossiers from frozen packets."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL  # noqa: E402
from editorial_v4_qa import run_quality_loop  # noqa: E402


DEFAULT_TICKERS = ("600900.SH", "000333.SZ", "600519.SH", "300750.SZ", "000001.SZ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/editorial-v4")
    parser.add_argument("--max-iterations", type=int, default=4)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_TICKERS))
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for ticker in args.tickers:
        packet_path = args.root / "evidence-packets" / f"{ticker}.json"
        out_dir = args.root / ticker
        started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        if not packet_path.exists():
            rows.append({"ticker": ticker, "status": "blocked", "reason": "evidence_packet_missing", "started_at": started})
            continue
        try:
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            receipt = run_quality_loop(packet, out_dir, max_iterations=max(1, args.max_iterations), key_file=args.key_file, model=args.model)
            rows.append({"ticker": ticker, "status": receipt.get("final_status"), "receipt": receipt, "started_at": started})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
        except Exception as exc:  # preserve a typed failure and continue to next company
            row = {"ticker": ticker, "status": "error", "error_type": type(exc).__name__, "error": str(exc), "started_at": started}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    batch = {"schema_version": "editorial-v4-batch-receipt-v1", "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "model": args.model, "tickers": list(args.tickers), "rows": rows}
    path = args.root / "batch-receipt.json"
    path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"batch_receipt": str(path), "statuses": {row["ticker"]: row["status"] for row in rows}}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
