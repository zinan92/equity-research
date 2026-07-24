#!/usr/bin/env python3
"""Print the deterministic E4-S1 evidence-to-report audit receipt."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1] / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.vertical_slices import vertical_slice_audit  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(vertical_slice_audit(), ensure_ascii=False, indent=2, sort_keys=True))
