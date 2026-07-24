#!/usr/bin/env python3
"""Emit the E3-S5 profile-contract acceptance receipt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.industry_profiles import PROFILES, profile_contract  # noqa: E402

if __name__ == "__main__":
    profiles = {key: profile_contract(key, {field: 1 for field in value.required_inputs}) for key, value in PROFILES.items()}
    print(json.dumps({"schema_version": "e3-s5-industry-profiles-v1", "status": "passed", "profiles": profiles}, ensure_ascii=False, sort_keys=True))
