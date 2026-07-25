"""Compile partial, evidence-bound Report Model candidates from E4 official PDFs.

The model is deliberately partial: a single official filing can support an
accepted primary evidence Context Pack but cannot support a target price,
position, Tier A/B recommendation, or numeric/page audit claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .ashare import normalize_ashare_ticker
from .contracts import RawCapture, RecordDomain, RecordEnvelope, SourceManifest, digest
from .evidence_gate import EvidenceCandidate, EvidenceGatePolicy, EvidenceRequirement, EvidenceRole, build_context_pack, build_evidence_set


E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION = "e4-s4-partial-report-model-v1"
OFFICIAL_DOCUMENT_HOSTS = frozenset({"static.cninfo.com.cn", "static.sse.com.cn", "www.sse.com.cn", "disc.static.szse.cn", "www.szse.cn", "www.bse.cn", "static.bse.cn"})
_QUOTE_FACTS = ("last_price", "change_pct", "high", "low", "pe_ttm", "circulating_market_cap", "market_cap", "pb", "observed_at")
_BAR_FACTS = ("trade_date", "adjustment", "open", "close", "high", "low", "volume")
_FUNDAMENTAL_FACTS = ("report_period", "announced_at", "report_type", "revenue", "net_profit_parent", "total_assets", "total_liabilities", "total_equity", "total_operating_income", "net_profit_parent_statement", "net_cash_operating")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _inside(root: Path, value: str) -> Path:
    declared = Path(value)
    candidate = declared.resolve() if declared.is_absolute() else (root / declared).resolve()
    if not candidate.is_file() and not declared.is_absolute():
        # Older E4 runtime receipts recorded the caller-relative raw path.  The
        # raw hash is still rechecked below; only the basename can be resolved
        # from the supplied batch root, never an arbitrary parent path.
        candidate = (root / "raw" / declared.name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("runtime raw path escapes the batch root") from exc
    return candidate


def _companion_by_ticker(path: Path, official_payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    boundary = payload.get("truth_boundary") or {}
    if payload.get("schema_version") != "e4-s4-market-fundamentals-batch-v1" or payload.get("data_kind") != "real" or boundary.get("counts_as_tier_a_or_b") is not False:
        raise ValueError("partial model compiler requires a real input-only market companion receipt")
    if not payload.get("official_receipt_sha256"):
        raise ValueError("market companion receipt is missing official lineage")
    return {str(row.get("ticker") or "").upper(): row for row in payload.get("tickers") or []}


def _source_identity_present(source: object) -> bool:
    if not isinstance(source, Mapping):
        return False
    raw_hash, manifest_hash, known_at = source.get("raw_hash"), source.get("manifest_hash"), source.get("known_at")
    return (
        isinstance(raw_hash, str) and len(raw_hash) == 64
        and isinstance(manifest_hash, str) and len(manifest_hash) == 64
        and bool(str(known_at or ""))
    )


def _selected_facts(value: object, keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value[key] for key in keys if isinstance(value, Mapping) and value.get(key) is not None}


def _companion_display_facts(companion: Mapping[str, Any] | None) -> dict[str, Any]:
    """Carry only a source-bound runtime projection into a partial model.

    Older receipts legitimately have no ``display_facts``.  They remain
    availability-only rather than being reinterpreted or filled from a newer
    source response.
    """
    if not companion or not isinstance(companion.get("display_facts"), Mapping):
        return {}
    facts = companion["display_facts"]
    sources = companion.get("source_receipts") or {}
    output: dict[str, Any] = {}
    market = facts.get("market") if isinstance(facts, Mapping) else None
    if isinstance(market, Mapping) and set(market.get("source_components") or ()) == {"quote", "daily_bars"}:
        quote = _selected_facts(market.get("quote"), _QUOTE_FACTS)
        bar = _selected_facts(market.get("latest_daily_bar"), _BAR_FACTS)
        if quote and bar and all(_source_identity_present(sources.get(component)) for component in ("quote", "daily_bars")):
            output["market"] = {"quote": quote, "latest_daily_bar": bar, "source_components": ["quote", "daily_bars"]}
    financial = facts.get("fundamentals") if isinstance(facts, Mapping) else None
    financial_components = ("fundamentals", "balance_sheet", "income_statement", "cash_flow")
    if isinstance(financial, Mapping) and set(financial.get("source_components") or ()) == set(financial_components):
        latest = _selected_facts(financial.get("latest_period"), _FUNDAMENTAL_FACTS)
        if latest.get("report_period") and latest.get("announced_at") and all(_source_identity_present(sources.get(component)) for component in financial_components):
            output["fundamentals"] = {"latest_period": latest, "source_components": list(financial_components)}
    return output


def _partial_model(row: Mapping[str, Any], runtime_root: Path, companion: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if row.get("status") != "captured" or row.get("data_kind") != "real":
        raise ValueError("partial model requires a captured real official input")
    ticker = str(row.get("ticker") or "").upper()
    instrument = normalize_ashare_ticker(ticker)
    source_url = str(row.get("source_url") or "")
    parsed = urlsplit(source_url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in OFFICIAL_DOCUMENT_HOSTS:
        raise ValueError("partial model requires an allowlisted official document URL")
    raw_path = _inside(runtime_root, str(row.get("runtime_raw_path") or ""))
    if not raw_path.is_file():
        raise ValueError("runtime raw document is unavailable")
    raw_bytes = raw_path.read_bytes()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    if raw_hash != row.get("raw_hash") or not raw_bytes.startswith(b"%PDF"):
        raise ValueError("runtime raw document hash or PDF identity is invalid")
    known_at, fetched_at = str(row.get("known_at") or ""), str(row.get("fetched_at") or "")
    raw = RawCapture(
        raw_hash=raw_hash, storage_uri=str(row.get("storage_uri") or ""), source_url=source_url,
        fetched_at=fetched_at, known_at=known_at, mime_type="application/pdf", payload_size=len(raw_bytes),
    )
    raw.validate()
    manifest = SourceManifest(
        source_key=str(row.get("source_key") or ""), domain_scope=RecordDomain.DOCUMENT.value,
        authority_tier="official", provider_version="e4-s4c-runtime", schema_version="official-a-share-filing-v1",
        license_status="public_disclosure_internal_use", source_url=source_url,
    )
    manifest.validate()
    record = RecordEnvelope.accepted(
        domain=RecordDomain.DOCUMENT, entity_key=f"{instrument.instrument_id}:partial-model:{row['document_id']}",
        payload={
            "document_id": row["document_id"], "instrument_id": instrument.instrument_id,
            "document_type": row["document_type"], "published_at": row["published_at"],
            "content_hash": raw_hash, "storage_uri": raw.storage_uri, "title": "official filing runtime capture",
            "ticker": instrument.ticker, "source_role": "official_primary", "official_platform": manifest.source_key,
            "http_metadata": {"source_url": source_url, "fetched_at": fetched_at},
        }, manifest=manifest, raw=raw,
    )
    candidate = EvidenceCandidate.from_record(
        record, manifest, ticker=instrument.ticker, component="filings", role=EvidenceRole.PRIMARY,
        source_family="official-regulatory", effective_at=str(row["published_at"]), evidence_id="official-primary:" + raw_hash[:40],
    )
    evidence_set = build_evidence_set(
        ticker=instrument.ticker, candidates=(candidate,), policy=EvidenceGatePolicy(
            as_of=known_at, requirements=(EvidenceRequirement("filings", min_primary=1),),
        ),
    )
    context = build_context_pack(evidence_set)
    input_facts = _companion_display_facts(companion)
    material = {
        "schema_version": E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION, "ticker": instrument.ticker,
        "as_of": known_at,
        "evidence_set_id": context.evidence_set_id, "evidence_manifest_hash": context.manifest_hash,
        "raw_hash": raw_hash, "document_id": row["document_id"],
        "sections": {"filings": "available", "market": "available" if companion and companion.get("market_available") else "missing_evidence", "fundamentals": "available" if companion and companion.get("fundamentals_available") else "missing_evidence", "valuation": "missing_evidence", "sell_side": "missing_evidence", "industry_position": "missing_evidence"},
        "input_facts": input_facts,
        "decision_boundary": {"tier": "C", "action": "no_action", "target_price": None, "position_range": None},
    }
    model_hash = digest(material)
    return {**material, "report_model_hash": model_hash, "data_kind": "real", "numeric_spot_audit": False, "page_citation_spot_audit": False, "blockers": ["partial_model_missing_market_fundamentals_valuation_sell_side_industry_position"]}


def compile_partial_report_models(batch_receipt_path: Path, runtime_root: Path, companion_receipt_path: Path | None = None) -> dict[str, Any]:
    payload = json.loads(batch_receipt_path.read_text(encoding="utf-8"))
    boundary = payload.get("truth_boundary") or {}
    if payload.get("schema_version") != "e4-s4-official-evidence-batch-v1" or payload.get("data_kind") != "real" or boundary.get("counts_as_report_model_coverage") is not False:
        raise ValueError("partial model compiler requires a real E4-S4c input-only receipt")
    companion_rows: dict[str, Mapping[str, Any]] = {}
    if companion_receipt_path is not None:
        companion_rows = _companion_by_ticker(companion_receipt_path, payload)
        if json.loads(companion_receipt_path.read_text(encoding="utf-8")).get("official_receipt_sha256") != hashlib.sha256(batch_receipt_path.read_bytes()).hexdigest():
            raise ValueError("market companion receipt does not match official receipt lineage")
    rows = []
    for input_row in payload.get("tickers") or []:
        ticker = str(input_row.get("ticker") or "").upper()
        if not ticker:
            continue
        try:
            rows.append({"ticker": ticker, "status": "compiled", "model": _partial_model(input_row, runtime_root, companion_rows.get(ticker))})
        except Exception as exc:
            rows.append({"ticker": ticker, "status": "blocked", "blockers": ["partial_model_input_invalid"], "error": type(exc).__name__})
    coverage = {
        row["ticker"]: ({"data_kind": "real", "report_model_hash": row["model"]["report_model_hash"], "tier": "C", "numeric_spot_audit": False, "page_citation_spot_audit": False, "blockers": row["model"]["blockers"]} if row["status"] == "compiled" else {"data_kind": "real", "report_model_hash": None, "tier": "missing", "numeric_spot_audit": False, "page_citation_spot_audit": False, "blockers": row["blockers"]})
        for row in rows
    }
    receipt = {
        "schema_version": E4_PARTIAL_REPORT_MODEL_SCHEMA_VERSION, "input_receipt_sha256": hashlib.sha256(batch_receipt_path.read_bytes()).hexdigest(), "companion_receipt_sha256": hashlib.sha256(companion_receipt_path.read_bytes()).hexdigest() if companion_receipt_path else None,
        "data_kind": "real", "models": rows, "coverage": coverage,
        "counts": {"compiled_partial_models": sum(row["status"] == "compiled" for row in rows), "blocked": sum(row["status"] == "blocked" for row in rows)},
        "truth_boundary": {"tier_is_c_only": True, "counts_as_tier_a_or_b": False, "counts_as_numeric_page_audit": False, "not_a_full_equity_research_report": True},
    }
    receipt["receipt_hash"] = digest(receipt)
    return receipt


def write_partial_report_models(
    batch_receipt_path: Path, runtime_root: Path, companion_receipt_path: Path | None = None,
) -> dict[str, Any]:
    receipt = compile_partial_report_models(batch_receipt_path, runtime_root, companion_receipt_path)
    path = runtime_root / f"partial-report-models-{receipt['receipt_hash'][:16]}.json"
    _write_json(path, receipt)
    _write_json(runtime_root / "partial-report-models-latest.json", {"receipt": path.name, "receipt_hash": receipt["receipt_hash"]})
    return {"path": str(path), "receipt": receipt}
