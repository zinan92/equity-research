#!/usr/bin/env python3
"""Bind real canonical market packets to the E4 financial sequences.

The output is runtime-only.  It carries the provider raw identities beside
market facts and never reclassifies an unavailable market component as real.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.ashare import collect_ashare_packet  # noqa: E402
from data_core.e4_catl_vertical import compile_vertical  # noqa: E402


def _market(summary: Mapping[str, Any]) -> dict[str, Any]:
    sources = summary.get("sources") or {}
    quote_source = sources.get("quote") or {}
    bars_source = sources.get("daily_bars") or {}
    quote = summary.get("quote") or {}
    bars = summary.get("daily_bars") or []
    required = (quote_source, bars_source)
    valid = all(
        source.get("data_kind") == "real" and source.get("publishable")
        and isinstance(source.get("raw_hash"), str) and len(source["raw_hash"]) == 64
        and source.get("known_at")
        for source in required
    )
    return {
        "quote": dict(quote) if valid else {},
        "daily_bars": list(bars) if valid else [],
        "status": "available" if valid and quote and bars else "missing",
        "source_receipts": {
            "quote": {key: quote_source.get(key) for key in ("selected_source", "raw_hash", "manifest_hash", "source_url", "known_at")},
            "daily_bars": {key: bars_source.get(key) for key in ("selected_source", "raw_hash", "manifest_hash", "source_url", "known_at")},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("financial_sequences", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    source = json.loads(args.financial_sequences.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(source.get("tickers") or []):
        ticker = str(row["ticker"]).upper()
        try:
            packet = collect_ashare_packet(ticker, bar_limit=30, fundamental_periods=4).to_summary()
            market = _market(packet)
            vertical = compile_vertical(
                {"reports": row.get("reports") or []}, market, ticker=ticker,
                context_manifest_hash=hashlib.sha256(args.financial_sequences.read_bytes()).hexdigest(),
                dossier_id="e4-m1-real-market-inputs",
            )
            rows.append({"ticker": ticker, "status": "completed", "market": market, "decision": vertical["decision"], "scores": vertical.get("scores"), "score_receipt": vertical.get("score_receipt"), "valuation": vertical["valuation"]})
        except Exception as exc:  # a failed source must be explicit, not filled
            rows.append({"ticker": ticker, "status": "missing", "reason": f"{type(exc).__name__}: {str(exc)[:240]}", "raw_text_excerpt": "canonical market packet could not be captured"})
        if index < len(source.get("tickers") or []) - 1 and args.delay:
            time.sleep(args.delay)
    payload = {"schema_version": "e4-m1-decision-inputs-v1", "data_kind": "real", "financial_sequences_sha256": hashlib.sha256(args.financial_sequences.read_bytes()).hexdigest(), "configured_max_concurrency": 1, "rows": rows, "counts": {"tickers": len(rows), "completed": sum(row["status"] == "completed" for row in rows), "no_action": sum(row.get("decision", {}).get("action") == "no_action" for row in rows)}, "truth_boundary": {"does_not_promote_tier_or_action": True, "provisional_scores_are_unreviewed": True}}
    payload["receipt_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(args.out), "counts": payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
