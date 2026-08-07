from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.verify_personal_holdings_risk_card_entry import (
    APPROVAL_SCHEMA_VERSION,
    REQUIRED_APPROVALS,
    EntryContractError,
    digest,
    load_json,
    scope_hash,
    verify_contract,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "product/schemas/personal-holdings-risk-card-entry-v1.schema.json"
CANONICAL = ROOT / "evidence/market-regime-m1/entry-readiness.json"
REFERENCE_TIME = datetime(2026, 8, 7, tzinfo=timezone.utc)


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
        authority = f"test-authority:{key}"
        evidence = {
            "schema_version": APPROVAL_SCHEMA_VERSION,
            "approval_key": key,
            "decision": "approved",
            "authority": authority,
            "scope_hash": expected_scope_hash,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "test_only": True,
        }
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
            with self.assertRaisesRegex(EntryContractError, "test_only_contract_rejected"):
                verify_contract(
                    contract_path,
                    SCHEMA,
                    repo_root=repo_root,
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
                "test_only": False,
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


if __name__ == "__main__":
    unittest.main()
