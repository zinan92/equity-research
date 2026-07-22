from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SNAPSHOT_PATH = ROOT / "data" / "industry-intelligence-v1.json"
SCHEMA_VERSION = "industry-intelligence-snapshot-v1"


class IndustryIntelligenceError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_snapshot() -> dict:
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndustryIntelligenceError("industry intelligence snapshot is unavailable") from exc
    summary = payload.get("summary") if isinstance(payload, dict) else None
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or not isinstance(summary, dict)
        or summary.get("dossier_count") != 489
        or len(payload.get("dossiers", {})) != 489
        or len(payload.get("companies", [])) != summary.get("primary_company_count")
        or len(payload.get("three_high_map", {}).get("nodes", [])) != summary.get("map_node_count")
        or summary.get("materials_node_count") != 94
        or len(payload.get("materials_map", {}).get("nodes", [])) != summary.get("materials_node_count")
    ):
        raise IndustryIntelligenceError("industry intelligence snapshot failed its integrity contract")
    return payload


def overview_payload() -> dict:
    payload = load_snapshot()
    dossiers = payload["dossiers"]
    dossier_index = [
        {key: value.get(key) for key in (
            "code", "name", "title", "updated", "market", "chains", "layer", "segment",
            "role", "rating", "sangao", "score", "opportunity", "flags", "summary",
        )}
        for value in dossiers.values()
    ]
    return {
        "schema_version": payload["schema_version"],
        "source": payload["source"],
        "summary": payload["summary"],
        "three_high_map": payload["three_high_map"],
        "materials_map": payload["materials_map"],
        "segments": payload["segments"],
        "companies": payload["companies"],
        "dossiers": dossier_index,
    }


def dossier_payload(code: str) -> dict | None:
    normalized = str(code).strip().upper()
    if not normalized or len(normalized) > 24:
        return None
    payload = load_snapshot()
    dossier = payload["dossiers"].get(normalized)
    if dossier is None:
        return None
    return {
        "schema_version": payload["schema_version"],
        "source": payload["source"],
        "dossier": dossier,
    }
