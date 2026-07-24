"""C2 valuation receipts bound to frozen E4 partial-model identities.

Inputs are supplied as runtime-only JSON because collection and analyst
assumption authoring are separate workflows.  This adapter does not invent an
assumption or fill a missing financial field; it only validates identities and
replays C2 deterministically.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from report_contract import HistoricalFinancialPeriod, ValuationEngineInput, ValuationScenarioAssumptions, run_deterministic_valuation

from .contracts import digest

E4_VALUATION_RECEIPT_SCHEMA_VERSION = "e4-s4-real-valuation-receipts-v1"


def _instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("research cutoff and known_at must include timezone")
    return parsed.astimezone(timezone.utc)


def _hash(value: object) -> str:
    value = str(value or "")
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise ValueError("source identity must be a SHA-256 hash")
    return value


def _engine(value: Mapping[str, Any]) -> ValuationEngineInput:
    try:
        historical = tuple(HistoricalFinancialPeriod(**dict(item)) for item in value["historical"])
        scenarios = tuple(ValuationScenarioAssumptions(**{**dict(item), "revenue_growth": tuple(item["revenue_growth"]), "ebit_margin": tuple(item["ebit_margin"])}) for item in value["scenarios"])
        return ValuationEngineInput(
            ticker=str(value["ticker"]).upper(), currency=str(value["currency"]), unit_scale=int(value["unit_scale"]),
            current_price=float(value["current_price"]), market_cap=float(value["market_cap"]), shares_outstanding=float(value["shares_outstanding"]),
            historical=historical, scenarios=scenarios, peer_ev_ebitda=tuple(float(x) for x in value["peer_ev_ebitda"]), historical_pe=tuple(float(x) for x in value["historical_pe"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("valuation engine input is incomplete or malformed") from exc


def _row(row: Mapping[str, Any], model: Mapping[str, Any], *, cutoff: datetime) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    if ticker != model["ticker"]:
        return {"ticker": model["ticker"], "status": "blocked", "blockers": ["valuation_ticker_mismatch"]}
    if row.get("context_evidence_set_id") != model.get("evidence_set_id") or row.get("context_manifest_hash") != model.get("evidence_manifest_hash"):
        return {"ticker": ticker, "status": "blocked", "blockers": ["valuation_context_mismatch"]}
    sources = row.get("source_receipts")
    if not isinstance(sources, Mapping):
        return {"ticker": ticker, "status": "blocked", "blockers": ["valuation_missing_canonical_sources"]}
    blockers = []
    for name in ("quote", "fundamentals", "balance_sheet", "income_statement", "cash_flow"):
        item = sources.get(name)
        if not isinstance(item, Mapping): blockers.append(f"valuation_missing_{name}_source"); continue
        try:
            _hash(item.get("raw_hash")); _hash(item.get("manifest_hash"))
            if _instant(item.get("known_at")) > cutoff: blockers.append(f"valuation_{name}_known_at_after_cutoff")
        except ValueError:
            blockers.append(f"valuation_invalid_{name}_source")
    assumption = row.get("assumption_receipt")
    if not isinstance(assumption, Mapping): blockers.append("valuation_missing_assumption_receipt")
    else:
        try:
            _hash(assumption.get("raw_hash")); _hash(assumption.get("manifest_hash"))
            if _instant(assumption.get("known_at")) > cutoff: blockers.append("valuation_assumption_known_at_after_cutoff")
        except ValueError: blockers.append("valuation_invalid_assumption_receipt")
    if blockers:
        return {"ticker": ticker, "status": "blocked", "blockers": sorted(set(blockers))}
    try:
        result = run_deterministic_valuation(_engine(row.get("engine_input") or {}))
    except Exception as exc:
        return {"ticker": ticker, "status": "blocked", "blockers": ["valuation_engine_input_rejected"], "error": type(exc).__name__}
    if result.input_hash != _engine(row["engine_input"]).input_hash:
        return {"ticker": ticker, "status": "blocked", "blockers": ["valuation_engine_input_hash_mismatch"]}
    payload = {"ticker": ticker, "as_of": row.get("research_cutoff"), "context_evidence_set_id": model["evidence_set_id"], "context_manifest_hash": model["evidence_manifest_hash"], "valuation_input_hash": result.input_hash, "valuation_output_hash": result.output_hash, "source_hashes": {name: sources[name]["raw_hash"] for name in sorted(sources)}, "assumption_raw_hash": assumption["raw_hash"]}
    return {"ticker": ticker, "status": "compiled", **payload, "receipt_hash": digest(payload), "valuation": {"engine_version": result.engine_version, "methods": [asdict(item) for item in result.methods]}}


def compile_real_valuation_receipts(partial_path: Path, inputs_path: Path, *, research_cutoff: str) -> dict[str, Any]:
    partial_bytes = partial_path.read_bytes(); partial = json.loads(partial_bytes); inputs = json.loads(inputs_path.read_text())
    if partial.get("schema_version") != "e4-s4-partial-report-model-v1" or partial.get("data_kind") != "real" or not partial.get("truth_boundary", {}).get("tier_is_c_only"):
        raise ValueError("valuation adapter requires real Tier-C partial models")
    if inputs.get("schema_version") != E4_VALUATION_RECEIPT_SCHEMA_VERSION or inputs.get("data_kind") != "real" or inputs.get("partial_receipt_sha256") != hashlib.sha256(partial_bytes).hexdigest():
        raise ValueError("valuation inputs do not match real partial-model lineage")
    if inputs.get("research_cutoff") != research_cutoff: raise ValueError("valuation input cutoff mismatch")
    cutoff = _instant(research_cutoff)
    by_ticker = {str(item.get("ticker") or "").upper(): item for item in inputs.get("receipts") or [] if isinstance(item, Mapping)}
    if len(by_ticker) != len(inputs.get("receipts") or []): raise ValueError("valuation input tickers must be unique and non-empty")
    rows=[]
    for entry in partial.get("models") or []:
        if entry.get("status") != "compiled": rows.append({"ticker": entry.get("ticker"), "status": "blocked", "blockers": ["partial_model_not_compiled"]}); continue
        rows.append(_row(by_ticker.get(entry["model"]["ticker"], {}), entry["model"], cutoff=cutoff))
    receipt={"schema_version": E4_VALUATION_RECEIPT_SCHEMA_VERSION,"data_kind":"real","partial_receipt_sha256":hashlib.sha256(partial_bytes).hexdigest(),"research_cutoff":research_cutoff,"receipts":rows,"counts":{"compiled":sum(x["status"]=="compiled" for x in rows),"blocked":sum(x["status"]=="blocked" for x in rows)},"truth_boundary":{"tier_is_c_only":True,"counts_as_tier_a_or_b":False,"counts_as_position_or_target":False}}
    receipt["receipt_hash"]=digest(receipt); return receipt
