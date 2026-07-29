"""Versioned, market-neutral contract for every renderable equity report."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from enum import Enum
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping
from urllib.parse import urlparse

from jsonschema import Draft202012Validator


SCHEMA_VERSION = "research-report-v1"
CONTRACT_VERSION = "1.0.0"
MODULE_STATUSES = {"available", "missing_evidence", "not_applicable"}
CLAIM_TYPES = ("fact", "inference", "assumption", "risk")


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    order: int
    anchor: str
    title: str
    kicker: str
    content_paths: tuple[str, ...]


MODULE_SPECS: tuple[ModuleSpec, ...] = (
    ModuleSpec("executive_summary", 1, "r-overview", "决策摘要", "INVESTMENT COMMITTEE", ("executive",)),
    ModuleSpec("investment_thesis", 2, "r-thesis", "核心投资逻辑", "THESIS", ("thesis",)),
    ModuleSpec(
        "business_and_industry", 3, "r-business", "经营、行业与竞争", "BUSINESS / INDUSTRY",
        ("business_model", "industry_position", "management"),
    ),
    ModuleSpec("financial_quality", 4, "r-financial", "财务质量", "FINANCIAL QUALITY", ("financials",)),
    ModuleSpec("framework_assessment", 5, "r-serenity", "研究框架评分", "FRAMEWORK", ("serenity",)),
    ModuleSpec("valuation", 6, "r-valuation", "估值框架", "VALUATION", ("valuation",)),
    ModuleSpec(
        "catalysts_risks", 7, "r-risks", "催化剂、风险与反证", "CATALYSTS / RISKS",
        ("catalysts", "risks", "falsification", "watchlist"),
    ),
    ModuleSpec(
        "evidence_ledger", 8, "r-evidence", "证据台账与方法", "EVIDENCE / METHOD",
        ("sources", "evidence_summary", "source_contract", "disclaimer"),
    ),
)


MARKET_POLICIES: dict[str, dict[str, str]] = {
    "CN": {"currency": "CNY", "reporting_standard": "PRC_GAAP", "cninfo_filings": "available", "sec_filings": "not_applicable"},
    "HK": {"currency": "HKD", "reporting_standard": "HKFRS_IFRS", "cninfo_filings": "not_applicable", "sec_filings": "not_applicable"},
    "US": {"currency": "USD", "reporting_standard": "US_GAAP", "cninfo_filings": "not_applicable", "sec_filings": "available"},
}

EXCHANGE_POLICIES: dict[str, set[str]] = {
    "SZ": {"深交所", "深圳证券交易所", "SZSE"},
    "SH": {"上交所", "上海证券交易所", "SSE"},
    "BJ": {"北交所", "北京证券交易所", "BSE"},
    "HK": {"港交所", "香港交易所", "HKEX"},
    "US": {"NASDAQ", "NYSE", "NYSE ARCA", "AMEX"},
}

US_SECURITY_MASTER: dict[str, dict[str, str]] = {
    "TSLA": {"exchange": "NASDAQ", "currency": "USD", "reporting_standard": "US_GAAP"},
}

HK_SECURITY_MASTER: dict[str, dict[str, str]] = {
    "00700.HK": {"exchange": "HKEX", "currency": "HKD", "reporting_standard": "HKFRS_IFRS"},
}

FINANCIAL_UNIT_LABELS = {"CNY": "亿元", "HKD": "亿港元", "USD": "亿美元"}


class ReportContractError(RuntimeError):
    pass


def infer_market(ticker: str) -> str:
    normalized = ticker.upper()
    if normalized.endswith((".SZ", ".SH", ".BJ")):
        return "CN"
    if normalized.endswith(".HK"):
        return "HK"
    if "." not in normalized:
        return "US"
    return "UNSUPPORTED"


def _market_disclosures(market: str) -> dict[str, dict[str, str]]:
    policy = MARKET_POLICIES[market]
    disclosures: dict[str, dict[str, str]] = {}
    for key in ("cninfo_filings", "sec_filings"):
        status = policy[key]
        disclosures[key] = {
            "status": status,
            "reason": (
                "This disclosure regime applies to the issuer market."
                if status == "available"
                else "Not applicable to the issuer market; do not map it to Missing evidence."
            ),
        }
    return disclosures


def _module_status(report: dict[str, Any], spec: ModuleSpec, *, structure_only: bool) -> tuple[str, str | None]:
    if structure_only:
        return "missing_evidence", "Structure truth set only; no live investment conclusion or evidence is asserted."
    depth = report.get("research_depth")
    if depth == "quantitative_baseline" and spec.id in {"business_and_industry", "valuation"}:
        return "missing_evidence", "Company-level evidence is not complete; the section renders its research boundary only."
    if spec.id == "valuation" and (report.get("valuation") or {}).get("status") in {
        "missing_evidence", "pending_company_research", "not_available",
    }:
        return "missing_evidence", str(
            (report.get("valuation") or {}).get("reason")
            or "Valuation evidence is incomplete; no target price is publishable."
        )
    return "available", None


def build_report_contract(
    report: dict[str, Any],
    *,
    market: str | None = None,
    currency: str | None = None,
    reporting_standard: str | None = None,
    structure_only: bool = False,
) -> dict[str, Any]:
    ticker = str(report.get("ticker") or "").upper()
    resolved_market = market or infer_market(ticker)
    if resolved_market not in MARKET_POLICIES:
        raise ReportContractError(f"unsupported issuer market: {resolved_market}")
    policy = MARKET_POLICIES[resolved_market]
    identity = {
        "ticker": ticker,
        "name": report.get("name"),
        "exchange": report.get("exchange"),
        "market": resolved_market,
        "currency": currency or policy["currency"],
        "reporting_standard": reporting_standard or policy["reporting_standard"],
    }
    modules = []
    for spec in MODULE_SPECS:
        status, reason = _module_status(report, spec, structure_only=structure_only)
        modules.append({
            "id": spec.id,
            "order": spec.order,
            "anchor": spec.anchor,
            "title": spec.title,
            "kicker": spec.kicker,
            "required": True,
            "status": status,
            "status_reason": reason,
            "content_paths": list(spec.content_paths),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "identity": identity,
        "as_of": {
            "market_data_at": report.get("market_known_at") or report.get("known_at") or report.get("as_of"),
            "research_cutoff": report.get("research_known_at") or report.get("known_at") or report.get("as_of"),
        },
        "measurement_policy": {
            "currency": identity["currency"],
            "price_currency": identity["currency"],
            "financial_presentation_currency": identity["currency"],
            "money_unit": "issuer_reporting_currency",
            "price_unit": "per_share",
            "financial_statement_scale": 100000000,
            "financial_statement_unit_label": FINANCIAL_UNIT_LABELS[identity["currency"]],
            "percent_unit": "percent",
            "percentage_point_unit": "percentage_point",
            "rule": "Every monetary field must inherit this currency or declare an explicit override; percent and percentage-point changes are never interchangeable.",
        },
        "claim_policy": {
            "allowed_types": list(CLAIM_TYPES),
            "fact_requires_source_ids": True,
            "inference_requires_source_ids": True,
            "assumption_requires_method": True,
            "risk_requires_trigger": True,
        },
        "absence_policy": {
            "missing_evidence": "The module applies, but current evidence is insufficient. It must remain visible with a reason.",
            "not_applicable": "The concept does not apply to this issuer or market. It must not be used as a synonym for missing data.",
        },
        "format_contract": {
            "module_order_is_authoritative": True,
            "same_order_desktop_mobile_print": True,
            "unknown_modules_fail_closed": True,
        },
        "market_specific_disclosures": _market_disclosures(resolved_market),
        "module_manifest": modules,
        "truth_set": {
            "scope": "structure_only" if structure_only else "runtime_report",
            "is_live_research": not structure_only,
            "note": (
                "Contract and format fixture only; not current data, valuation, rating, or position advice."
                if structure_only
                else "Runtime contract generated from the current report and its evidence gates."
            ),
        },
    }


def _path_value(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


@lru_cache(maxsize=2)
def _schema_validator(filename: str) -> Draft202012Validator:
    schema = json.loads((Path(__file__).with_name("schemas") / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _schema_errors(filename: str, value: dict[str, Any]) -> list[str]:
    errors = []
    for error in sorted(_schema_validator(filename).iter_errors(value), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(item) for item in error.absolute_path) or "$"
        errors.append(f"schema {path}: {error.message}")
    return errors


@lru_cache(maxsize=1)
def _public_ai_narrative_validator() -> Draft202012Validator:
    payload_schema = json.loads(
        (Path(__file__).with_name("schemas") / "research-report-payload-v1.schema.json").read_text(encoding="utf-8")
    )
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/aiNarrative",
        "$defs": payload_schema["$defs"],
    }
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def public_ai_narrative(narrative: dict[str, Any]) -> dict[str, Any]:
    """Project an approved artifact onto the exact non-executable public shape."""
    if not isinstance(narrative, dict):
        raise ReportContractError("public AI narrative must be an object")
    public = deepcopy(narrative)
    public.pop("position_conclusion", None)
    committee = public.get("investment_committee")
    if isinstance(committee, dict):
        committee.pop("decision", None)
    return public


def validate_public_ai_narrative(narrative: dict[str, Any]) -> list[str]:
    errors = []
    public = public_ai_narrative(narrative)
    for error in sorted(_public_ai_narrative_validator().iter_errors(public), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(item) for item in error.absolute_path) or "$"
        errors.append(f"public narrative schema {path}: {error.message}")
    return errors


def _parse_contract_time(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        if len(raw) == 10:
            parsed_date = datetime.fromisoformat(raw).date()
            return datetime.combine(parsed_date, time.max if end_of_day else time.min, tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _exchange_bucket(ticker: str) -> str:
    normalized = ticker.upper()
    for suffix in ("SZ", "SH", "BJ", "HK"):
        if normalized.endswith(f".{suffix}"):
            return suffix
    return "US" if "." not in normalized else "UNSUPPORTED"


def _validate_claims(report: dict[str, Any], *, research_cutoff: datetime | None) -> list[str]:
    errors: list[str] = []
    source_rows = report.get("sources") or []
    source_values = [str(item.get("id")) for item in source_rows if isinstance(item, dict) and item.get("id")]
    source_ids = set(source_values)
    if len(source_values) != len(source_ids):
        errors.append("source IDs must be unique")
    snapshot_id = str((report.get("generated_from") or {}).get("snapshot_id") or "")
    for index, source in enumerate(source_rows):
        if not isinstance(source, dict):
            continue
        source_path = f"report.sources[{index}]"
        for field in ("id", "document_id", "title", "kind", "strength", "known_at", "note"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append(f"{source_path} requires non-empty {field}")
        known_at = _parse_contract_time(source.get("known_at"), end_of_day=True)
        if known_at is None:
            errors.append(f"{source_path} known_at must be ISO date or timezone-aware datetime")
        elif research_cutoff is not None and known_at > research_cutoff:
            errors.append(f"{source_path} is newer than research cutoff")
        url = source.get("url")
        if url is not None:
            parsed_url = urlparse(str(url))
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                errors.append(f"{source_path} URL must use https")
        if source.get("kind") == "market_snapshot" and snapshot_id:
            if source.get("snapshot_id") != snapshot_id:
                errors.append(f"{source_path} is not bound to generated snapshot")
            if not source.get("provider"):
                errors.append(f"{source_path} requires provider")
            quote_time = _parse_contract_time(source.get("quote_time"))
            if quote_time is None:
                errors.append(f"{source_path} quote_time must be timezone-aware")
            elif known_at is not None and quote_time != known_at:
                errors.append(f"{source_path} quote_time disagrees with known_at")
        if source.get("id") == "financial_snapshot" and snapshot_id:
            if source.get("snapshot_id") != snapshot_id or not source.get("provider"):
                errors.append(f"{source_path} financial snapshot provenance is incomplete")
        manifest_hash = str((report.get("generated_from") or {}).get("evidence_manifest_hash") or "")
        if report.get("research_depth") == "deep" and source.get("kind") != "market_snapshot":
            if not manifest_hash or source.get("evidence_manifest_hash") != manifest_hash:
                errors.append(f"{source_path} is not bound to the frozen evidence manifest")

    def walk(value: Any, path: str = "report") -> None:
        if isinstance(value, dict):
            claim_type = value.get("claim_type")
            if claim_type is not None:
                if claim_type not in CLAIM_TYPES:
                    errors.append(f"{path} has unsupported claim_type")
                if claim_type in {"fact", "inference", "risk"} and not isinstance(value.get("source_ids"), list):
                    errors.append(f"{path} {claim_type} requires source_ids array")
                elif claim_type in {"fact", "inference", "risk"} and not value.get("source_ids"):
                    errors.append(f"{path} {claim_type} requires source_ids")
                if claim_type == "assumption" and not value.get("method"):
                    errors.append(f"{path} assumption requires method")
                if claim_type == "risk" and not value.get("trigger"):
                    errors.append(f"{path} risk requires trigger")
            referenced = value.get("source_ids")
            if "source_ids" in value and not isinstance(referenced, list):
                errors.append(f"{path} source_ids must be an array")
            elif isinstance(referenced, list):
                if not referenced or any(not isinstance(item, str) or not item for item in referenced):
                    errors.append(f"{path} source_ids must be non-empty strings")
                if len(referenced) != len(set(referenced)):
                    errors.append(f"{path} source_ids must be unique")
                unknown = sorted({str(item) for item in referenced} - source_ids)
                if unknown:
                    errors.append(f"{path} references unknown source_ids: {', '.join(unknown)}")
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(report)
    for index, risk in enumerate(report.get("risks") or []):
        if not isinstance(risk, dict) or not risk.get("trigger"):
            errors.append(f"report.risks[{index}] requires trigger")
        if not isinstance(risk, dict) or not risk.get("source_ids"):
            errors.append(f"report.risks[{index}] requires source_ids")
    source_contract = report.get("source_contract") or {}
    for key, references in source_contract.items():
        if not isinstance(references, list):
            errors.append(f"report.source_contract.{key} must be a source_ids array")
            continue
        unknown = sorted({str(item) for item in references} - source_ids)
        if unknown:
            errors.append(f"report.source_contract.{key} references unknown source_ids: {', '.join(unknown)}")
    evidence = report.get("evidence_summary") or {}
    document_ids = {str(item.get("document_id")) for item in source_rows if isinstance(item, dict) and item.get("document_id")}
    independent_document_ids = {
        str(item.get("document_id")) for item in source_rows
        if isinstance(item, dict) and item.get("kind") == "independent" and item.get("document_id")
    }
    expected_counts = {
        "claim_locator_count": len(source_rows),
        "document_count": len(document_ids),
        "independent_document_count": len(independent_document_ids),
        "primary_count": sum(isinstance(item, dict) and item.get("kind") in {"primary", "market_snapshot"} for item in source_rows),
        "company_release_count": sum(isinstance(item, dict) and item.get("kind") == "company_release" for item in source_rows),
    }
    for key, expected in expected_counts.items():
        if key in evidence and evidence.get(key) != expected:
            errors.append(f"report.evidence_summary.{key} does not match source ledger")
    if report.get("research_depth") == "deep":
        non_market_documents = {
            str(item.get("document_id")) for item in source_rows
            if isinstance(item, dict) and item.get("kind") != "market_snapshot" and item.get("document_id")
        }
        generated = report.get("generated_from") or {}
        if evidence.get("frozen_document_count") != len(non_market_documents):
            errors.append("report.evidence_summary.frozen_document_count does not match frozen sources")
        if evidence.get("frozen_manifest_hash") != generated.get("evidence_manifest_hash"):
            errors.append("report evidence manifest hash disagrees with generated identity")
        if evidence.get("frozen_evidence_set_id") != generated.get("evidence_set_id"):
            errors.append("report evidence set ID disagrees with generated identity")
    return errors


def validate_report_contract(contract: dict[str, Any], report: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = _schema_errors("research-report-v1.schema.json", contract)
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be research-report-v1")
    if contract.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version is unsupported")
    identity = contract.get("identity") or {}
    ticker = str(identity.get("ticker") or "").upper()
    market = identity.get("market")
    if not ticker or not identity.get("name") or not identity.get("exchange"):
        errors.append("identity requires ticker, name, and exchange")
    exchange_bucket = _exchange_bucket(ticker)
    if exchange_bucket not in EXCHANGE_POLICIES or identity.get("exchange") not in EXCHANGE_POLICIES[exchange_bucket]:
        errors.append("exchange does not match ticker listing")
    if exchange_bucket == "US":
        security = US_SECURITY_MASTER.get(ticker)
        if security is None:
            errors.append("US issuer identity is not registered in the v1 security master")
        elif any(identity.get(key) != value for key, value in security.items()):
            errors.append("US issuer identity disagrees with the v1 security master")
    if exchange_bucket == "HK":
        security = HK_SECURITY_MASTER.get(ticker)
        if security is None:
            errors.append("HK issuer identity is not registered in the v1 security master")
        elif any(identity.get(key) != value for key, value in security.items()):
            errors.append("HK issuer identity disagrees with the v1 security master")
    if market not in MARKET_POLICIES:
        errors.append("identity market is unsupported")
    else:
        policy = MARKET_POLICIES[market]
        if infer_market(ticker) != market:
            errors.append("ticker and issuer market disagree")
        if identity.get("currency") != policy["currency"]:
            errors.append("currency does not match issuer market")
        if identity.get("reporting_standard") != policy["reporting_standard"]:
            errors.append("reporting standard does not match issuer market")
        if (contract.get("measurement_policy") or {}).get("currency") != identity.get("currency"):
            errors.append("measurement currency disagrees with identity")
        measurement = contract.get("measurement_policy") or {}
        if measurement.get("price_currency") != identity.get("currency") or measurement.get("financial_presentation_currency") != identity.get("currency"):
            errors.append("price or financial presentation currency disagrees with identity")
        if measurement.get("money_unit") != "issuer_reporting_currency":
            errors.append("money unit semantics changed")
        if measurement.get("price_unit") != "per_share" or measurement.get("financial_statement_scale") != 100000000:
            errors.append("monetary scale semantics changed")
        if measurement.get("financial_statement_unit_label") != FINANCIAL_UNIT_LABELS[identity.get("currency")]:
            errors.append("financial statement unit label disagrees with currency")
        if measurement.get("percent_unit") != "percent" or measurement.get("percentage_point_unit") != "percentage_point":
            errors.append("percent and percentage-point semantics changed")
        disclosures = contract.get("market_specific_disclosures") or {}
        for key in ("cninfo_filings", "sec_filings"):
            value = disclosures.get(key) or {}
            if value.get("status") != policy[key]:
                errors.append(f"{key} status does not match issuer market")
            if value.get("status") != "available" and not value.get("reason"):
                errors.append(f"{key} requires a not-applicable reason")
    claim_types = tuple((contract.get("claim_policy") or {}).get("allowed_types") or [])
    if claim_types != CLAIM_TYPES:
        errors.append("claim type semantics changed")
    modules = contract.get("module_manifest") or []
    expected_ids = [spec.id for spec in MODULE_SPECS]
    expected_orders = [spec.order for spec in MODULE_SPECS]
    if [item.get("id") for item in modules] != expected_ids:
        errors.append("module IDs or order do not match research-report-v1")
    if [item.get("order") for item in modules] != expected_orders:
        errors.append("module order values are invalid")
    if len({item.get("anchor") for item in modules}) != len(MODULE_SPECS):
        errors.append("module anchors must be unique")
    for spec, module in zip(MODULE_SPECS, modules):
        if (
            module.get("anchor") != spec.anchor
            or module.get("title") != spec.title
            or module.get("kicker") != spec.kicker
            or module.get("content_paths") != list(spec.content_paths)
        ):
            errors.append(f"{spec.id} rendering contract changed")
        if module.get("required") is not True:
            errors.append(f"{spec.id} must remain required")
        status = module.get("status")
        if status not in MODULE_STATUSES:
            errors.append(f"{spec.id} has unsupported status")
        if status != "available" and not module.get("status_reason"):
            errors.append(f"{spec.id} requires a visible absence reason")
        if report is not None and status == "available":
            missing = [path for path in spec.content_paths if _path_value(report, path) in (None, "", [], {})]
            if missing:
                errors.append(f"{spec.id} is available but content is missing: {', '.join(missing)}")
        if report is not None:
            structure_only = (contract.get("truth_set") or {}).get("scope") == "structure_only"
            expected_status, expected_reason = _module_status(report, spec, structure_only=structure_only)
            if status != expected_status:
                errors.append(
                    f"{spec.id} status disagrees with report evidence state: expected {expected_status}"
                )
            if expected_status != "available" and module.get("status_reason") != expected_reason:
                errors.append(f"{spec.id} absence reason disagrees with report evidence state")
    if report is not None:
        errors.extend(_schema_errors("research-report-payload-v1.schema.json", report))
        if (
            ticker != str(report.get("ticker") or "").upper()
            or identity.get("name") != report.get("name")
            or identity.get("exchange") != report.get("exchange")
        ):
            errors.append("contract identity does not match report payload")
        valuation_currency = (report.get("valuation") or {}).get("currency")
        if valuation_currency and valuation_currency != identity.get("currency"):
            errors.append("valuation currency disagrees with report contract")
        expected_currency = identity.get("currency")

        def check_currency(value: Any, path: str = "report") -> None:
            if isinstance(value, dict):
                explicit = value.get("currency")
                if explicit is not None and explicit != expected_currency:
                    errors.append(f"{path}.currency disagrees with report contract")
                for key, child in value.items():
                    check_currency(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    check_currency(child, f"{path}[{index}]")

        check_currency(report)
    truth_set = contract.get("truth_set") or {}
    as_of = contract.get("as_of") or {}
    market_data_at = _parse_contract_time(as_of.get("market_data_at"))
    research_cutoff = _parse_contract_time(as_of.get("research_cutoff"))
    if truth_set.get("scope") == "runtime_report" and (not as_of.get("market_data_at") or not as_of.get("research_cutoff")):
        errors.append("runtime report requires market and research cutoffs")
    if truth_set.get("scope") == "runtime_report" and (market_data_at is None or research_cutoff is None):
        errors.append("runtime report cutoffs must be timezone-aware ISO datetimes")
    if market_data_at is not None and research_cutoff is not None and market_data_at > research_cutoff:
        errors.append("market data time cannot be newer than research cutoff")
    if research_cutoff is not None and research_cutoff > datetime.now(timezone.utc).replace(microsecond=0):
        errors.append("research cutoff cannot be in the future")
    if truth_set.get("scope") == "runtime_report" and truth_set.get("is_live_research") is not True:
        errors.append("runtime report must identify itself as live research")
    if truth_set.get("scope") == "structure_only" and truth_set.get("is_live_research") is not False:
        errors.append("structure truth set cannot claim live research")
    if report is not None:
        errors.extend(_validate_claims(report, research_cutoff=research_cutoff))
    return sorted(set(errors))


def attach_report_contract(report: dict[str, Any], *, structure_only: bool = False) -> dict[str, Any]:
    payload = deepcopy(report)
    payload.setdefault(
        "disclaimer",
        "本报告用于研究框架与模型组合讨论，不构成投资建议。事实、推断和估值假设已分层；公司公告能证明公司披露了什么，但不自动证明未来一定兑现。",
    )
    contract = build_report_contract(payload, structure_only=structure_only)
    payload.setdefault("valuation", {})["currency"] = contract["identity"]["currency"]
    payload["report_contract"] = contract
    errors = validate_report_contract(contract, payload)
    if errors:
        raise ReportContractError("report contract rejected: " + "; ".join(errors))
    return payload


def build_structure_truth_set(*, ticker: str, name: str, exchange: str, market: str) -> dict[str, Any]:
    return build_report_contract(
        {"ticker": ticker, "name": name, "exchange": exchange},
        market=market,
        structure_only=True,
    )


# Research Section Contract v2 is additive while the v1 renderer migrates.
SECTION_CONTRACT_SCHEMA_VERSION = "research-section-contract-v2"
SECTION_CONTRACT_VERSION = "2.0.0"


class SectionCompletion(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    MISSING = "missing"


@dataclass(frozen=True)
class SectionInputSpec:
    key: str
    value_type: str
    description: str

    def validate(self) -> None:
        if not all((self.key.strip(), self.value_type.strip(), self.description.strip())):
            raise ValueError("section input identity fields are required")
        if self.value_type not in {"object", "array", "string", "number", "boolean"}:
            raise ValueError(f"unsupported section input type: {self.value_type}")


@dataclass(frozen=True)
class ResearchSectionSpec:
    section_id: str
    order: int
    title: str
    purpose: str
    required_inputs: tuple[SectionInputSpec, ...]
    optional_inputs: tuple[SectionInputSpec, ...]
    page_budget: tuple[int, int]
    origins: tuple[str, ...]

    def validate(self) -> None:
        if not all((self.section_id.strip(), self.title.strip(), self.purpose.strip())):
            raise ValueError("section identity fields are required")
        if type(self.order) is not int or self.order < 1:
            raise ValueError("section order must be a positive int")
        if not self.required_inputs:
            raise ValueError(f"{self.section_id} must declare required inputs")
        inputs = self.required_inputs + self.optional_inputs
        for item in inputs:
            item.validate()
        keys = [item.key for item in inputs]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.section_id} repeats an input key")
        minimum, maximum = self.page_budget
        if type(minimum) is not int or type(maximum) is not int or minimum < 1 or maximum < minimum:
            raise ValueError(f"{self.section_id} page budget is invalid")
        if not self.origins or not all(value.strip() for value in self.origins):
            raise ValueError(f"{self.section_id} must identify its taxonomy origin")

    @property
    def section_hash(self) -> str:
        self.validate()
        return _section_digest(self.identity_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "order": self.order,
            "title": self.title,
            "purpose": self.purpose,
            "required_inputs": [item.__dict__ for item in self.required_inputs],
            "optional_inputs": [item.__dict__ for item in self.optional_inputs],
            "page_budget": list(self.page_budget),
            "origins": list(self.origins),
        }


@dataclass(frozen=True)
class ResearchReportProfile:
    profile_id: str
    profile_version: str
    market: str
    section_ids: tuple[str, ...]
    optional_modules: tuple[str, ...] = ()

    def validate(self, specs: tuple[ResearchSectionSpec, ...]) -> None:
        if not all((self.profile_id.strip(), self.profile_version.strip(), self.market.strip())):
            raise ValueError("profile identity fields are required")
        known = {item.section_id for item in specs}
        if set(self.section_ids) != known or len(self.section_ids) != len(known):
            raise ValueError("profile must contain every canonical section exactly once")
        if self.section_ids != tuple(item.section_id for item in specs):
            raise ValueError("profile section order must match the canonical contract")

    def profile_hash(self, specs: tuple[ResearchSectionSpec, ...]) -> str:
        self.validate(specs)
        return _section_digest(
            {
                "profile_id": self.profile_id,
                "profile_version": self.profile_version,
                "market": self.market,
                "section_ids": list(self.section_ids),
                "optional_modules": list(self.optional_modules),
                "section_hashes": [item.section_hash for item in specs],
            }
        )


@dataclass(frozen=True)
class SectionAssessment:
    section_id: str
    order: int
    title: str
    status: SectionCompletion
    present_required: tuple[str, ...]
    missing_required: tuple[str, ...]
    present_optional: tuple[str, ...]
    missing_optional: tuple[str, ...]
    status_reason: str | None
    pending_judgment_inputs: tuple[str, ...]
    page_budget: tuple[int, int]
    section_hash: str
    profile_hash: str
    version_hash: str
    input_hash: str


@dataclass(frozen=True)
class ResearchSectionContract:
    schema_version: str
    contract_version: str
    contract_hash: str
    version_hash: str
    profile_id: str
    profile_version: str
    profile_hash: str
    evidence_set_id: str | None
    evidence_manifest_hash: str | None
    live_eligible: bool
    sections: tuple[SectionAssessment, ...]
    total_page_budget: tuple[int, int]


def _section_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _input(key: str, value_type: str, description: str) -> SectionInputSpec:
    return SectionInputSpec(key, value_type, description)


RESEARCH_SECTION_SPECS_V2: tuple[ResearchSectionSpec, ...] = (
    ResearchSectionSpec(
        "executive_summary", 1, "一页决策摘要", "用可复算的事实、估值与风险边界给出结论先行的阅读入口。",
        (_input("market_snapshot", "object", "带时点的价格、市值与估值快照"), _input("decision_summary", "object", "政策引擎生成的结论摘要")),
        (_input("key_chart", "object", "最能解释当前判断的一张核心图"),), (2, 3), ("rolling:chapter-1",),
    ),
    ResearchSectionSpec(
        "investment_thesis", 2, "投资逻辑与预期差", "明确多空逻辑、市场隐含假设、独立判断与可证伪差异。",
        (_input("investment_thesis", "object", "主论点与证据链"), _input("variant_view", "object", "相对市场共识的差异")),
        (_input("bear_case", "object", "最强反方论点"),), (2, 3), ("rolling:chapters-1-9", "day1:variant-view"),
    ),
    ResearchSectionSpec(
        "business_model", 3, "业务模式与收入结构", "解释公司靠什么赚钱、收入确认、分部结构、客户和价值链位置。",
        (_input("company_profile", "object", "公司与业务边界"), _input("segment_financials", "array", "分部收入和利润序列")),
        (_input("customer_concentration", "object", "客户集中度"), _input("partner_ecosystem", "object", "合作伙伴生态")), (2, 3), ("rolling:chapter-2", "day1:partner-ecosystem"),
    ),
    ResearchSectionSpec(
        "industry_structure", 4, "行业空间与价值链", "界定 TAM、周期位置、供需结构、产业链利润池与行业分类口径。",
        (_input("industry_profile", "object", "行业分类与生命周期"), _input("market_size", "object", "TAM、增速和口径")),
        (_input("value_chain", "array", "产业链分层和利润池"),), (2, 3), ("rolling:chapter-3",),
    ),
    ResearchSectionSpec(
        "competition_and_moat", 5, "竞争格局与护城河", "用份额、同业差异和长期资本回报验证竞争优势。",
        (_input("peer_comparison", "array", "口径可比的同行矩阵"), _input("moat_assessment", "object", "护城河来源、强度和证据")),
        (_input("competitive_events", "array", "近期竞争或并购变化"),), (2, 3), ("rolling:chapter-3", "day1:competition"),
    ),
    ResearchSectionSpec(
        "management_and_governance", 6, "管理层、治理与资本配置", "评估管理层记录、激励、股东结构、分红回购、并购和治理红旗。",
        (_input("management_record", "object", "核心管理层履历与经营记录"), _input("governance_events", "array", "治理、关联交易和信披事件")),
        (_input("ownership_structure", "object", "股东与内部人持股"), _input("capital_allocation", "object", "历史资本配置回报")), (2, 3), ("rolling:chapter-4", "day1:executives-ownership"),
    ),
    ResearchSectionSpec(
        "revenue_quality_and_kpis", 7, "收入质量与经营 KPI", "拆解量价组合、内生增长、客户/地区质量和行业核心 KPI。",
        (_input("revenue_history", "array", "多期收入与增长桥"), _input("operating_kpis", "array", "行业核心 KPI 与定义")),
        (_input("guidance_history", "array", "管理层指引与兑现记录"), _input("rd_efficiency", "object", "研发投入与转化效率")), (2, 3), ("rolling:chapters-2-5", "day1:modules-A-D-F-N"),
    ),
    ResearchSectionSpec(
        "profitability_and_earnings_quality", 8, "盈利能力与利润质量", "解释毛利、费用、利润率、GAAP/Non-GAAP 和利润驱动是否可持续。",
        (_input("income_history", "array", "多期利润表和利润率"), _input("margin_bridge", "object", "利润率变化桥")),
        (_input("adjusted_earnings_bridge", "object", "调整项和股权激励"),), (2, 3), ("rolling:chapter-5", "day1:modules-B"),
    ),
    ResearchSectionSpec(
        "cash_flow_and_balance_sheet", 9, "现金流与资产负债表", "验证利润含金量、营运资本、资本开支、负债和流动性韧性。",
        (_input("cash_flow_history", "array", "经营现金流、资本开支与自由现金流"), _input("balance_sheet_history", "array", "现金、负债和营运资本")),
        (_input("liquidity_stress", "object", "压力情景与融资需求"),), (2, 3), ("rolling:chapter-5", "day1:module-C"),
    ),
    ResearchSectionSpec(
        "accounting_quality", 10, "会计质量与审计检查", "检查应计、收入确认、减值、表外项目、重述和审计意见。",
        (_input("accounting_checks", "array", "会计质量检查结果"), _input("audit_opinions", "array", "审计意见与重大事项")),
        (_input("restatement_history", "array", "重述和口径变更"),), (1, 2), ("day1:module-O",),
    ),
    ResearchSectionSpec(
        "forecasts_and_consensus", 11, "盈利预测、共识与修订", "展示券商逐篇预测、共识区间、离散度、修订方向和 Park 模型桥。",
        (_input("broker_estimates", "array", "逐券商逐年度预测"), _input("consensus_history", "array", "可回放共识和修订")),
        (_input("forecast_model", "object", "Park 确定性预测模型"), _input("guidance_vs_consensus", "object", "指引相对共识")), (2, 3), ("rolling:chapter-7", "day1:modules-D"),
    ),
    ResearchSectionSpec(
        "valuation", 12, "估值与市场隐含预期", "用至少三类可执行方法交叉验证价值区间、敏感性和安全边际。",
        (_input("valuation_scenarios", "array", "bear/base/bull 估值情景"), _input("valuation_assumptions", "object", "模型假设和版本"), _input("current_market", "object", "现价和估值基准")),
        (_input("reverse_dcf", "object", "现价隐含假设"), _input("sotp", "object", "分部估值"), _input("epv", "object", "盈利能力价值")), (3, 4), ("rolling:chapter-6", "day1:module-K"),
    ),
    ResearchSectionSpec(
        "macro_policy_and_costs", 13, "宏观、政策与成本传导", "把利率、汇率、政策和原材料变化连接到收入、利润率与估值。",
        (_input("macro_exposures", "object", "宏观敏感性和传导链"), _input("policy_events", "array", "政策原文与公司影响")),
        (_input("commodity_sensitivity", "object", "原材料和套保敏感性"),), (1, 2), ("day1:module-J", "uzi:qualitative-3-8-9-13"),
    ),
    ResearchSectionSpec(
        "catalysts_and_events", 14, "事件、催化剂与时间表", "区分已发生证据与未来催化，量化可能影响和兑现窗口。",
        (_input("event_timeline", "array", "已去重且有原文证据的事件"), _input("catalyst_calendar", "array", "未来催化日期与机制")),
        (_input("event_impact_inference", "array", "版本化事件影响推断"),), (1, 2), ("rolling:chapter-8", "day1:catalyst"),
    ),
    ResearchSectionSpec(
        "risks_and_falsification", 15, "风险、反证与 Kill Conditions", "给出最强反方证据、具体触发阈值和论点失效条件。",
        (_input("risk_register", "array", "带概率、影响和证据的风险"), _input("falsification_tests", "array", "可观察反证和 kill conditions")),
        (_input("bias_check", "object", "反偏见检查"), _input("esg_screen", "object", "重大 ESG 风险筛查")), (2, 3), ("rolling:chapters-3-9", "day1:modules-M-P"),
    ),
    ResearchSectionSpec(
        "decision_framework", 16, "结论、目标价与仓位框架", "消费可审计政策输出，固定动作、目标价窗口、仓位边界和否决项。",
        (_input("recommendation_policy_output", "object", "C5 策略引擎的结论、目标价和仓位输出"),),
        (_input("committee_synthesis", "object", "不覆盖政策输出的投委会解释"),), (1, 2), ("rolling:chapters-1-9", "day1:action-system"),
    ),
    ResearchSectionSpec(
        "monitoring_and_action_triggers", 17, "跟踪指标与行动触发器", "把论点转成持续覆盖所需的 KPI、阈值、频率和下一步动作。",
        (_input("monitoring_kpis", "array", "3–8 个关键跟踪指标"), _input("action_triggers", "array", "加仓、减仓、退出和复核条件")),
        (_input("next_update_calendar", "array", "下次财报和数据刷新计划"),), (1, 2), ("rolling:chapter-9", "day1:modules-M"),
    ),
    ResearchSectionSpec(
        "evidence_and_methodology", 18, "证据台账、方法与附录", "列出 evidence set、页级引用、覆盖缺口、模型版本和方法限制。",
        (_input("evidence_set_receipt", "object", "B6 evidence/gate identity"), _input("citation_index", "array", "document/page/raw hash 引用索引"), _input("methodology", "object", "计算方法和版本")),
        (_input("coverage_gaps", "array", "required/optional 缺口"), _input("industry_appendix", "object", "profile 选择的行业 KPI 附录")), (2, 3), ("rolling:source-appendix", "park:B3-B6"),
    ),
)


A_SHARE_GENERAL_PROFILE_V1 = ResearchReportProfile(
    profile_id="a-share-general",
    profile_version="1.0.0",
    market="CN",
    section_ids=tuple(item.section_id for item in RESEARCH_SECTION_SPECS_V2),
    optional_modules=("industry_kpi_appendix", "earnings_update_bridge", "ah_listing_comparison"),
)


def _input_present(value: Any) -> bool:
    return value not in (None, "", (), [], {})


def _input_type_matches(value: Any, value_type: str) -> bool:
    if value_type == "object":
        return isinstance(value, dict)
    if value_type == "array":
        return isinstance(value, (list, tuple))
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == "boolean":
        return isinstance(value, bool)
    return False


UNREVIEWED_JUDGMENT_STATUS = "ai_generated_judgment_unreviewed"


def _contains_unreviewed_judgment(value: Any) -> bool:
    """Return whether a supplied C1 input is backed only by an AI draft.

    This checks data status, rather than the module that happened to create an
    object.  A later human-reviewed revision may retain the same evidence and
    text, but must carry a different review status before it can complete a
    section.
    """
    if isinstance(value, dict):
        if value.get("status") == UNREVIEWED_JUDGMENT_STATUS:
            return True
        return any(_contains_unreviewed_judgment(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_unreviewed_judgment(item) for item in value)
    return False


def assess_research_section(
    spec: ResearchSectionSpec,
    values: Mapping[str, Any],
    *,
    profile_hash: str,
    version_hash: str,
) -> SectionAssessment:
    spec.validate()
    known = {item.key: item for item in spec.required_inputs + spec.optional_inputs}
    unknown = sorted(set(values).difference(known))
    if unknown:
        raise ReportContractError(f"{spec.section_id} received unknown inputs: {', '.join(unknown)}")
    for key, value in values.items():
        if _input_present(value) and not _input_type_matches(value, known[key].value_type):
            raise ReportContractError(
                f"{spec.section_id}.{key} must be {known[key].value_type}"
            )
    present_required = tuple(item.key for item in spec.required_inputs if _input_present(values.get(item.key)))
    missing_required = tuple(item.key for item in spec.required_inputs if item.key not in present_required)
    present_optional = tuple(item.key for item in spec.optional_inputs if _input_present(values.get(item.key)))
    missing_optional = tuple(item.key for item in spec.optional_inputs if item.key not in present_optional)
    pending_judgment_inputs = tuple(
        key for key in present_required if _contains_unreviewed_judgment(values[key])
    )
    if not missing_required:
        status = SectionCompletion.PARTIAL if pending_judgment_inputs else SectionCompletion.FULL
    elif present_required or present_optional:
        status = SectionCompletion.PARTIAL
    else:
        status = SectionCompletion.MISSING
    status_reason = "pending_judgment_review" if pending_judgment_inputs else None
    supplied = {key: values[key] for key in sorted(values) if _input_present(values[key])}
    return SectionAssessment(
        section_id=spec.section_id,
        order=spec.order,
        title=spec.title,
        status=status,
        present_required=present_required,
        missing_required=missing_required,
        present_optional=present_optional,
        missing_optional=missing_optional,
        status_reason=status_reason,
        pending_judgment_inputs=pending_judgment_inputs,
        page_budget=spec.page_budget,
        section_hash=spec.section_hash,
        profile_hash=profile_hash,
        version_hash=version_hash,
        input_hash=_section_digest(supplied),
    )


def build_research_section_contract_v2(
    section_inputs: Mapping[str, Mapping[str, Any]],
    *,
    profile: ResearchReportProfile = A_SHARE_GENERAL_PROFILE_V1,
    structure_only: bool = True,
    evidence_set: Any | None = None,
) -> ResearchSectionContract:
    for spec in RESEARCH_SECTION_SPECS_V2:
        spec.validate()
    orders = [item.order for item in RESEARCH_SECTION_SPECS_V2]
    if orders != list(range(1, len(RESEARCH_SECTION_SPECS_V2) + 1)):
        raise ReportContractError("research section orders must be contiguous")
    profile.validate(RESEARCH_SECTION_SPECS_V2)
    unknown_sections = sorted(set(section_inputs).difference(profile.section_ids))
    if unknown_sections:
        raise ReportContractError("unknown research sections: " + ", ".join(unknown_sections))
    profile_hash = profile.profile_hash(RESEARCH_SECTION_SPECS_V2)
    version_hash = _section_digest(
        {
            "schema_version": SECTION_CONTRACT_SCHEMA_VERSION,
            "contract_version": SECTION_CONTRACT_VERSION,
        }
    )
    contract_hash = _section_digest(
        {
            "version_hash": version_hash,
            "profile_hash": profile_hash,
            "section_hashes": [item.section_hash for item in RESEARCH_SECTION_SPECS_V2],
        }
    )
    assessments = tuple(
        assess_research_section(
            spec,
            section_inputs.get(spec.section_id, {}),
            profile_hash=profile_hash,
            version_hash=version_hash,
        )
        for spec in RESEARCH_SECTION_SPECS_V2
    )
    evidence_set_id = getattr(evidence_set, "evidence_set_id", None)
    evidence_manifest_hash = getattr(evidence_set, "manifest_hash", None)
    evidence_passed = bool(evidence_set is not None and getattr(evidence_set, "publishable", False))
    if not structure_only and not evidence_passed:
        raise ReportContractError("live section contract requires a B6-passed evidence set")
    minimum_pages = sum(item.page_budget[0] for item in RESEARCH_SECTION_SPECS_V2)
    maximum_pages = sum(item.page_budget[1] for item in RESEARCH_SECTION_SPECS_V2)
    if not 30 <= minimum_pages <= maximum_pages <= 50:
        raise ReportContractError("canonical report page budget must stay within 30–50 pages")
    return ResearchSectionContract(
        schema_version=SECTION_CONTRACT_SCHEMA_VERSION,
        contract_version=SECTION_CONTRACT_VERSION,
        contract_hash=contract_hash,
        version_hash=version_hash,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_hash=profile_hash,
        evidence_set_id=evidence_set_id,
        evidence_manifest_hash=evidence_manifest_hash,
        live_eligible=not structure_only and evidence_passed,
        sections=assessments,
        total_page_budget=(minimum_pages, maximum_pages),
    )


# Deterministic Financial & Valuation Engine v1. Calculations live beside the
# report contract until C-series compiler modules are split into packages.
VALUATION_ENGINE_VERSION = "deterministic-valuation-v1"


@dataclass(frozen=True)
class HistoricalFinancialPeriod:
    period: str
    currency: str
    revenue: float
    ebit: float
    tax_rate: float
    depreciation_amortization: float
    capital_expenditure: float
    change_in_nwc: float
    operating_cash_flow: float
    net_income: float
    cash: float
    debt: float
    assets: float
    liabilities: float
    equity: float
    shares_outstanding: float
    share_event: bool = False

    def validate(self) -> None:
        if not self.period.strip() or not self.currency.strip():
            raise ReportContractError("financial period and currency are required")
        values = asdict(self)
        for key, value in values.items():
            if key in {"period", "currency", "share_event"}:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ReportContractError(f"{self.period}.{key} must be numeric")
        if not 0 <= self.tax_rate <= 1:
            raise ReportContractError(f"{self.period}.tax_rate must be between 0 and 1")
        if self.revenue <= 0 or self.assets <= 0 or self.shares_outstanding <= 0:
            raise ReportContractError(f"{self.period} revenue/assets/shares must be positive")
        imbalance = abs(self.assets - self.liabilities - self.equity)
        if imbalance > max(0.01, abs(self.assets) * 0.005):
            raise ReportContractError(f"{self.period} balance sheet does not balance")


@dataclass(frozen=True)
class FinancialBridgeRow:
    period: str
    revenue: float
    nopat: float
    unlevered_fcf: float
    reported_fcf: float
    cash_conversion: float | None
    net_debt: float
    balance_check: float
    shares_outstanding: float


@dataclass(frozen=True)
class ValuationScenarioAssumptions:
    name: str
    probability: float
    revenue_growth: tuple[float, ...]
    ebit_margin: tuple[float, ...]
    tax_rate: float
    depreciation_pct_revenue: float
    capex_pct_revenue: float
    nwc_investment_pct_revenue: float
    wacc: float
    terminal_growth: float

    def validate(self) -> None:
        if self.name not in {"bear", "base", "bull"}:
            raise ReportContractError("valuation scenarios must be bear/base/bull")
        if len(self.revenue_growth) < 3 or len(self.revenue_growth) != len(self.ebit_margin):
            raise ReportContractError(f"{self.name} forecast arrays must have the same 3+ year horizon")
        if not 0 < self.probability < 1:
            raise ReportContractError(f"{self.name} probability must be between 0 and 1")
        if not all(-0.8 < value < 2 for value in self.revenue_growth):
            raise ReportContractError(f"{self.name} revenue growth assumption is out of bounds")
        if not all(-1 < value < 1 for value in self.ebit_margin):
            raise ReportContractError(f"{self.name} EBIT margin assumption is out of bounds")
        if not 0 <= self.tax_rate <= 1:
            raise ReportContractError(f"{self.name} tax rate is invalid")
        if not 0 < self.wacc < 0.5 or not -0.05 < self.terminal_growth < self.wacc:
            raise ReportContractError(f"{self.name} WACC/terminal growth is invalid")
        for field in (
            "depreciation_pct_revenue", "capex_pct_revenue", "nwc_investment_pct_revenue"
        ):
            if not -0.5 < getattr(self, field) < 0.5:
                raise ReportContractError(f"{self.name}.{field} is out of bounds")

    @property
    def assumption_hash(self) -> str:
        self.validate()
        return _section_digest(asdict(self))


@dataclass(frozen=True)
class ValuationEngineInput:
    ticker: str
    currency: str
    unit_scale: int
    current_price: float
    market_cap: float
    shares_outstanding: float
    historical: tuple[HistoricalFinancialPeriod, ...]
    scenarios: tuple[ValuationScenarioAssumptions, ...]
    peer_ev_ebitda: tuple[float, ...]
    historical_pe: tuple[float, ...]

    def validate(self) -> None:
        if not self.ticker.strip() or not self.currency.strip():
            raise ReportContractError("valuation ticker and currency are required")
        if type(self.unit_scale) is not int or self.unit_scale not in {1, 1000, 10000, 1000000, 100000000}:
            raise ReportContractError("unsupported financial unit scale")
        if self.current_price <= 0 or self.market_cap <= 0 or self.shares_outstanding <= 0:
            raise ReportContractError("price, market cap and shares must be positive")
        implied_market_cap = self.current_price * self.shares_outstanding
        if abs(implied_market_cap - self.market_cap) / self.market_cap > 0.02:
            raise ReportContractError("price, market cap and share count are inconsistent")
        if len(self.historical) < 2:
            raise ReportContractError("at least two historical financial periods are required")
        periods = [item.period for item in self.historical]
        if periods != sorted(periods) or len(periods) != len(set(periods)):
            raise ReportContractError("historical periods must be unique and ascending")
        previous_shares = None
        for item in self.historical:
            item.validate()
            if item.currency != self.currency:
                raise ReportContractError("historical currency mismatch")
            if previous_shares is not None:
                change = abs(item.shares_outstanding / previous_shares - 1)
                if change > 0.5 and not item.share_event:
                    raise ReportContractError("share-count jump requires an explicit share event")
            previous_shares = item.shares_outstanding
        if abs(self.historical[-1].shares_outstanding - self.shares_outstanding) / self.shares_outstanding > 0.02:
            raise ReportContractError("latest financial share count disagrees with valuation input")
        if {item.name for item in self.scenarios} != {"bear", "base", "bull"} or len(self.scenarios) != 3:
            raise ReportContractError("exactly one bear/base/bull scenario is required")
        for scenario in self.scenarios:
            scenario.validate()
        if abs(sum(item.probability for item in self.scenarios) - 1) > 1e-9:
            raise ReportContractError("scenario probabilities must sum to 1")
        if any(value <= 0 or value > 200 for value in self.peer_ev_ebitda + self.historical_pe):
            raise ReportContractError("valuation multiple is out of bounds")

    @property
    def input_hash(self) -> str:
        self.validate()
        return _section_digest(asdict(self))


@dataclass(frozen=True)
class DCFScenarioResult:
    name: str
    probability: float
    assumption_hash: str
    revenues: tuple[float, ...]
    unlevered_fcf: tuple[float, ...]
    enterprise_value: float
    equity_value: float
    per_share_value: float


@dataclass(frozen=True)
class ValuationMethodResult:
    method: str
    per_share_value: float
    currency: str
    unit: str
    inputs_hash: str


@dataclass(frozen=True)
class SensitivityTable:
    wacc_values: tuple[float, ...]
    terminal_growth_values: tuple[float, ...]
    per_share_values: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class DeterministicValuationResult:
    engine_version: str
    input_hash: str
    currency: str
    financial_bridge: tuple[FinancialBridgeRow, ...]
    scenario_results: tuple[DCFScenarioResult, ...]
    methods: tuple[ValuationMethodResult, ...]
    methods_missing: tuple[str, ...]
    valuation_completeness: str
    weighted_dcf_per_share: float
    reverse_dcf_implied_growth: float
    sensitivity: SensitivityTable
    output_hash: str


def build_financial_bridge(value: ValuationEngineInput) -> tuple[FinancialBridgeRow, ...]:
    value.validate()
    rows = []
    for period in value.historical:
        nopat = period.ebit * (1 - period.tax_rate)
        unlevered = (
            nopat
            + period.depreciation_amortization
            - period.capital_expenditure
            - period.change_in_nwc
        )
        reported = period.operating_cash_flow - period.capital_expenditure
        conversion = period.operating_cash_flow / period.net_income if period.net_income else None
        rows.append(
            FinancialBridgeRow(
                period=period.period,
                revenue=period.revenue,
                nopat=round(nopat, 8),
                unlevered_fcf=round(unlevered, 8),
                reported_fcf=round(reported, 8),
                cash_conversion=round(conversion, 8) if conversion is not None else None,
                net_debt=round(period.debt - period.cash, 8),
                balance_check=round(period.assets - period.liabilities - period.equity, 8),
                shares_outstanding=period.shares_outstanding,
            )
        )
    return tuple(rows)


def _project_scenario(
    value: ValuationEngineInput,
    scenario: ValuationScenarioAssumptions,
    *,
    growth_override: float | None = None,
    wacc_override: float | None = None,
    terminal_growth_override: float | None = None,
) -> DCFScenarioResult:
    latest = value.historical[-1]
    revenue = latest.revenue
    revenues = []
    cash_flows = []
    growth_values = (
        (growth_override,) * len(scenario.revenue_growth)
        if growth_override is not None else scenario.revenue_growth
    )
    for growth, margin in zip(growth_values, scenario.ebit_margin):
        revenue *= 1 + growth
        nopat = revenue * margin * (1 - scenario.tax_rate)
        fcf = revenue * (
            margin * (1 - scenario.tax_rate)
            + scenario.depreciation_pct_revenue
            - scenario.capex_pct_revenue
            - scenario.nwc_investment_pct_revenue
        )
        revenues.append(revenue)
        cash_flows.append(fcf)
    wacc = scenario.wacc if wacc_override is None else wacc_override
    terminal_growth = (
        scenario.terminal_growth if terminal_growth_override is None else terminal_growth_override
    )
    if terminal_growth >= wacc:
        raise ReportContractError("terminal growth must stay below WACC")
    discounted = sum(fcf / (1 + wacc) ** year for year, fcf in enumerate(cash_flows, 1))
    terminal = cash_flows[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    enterprise = discounted + terminal / (1 + wacc) ** len(cash_flows)
    net_debt = latest.debt - latest.cash
    equity = enterprise - net_debt
    per_share = equity * value.unit_scale / value.shares_outstanding
    return DCFScenarioResult(
        name=scenario.name,
        probability=scenario.probability,
        assumption_hash=scenario.assumption_hash,
        revenues=tuple(round(item, 8) for item in revenues),
        unlevered_fcf=tuple(round(item, 8) for item in cash_flows),
        enterprise_value=round(enterprise, 8),
        equity_value=round(equity, 8),
        per_share_value=round(per_share, 6),
    )


def _reverse_dcf_growth(value: ValuationEngineInput, base: ValuationScenarioAssumptions) -> float:
    target = value.current_price
    low, high = -0.5, 1.0
    low_value = _project_scenario(value, base, growth_override=low).per_share_value
    high_value = _project_scenario(value, base, growth_override=high).per_share_value
    if not low_value <= target <= high_value:
        raise ReportContractError("current price is outside reverse-DCF solvable bounds")
    for _ in range(100):
        middle = (low + high) / 2
        result = _project_scenario(value, base, growth_override=middle).per_share_value
        if result < target:
            low = middle
        else:
            high = middle
    return round((low + high) / 2, 8)


def _sensitivity(value: ValuationEngineInput, base: ValuationScenarioAssumptions) -> SensitivityTable:
    wacc_values = tuple(round(base.wacc + offset, 6) for offset in (-0.01, -0.005, 0, 0.005, 0.01))
    growth_values = tuple(round(base.terminal_growth + offset, 6) for offset in (-0.01, -0.005, 0, 0.005, 0.01))
    if min(wacc_values) <= max(growth_values):
        raise ReportContractError("sensitivity grid crosses WACC/terminal-growth boundary")
    matrix = tuple(
        tuple(
            _project_scenario(
                value,
                base,
                wacc_override=wacc,
                terminal_growth_override=growth,
            ).per_share_value
            for growth in growth_values
        )
        for wacc in wacc_values
    )
    return SensitivityTable(wacc_values, growth_values, matrix)


def run_deterministic_valuation(value: ValuationEngineInput) -> DeterministicValuationResult:
    value.validate()
    bridge = build_financial_bridge(value)
    by_name = {item.name: item for item in value.scenarios}
    scenario_results = tuple(_project_scenario(value, by_name[name]) for name in ("bear", "base", "bull"))
    per_share = [item.per_share_value for item in scenario_results]
    if per_share != sorted(per_share):
        raise ReportContractError("bear/base/bull DCF values are not ordered")
    weighted = sum(item.per_share_value * item.probability for item in scenario_results)
    latest = value.historical[-1]
    input_hash = value.input_hash
    methods = [ValuationMethodResult("probability_weighted_dcf", round(weighted, 6), value.currency, f"{value.currency}/share", input_hash)]
    missing = []
    if value.peer_ev_ebitda:
        ebitda = latest.ebit + latest.depreciation_amortization
        net_debt = latest.debt - latest.cash
        comps_equity = median(value.peer_ev_ebitda) * ebitda - net_debt
        methods.append(ValuationMethodResult("peer_ev_ebitda", round(comps_equity * value.unit_scale / value.shares_outstanding, 6), value.currency, f"{value.currency}/share", input_hash))
    else:
        missing.append("peer_ev_ebitda: peer multiple input unavailable")
    if value.historical_pe:
        eps = latest.net_income * value.unit_scale / value.shares_outstanding
        methods.append(ValuationMethodResult("historical_pe", round(median(value.historical_pe) * eps, 6), value.currency, f"{value.currency}/share", input_hash))
    else:
        missing.append("historical_pe: historical multiple input unavailable")
    methods = tuple(methods)
    if any(item.per_share_value <= 0 for item in methods):
        raise ReportContractError("valuation cross-check produced a nonpositive value")
    reverse_growth = _reverse_dcf_growth(value, by_name["base"])
    sensitivity = _sensitivity(value, by_name["base"])
    output_payload = {
        "engine_version": VALUATION_ENGINE_VERSION,
        "input_hash": input_hash,
        "currency": value.currency,
        "bridge": [asdict(item) for item in bridge],
        "scenarios": [asdict(item) for item in scenario_results],
        "methods": [asdict(item) for item in methods],
        "methods_missing": missing,
        "weighted_dcf_per_share": round(weighted, 6),
        "reverse_dcf_implied_growth": reverse_growth,
        "sensitivity": asdict(sensitivity),
    }
    return DeterministicValuationResult(
        engine_version=VALUATION_ENGINE_VERSION,
        input_hash=input_hash,
        currency=value.currency,
        financial_bridge=bridge,
        scenario_results=scenario_results,
        methods=methods,
        methods_missing=tuple(missing),
        valuation_completeness="complete" if not missing else "partial",
        weighted_dcf_per_share=round(weighted, 6),
        reverse_dcf_implied_growth=reverse_growth,
        sensitivity=sensitivity,
        output_hash=_section_digest(output_payload),
    )
