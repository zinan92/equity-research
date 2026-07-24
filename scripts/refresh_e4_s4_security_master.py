#!/usr/bin/env python3
"""Capture the runtime-only real identity corpus used by E4-S4 acceptance."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "product") not in sys.path:
    sys.path.insert(0, str(ROOT / "product"))

from data_core.ashare_security_master import collect_security_master, write_runtime_capture  # noqa: E402


def curl_http_get(url: str) -> bytes:
    """Use the local curl TLS stack for the attended live probe only."""
    result = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location", "--retry", "3", "--retry-all-errors", "--connect-timeout", "10", "--max-time", "30", url],
        check=False, capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"security-master live request failed: {result.stderr.decode('utf-8', errors='replace')[:300]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture real A-share security-master identity acceptance corpus")
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "product" / "runtime" / "e4-s4-security-master")
    parser.add_argument("--per-market", type=int, default=40)
    args = parser.parse_args()
    capture = collect_security_master(http_get=curl_http_get, per_market=args.per_market)
    result = write_runtime_capture(capture, args.runtime_root)
    receipt = result["receipt"]
    print(json.dumps({
        "status": "captured", "path": result["path"], "record_count": receipt["record_count"],
        "exchanges": receipt["exchanges"], "receipt_hash": receipt["receipt_hash"], "truth_boundary": receipt["truth_boundary"],
    }, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
