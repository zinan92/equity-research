#!/usr/bin/env python3
"""Replay a frozen dossier through the versioned structural template.

This experiment deliberately keeps the evidence and prose frozen. A real
refresh changes evidence first; this command proves that identical inputs
produce a new version with the same structure and an auditable identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


TABLE_DIVIDER = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _signature(text: str) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("## ") or TABLE_DIVIDER.match(line)
    ]
    return _sha256("\n".join(lines).encode())


def replay(source: Path, output: Path, *, run_id: str) -> dict[str, object]:
    source_bytes = source.read_bytes()
    text = source_bytes.decode()
    source_hash = _sha256(source_bytes)
    if "status:" not in text or "| 运行 ID |" not in text:
        raise ValueError("source is not a versioned dossier")
    replayed = re.sub(r"(?m)^status: .+$", 'status: "structural-replay"', text, count=1)
    replayed = replayed.replace(
        "---\n\n#",
        f'replayed_from_sha256: "{source_hash}"\n---\n\n#',
        1,
    )
    replayed = re.sub(
        r"(?m)^\| 运行 ID \| .+ \|$",
        f"| 运行 ID | `{run_id}` |",
        replayed,
        count=1,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(replayed, encoding="utf-8")
    receipt = {
        "schema_version": "dossier-structural-replay-v1",
        "source": str(source),
        "output": str(output),
        "source_sha256": source_hash,
        "output_sha256": _sha256(replayed.encode()),
        "source_structure_signature": _signature(text),
        "output_structure_signature": _signature(replayed),
    }
    receipt["structure_match"] = (
        receipt["source_structure_signature"] == receipt["output_structure_signature"]
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    receipt = replay(args.source, args.output, run_id=args.run_id)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["structure_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
