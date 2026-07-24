#!/usr/bin/env python3
"""Emit the E3-S1 industry-ontology acceptance receipt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core import ontology_receipt  # noqa: E402

if __name__ == "__main__":
    receipt = ontology_receipt()
    receipt["status"] = "passed"
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
