#!/usr/bin/env python3
"""Generate one new review-only Ainiu/V4 dossier from a frozen packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL  # noqa: E402
from editorial_v4_generator import generate_once, write_draft  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--iteration", type=int, default=0)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    result, provider_receipt, request = generate_once(packet, key_file=args.key_file, model=args.model, iteration=args.iteration)
    paths = write_draft(result, args.out_dir)
    (args.out_dir / "generation-request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "provider-receipt.json").write_text(json.dumps(provider_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ticker": packet.get("ticker"), "run_id": result["production_record"]["run_id"], "request_id": provider_receipt.get("request_id"), **paths}, ensure_ascii=False))


if __name__ == "__main__":
    main()
