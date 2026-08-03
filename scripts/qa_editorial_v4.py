#!/usr/bin/env python3
"""Generate and independently QA one review-only editorial V4 dossier."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL  # noqa: E402
from editorial_v4_qa import run_quality_loop  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    receipt = run_quality_loop(
        packet,
        args.out_dir,
        max_iterations=max(1, args.max_iterations),
        key_file=args.key_file,
        model=args.model,
    )
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
