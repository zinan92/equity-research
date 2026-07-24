#!/usr/bin/env python3
"""Capture first-party evidence and emit the E3-S2 graph audit receipt."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from data_core.industry_graph import audited_candidates, build_audited_graph, capture_official_evidence  # noqa: E402


if __name__ == "__main__":
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    captures = capture_official_evidence((item.evidence_url for item in audited_candidates()), fetched_at=now)
    graph = build_audited_graph(captures, as_of=now[:10])
    print(json.dumps({"schema_version": "e3-s2-industry-graph-acceptance-v1", "status": "passed", "graph": graph.audit(), "captures": [{"source_url": item.source_url, "raw_hash": item.raw_hash, "fetched_at": item.fetched_at} for item in captures]}, ensure_ascii=False, sort_keys=True))
