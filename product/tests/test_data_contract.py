from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core import (  # noqa: E402
    CONTRACT_VERSION,
    RECORD_SCHEMAS,
    Provenance,
    RawCapture,
    RecordDomain,
    RecordEnvelope,
    RecordStatus,
    SourceManifest,
    contract_descriptor,
    validate_adapter_output,
)


MANIFEST = SourceManifest(
    source_key="official_market_v1",
    domain_scope="market",
    authority_tier="official",
    provider_version="2026-07-22",
    schema_version="provider-market-v3",
    license_status="configured_internal_use",
    source_url="https://example.test/market",
)
RAW = RawCapture(
    raw_hash="a" * 64,
    storage_uri="raw/official_market_v1/2026/07/22/a.json",
    source_url="https://example.test/market/300750",
    fetched_at="2026-07-22T09:00:00+08:00",
    known_at="2026-07-22T09:00:00+08:00",
    mime_type="application/json",
    payload_size=128,
)
MARKET_PAYLOAD = {
    "instrument_id": "CN:300750.SZ",
    "observed_at": "2026-07-22",
    "metric": "close",
    "value": 258.2,
    "unit": "CNY/share",
}
VALID_PAYLOADS = {
    RecordDomain.MARKET: MARKET_PAYLOAD,
    RecordDomain.FUNDAMENTAL: {
        "instrument_id": "CN:300750.SZ",
        "report_period": "2026-06-30",
        "announced_at": "2026-07-21T18:00:00+08:00",
        "metric": "revenue",
        "value": 102400000000,
        "unit": "CNY",
    },
    RecordDomain.DOCUMENT: {
        "document_id": "doc-1",
        "instrument_id": "CN:300750.SZ",
        "document_type": "quarterly_report",
        "published_at": "2026-07-21T18:00:00+08:00",
        "content_hash": "b" * 64,
        "storage_uri": "raw/documents/doc-1.pdf",
    },
    RecordDomain.ESTIMATE: {
        "estimate_id": "estimate-1",
        "instrument_id": "CN:300750.SZ",
        "broker": "Example Securities",
        "published_at": "2026-07-21T18:00:00+08:00",
        "fiscal_period": "2027-12-31",
        "metric": "eps",
        "value": 18.5,
        "unit": "CNY/share",
    },
    RecordDomain.EVENT: {
        "event_id": "evt-1",
        "instrument_id": "CN:300750.SZ",
        "event_type": "announcement",
        "occurred_at": "2026-07-21T18:00:00+08:00",
        "title": "Example event",
        "evidence_ids": ["doc-1"],
    },
}


def manifest_for(domain: RecordDomain, *, active: bool = True) -> SourceManifest:
    return SourceManifest(
        **{**MANIFEST.__dict__, "domain_scope": domain.value, "active": active}
    )


