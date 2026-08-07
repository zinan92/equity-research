#!/usr/bin/env python3
"""Verify the fail-closed M1.0 entry contract for the personal risk card."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_VERSION = "personal-holdings-risk-card-entry-v1"
APPROVAL_SCHEMA_VERSION = "personal-holdings-risk-card-approval-v1"
TRUST_HMAC_ENV = "PARK_RISK_CARD_TRUST_HMAC_KEY"
# Enrolling the production trust root is a separate Park-approved contract
# change.  None makes every production-ready trust policy fail closed.
PRODUCTION_TRUST_ROOT_KEY_SHA256: str | None = None
PRODUCTION_TRUST_POLICY_RECEIPT_SHA256: str | None = None
REQUIRED_APPROVALS = (
    "market_data_rights",
    "securities_service_boundary",
    "personal_information_processing",
    "notification_channel",
    "park_owner_approval",
)
APPROVAL_METHODS = {
    "market_data_rights": {
        "provider_executed_agreement",
        "provider_written_permission",
        "provider_agreement_bundle",
    },
    "securities_service_boundary": {
        "counsel_signed_opinion",
        "licensed_partner_written_confirmation",
    },
    "personal_information_processing": {
        "privacy_counsel_signed_assessment",
        "dpo_signed_assessment",
    },
    "notification_channel": {"channel_admin_written_confirmation"},
    "park_owner_approval": {"park_github_approval", "park_signed_approval"},
}
APPROVAL_AUTHORITY_TYPES = {
    "market_data_rights": {"data_provider", "data_rights_bundle"},
    "securities_service_boundary": {
        "qualified_legal_counsel",
        "licensed_securities_partner",
    },
    "personal_information_processing": {
        "privacy_counsel",
        "data_protection_officer",
    },
    "notification_channel": {"channel_administrator"},
    "park_owner_approval": {"park_owner"},
}
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


def trust_policy_hmac(policy: Mapping[str, Any], key: bytes) -> str:
    unsigned = {
        field: value
        for field, value in policy.items()
        if field not in {"receipt_hash", "dual_control_hmac_sha256"}
    }
    return hmac.new(key, _canonical_bytes(unsigned), hashlib.sha256).hexdigest()


def approval_summary_hmac(summary: Mapping[str, Any], key: bytes) -> str:
    unsigned = {
        field: value
        for field, value in summary.items()
        if field not in {"receipt_hash", "dual_control_hmac_sha256"}
    }
    return hmac.new(key, _canonical_bytes(unsigned), hashlib.sha256).hexdigest()


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


def approval_scope(payload: Mapping[str, Any]) -> dict[str, Any]:
    requested_sources = [
        {
            key: source[key]
            for key in ("source_key", "provider", "fields", "derived_outputs")
        }
        for source in payload["data_sources"]
    ]
    return {
        "product_scope": payload["product_scope"],
        "requested_data_sources": requested_sources,
        "decision_window": payload["decision_window"],
        "communication_policy": payload["communication_policy"],
        "personal_data_policy": payload["personal_data_policy"],
        "human_review": payload["human_review"],
        "incident_response": payload["incident_response"],
    }


def scope_hash(payload: Mapping[str, Any]) -> str:
    return digest(approval_scope(payload))


def _schema_errors(payload: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"schema:{'/'.join(str(part) for part in error.absolute_path) or '$'}:{error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    ]


def _trust_schema(approval_schema: Mapping[str, Any]) -> dict[str, Any]:
    definitions = approval_schema.get("$defs")
    if not isinstance(definitions, Mapping) or "trust_policy" not in definitions:
        raise EntryContractError("approval_schema_missing_trust_policy_definition")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/trust_policy",
        "$defs": definitions,
    }


def _trust_policy_errors(
    policy: Mapping[str, Any], *, trust_hmac_key: bytes | None, reference_time: datetime
) -> list[str]:
    errors: list[str] = []
    unsigned = {key: value for key, value in policy.items() if key != "receipt_hash"}
    if policy.get("receipt_hash") != digest(unsigned):
        errors.append("trust_policy_receipt_hash_mismatch")
    try:
        policy_issued_at = parse_datetime(str(policy["issued_at"]))
        policy_expires_at = parse_datetime(str(policy["expires_at"]))
    except (EntryContractError, KeyError, TypeError, ValueError):
        errors.append("trust_policy_validity_window_invalid")
    else:
        if (
            policy_issued_at > reference_time
            or policy_expires_at <= reference_time
            or policy_expires_at <= policy_issued_at
        ):
            errors.append("trust_policy_outside_validity_window")
    policy_epoch = policy.get("policy_epoch")
    revokes_before_epoch = policy.get("revokes_before_epoch")
    if (
        not isinstance(policy_epoch, int)
        or not isinstance(revokes_before_epoch, int)
        or policy_epoch <= revokes_before_epoch
    ):
        errors.append("trust_policy_epoch_revoked_or_invalid")

    if policy.get("status") == "onboarding_required":
        if policy.get("trust_root_key_sha256") is not None:
            errors.append("trust_policy_onboarding_root_must_be_null")
        if policy.get("dual_control_hmac_sha256") is not None:
            errors.append("trust_policy_onboarding_hmac_must_be_null")
    elif policy.get("status") == "ready":
        declared_root = policy.get("trust_root_key_sha256")
        if PRODUCTION_TRUST_ROOT_KEY_SHA256 is None:
            errors.append("production_trust_root_not_enrolled")
        elif declared_root != PRODUCTION_TRUST_ROOT_KEY_SHA256:
            errors.append("trust_policy_root_fingerprint_mismatch")
        if trust_hmac_key is None:
            errors.append("trust_policy_dual_control_key_missing")
        elif len(trust_hmac_key) < 32:
            errors.append("trust_policy_dual_control_key_too_short")
        elif hashlib.sha256(trust_hmac_key).hexdigest() != declared_root:
            errors.append("trust_policy_dual_control_key_fingerprint_mismatch")
        elif not hmac.compare_digest(
            str(policy.get("dual_control_hmac_sha256")),
            trust_policy_hmac(policy, trust_hmac_key),
        ):
            errors.append("trust_policy_dual_control_hmac_mismatch")
        if PRODUCTION_TRUST_POLICY_RECEIPT_SHA256 is None:
            errors.append("production_trust_policy_not_pinned")
        elif policy.get("receipt_hash") != PRODUCTION_TRUST_POLICY_RECEIPT_SHA256:
            errors.append("trust_policy_pinned_receipt_mismatch")

    authorities = policy.get("trusted_authorities") or {}
    if not isinstance(authorities, Mapping):
        return errors + ["trust_policy_authorities_invalid"]
    for approval_key in REQUIRED_APPROVALS:
        entries = authorities.get(approval_key) or []
        if not isinstance(entries, list):
            errors.append(f"trust_policy_authority_list_invalid:{approval_key}")
            continue
        if any(not isinstance(entry, Mapping) for entry in entries):
            errors.append(f"trust_policy_authority_entry_invalid:{approval_key}")
            continue
        identities = [entry.get("safe_identifier") for entry in entries]
        if len(identities) != len(set(identities)):
            errors.append(f"trust_policy_duplicate_authority:{approval_key}")
        for entry in entries:
            if entry.get("authority_type") not in APPROVAL_AUTHORITY_TYPES[approval_key]:
                errors.append(f"trust_policy_authority_type_mismatch:{approval_key}")
            if entry.get("identity_evidence_sha256") == "0" * 64:
                errors.append(f"trust_policy_zero_identity_hash:{approval_key}")

    verifiers = policy.get("trusted_verifiers") or []
    if not isinstance(verifiers, list):
        return errors + ["trust_policy_verifiers_invalid"]
    if any(not isinstance(entry, Mapping) for entry in verifiers):
        return errors + ["trust_policy_verifier_entry_invalid"]
    verifier_identities = [
        (entry.get("safe_identifier"), entry.get("role")) for entry in verifiers
    ]
    if len(verifier_identities) != len(set(verifier_identities)):
        errors.append("trust_policy_duplicate_verifier")
    for entry in verifiers:
        if entry.get("identity_evidence_sha256") == "0" * 64:
            errors.append("trust_policy_zero_verifier_identity_hash")
        for approval_key in entry.get("approval_keys") or ():
            authority_ids = {
                authority.get("safe_identifier")
                for authority in authorities.get(approval_key) or ()
                if isinstance(authority, Mapping)
            }
            if entry.get("safe_identifier") in authority_ids:
                errors.append(f"trust_policy_authority_verifier_not_independent:{approval_key}")

    if policy.get("status") == "ready":
        for approval_key in REQUIRED_APPROVALS:
            if not authorities.get(approval_key):
                errors.append(f"trust_policy_missing_authority:{approval_key}")
            if not any(
                approval_key in (entry.get("approval_keys") or ())
                for entry in verifiers
            ):
                errors.append(f"trust_policy_missing_verifier:{approval_key}")
    return errors


def _production_identity_is_trusted(
    approval_key: str,
    evidence: Mapping[str, Any],
    *,
    trust_policy: Mapping[str, Any],
    evidence_verified_at: datetime,
) -> bool:
    if trust_policy.get("status") != "ready":
        return False
    authority_identity = evidence["authority_identity"]
    trusted_authority = next(
        (
            entry
            for entry in trust_policy["trusted_authorities"][approval_key]
            if entry["safe_identifier"] == authority_identity["safe_identifier"]
            and entry["authority_type"] == authority_identity["authority_type"]
            and entry["jurisdiction"] == authority_identity["jurisdiction"]
        ),
        None,
    )
    verified_by = evidence["verified_by"]
    trusted_verifier = next(
        (
            entry
            for entry in trust_policy["trusted_verifiers"]
            if entry["safe_identifier"] == verified_by["safe_identifier"]
            and entry["role"] == verified_by["role"]
            and approval_key in entry["approval_keys"]
        ),
        None,
    )
    if trusted_authority is None or trusted_verifier is None:
        return False
    try:
        authority_enrolled_at = parse_datetime(trusted_authority["enrolled_at"])
        verifier_enrolled_at = parse_datetime(trusted_verifier["enrolled_at"])
    except (EntryContractError, KeyError):
        return False
    return (
        authority_enrolled_at <= evidence_verified_at
        and verifier_enrolled_at <= evidence_verified_at
    )


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
    approval_schema: Mapping[str, Any],
    expected_source_keys: set[str],
    trust_policy: Mapping[str, Any],
    trust_policy_authenticated: bool,
    trust_hmac_key: bytes | None,
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
    if _schema_errors(evidence, approval_schema):
        return approval_key
    unsigned_evidence = {
        key: value for key, value in evidence.items() if key != "receipt_hash"
    }
    if evidence.get("receipt_hash") != digest(unsigned_evidence):
        return approval_key
    authority_identity = evidence.get("authority_identity") or {}
    verified_by = evidence.get("verified_by") or {}
    expected = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_key": approval_key,
        "decision": "approved",
        "scope_hash": expected_scope_hash,
        "issued_at": approval["issued_at"],
        "expires_at": approval["expires_at"],
        "test_only": approval["test_only"],
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        return approval_key
    if authority_identity.get("safe_identifier") != approval["authority"]:
        return approval_key
    if authority_identity.get("safe_identifier") == verified_by.get("safe_identifier"):
        return approval_key
    if evidence.get("verification_method") not in APPROVAL_METHODS[approval_key]:
        return approval_key
    if authority_identity.get("authority_type") not in APPROVAL_AUTHORITY_TYPES[approval_key]:
        return approval_key
    covered_source_keys = set(authority_identity.get("covered_source_keys") or ())
    if approval_key == "market_data_rights":
        if covered_source_keys != expected_source_keys:
            return approval_key
    elif covered_source_keys:
        return approval_key
    underlying_hash = evidence.get("underlying_evidence_sha256")
    if underlying_hash == "0" * 64 or underlying_hash == evidence.get("receipt_hash"):
        return approval_key
    try:
        verified_at = parse_datetime(str(evidence["verified_at"]))
    except (EntryContractError, KeyError):
        return approval_key
    if verified_at < issued_at or verified_at > reference_time:
        return approval_key
    if evidence.get("test_only") and not allow_test_only:
        return approval_key
    if evidence.get("test_only") and verified_by.get("role") != "test_fixture":
        return approval_key
    if not evidence.get("test_only") and verified_by.get("role") == "test_fixture":
        return approval_key
    if not evidence.get("test_only"):
        if not trust_policy_authenticated:
            return approval_key
        if not _production_identity_is_trusted(
            approval_key,
            evidence,
            trust_policy=trust_policy,
            evidence_verified_at=verified_at,
        ):
            return approval_key
        if trust_hmac_key is None or not hmac.compare_digest(
            str(evidence.get("dual_control_hmac_sha256")),
            approval_summary_hmac(evidence, trust_hmac_key),
        ):
            return approval_key
    return None


def _semantic_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    unsigned = {key: value for key, value in payload.items() if key != "receipt_hash"}
    expected_receipt_hash = digest(unsigned)
    if payload.get("receipt_hash") != expected_receipt_hash:
        errors.append("receipt_hash_mismatch")
    if any(
        approval.get("test_only") is not payload["test_only"]
        for approval in payload["required_approvals"].values()
    ):
        errors.append("mixed_test_only_contract")

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
    approval_schema: Mapping[str, Any] | None = None,
    trust_policy: Mapping[str, Any] | None = None,
    trust_policy_authenticated: bool = False,
    trust_hmac_key: bytes | None = None,
) -> dict[str, Any]:
    now = (reference_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expected_scope_hash = scope_hash(payload)
    if approval_schema is None:
        approval_schema = load_json(
            repo_root
            / "product/schemas/personal-holdings-risk-card-approval-v1.schema.json"
        )
    if trust_policy is None:
        trust_policy = load_json(
            repo_root / "evidence/market-regime-m1/approval-requests/trust-policy.json"
        )
    expected_source_keys = {source["source_key"] for source in payload["data_sources"]}
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
            approval_schema=approval_schema,
            expected_source_keys=expected_source_keys,
            trust_policy=trust_policy,
            trust_policy_authenticated=trust_policy_authenticated,
            trust_hmac_key=trust_hmac_key,
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
        "test_only": bool(payload["test_only"]),
        "production_eligible": (
            status == "go" and not payload["test_only"] and not allow_test_only
        ),
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
    approval_schema_path: Path | None = None,
    trust_policy_path: Path | None = None,
    trust_hmac_key: bytes | None = None,
) -> dict[str, Any]:
    now = (reference_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = load_json(contract_path)
    schema = load_json(schema_path)
    approval_schema = load_json(
        approval_schema_path
        or schema_path.with_name("personal-holdings-risk-card-approval-v1.schema.json")
    )
    trust_schema = _trust_schema(approval_schema)
    trust_policy = load_json(
        trust_policy_path
        or repo_root / "evidence/market-regime-m1/approval-requests/trust-policy.json"
    )
    if trust_hmac_key is None:
        environment_key = os.environ.get(TRUST_HMAC_ENV)
        trust_hmac_key = environment_key.encode("utf-8") if environment_key else None
    trust_errors = _schema_errors(trust_policy, trust_schema)
    trust_errors.extend(
        _trust_policy_errors(
            trust_policy,
            trust_hmac_key=trust_hmac_key,
            reference_time=now,
        )
    )
    if trust_errors:
        raise EntryContractError(";".join(trust_errors))
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
        reference_time=now,
        allow_test_only=allow_test_only,
        approval_schema=approval_schema,
        trust_policy=trust_policy,
        trust_policy_authenticated=True,
        trust_hmac_key=trust_hmac_key,
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
    parser.add_argument(
        "--approval-schema",
        type=Path,
        default=Path(
            "product/schemas/personal-holdings-risk-card-approval-v1.schema.json"
        ),
    )
    parser.add_argument("--reference-time")
    parser.add_argument("--allow-test-only", action="store_true")
    parser.add_argument("--require-go", action="store_true")
    args = parser.parse_args(argv)

    if args.require_go and args.allow_test_only:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "contract_valid": False,
                    "error": "require_go_rejects_allow_test_only",
                    "production_eligible": False,
                },
                sort_keys=True,
            )
        )
        return 1
    if args.require_go and args.reference_time:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "contract_valid": False,
                    "error": "require_go_rejects_reference_time_override",
                    "production_eligible": False,
                },
                sort_keys=True,
            )
        )
        return 1

    repo_root = args.root.resolve()
    contract_path = args.contract if args.contract.is_absolute() else repo_root / args.contract
    schema_path = args.schema if args.schema.is_absolute() else repo_root / args.schema
    approval_schema_path = (
        args.approval_schema
        if args.approval_schema.is_absolute()
        else repo_root / args.approval_schema
    )
    canonical_root = root.resolve()
    if args.require_go and (
        repo_root != canonical_root
        or contract_path.resolve()
        != canonical_root / "evidence/market-regime-m1/entry-readiness.json"
        or schema_path.resolve()
        != canonical_root / "product/schemas/personal-holdings-risk-card-entry-v1.schema.json"
        or approval_schema_path.resolve()
        != canonical_root
        / "product/schemas/personal-holdings-risk-card-approval-v1.schema.json"
    ):
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "contract_valid": False,
                    "error": "require_go_rejects_path_override",
                    "production_eligible": False,
                },
                sort_keys=True,
            )
        )
        return 1
    reference_time = parse_datetime(args.reference_time) if args.reference_time else None
    try:
        result = verify_contract(
            contract_path,
            schema_path,
            repo_root=repo_root,
            reference_time=reference_time,
            allow_test_only=args.allow_test_only,
            approval_schema_path=approval_schema_path,
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
    if args.require_go and not result["production_eligible"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
