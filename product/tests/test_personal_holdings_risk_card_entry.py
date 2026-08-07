from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.verify_personal_holdings_risk_card_entry import (
    APPROVAL_SCHEMA_VERSION,
    REQUIRED_APPROVALS,
    EntryContractError,
    approval_summary_hmac,
    digest,
    load_json,
    main as entry_main,
    scope_hash,
    trust_policy_hmac,
    verify_contract as verify_entry_contract,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "product/schemas/personal-holdings-risk-card-entry-v1.schema.json"
CANONICAL = ROOT / "evidence/market-regime-m1/entry-readiness.json"
TRUST_POLICY = ROOT / "evidence/market-regime-m1/approval-requests/trust-policy.json"
REFERENCE_TIME = datetime(2026, 8, 7, tzinfo=timezone.utc)
TEST_TRUST_HMAC_KEY = b"test-only-dual-control-key-32-bytes-minimum"
TEST_TRUST_ROOT_SHA256 = hashlib.sha256(TEST_TRUST_HMAC_KEY).hexdigest()

TEST_APPROVAL_IDENTITIES = {
    "market_data_rights": ("data_rights_bundle", "provider_agreement_bundle"),
    "securities_service_boundary": (
        "qualified_legal_counsel",
        "counsel_signed_opinion",
    ),
    "personal_information_processing": (
        "privacy_counsel",
        "privacy_counsel_signed_assessment",
    ),
    "notification_channel": (
        "channel_administrator",
        "channel_admin_written_confirmation",
    ),
    "park_owner_approval": ("park_owner", "park_github_approval"),
}


def verify_contract(*args, **kwargs):
    kwargs.setdefault("trust_policy_path", TRUST_POLICY)
    return verify_entry_contract(*args, **kwargs)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _resign(payload: dict) -> None:
    payload["receipt_hash"] = digest(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )


def _resign_approval(payload: dict) -> None:
    payload["receipt_hash"] = digest(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )


def _synthetic_go(repo_root: Path) -> tuple[dict, Path]:
    payload = copy.deepcopy(load_json(CANONICAL))
    payload["test_only"] = True
    expected_scope_hash = scope_hash(payload)
    issued_at = "2026-08-01T00:00:00Z"
    expires_at = "2027-08-01T00:00:00Z"

    for source in payload["data_sources"]:
        source["target_use_status"] = "approved"
        source["external_distribution_allowed"] = True
        source["commercial_use_allowed"] = True
        source["approval_reference"] = "test-only synthetic approval"

    for key in REQUIRED_APPROVALS:
        authority_type, verification_method = TEST_APPROVAL_IDENTITIES[key]
        authority = f"test:authority-{key.replace('_', '-')}"
        evidence = {
            "schema_version": APPROVAL_SCHEMA_VERSION,
            "approval_id": f"m1-approval:test-{key.replace('_', '-')}",
            "approval_key": key,
            "decision": "approved",
            "authority_identity": {
                "display_name": f"Synthetic authority for {key}",
                "authority_type": authority_type,
                "safe_identifier": authority,
                "jurisdiction": "CN",
                "covered_source_keys": (
                    [source["source_key"] for source in payload["data_sources"]]
                    if key == "market_data_rights"
                    else []
                ),
            },
            "verification_method": verification_method,
            "scope_hash": expected_scope_hash,
            "underlying_evidence_sha256": hashlib.sha256(
                f"synthetic underlying evidence:{key}".encode("utf-8")
            ).hexdigest(),
            "safe_evidence_locator": f"test:{key.replace('_', '-')}",
            "dual_control_hmac_sha256": None,
            "verified_by": {
                "role": "test_fixture",
                "safe_identifier": "test:fixture-01",
            },
            "verified_at": "2026-08-02T00:00:00Z",
            "issued_at": issued_at,
            "expires_at": expires_at,
            "test_only": True,
        }
        _resign_approval(evidence)
        relative = Path("evidence/test-only") / f"{key}.json"
        evidence_path = repo_root / relative
        _write_json(evidence_path, evidence)
        payload["required_approvals"][key] = {
            "status": "approved",
            "authority": authority,
            "scope_hash": expected_scope_hash,
            "evidence_ref": f"repo:{relative.as_posix()}",
            "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "issued_at": issued_at,
            "expires_at": expires_at,
            "test_only": True,
        }

    market_approval_ref = payload["required_approvals"]["market_data_rights"]["evidence_ref"]
    for source in payload["data_sources"]:
        source["approval_reference"] = market_approval_ref

    payload["readiness_status"] = "go"
    payload["blocked_by"] = []
    payload["truth_boundary"].update(
        {
            "legal_opinion_provided": True,
            "commercial_rights_proven": True,
            "external_distribution_allowed": True,
            "real_user_data_allowed": True,
            "payment_allowed": True,
        }
    )
    _resign(payload)
    contract_path = repo_root / "entry-readiness.json"
    _write_json(contract_path, payload)
    return payload, contract_path


def _production_shaped_go(repo_root: Path) -> tuple[Path, Path]:
    payload, contract_path = _synthetic_go(repo_root)
    payload["test_only"] = False
    trusted_authorities: dict[str, list[dict]] = {
        key: [] for key in REQUIRED_APPROVALS
    }

    for key in REQUIRED_APPROVALS:
        approval = payload["required_approvals"][key]
        old_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
        evidence = load_json(old_path)
        authority = f"authority:{key.replace('_', '-')}"
        evidence["approval_id"] = f"m1-approval:production-shaped-{key.replace('_', '-')}"
        evidence["test_only"] = False
        evidence["authority_identity"]["safe_identifier"] = authority
        evidence["safe_evidence_locator"] = f"contract:{key.replace('_', '-')}"
        evidence["verified_by"] = {
            "role": "authorized_compliance_reviewer",
            "safe_identifier": "reviewer:compliance-01",
        }
        evidence["dual_control_hmac_sha256"] = approval_summary_hmac(
            evidence, TEST_TRUST_HMAC_KEY
        )
        _resign_approval(evidence)
        relative = Path("evidence/production-shaped-test") / f"{key}.json"
        evidence_path = repo_root / relative
        _write_json(evidence_path, evidence)
        approval.update(
            {
                "authority": authority,
                "evidence_ref": f"repo:{relative.as_posix()}",
                "evidence_sha256": hashlib.sha256(
                    evidence_path.read_bytes()
                ).hexdigest(),
                "test_only": False,
            }
        )
        trusted_authorities[key].append(
            {
                "safe_identifier": authority,
                "authority_type": evidence["authority_identity"]["authority_type"],
                "jurisdiction": "CN",
                "identity_evidence_sha256": hashlib.sha256(
                    f"authority identity fixture:{key}".encode("utf-8")
                ).hexdigest(),
                "safe_identity_locator": f"case:authority-{key.replace('_', '-')}",
                "enrolled_by": "park:owner",
                "enrolled_at": "2026-08-01T00:00:00Z",
            }
        )

    market_ref = payload["required_approvals"]["market_data_rights"]["evidence_ref"]
    for source in payload["data_sources"]:
        source["approval_reference"] = market_ref
    _resign(payload)
    _write_json(contract_path, payload)

    trust_policy = {
        "schema_version": "personal-holdings-risk-card-approval-trust-v1",
        "policy_id": "m1-approval-trust:personal-holdings-risk-card-v1",
        "status": "ready",
        "policy_epoch": 1,
        "issued_at": "2026-08-01T00:00:00Z",
        "expires_at": "2027-08-01T00:00:00Z",
        "revokes_before_epoch": 0,
        "previous_policy_receipt_hash": None,
        "trust_root_key_sha256": TEST_TRUST_ROOT_SHA256,
        "dual_control_hmac_sha256": None,
        "trusted_authorities": trusted_authorities,
        "trusted_verifiers": [
            {
                "safe_identifier": "reviewer:compliance-01",
                "role": "authorized_compliance_reviewer",
                "approval_keys": list(REQUIRED_APPROVALS),
                "identity_evidence_sha256": hashlib.sha256(
                    b"compliance reviewer identity fixture"
                ).hexdigest(),
                "safe_identity_locator": "case:reviewer-compliance-01",
                "enrolled_by": "park:owner",
                "enrolled_at": "2026-08-01T00:00:00Z",
            },
        ],
    }
    trust_policy["dual_control_hmac_sha256"] = trust_policy_hmac(
        trust_policy, TEST_TRUST_HMAC_KEY
    )
    _resign_approval(trust_policy)
    trust_path = repo_root / "trust-policy.json"
    _write_json(trust_path, trust_policy)
    return contract_path, trust_path


class PersonalHoldingsRiskCardEntryTests(unittest.TestCase):
    def test_canonical_contract_is_truthfully_blocked(self) -> None:
        result = verify_contract(
            CANONICAL,
            SCHEMA,
            repo_root=ROOT,
            reference_time=REFERENCE_TIME,
        )
        self.assertEqual("blocked", result["readiness_status"])
        self.assertEqual(list(REQUIRED_APPROVALS), result["blocked_by"])

    def test_synthetic_go_requires_explicit_test_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            _, contract_path = _synthetic_go(repo_root)
            result = verify_contract(
                contract_path,
                SCHEMA,
                repo_root=repo_root,
                reference_time=REFERENCE_TIME,
                allow_test_only=True,
            )
            self.assertEqual("go", result["readiness_status"])
            self.assertIs(True, result["test_only"])
            self.assertIs(False, result["production_eligible"])
            with self.assertRaisesRegex(EntryContractError, "test_only_contract_rejected"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                )

    def test_mixed_contract_and_approval_test_flags_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            payload["test_only"] = False
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "mixed_test_only_contract"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_allow_test_mode_never_reports_production_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            contract_path, trust_path = _production_shaped_go(repo_root)
            with patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_ROOT_KEY_SHA256",
                TEST_TRUST_ROOT_SHA256,
            ), patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_POLICY_RECEIPT_SHA256",
                load_json(trust_path)["receipt_hash"],
            ):
                result = verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    trust_policy_path=trust_path,
                    trust_hmac_key=TEST_TRUST_HMAC_KEY,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )
            self.assertEqual("go", result["readiness_status"])
            self.assertIs(False, result["production_eligible"])

    def test_cli_cannot_combine_test_mode_with_production_require_go(self) -> None:
        self.assertEqual(1, entry_main(["--allow-test-only", "--require-go"]))

    def test_cli_production_gate_rejects_replay_time_and_path_overrides(self) -> None:
        self.assertEqual(
            1,
            entry_main(
                [
                    "--require-go",
                    "--reference-time",
                    "2026-08-01T00:00:00Z",
                ]
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                1,
                entry_main(["--require-go", "--root", directory]),
            )

    def test_ready_trust_policy_can_validate_a_production_shaped_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            contract_path, trust_path = _production_shaped_go(repo_root)
            with self.assertRaisesRegex(
                EntryContractError, "production_trust_root_not_enrolled"
            ):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    trust_policy_path=trust_path,
                    trust_hmac_key=TEST_TRUST_HMAC_KEY,
                    reference_time=REFERENCE_TIME,
                )
            with patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_ROOT_KEY_SHA256",
                TEST_TRUST_ROOT_SHA256,
            ), patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_POLICY_RECEIPT_SHA256",
                load_json(trust_path)["receipt_hash"],
            ):
                result = verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    trust_policy_path=trust_path,
                    trust_hmac_key=TEST_TRUST_HMAC_KEY,
                    reference_time=REFERENCE_TIME,
                )
            self.assertEqual("go", result["readiness_status"])
            self.assertIs(True, result["production_eligible"])

    def test_ready_policy_must_match_the_pinned_current_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            contract_path, trust_path = _production_shaped_go(repo_root)
            with patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_ROOT_KEY_SHA256",
                TEST_TRUST_ROOT_SHA256,
            ), patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_POLICY_RECEIPT_SHA256",
                "f" * 64,
            ):
                with self.assertRaisesRegex(
                    EntryContractError, "trust_policy_pinned_receipt_mismatch"
                ):
                    verify_contract(
                        contract_path,
                        SCHEMA,
                        repo_root=repo_root,
                        trust_policy_path=trust_path,
                        trust_hmac_key=TEST_TRUST_HMAC_KEY,
                        reference_time=REFERENCE_TIME,
                    )

    def test_identity_enrolled_after_receipt_verification_is_not_retroactive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            contract_path, trust_path = _production_shaped_go(repo_root)
            trust = load_json(trust_path)
            trust["trusted_authorities"]["market_data_rights"][0]["enrolled_at"] = (
                "2026-08-03T00:00:00Z"
            )
            trust["dual_control_hmac_sha256"] = trust_policy_hmac(
                trust, TEST_TRUST_HMAC_KEY
            )
            _resign_approval(trust)
            _write_json(trust_path, trust)
            with patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_ROOT_KEY_SHA256",
                TEST_TRUST_ROOT_SHA256,
            ), patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_POLICY_RECEIPT_SHA256",
                trust["receipt_hash"],
            ):
                with self.assertRaisesRegex(
                    EntryContractError, "declared_readiness_mismatch"
                ):
                    verify_contract(
                        contract_path,
                        SCHEMA,
                        repo_root=repo_root,
                        trust_policy_path=trust_path,
                        trust_hmac_key=TEST_TRUST_HMAC_KEY,
                        reference_time=REFERENCE_TIME,
                    )

    def test_authority_cannot_be_its_own_independent_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            contract_path, trust_path = _production_shaped_go(repo_root)
            payload = load_json(contract_path)
            approval = payload["required_approvals"]["market_data_rights"]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence = load_json(evidence_path)
            authority_id = evidence["authority_identity"]["safe_identifier"]
            evidence["verified_by"]["safe_identifier"] = authority_id
            evidence["dual_control_hmac_sha256"] = approval_summary_hmac(
                evidence, TEST_TRUST_HMAC_KEY
            )
            _resign_approval(evidence)
            _write_json(evidence_path, evidence)
            approval["evidence_sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            _resign(payload)
            _write_json(contract_path, payload)

            trust = load_json(trust_path)
            trust["trusted_verifiers"][0]["safe_identifier"] = authority_id
            trust["dual_control_hmac_sha256"] = trust_policy_hmac(
                trust, TEST_TRUST_HMAC_KEY
            )
            _resign_approval(trust)
            _write_json(trust_path, trust)
            with patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_ROOT_KEY_SHA256",
                TEST_TRUST_ROOT_SHA256,
            ), patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_POLICY_RECEIPT_SHA256",
                trust["receipt_hash"],
            ):
                with self.assertRaisesRegex(
                    EntryContractError,
                    "trust_policy_authority_verifier_not_independent",
                ):
                    verify_contract(
                        contract_path,
                        SCHEMA,
                        repo_root=repo_root,
                        trust_policy_path=trust_path,
                        trust_hmac_key=TEST_TRUST_HMAC_KEY,
                        reference_time=REFERENCE_TIME,
                    )

    def test_trusted_names_cannot_author_a_new_production_receipt_without_hmac(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            contract_path, trust_path = _production_shaped_go(repo_root)
            payload = load_json(contract_path)
            approval = payload["required_approvals"]["market_data_rights"]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence = load_json(evidence_path)
            evidence["underlying_evidence_sha256"] = "f" * 64
            _resign_approval(evidence)
            _write_json(evidence_path, evidence)
            approval["evidence_sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            _resign(payload)
            _write_json(contract_path, payload)
            with patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_ROOT_KEY_SHA256",
                TEST_TRUST_ROOT_SHA256,
            ), patch(
                "scripts.verify_personal_holdings_risk_card_entry."
                "PRODUCTION_TRUST_POLICY_RECEIPT_SHA256",
                load_json(trust_path)["receipt_hash"],
            ):
                with self.assertRaisesRegex(
                    EntryContractError, "declared_readiness_mismatch"
                ):
                    verify_contract(
                        contract_path,
                        SCHEMA,
                        repo_root=repo_root,
                        trust_policy_path=trust_path,
                        trust_hmac_key=TEST_TRUST_HMAC_KEY,
                        reference_time=REFERENCE_TIME,
                    )

    def test_expired_approval_blocks_declared_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            key = "notification_channel"
            approval = payload["required_approvals"][key]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence = load_json(evidence_path)
            evidence["expires_at"] = "2026-08-06T23:59:59Z"
            _resign_approval(evidence)
            _write_json(evidence_path, evidence)
            approval["expires_at"] = evidence["expires_at"]
            approval["evidence_sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_method_key_mismatch_cannot_unlock_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            approval = payload["required_approvals"]["notification_channel"]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence = load_json(evidence_path)
            evidence["verification_method"] = "park_signed_approval"
            _resign_approval(evidence)
            _write_json(evidence_path, evidence)
            approval["evidence_sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_missing_underlying_evidence_hash_cannot_unlock_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            approval = payload["required_approvals"]["securities_service_boundary"]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence = load_json(evidence_path)
            evidence.pop("underlying_evidence_sha256")
            _resign_approval(evidence)
            _write_json(evidence_path, evidence)
            approval["evidence_sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_tampered_safe_summary_receipt_hash_cannot_unlock_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            approval = payload["required_approvals"]["park_owner_approval"]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence = load_json(evidence_path)
            evidence["receipt_hash"] = "f" * 64
            _write_json(evidence_path, evidence)
            approval["evidence_sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_market_rights_must_cover_every_source_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            approval = payload["required_approvals"]["market_data_rights"]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence = load_json(evidence_path)
            evidence["authority_identity"]["covered_source_keys"] = ["yahoo_chart"]
            _resign_approval(evidence)
            _write_json(evidence_path, evidence)
            approval["evidence_sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_untrusted_operator_strings_cannot_unlock_production_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            contract_path, _ = _production_shaped_go(repo_root)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                )

    def test_scope_mismatch_blocks_declared_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            payload["required_approvals"]["market_data_rights"]["scope_hash"] = "f" * 64
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_tampered_approval_file_blocks_declared_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            approval = payload["required_approvals"]["park_owner_approval"]
            evidence_path = repo_root / approval["evidence_ref"].removeprefix("repo:")
            evidence_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_unsupported_external_approval_reference_blocks_declared_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            payload["required_approvals"]["market_data_rights"]["evidence_ref"] = (
                "https://example.invalid/approval.json"
            )
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_unbound_source_approval_reference_blocks_declared_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            payload["data_sources"][0]["approval_reference"] = "repo:evidence/test-only/other.json"
            _resign(payload)
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "declared_readiness_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                    allow_test_only=True,
                )

    def test_missing_prohibited_capability_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload = copy.deepcopy(load_json(CANONICAL))
            payload["communication_policy"]["prohibited_capabilities"].remove("target_price")
            _resign(payload)
            contract_path = repo_root / "entry-readiness.json"
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "prohibited_capabilities_incomplete"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                )

    def test_missing_personal_data_approval_is_structured_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload, contract_path = _synthetic_go(repo_root)
            payload["required_approvals"]["personal_information_processing"] = {
                "status": "pending",
                "authority": None,
                "scope_hash": None,
                "evidence_ref": None,
                "evidence_sha256": None,
                "issued_at": None,
                "expires_at": None,
                "test_only": True,
            }
            payload["readiness_status"] = "blocked"
            payload["blocked_by"] = ["personal_information_processing"]
            payload["truth_boundary"]["real_user_data_allowed"] = False
            _resign(payload)
            _write_json(contract_path, payload)
            result = verify_contract(
                contract_path,
                SCHEMA,
                repo_root=repo_root,
                reference_time=REFERENCE_TIME,
                allow_test_only=True,
            )
            self.assertEqual("blocked", result["readiness_status"])
            self.assertEqual(["personal_information_processing"], result["blocked_by"])

    def test_receipt_hash_tamper_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            payload = copy.deepcopy(load_json(CANONICAL))
            payload["receipt_hash"] = "f" * 64
            contract_path = repo_root / "entry-readiness.json"
            _write_json(contract_path, payload)
            with self.assertRaisesRegex(EntryContractError, "receipt_hash_mismatch"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
                    reference_time=REFERENCE_TIME,
                )

    def test_trust_policy_tamper_is_invalid_even_while_entry_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trust_path = Path(directory) / "trust-policy.json"
            trust = load_json(TRUST_POLICY)
            trust["receipt_hash"] = "f" * 64
            _write_json(trust_path, trust)
            with self.assertRaisesRegex(
                EntryContractError, "trust_policy_receipt_hash_mismatch"
            ):
                verify_contract(
                    CANONICAL,
                    SCHEMA,
                    repo_root=ROOT,
                    trust_policy_path=trust_path,
                    reference_time=REFERENCE_TIME,
                )


if __name__ == "__main__":
    unittest.main()
