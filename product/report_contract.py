"""Versioned, market-neutral contract for every renderable equity report."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timezone
from functools import lru_cache
import json
from pathlib import Path
from typing import Any
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
