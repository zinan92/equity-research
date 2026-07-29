"""Honest CATL sell-side/consensus source admission for L1-M3.

Existing B2/B4 adapters are useful diagnostics, but their Eastmoney/THS
aggregator origins are forbidden as research facts by this product contract.
This module records the real B4 probe only as a source-policy rejection.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .consensus_history import THS_FORECAST_SOURCE, build_ths_forecast_runtime, ths_consensus_references
from .contracts import RecordDomain
from .ingestion import FetchRequest, SourceChoice
from .official_filings import default_http_transport
from .sell_side_archive import EASTMONEY_SELL_SIDE_CATALOG_SOURCE, EASTMONEY_SELL_SIDE_PDF_SOURCE

SCHEMA = "e4-l1-m3-sell-side-admission-v1"


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def probe_catl_sell_side_admission() -> dict[str, Any]:
    """Run B4 once, but never admit its aggregator values into C1 inputs."""
    runtime = build_ths_forecast_runtime(transport=default_http_transport)
    request = FetchRequest.create(
        request_id="e4-l1-m3-ths-catl", domain=RecordDomain.EVENT,
        entity_key="300750.SZ", parameters={"as_of": "2026-07-29"},
    )
    outcome = asyncio.run(runtime.run(request, (SourceChoice(THS_FORECAST_SOURCE, "primary"),)))
    attempt = outcome.attempts[-1] if outcome.attempts else None
    raw = attempt.raw if attempt else None
    b4 = {
        "module": "B4 consensus_history", "source_key": THS_FORECAST_SOURCE,
        "status": "missing", "reason": "source_policy_inadmissible_aggregator",
        "observed": {
            "run_status": "responded" if outcome.publishable else "failed",
            "http_status": getattr(attempt.fetched, "status_code", None) if attempt else None,
            "raw_hash": getattr(raw, "raw_hash", None),
            "reference_count": len(ths_consensus_references(outcome)),
            "attempt_error": getattr(attempt, "error", None),
        },
    }
    b2 = {
        "module": "B2 sell_side_archive", "source_keys": [EASTMONEY_SELL_SIDE_CATALOG_SOURCE, EASTMONEY_SELL_SIDE_PDF_SOURCE],
        "status": "missing", "reason": "source_policy_inadmissible_aggregator",
        "observed": {"run_status": "not_requested", "reason": "Eastmoney catalog/PDF would be inadmissible before collection"},
    }
    payload = {
        "schema_version": SCHEMA, "data_kind": "real", "ticker": "300750.SZ",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "inputs": {"broker_estimates": b2, "consensus_history": b4},
        "admitted_c1_inputs": {},
        "truth_boundary": {"aggregator_output_not_research_fact": True, "counts_as_tier_a_or_b": False, "forecasts_and_consensus_remains_missing": True},
    }
    payload["receipt_hash"] = _digest(payload)
    payload["receipt_id"] = f"{SCHEMA}:{payload['receipt_hash']}"
    return payload