class CanonicalDataContractTests(unittest.TestCase):
    def test_contract_has_exactly_five_versioned_record_domains(self) -> None:
        self.assertEqual(set(RECORD_SCHEMAS), set(RecordDomain))
        self.assertEqual(len(RECORD_SCHEMAS), 5)
        for domain, schema in RECORD_SCHEMAS.items():
            self.assertEqual(schema.domain, domain)
            self.assertRegex(schema.version, rf"^{domain.value}-record-v\d+$")
            self.assertGreaterEqual(len(schema.required_fields), 5)

    def test_descriptor_is_stable_and_names_only_accepted_or_rejected_states(self) -> None:
        descriptor = contract_descriptor()
        self.assertEqual(descriptor["contract_version"], CONTRACT_VERSION)
        self.assertEqual(descriptor["record_statuses"], ["accepted", "rejected"])
        self.assertEqual(set(descriptor["record_schemas"]), {domain.value for domain in RecordDomain})
        self.assertIn("raw_hash", descriptor["required_provenance"])
        self.assertIn("source_manifest_hash", descriptor["required_provenance"])
        golden = json.loads(
            (ROOT / "product/data_core/schemas/canonical-data-contract-v1.json").read_text()
        )
        self.assertEqual(descriptor, golden)

    def test_accepted_record_is_bound_to_manifest_and_raw_capture(self) -> None:
        envelope = RecordEnvelope.accepted(
            domain=RecordDomain.MARKET,
            entity_key="CN:300750.SZ:2026-07-22:close",
            payload=MARKET_PAYLOAD,
            manifest=MANIFEST,
            raw=RAW,
        )
        self.assertEqual(envelope.status, RecordStatus.ACCEPTED)
        self.assertEqual(envelope.provenance.source_manifest_hash, MANIFEST.manifest_hash)
        self.assertEqual(len(envelope.record_hash), 64)

    def test_manual_or_tampered_provenance_cannot_pass_adapter_boundary(self) -> None:
        valid = RecordEnvelope.accepted(
            domain=RecordDomain.MARKET,
            entity_key="CN:300750.SZ:2026-07-22:close",
            payload=MARKET_PAYLOAD,
            manifest=MANIFEST,
            raw=RAW,
        )
        tampered = copy.copy(valid)
        object.__setattr__(
            tampered,
            "provenance",
            Provenance(**{**valid.provenance.__dict__, "raw_hash": "b" * 64}),
        )
        with self.assertRaisesRegex(ValueError, "not bound"):
            validate_adapter_output(manifest=MANIFEST, raw=RAW, records=[tampered])

    def test_adapter_boundary_rejects_untyped_payloads(self) -> None:
        with self.assertRaisesRegex(ValueError, "only RecordEnvelope"):
            validate_adapter_output(manifest=MANIFEST, raw=RAW, records=[MARKET_PAYLOAD])

    def test_payload_is_detached_and_cannot_change_after_boundary_validation(self) -> None:
        envelope = RecordEnvelope.accepted(
            domain=RecordDomain.MARKET,
            entity_key="CN:300750.SZ:2026-07-22:close",
            payload=dict(MARKET_PAYLOAD),
            manifest=MANIFEST,
            raw=RAW,
        )
        detached = envelope.payload
        detached["value"] = 9999
        validated = validate_adapter_output(manifest=MANIFEST, raw=RAW, records=[envelope])
        self.assertEqual(validated[0].payload["value"], MARKET_PAYLOAD["value"])
        self.assertNotEqual(validated[0].payload["value"], detached["value"])

    def test_rejected_record_requires_a_reason_and_keeps_provenance(self) -> None:
        rejected = RecordEnvelope.rejected(
            domain=RecordDomain.MARKET,
            entity_key="CN:300750.SZ:2026-07-22:close",
            payload=MARKET_PAYLOAD,
            manifest=MANIFEST,
            raw=RAW,
            rejection_reason="provider returned an impossible negative close",
            violations=("value.invalid_range",),
            quality_flags=("invalid_range",),
        )
        self.assertEqual(rejected.status, RecordStatus.REJECTED)
        object.__setattr__(rejected, "rejection_reason", "")
        with self.assertRaisesRegex(ValueError, "requires rejection_reason"):
            rejected.validate(manifest=MANIFEST, raw=RAW)

    def test_rejected_record_can_audit_an_invalid_provider_payload(self) -> None:
        rejected = RecordEnvelope.rejected(
            domain=RecordDomain.FUNDAMENTAL,
            entity_key="provider-row-17",
            payload={"instrument_id": "CN:300750.SZ", "value": None},
            manifest=manifest_for(RecordDomain.FUNDAMENTAL),
            raw=RAW,
            rejection_reason="required provider fields were missing",
            violations=("report_period.missing", "announced_at.missing"),
        )
        self.assertEqual(rejected.status, RecordStatus.REJECTED)
        validate_adapter_output(
            manifest=manifest_for(RecordDomain.FUNDAMENTAL), raw=RAW, records=[rejected]
        )

    def test_rejection_metadata_types_are_strict(self) -> None:
        accepted = RecordEnvelope.accepted(
            domain=RecordDomain.MARKET,
            entity_key="market:accepted",
            payload=MARKET_PAYLOAD,
            manifest=MANIFEST,
            raw=RAW,
        )
        object.__setattr__(accepted, "rejection_reason", 0)
        with self.assertRaisesRegex(ValueError, "accepted record cannot include"):
            accepted.validate(manifest=MANIFEST, raw=RAW)
        rejected = RecordEnvelope.rejected(
            domain=RecordDomain.MARKET,
            entity_key="market:rejected",
            payload={"provider_value": "bad"},
            manifest=MANIFEST,
            raw=RAW,
            rejection_reason="invalid provider value",
            violations=("value.invalid",),
        )
        object.__setattr__(rejected, "rejection_reason", object())
        with self.assertRaisesRegex(ValueError, "requires rejection_reason"):
            rejected.validate(manifest=MANIFEST, raw=RAW)

    def test_manual_string_status_cannot_bypass_closed_status_enum(self) -> None:
        valid = RecordEnvelope.accepted(
            domain=RecordDomain.MARKET,
            entity_key="CN:300750.SZ:2026-07-22:close",
            payload=MARKET_PAYLOAD,
            manifest=MANIFEST,
            raw=RAW,
        )
        object.__setattr__(valid, "status", "accepted")
        with self.assertRaisesRegex(ValueError, "unsupported record status"):
            valid.validate(manifest=MANIFEST, raw=RAW)

    def test_mutable_record_metadata_is_rejected(self) -> None:
        valid = RecordEnvelope.accepted(
            domain=RecordDomain.MARKET,
            entity_key="CN:300750.SZ:2026-07-22:close",
            payload=MARKET_PAYLOAD,
            manifest=MANIFEST,
            raw=RAW,
        )
        object.__setattr__(valid, "quality_flags", ["mutable"])
        with self.assertRaisesRegex(ValueError, "quality_flags must be a tuple"):
            valid.validate(manifest=MANIFEST, raw=RAW)

    def test_manifest_domain_scope_prevents_cross_domain_adapter_output(self) -> None:
        payload = {
            "event_id": "evt-1",
            "instrument_id": "CN:300750.SZ",
            "event_type": "announcement",
            "occurred_at": "2026-07-22T08:00:00+08:00",
            "title": "Test",
            "evidence_ids": ["doc-1"],
        }
        with self.assertRaisesRegex(ValueError, "not registered for event"):
            RecordEnvelope.accepted(
                domain=RecordDomain.EVENT,
                entity_key="evt-1",
                payload=payload,
                manifest=MANIFEST,
                raw=RAW,
            )

    def test_shipped_market_bundle_scope_remains_backward_compatible(self) -> None:
        legacy = SourceManifest(
            **{**MANIFEST.__dict__, "domain_scope": "a_share_market_bundle"}
        )
        legacy.validate()
        self.assertEqual(
            legacy.domains,
            {RecordDomain.MARKET, RecordDomain.FUNDAMENTAL, RecordDomain.EVENT},
        )

    def test_missing_required_payload_field_fails_closed(self) -> None:
        payload = dict(MARKET_PAYLOAD)
        payload.pop("unit")
        with self.assertRaisesRegex(ValueError, "payload missing: unit"):
            RecordEnvelope.accepted(
                domain=RecordDomain.MARKET,
                entity_key="CN:300750.SZ:2026-07-22:close",
                payload=payload,
                manifest=MANIFEST,
                raw=RAW,
            )

    def test_every_domain_rejects_null_required_values(self) -> None:
        for domain, valid_payload in VALID_PAYLOADS.items():
            with self.subTest(domain=domain.value):
                payload = dict(valid_payload)
                payload[next(iter(RECORD_SCHEMAS[domain].required_fields))] = None
                with self.assertRaisesRegex(ValueError, "payload null"):
                    RecordEnvelope.accepted(
                        domain=domain,
                        entity_key=f"{domain.value}:invalid-null",
                        payload=payload,
                        manifest=manifest_for(domain),
                        raw=RAW,
                    )

    def test_every_domain_blocks_future_visible_records(self) -> None:
        temporal_fields = {
            RecordDomain.MARKET: "observed_at",
            RecordDomain.FUNDAMENTAL: "announced_at",
            RecordDomain.DOCUMENT: "published_at",
            RecordDomain.ESTIMATE: "published_at",
            RecordDomain.EVENT: "occurred_at",
        }
        for domain, field in temporal_fields.items():
            with self.subTest(domain=domain.value):
                payload = dict(VALID_PAYLOADS[domain])
                payload[field] = "2026-07-23T00:00:00+08:00"
                with self.assertRaisesRegex(ValueError, "later than provenance known_at"):
                    RecordEnvelope.accepted(
                        domain=domain,
                        entity_key=f"{domain.value}:future",
                        payload=payload,
                        manifest=manifest_for(domain),
                        raw=RAW,
                    )

    def test_non_json_or_non_finite_values_fail_closed(self) -> None:
        non_json = dict(MARKET_PAYLOAD, metadata=object())
        with self.assertRaisesRegex(ValueError, "non-JSON value"):
            RecordEnvelope.accepted(
                domain=RecordDomain.MARKET,
                entity_key="market:non-json",
                payload=non_json,
                manifest=MANIFEST,
                raw=RAW,
            )
        non_finite = dict(MARKET_PAYLOAD, value=float("nan"))
        with self.assertRaisesRegex(ValueError, "non-finite number"):
            RecordEnvelope.accepted(
                domain=RecordDomain.MARKET,
                entity_key="market:nan",
                payload=non_finite,
                manifest=MANIFEST,
                raw=RAW,
            )

    def test_inactive_source_cannot_emit_accepted_records(self) -> None:
        with self.assertRaisesRegex(ValueError, "is inactive"):
            RecordEnvelope.accepted(
                domain=RecordDomain.MARKET,
                entity_key="market:inactive",
                payload=MARKET_PAYLOAD,
                manifest=manifest_for(RecordDomain.MARKET, active=False),
                raw=RAW,
            )

    def test_manifest_types_are_strict_and_cannot_bypass_inactive_gate(self) -> None:
        for invalid_active in ("false", 0, 1, None):
            with self.subTest(active=invalid_active):
                invalid = SourceManifest(**{**MANIFEST.__dict__, "active": invalid_active})
                with self.assertRaisesRegex(ValueError, "active must be a bool"):
                    invalid.validate()
        invalid_identity = SourceManifest(**{**MANIFEST.__dict__, "provider_version": object()})
        with self.assertRaisesRegex(ValueError, "non-empty strings: provider_version"):
            invalid_identity.validate()
        invalid_flags = SourceManifest(**{**MANIFEST.__dict__, "quality_flags": ["mutable"]})
        with self.assertRaisesRegex(ValueError, "quality_flags must be a tuple"):
            invalid_flags.validate()

    def test_raw_capture_requires_hash_url_and_timezone(self) -> None:
        bad = RawCapture(**{**RAW.__dict__, "known_at": "2026-07-22T09:00:00"})
        with self.assertRaisesRegex(ValueError, "known_at must include timezone"):
            bad.validate()
        for invalid_size in (True, 1.5, -1):
            with self.subTest(payload_size=invalid_size):
                bad_size = RawCapture(**{**RAW.__dict__, "payload_size": invalid_size})
                with self.assertRaisesRegex(ValueError, "nonnegative int"):
                    bad_size.validate()

    def test_architecture_entry_evidence_is_locked_and_names_single_authority(self) -> None:
        architecture = (ROOT / "docs/architecture/repo-composition-architecture.md").read_text()
        lock = json.loads(
            (ROOT / "docs/architecture/repo-components.lock.yaml").read_text()
        )
        adr = (ROOT / "docs/architecture/adr/0001-canonical-data-contract-v1.md").read_text()
        expected_repos = {
            "zinan92/datafeed", "simonlin1212/a-stock-data", "HKUDS/Vibe-Trading",
            "simonlin1212/global-stock-data", "zinan92/quant-data-pipeline", "zinan92/intel",
            "rollingSirius/equity-research-skill", "star23/Day1Global-Skills",
        }
        components = lock["components"]
        self.assertEqual(lock["format"], "json-compatible-yaml")
        self.assertEqual(len(components), len(expected_repos))
        self.assertEqual(
            {component["repo"].removeprefix("https://github.com/") for component in components},
            expected_repos,
        )
        required = {
            "repo", "commit", "license", "adoption", "selected", "target",
            "upgrade_gate", "audited_at", "update_policy", "contract_tests",
        }
        for component in components:
            self.assertTrue(required.issubset(component), component["repo"])
            self.assertRegex(component["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(component["license"])
            self.assertTrue(component["adoption"])
            self.assertTrue(component["selected"])
            self.assertTrue(component["target"])
            self.assertEqual(component["audited_at"], lock["audited_at"])
            self.assertEqual(component["contract_tests"], [component["upgrade_gate"]])
            self.assertIn(component["repo"].removeprefix("https://github.com/"), architecture)
        self.assertIn("只有 Supabase PostgreSQL + Storage 是 authority", architecture)
        self.assertEqual(len(re.findall(r"只有 Supabase PostgreSQL \+ Storage 是 authority", architecture)), 1)
        self.assertIn(CONTRACT_VERSION, adr)
        self.assertIn("adapter 只能产生带 provenance 的 RecordEnvelope", adr)


if __name__ == "__main__":
    unittest.main()
