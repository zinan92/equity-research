"""N3 financial-delivery receipt over the exact 20-company dossier selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import digest
from .e4_market_fundamentals_batch import _collect_isolated, _collector_worker
from .n3_dossier_batch import N3_DOSSIER_BATCH_SIZE, selected_positions, selection_identity


N3_FINANCIAL_DELIVERY_SCHEMA_VERSION = "n3-financial-delivery-v1"
Worker = Callable[[str, Any], None]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _row(ticker: str, collected: Mapping[str, Any]) -> dict[str, Any]:
    receipts = collected.get("source_receipts") or {}
    required = ("fundamentals", "balance_sheet", "income_statement", "cash_flow")
    available = bool(collected.get("fundamentals_available"))
    identity_complete = all(
        isinstance(receipts.get(key), Mapping)
        and receipts[key].get("raw_hash")
        and receipts[key].get("manifest_hash")
        and receipts[key].get("known_at")
        for key in required
    )
    period = collected.get("latest_financial_period")
    return {
        "ticker": ticker,
        "status": "available" if available and identity_complete and period else "gap",
        "data_kind": "real",
        "financial_delivery_available": available and identity_complete and bool(period),
        "report_period": period,
        "announced_at": collected.get("latest_financial_announced_at"),
        "source_receipts": {key: receipts.get(key) for key in required},
        "blockers": list(collected.get("blockers") or []) + ([] if period else ["missing_latest_financial_period"]),
    }


def _receipt(rows: list[dict[str, Any]], *, state: str) -> dict[str, Any]:
    positions = selected_positions()
    output = {
        "schema_version": N3_FINANCIAL_DELIVERY_SCHEMA_VERSION,
        "state": state,
        "data_kind": "real",
        "selection_identity": selection_identity(positions),
        "tickers": rows,
        "counts": {
            "requested": len(positions),
            "resolved": len(rows),
            "available": sum(bool(row["financial_delivery_available"]) for row in rows),
            "gaps": sum(not bool(row["financial_delivery_available"]) for row in rows),
        },
        "truth_boundary": {
            "financial_delivery_is_input_only": True,
            "counts_as_valuation": False,
            "counts_as_tier_a_or_b": False,
            "counts_as_target_or_position": False,
        },
    }
    output["receipt_hash"] = digest(output)
    return output


def run_financial_delivery_batch(
    runtime_root: Path,
    *,
    collector_timeout_seconds: float = 30.0,
    worker: Worker = _collector_worker,
) -> dict[str, Any]:
    """Sequentially collect only the exact N3 20-company selection."""

    if collector_timeout_seconds <= 0:
        raise ValueError("collector timeout must be positive")
    positions = selected_positions()
    runtime_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for position in positions:
        rows.append(_row(position.ticker, _collect_isolated(position.ticker, collector_timeout_seconds, worker)))
        checkpoint = _receipt(rows, state="in_progress")
        _write_json(runtime_root / "n3-financial-delivery-checkpoint.json", checkpoint)
        _write_json(runtime_root / "n3-financial-delivery-latest.json", {"state": "in_progress", "receipt_hash": checkpoint["receipt_hash"]})
    receipt = _receipt(rows, state="completed")
    path = runtime_root / f"n3-financial-delivery-{receipt['receipt_hash'][:16]}.json"
    _write_json(path, receipt)
    _write_json(runtime_root / "n3-financial-delivery-latest.json", {"state": "completed", "receipt": path.name, "receipt_hash": receipt["receipt_hash"]})
    return {"path": str(path), "receipt": receipt}
