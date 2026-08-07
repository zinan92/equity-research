#!/usr/bin/env python3
"""Verify the fail-closed M1.0 entry contract for the personal risk card."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_VERSION = "personal-holdings-risk-card-entry-v1"
APPROVAL_SCHEMA_VERSION = "personal-holdings-risk-card-approval-v1"
REQUIRED_APPROVALS = (
    "market_data_rights",
    "securities_service_boundary",
    "personal_information_processing",
    "notification_channel",
    "park_owner_approval",
)
REQUIRED_PORTFOLIO_INPUTS = {
    "ticker",
    "portfolio_weight",
    "holding_horizon",
    "user_risk_rule",
}
REQUIRED_PROHIBITED_INPUTS = {
    "broker_password",
    "broker_session",
    "account_balance",
    "cost_basis",
    "complete_trade_history",
}
REQUIRED_PROHIBITED_CAPABILITIES = {
    "specific_buy_instruction",
    "specific_sell_instruction",
    "market_timing_instruction",
    "target_price",
    "position_size_instruction",
    "broker_connection",
    "automatic_trading",
    "guaranteed_return",
}
REQUIRED_DISCLOSURES = {
    "model_generated_unreviewed_until_human_review",
    "not_investment_advice",
    "data_freshness_and_quality",
    "invalidation_conditions",
    "source_identity",
}


class EntryContractError(ValueError):
    """Raised when an entry contract cannot be trusted."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EntryContractError(f"json_unreadable:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise EntryContractError(f"json_root_not_object:{path}")
    return payload


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise EntryContractError(f"datetime_missing_timezone:{value}")
    return parsed.astimezone(timezone.utc)


def scope_hash(payload: Mapping[str, Any]) -> str:
    requested_sources = [
        {
            key: source[key]
            for key in ("source_key", "provider", "fields", "derived_outputs")
        }
        for source in payload["data_sources"]
    ]
    return digest(
        {
            "product_scope": payload["product_scope"],
            "requested_data_sources": requested_sources,
            "decision_window": payload["decision_window"],
            "communication_policy": payload["communication_policy"],
            "personal_data_policy": payload["personal_data_policy"],
            "human_review": payload["human_review"],
            "incident_response": payload["incident_response"],
        }
    )


