#!/usr/bin/env python3
"""Materialize a tracked V4-N1 evidence packet from runtime receipts."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.contracts import digest  # noqa: E402
from data_core.v4_n1_official_evidence import build_packet  # noqa: E402


def _mapping(values: list[str] | None, *, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or ():
        if "=" not in value:
            raise ValueError(f"{label} must use TICKER=PATH")
        ticker, path = value.split("=", 1)
        key = ticker.strip().upper()
        if key in result:
            raise ValueError(f"duplicate {label} ticker: {key}")
        result[key] = path
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--financial", action="append", required=True, help="TICKER=financial sequence receipt")
    parser.add_argument("--narrative", action="append", help="TICKER=narrative receipt")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    financial_paths = _mapping(args.financial, label="--financial")
    narrative_paths = _mapping(args.narrative, label="--narrative")
    financial_inputs = {ticker: json.loads(Path(path).read_text(encoding="utf-8")) for ticker, path in financial_paths.items()}
    narrative_inputs = {ticker: json.loads(Path(path).read_text(encoding="utf-8")) for ticker, path in narrative_paths.items()}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    tracked_financial_paths: dict[str, str] = {}
    for ticker, path in financial_paths.items():
        target = args.out_dir / f"{ticker}-financial-sequence.json"
        if Path(path).resolve() != target.resolve():
            shutil.copyfile(path, target)
        tracked_financial_paths[ticker] = str(target)
    tracked_narrative_paths: dict[str, str] = {}
    for ticker, path in narrative_paths.items():
        target = args.out_dir / f"{ticker}-official-narrative-evidence.json"
        if Path(path).resolve() != target.resolve():
            shutil.copyfile(path, target)
        tracked_narrative_paths[ticker] = str(target)
    packet = build_packet(
        financial_inputs,
        input_paths=tracked_financial_paths,
        narrative_inputs=narrative_inputs,
        narrative_paths=tracked_narrative_paths,
    )
    for company in packet["companies"]:
        ticker = company["ticker"]
        financial = next(
            json.loads(Path(financial_paths[ticker]).read_text(encoding="utf-8"))
            for key in financial_paths
            if key == ticker
        )
        # The Round 7 page-fact artifact is the only financial input that the
        # future chapter runner may consume.  The original sequence receipt
        # remains runtime-only but its hash is preserved in the source field.
        financial_artifact = {
                "schema_version": "round7-financial-page-evidence-v1",
                "data_kind": "real",
                "ticker": ticker,
                "source": {
                    "schema_version": financial["schema_version"],
                    "receipt_hash": financial["receipt_hash"],
                    "input_path": tracked_financial_paths[ticker],
                },
                "page_facts": company["round7_page_facts"],
            }
        financial_artifact["receipt_hash"] = digest(financial_artifact)
        (args.out_dir / f"{ticker}-financial-page-evidence.json").write_text(
            json.dumps(financial_artifact, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    packet_path = args.out_dir / "receipt.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(packet_path), "receipt_hash": packet["receipt_hash"], "companies": [{"ticker": row["ticker"], "financial": row["financial_status"], "available_reports": row["available_reports"], "narrative": row["narrative"]["status"], "page_facts": len(row["round7_page_facts"])} for row in packet["companies"]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
