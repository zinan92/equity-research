"""Canonical read projections that never fall back to cached or fixture data."""
from __future__ import annotations

from typing import Any, Mapping


def canonical_read_projection(kind: str, report: Mapping[str, Any]) -> dict[str, Any]:
    """Project a verified canonical report into one bounded read surface."""
    ticker = str(report.get("ticker") or "").upper()
    if not ticker:
        raise ValueError("canonical report has no ticker")
    mode = str(report.get("data_mode") or "").upper()
    source_state = "live" if mode == "REAL" else "fixture" if mode in {"DEMO", "FIXTURE"} else "unknown"
    base = {
        "ticker": ticker,
        "source_state": source_state,
        "fallback": "none",
        "truth_boundary": {"canonical_active_only": True, "cached_fallback": False, "fixture_fallback": False},
    }
    if kind == "report":
        return {**base, "report": dict(report)}
    if kind == "company":
        return {**base, "company": {key: report.get(key) for key in ("ticker", "name", "industry", "exchange", "data_mode")}}
    if kind == "sector":
        return {**base, "sector": report.get("industry") or report.get("sector")}
    if kind == "dossier":
        return {**base, "dossier": report.get("evidence_pack") or report.get("research_dossier"), "status": report.get("research_status")}
    if kind == "score":
        return {**base, "score": report.get("scores") or report.get("executive", {}).get("score"), "status": report.get("research_status")}
    if kind == "roadmap":
        return {**base, "roadmap": report.get("roadmap") or report.get("research_roadmap"), "contract": report.get("report_contract")}
    raise ValueError("unsupported canonical read kind")