def _schema_errors(payload: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"schema:{'/'.join(str(part) for part in error.absolute_path) or '$'}:{error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    ]


def _approval_evidence_path(repo_root: Path, evidence_ref: str) -> Path:
    if not evidence_ref.startswith("repo:"):
        raise EntryContractError("approval_evidence_ref_must_use_repo_prefix")
    relative = evidence_ref.removeprefix("repo:")
    if not relative or Path(relative).is_absolute():
        raise EntryContractError("approval_evidence_ref_invalid")
    candidate = repo_root / relative
    if candidate.is_symlink():
        raise EntryContractError("approval_evidence_symlink_rejected")
    resolved_root = repo_root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise EntryContractError("approval_evidence_outside_repo")
    if not resolved.is_file():
        raise EntryContractError(f"approval_evidence_missing:{relative}")
    return resolved


def _approval_blocker(
    approval_key: str,
    approval: Mapping[str, Any],
    *,
    expected_scope_hash: str,
    repo_root: Path,
    reference_time: datetime,
    allow_test_only: bool,
) -> str | None:
    if approval.get("status") != "approved":
        return approval_key
    if approval.get("scope_hash") != expected_scope_hash:
        return approval_key
    if not all(
        approval.get(field)
        for field in ("authority", "evidence_ref", "evidence_sha256", "issued_at", "expires_at")
    ):
        return approval_key
    if approval.get("test_only") and not allow_test_only:
        return approval_key

    try:
        issued_at = parse_datetime(str(approval["issued_at"]))
        expires_at = parse_datetime(str(approval["expires_at"]))
        evidence_path = _approval_evidence_path(repo_root, str(approval["evidence_ref"]))
    except EntryContractError:
        return approval_key
    if issued_at > reference_time or expires_at <= reference_time or expires_at <= issued_at:
        return approval_key
    try:
        if file_sha256(evidence_path) != approval.get("evidence_sha256"):
            return approval_key
        evidence = load_json(evidence_path)
    except (EntryContractError, OSError):
        return approval_key
    expected = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_key": approval_key,
        "decision": "approved",
        "authority": approval["authority"],
        "scope_hash": expected_scope_hash,
        "issued_at": approval["issued_at"],
        "expires_at": approval["expires_at"],
        "test_only": approval["test_only"],
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        return approval_key
    if evidence.get("test_only") and not allow_test_only:
        return approval_key
    if set(evidence) != set(expected):
        return approval_key
    return None


def _semantic_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    unsigned = {key: value for key, value in payload.items() if key != "receipt_hash"}
    expected_receipt_hash = digest(unsigned)
    if payload.get("receipt_hash") != expected_receipt_hash:
        errors.append("receipt_hash_mismatch")

    if set(payload["product_scope"]["portfolio_inputs"]) != REQUIRED_PORTFOLIO_INPUTS:
        errors.append("portfolio_inputs_not_minimal_contract")
    if set(payload["personal_data_policy"]["minimum_inputs"]) != REQUIRED_PORTFOLIO_INPUTS:
        errors.append("personal_data_minimum_inputs_mismatch")
    source_keys = [source["source_key"] for source in payload["data_sources"]]
    if len(source_keys) != len(set(source_keys)):
        errors.append("duplicate_data_source_key")
    if not REQUIRED_PROHIBITED_INPUTS.issubset(
        set(payload["personal_data_policy"]["prohibited_inputs"])
    ):
        errors.append("prohibited_personal_inputs_incomplete")
    if not REQUIRED_PROHIBITED_CAPABILITIES.issubset(
        set(payload["communication_policy"]["prohibited_capabilities"])
    ):
        errors.append("prohibited_capabilities_incomplete")
    if not REQUIRED_DISCLOSURES.issubset(
        set(payload["communication_policy"]["required_disclosures"])
    ):
        errors.append("required_disclosures_incomplete")

    if payload["product_scope"]["external_distribution"]:
        if set(payload["product_scope"]["delivery_channels"]) == {"local_web"}:
            errors.append("external_scope_cannot_be_local_web_only")
    if payload["product_scope"]["commercial_mode"] == "paid" and not payload["product_scope"][
        "external_distribution"
    ]:
        errors.append("paid_scope_requires_external_distribution")
    return errors


def evaluate_readiness(
    payload: Mapping[str, Any],
    *,
    repo_root: Path,
    reference_time: datetime | None = None,
    allow_test_only: bool = False,
) -> dict[str, Any]:
    now = (reference_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expected_scope_hash = scope_hash(payload)
    blockers: list[str] = []
    approval_validity: dict[str, bool] = {}

    for key in REQUIRED_APPROVALS:
        blocker = _approval_blocker(
            key,
            payload["required_approvals"][key],
            expected_scope_hash=expected_scope_hash,
            repo_root=repo_root,
            reference_time=now,
            allow_test_only=allow_test_only,
        )
        approval_validity[key] = blocker is None
        if blocker and blocker not in blockers:
            blockers.append(blocker)

    sources = payload["data_sources"]
    sources_target_approved = all(source["target_use_status"] == "approved" for source in sources)
    sources_external_approved = all(source["external_distribution_allowed"] for source in sources)
    sources_commercial_approved = all(source["commercial_use_allowed"] for source in sources)
    market_approval_ref = payload["required_approvals"]["market_data_rights"].get("evidence_ref")
    sources_references_bound = bool(market_approval_ref) and all(
        source["approval_reference"] == market_approval_ref for source in sources
    )
    if not sources_target_approved:
        if "market_data_rights" not in blockers:
            blockers.append("market_data_rights")
    if payload["product_scope"]["external_distribution"] and not sources_external_approved:
        if "market_data_rights" not in blockers:
            blockers.append("market_data_rights")
    if payload["product_scope"]["commercial_mode"] == "paid" and not sources_commercial_approved:
        if "market_data_rights" not in blockers:
            blockers.append("market_data_rights")
    if sources_target_approved and not sources_references_bound:
        if "market_data_rights" not in blockers:
            blockers.append("market_data_rights")

    ordered = [key for key in REQUIRED_APPROVALS if key in blockers]
    status = "go" if not ordered else "blocked"
    market_rights_proven = (
        approval_validity["market_data_rights"]
        and sources_target_approved
        and sources_references_bound
    )
    legal_boundary_proven = approval_validity["securities_service_boundary"]
    owner_approved = approval_validity["park_owner_approval"]
    proven_truth_boundary = {
        "legal_opinion_provided": legal_boundary_proven,
        "commercial_rights_proven": market_rights_proven and sources_commercial_approved,
        "external_distribution_allowed": (
            payload["product_scope"]["external_distribution"]
            and market_rights_proven
            and sources_external_approved
            and approval_validity["notification_channel"]
        ),
        "real_user_data_allowed": approval_validity["personal_information_processing"],
        "payment_allowed": (
            payload["product_scope"]["commercial_mode"] == "paid"
            and market_rights_proven
            and sources_commercial_approved
            and legal_boundary_proven
            and owner_approved
        ),
        "investment_advice_allowed": False,
        "broker_connection_allowed": False,
        "automatic_trading_allowed": False,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": payload["contract_id"],
        "reference_time": now.isoformat().replace("+00:00", "Z"),
        "scope_hash": expected_scope_hash,
        "readiness_status": status,
        "blocked_by": ordered,
        "proven_truth_boundary": proven_truth_boundary,
        "receipt_hash": payload["receipt_hash"],
    }


def verify_contract(
    contract_path: Path,
    schema_path: Path,
    *,
    repo_root: Path,
    reference_time: datetime | None = None,
    allow_test_only: bool = False,
) -> dict[str, Any]:
    payload = load_json(contract_path)
    schema = load_json(schema_path)
    errors = _schema_errors(payload, schema)
    if errors:
        raise EntryContractError(";".join(errors))
    errors = _semantic_errors(payload)
    if payload.get("test_only") and not allow_test_only:
        errors.append("test_only_contract_rejected")
    if errors:
        raise EntryContractError(";".join(errors))

    result = evaluate_readiness(
        payload,
        repo_root=repo_root,
        reference_time=reference_time,
        allow_test_only=allow_test_only,
    )
    if payload["readiness_status"] != result["readiness_status"]:
        raise EntryContractError(
            f"declared_readiness_mismatch:{payload['readiness_status']}:{result['readiness_status']}"
        )
    if payload["blocked_by"] != result["blocked_by"]:
        raise EntryContractError("declared_blockers_mismatch")

    boundary = payload["truth_boundary"]
    mismatched_boundary = [
        key
        for key, expected in result["proven_truth_boundary"].items()
        if boundary[key] is not expected
    ]
    if mismatched_boundary:
        raise EntryContractError(f"truth_boundary_mismatch:{','.join(mismatched_boundary)}")
    return result


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = _default_repo_root()
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("evidence/market-regime-m1/entry-readiness.json"),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("product/schemas/personal-holdings-risk-card-entry-v1.schema.json"),
    )
    parser.add_argument("--reference-time")
    parser.add_argument("--allow-test-only", action="store_true")
    parser.add_argument("--require-go", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    contract_path = args.contract if args.contract.is_absolute() else repo_root / args.contract
    schema_path = args.schema if args.schema.is_absolute() else repo_root / args.schema
    reference_time = parse_datetime(args.reference_time) if args.reference_time else None
    try:
        result = verify_contract(
            contract_path,
            schema_path,
            repo_root=repo_root,
            reference_time=reference_time,
            allow_test_only=args.allow_test_only,
        )
    except EntryContractError as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "contract_valid": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1

    result["contract_valid"] = True
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.require_go and result["readiness_status"] != "go":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
