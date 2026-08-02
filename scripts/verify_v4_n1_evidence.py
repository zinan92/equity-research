#!/usr/bin/env python3
"""Replay verifier for the tracked V4-N1 official evidence packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.contracts import digest  # noqa: E402
from data_core.round7_evidence import load_source_receipts  # noqa: E402
from data_core.v4_n1_official_evidence import materialize_financial_receipt  # noqa: E402


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def verify(packet_path: Path) -> dict:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    expected_packet_hash = digest({key: value for key, value in packet.items() if key != "receipt_hash"})
    if packet.get("schema_version") != "v4-n1-official-evidence-packet-v1" or packet.get("data_kind") != "real":
        raise ValueError("V4-N1 packet is not a real packet")
    if packet.get("receipt_hash") != expected_packet_hash:
        raise ValueError("V4-N1 packet hash mismatch")
    results = []
    for company in packet.get("companies") or ():
        ticker = str(company.get("ticker") or "").upper()
        sequence_path = _resolve(str(company["round7_financial_path"]))
        narrative_path = _resolve(str(company["narrative"]["path"]))
        sequence = json.loads(sequence_path.read_text(encoding="utf-8"))
        if sequence.get("receipt_hash") != company.get("financial_receipt_hash"):
            raise ValueError(f"{ticker} financial receipt hash mismatch")
        if digest({key: value for key, value in sequence.items() if key != "receipt_hash"}) != sequence.get("receipt_hash"):
            raise ValueError(f"{ticker} financial receipt cannot be replayed")
        materialized = materialize_financial_receipt(sequence, ticker=ticker)
        financial_path = ROOT / "docs/evidence/v4-n1-official" / f"{ticker}-financial-page-evidence.json"
        narrative, financial = load_source_receipts(narrative_path=narrative_path, financial_path=financial_path, ticker=ticker)
        if narrative.get("source_financial_receipt_sha256") != sequence.get("receipt_hash"):
            raise ValueError(f"{ticker} narrative is not bound to sequence receipt")
        if financial.get("page_facts") != company.get("round7_page_facts"):
            raise ValueError(f"{ticker} packet page facts drifted from tracked artifact")
        if len(financial.get("page_facts") or ()) != len(materialized.get("round7_financial", {}).get("page_facts") or ()):
            raise ValueError(f"{ticker} materializer page-fact count mismatch")
        results.append({
            "ticker": ticker,
            "financial_receipt_hash": sequence["receipt_hash"],
            "financial_page_facts": len(financial.get("page_facts") or ()),
            "narrative_receipt_id": narrative.get("receipt_id"),
            "narrative_blocks": len(narrative.get("blocks") or ()),
            "available_reports": company.get("available_reports"),
        })
    return {"status": "passed", "packet": str(packet_path), "packet_receipt_hash": packet["receipt_hash"], "companies": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.packet), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
