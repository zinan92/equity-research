#!/usr/bin/env python3
"""Emit the deterministic N3-S1 company-to-industry index receipt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from data_core.industry_company_index import build_industry_company_index  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(build_industry_company_index().receipt(), ensure_ascii=False, sort_keys=True))
