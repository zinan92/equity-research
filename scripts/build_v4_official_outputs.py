#!/usr/bin/env python3
"""Retired legacy adapter command.

The old sample regrouping route is intentionally not executable.  Use the
canonical Round 7 receipt/markdown plus ``publish_v4_round7_dossier.py``.
"""
from __future__ import annotations

import argparse


def main() -> int:
    argparse.ArgumentParser().parse_args()
    raise SystemExit(
        "legacy official-output builder is retired; use "
        "scripts/publish_v4_round7_dossier.py with canonical Round 7 inputs"
    )


if __name__ == "__main__":
    raise SystemExit(main())
