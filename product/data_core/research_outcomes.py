"""Read-only, point-in-time outcome attribution for published research."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .contracts import digest


OUTCOME_SCHEMA_VERSION = "research-outcome-attribution-v1"


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc


def _price(value: Mapping[str, Any], field: str) -> float:
    result = value.get(field)
    if isinstance(result, bool) or not isinstance(result, (int, float)) or result <= 0:
        raise ValueError(f"{field} must be a positive number")
    return float(result)


def build_outcome_receipt(
    *,
    publication_id: str,
    snapshot_id: str,
    ticker: str,
    frozen_report: Mapping[str, Any],
    outcome_observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return deterministic later observations without changing frozen research.

    Each observation is an independently captured outcome and must contain
    `known_at`, `company_price`, and `benchmark_price`; optional industry price
    and fundamental status stay explicit rather than being inferred.
    """
    cutoff = _instant(frozen_report.get("known_at"), "frozen_report.known_at")
    if frozen_report.get("ticker") != ticker.upper():
        raise ValueError("frozen report ticker mismatch")
    generated = frozen_report.get("generated_from") or {}
    if generated.get("snapshot_id") != snapshot_id:
        raise ValueError("frozen report snapshot mismatch")
    start_company = _price(frozen_report.get("market") or {}, "price")
    rows = []
    for observation in outcome_observations:
        known_at = _instant(observation.get("known_at"), "outcome known_at")
        if known_at <= cutoff:
            raise ValueError("outcome observation must be after frozen research cutoff")
        company_price = _price(observation, "company_price")
        benchmark_price = _price(observation, "benchmark_price")
        benchmark_start = _price(observation, "benchmark_start_price")
        company_return = company_price / start_company - 1
        benchmark_return = benchmark_price / benchmark_start - 1
        row = {
            "known_at": observation["known_at"],
            "company_return": company_return,
            "benchmark_return": benchmark_return,
            "relative_return": company_return - benchmark_return,
            "industry_return": None,
            "fundamental_observation": observation.get("fundamental_observation", "missing"),
        }
        if observation.get("industry_price") is not None:
            industry_price = _price(observation, "industry_price")
            industry_start = _price(observation, "industry_start_price")
            row["industry_return"] = industry_price / industry_start - 1
        rows.append(row)
    ordered = sorted(rows, key=lambda item: item["known_at"])
    payload = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "publication_id": publication_id,
        "snapshot_id": snapshot_id,
        "ticker": ticker.upper(),
        "frozen_research": {
            "as_of": frozen_report.get("as_of"), "known_at": frozen_report.get("known_at"),
            "report_hash": frozen_report.get("report_hash"), "research_inputs_mutable": False,
        },
        "outcome_window": ordered,
        "boundary": "Outcome observations are separate from frozen research and cannot create an action, target, rating, or position.",
    }
    payload["receipt_id"] = "outcome:" + digest(payload)[:32]
    return payload
