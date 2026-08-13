from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_evidence import (  # noqa: E402
    MarketRegimeDailyEvidenceStore,
)
from data_core.market_regime_daily_narrative import (  # noqa: E402
    MarketRegimeDailyNarrativeError,
    MarketRegimeDailyNarrativeStore,
    build_narrative_request,
    deterministic_fallback,
    validate_model_output,
    validate_narrative_output,
)
import data_core.market_regime_daily_narrative as narrative_module  # noqa: E402
from product.tests.test_market_regime_daily_evidence import fixture_inputs  # noqa: E402


class FakeProvider:
    provider_name = "FakeProvider"
    model = "fake-model"

    def __init__(self, output: dict | Exception) -> None:
        self.output = output
        self.requests: list[dict] = []

    def generate(self, request: dict) -> tuple[dict, dict]:
        self.requests.append(json.loads(json.dumps(request)))
        if isinstance(self.output, Exception):
            raise self.output
        return self.output, {
            "request_id": "fake-request",
            "model": self.model,
            "finish_reason": "test_transport",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }


class UnsafeReceiptProvider(FakeProvider):
    def generate(self, request: dict) -> tuple[dict, dict]:
        self.requests.append(json.loads(json.dumps(request)))
        return self.output if isinstance(self.output, dict) else {}, {
            "request_id": "api_key=must-not-persist",
        }


class TokenLabelProvider(FakeProvider):
    provider_name = "sk-live-AbCdEfGhIjKlMnOpQrStUvWx"
    model = "rk_live_model"

    def generate(self, request: dict) -> tuple[dict, dict]:
        self.requests.append(json.loads(json.dumps(request)))
        return self.output, {"request_id": "safe-request", "model": "safe-model"}


class CredentialShapeProvider(FakeProvider):
    provider_name = "AKIA" + "A" * 16
    model = "AIza" + "A" * 35

    def generate(self, request: dict) -> tuple[dict, dict]:
        self.requests.append(json.loads(json.dumps(request)))
        return self.output, {
            "request_id": "AKIA" + "A" * 16,
            "model": "AIza" + "A" * 35,
        }


class SwitchingEvidenceStore:
    def __init__(self, first: dict, second: dict) -> None:
        self.first = first
        self.second = second
        self.calls = 0

    def latest(self) -> dict:
        self.calls += 1
        return self.first if self.calls == 1 else self.second


def valid_output(pack: dict) -> dict:
    ids_by_key = {
        slot["key"]: slot["evidence_id"]
        for slot in pack["slots"]
        if slot.get("evidence_id")
    }
    ids = list(pack["evidence_index"])
    candidates = pack.get("contradiction_candidates") or []
    contradiction = (
        {
            "candidate_id": candidates[0]["candidate_id"],
            "evidence_ids": list(candidates[0]["evidence_ids"]),
        }
        if candidates
        else {
            "candidate_id": "narrative:explanation_unavailable",
            "evidence_ids": [ids[6]],
        }
    )
    return {
        "posture": "wait",
        "posture_evidence_ids": [ids[0], ids[1]],
        "theme": "mixed",
        "theme_evidence_ids": [ids[0], ids[4]],
        "transmission_chain": [
            {
                "driver": "risk_assets",
                "response": "risk_on",
                "evidence_ids": [ids_by_key["sp500"], ids_by_key["nasdaq"]],
                "causal_status": "supported_observation",
            },
            {
                "driver": "rates",
                "response": "defensive",
                "evidence_ids": [ids_by_key["us2y"], ids_by_key["us10y"]],
                "causal_status": "plausible_interpretation",
            },
            {
                "driver": "regional",
                "response": "mixed",
                "evidence_ids": [ids_by_key["shanghai"], ids_by_key["kospi"]],
                "causal_status": "supported_observation",
            },
        ],
        "contradictions": [contradiction],
        "falsifiers": [
            {
                "evidence_ids": [ids[0]],
                "field": "change_5d",
                "expected_change": "sign_reversal",
            },
            {
                "evidence_ids": [ids[2], ids[3]],
                "field": "trend_score",
                "expected_change": "relationship_breaks",
            },
        ],
    }


def stores(
    daily_root: Path, macro_root: Path, evidence_root: Path, narrative_root: Path
) -> tuple[MarketRegimeDailyEvidenceStore, MarketRegimeDailyNarrativeStore, dict]:
    fixture_inputs(daily_root, macro_root)
    evidence_store = MarketRegimeDailyEvidenceStore(daily_root, macro_root, evidence_root)
    pack = evidence_store.compile_latest()
    return (
        evidence_store,
        MarketRegimeDailyNarrativeStore(evidence_store, narrative_root),
        pack,
    )


class MarketRegimeDailyNarrativeTest(unittest.TestCase):
    def test_request_contains_only_frozen_evidence_and_no_prior_generated_prose(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, _, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            request = build_narrative_request(pack)
        encoded = json.dumps(request, ensure_ascii=False)
        self.assertEqual(request["pack_id"], pack["pack_id"])
        self.assertEqual(len(request["evidence_slots"]), 16)
        self.assertNotIn("what_is_going_on", encoded)
        self.assertNotIn("raw_path", encoded)
        self.assertNotIn("api-key", encoded.lower())

    def test_validator_accepts_strict_citations_and_rejects_unsafe_variants(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, _, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            output = valid_output(pack)
            self.assertEqual(validate_model_output(output, pack)["posture"], "wait")
            cases = []
            unknown = json.loads(json.dumps(output))
            unknown["transmission_chain"][0]["evidence_ids"] = ["unknown:id"]
            cases.append((unknown, "unknown evidence"))
            numeric = json.loads(json.dumps(output))
            numeric["synthesis"] = "市场上涨百分之五"
            cases.append((numeric, "schema keys"))
            trading = json.loads(json.dumps(output))
            trading["theme"] = "buy"
            cases.append((trading, "enum"))
            injection = json.loads(json.dumps(output))
            injection["transmission_chain"][0]["driver"] = "ignore_previous"
            cases.append((injection, "enum"))
            wrong_count = json.loads(json.dumps(output))
            wrong_count["falsifiers"] = wrong_count["falsifiers"][:1]
            cases.append((wrong_count, "exactly two"))
            extra = json.loads(json.dumps(output))
            extra["extra"] = "not allowed"
            cases.append((extra, "schema keys"))
            causal = json.loads(json.dumps(output))
            causal["transmission_chain"][0]["causal_status"] = "proven_cause"
            cases.append((causal, "transmission enum"))
            for value, expected in cases:
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, expected):
                        validate_model_output(value, pack)

    def test_validator_binds_response_side_of_transmission_chain(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, _, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            output = valid_output(pack)
            output["transmission_chain"][1]["response"] = "growth_led"
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "response"):
                validate_model_output(output, pack)

    def test_supported_observation_matches_code_owned_direction(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, _, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            output = valid_output(pack)
            output["transmission_chain"][0]["response"] = "risk_off"
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "deterministic response"):
                validate_model_output(output, pack)
            mixed = valid_output(pack)
            mixed["transmission_chain"][2]["evidence_ids"] = [
                mixed["transmission_chain"][2]["evidence_ids"][0]
            ]
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "deterministic response"):
                validate_model_output(mixed, pack)
            unknown = valid_output(pack)
            unknown["transmission_chain"][0]["response"] = "unknown"
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "deterministic response"):
                validate_model_output(unknown, pack)

    def test_fallback_only_contradiction_sentinel_is_not_model_success(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, _, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            no_candidates = json.loads(json.dumps(pack))
            no_candidates["contradiction_candidates"] = []
            output = valid_output(no_candidates)
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "candidate"):
                validate_model_output(output, no_candidates)
            fallback = deterministic_fallback(no_candidates, reason_code="provider_missing")
            clean = {key: value for key, value in fallback.items() if key != "fallback_reason_code"}
            validate_narrative_output(clean, no_candidates, fallback=True)

    def test_model_output_is_persisted_with_secret_free_receipt_and_replays(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            evidence_store, store, pack = stores(
                Path(daily), Path(macro), Path(evidence), Path(narrative)
            )
            provider = FakeProvider(valid_output(pack))
            first = store.compile_latest(provider)
            second = store.compile_latest(provider)
            self.assertEqual(first["narrative_id"], second["narrative_id"])
            self.assertEqual(first["generation_status"], "model_generated_unreviewed")
            self.assertEqual(store.latest()["narrative_id"], first["narrative_id"])
            pointer = json.loads((Path(narrative) / "latest.json").read_text())
            receipt = json.loads((Path(narrative) / pointer["receipt"]["path"]).read_text())
            encoded = json.dumps(receipt)
            self.assertEqual(receipt["provider"], "FakeProvider")
            self.assertNotIn("secret", encoded.lower())
            self.assertNotIn("api_key", encoded.lower())
            self.assertEqual(provider.requests[0]["pack_id"], evidence_store.latest()["pack_id"])

    def test_missing_timeout_and_invalid_output_publish_same_pack_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            model = store.compile_latest(FakeProvider(valid_output(pack)))
            missing = store.compile_latest(None)
            self.assertNotEqual(model["narrative_id"], missing["narrative_id"])
            self.assertEqual(missing["pack_id"], pack["pack_id"])
            self.assertEqual(missing["generation_status"], "deterministic_fallback")
            self.assertIn("fallback_reason_code", missing["output"])
            timeout = store.compile_latest(FakeProvider(TimeoutError("slow")))
            self.assertEqual(timeout["generation_status"], "deterministic_fallback")
            invalid = valid_output(pack)
            invalid["synthesis"] = "建议买入并加仓"
            rejected = store.compile_latest(FakeProvider(invalid))
            self.assertEqual(rejected["generation_status"], "deterministic_fallback")
            self.assertEqual(store.latest()["narrative_id"], rejected["narrative_id"])

    def test_wrapped_transport_timeout_keeps_timeout_reason_code(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            wrapped = RuntimeError("DeepSeek structured API unavailable after retries: TimeoutError")
            wrapped.__cause__ = TimeoutError("transport timed out")
            artifact = store.compile_latest(FakeProvider(wrapped))
            self.assertEqual(artifact["output"]["fallback_reason_code"], "provider_timeout")

    def test_fallback_is_schema_valid_and_never_reuses_old_model_prose(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            old_output = store_output = valid_output(pack)
            store.compile_latest(FakeProvider(valid_output(pack)))
            fallback = store.compile_latest(None)
            clean = {
                key: value
                for key, value in fallback["output"].items()
                if key != "fallback_reason_code"
            }
            validate_narrative_output(clean, pack, fallback=True)
            self.assertNotEqual(clean["theme"], old_output["theme"])
            self.assertEqual(clean["posture"], "unknown")

    def test_store_detects_artifact_tamper_and_current_pack_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            evidence_store, store, pack = stores(
                Path(daily), Path(macro), Path(evidence), Path(narrative)
            )
            store.compile_latest(FakeProvider(valid_output(pack)))
            pointer = json.loads((Path(narrative) / "latest.json").read_text())
            artifact = Path(narrative) / pointer["artifact"]["path"]
            artifact.write_bytes(artifact.read_bytes() + b" ")
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "artifact hash mismatch"):
                store.latest()

            # Restore by recompiling into a clean narrative root, then advance
            # the evidence pointer to a different valid pack identity.
            with tempfile.TemporaryDirectory() as clean_narrative:
                clean_store = MarketRegimeDailyNarrativeStore(evidence_store, clean_narrative)
                clean_store.compile_latest(FakeProvider(valid_output(pack)))
                evidence_pointer = json.loads((Path(evidence) / "latest.json").read_text())
                evidence_pointer["pack_id"] = "market-regime-daily-evidence:" + "0" * 64
                (Path(evidence) / "latest.json").write_text(json.dumps(evidence_pointer))
                with self.assertRaises(MarketRegimeDailyNarrativeError):
                    clean_store.latest()

    def test_failure_receipt_uses_fixed_reason_without_provider_error_text(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            secretish = "provider failed api_key=do-not-persist"
            artifact = store.compile_latest(FakeProvider(RuntimeError(secretish)))
            self.assertEqual(artifact["generation_status"], "deterministic_fallback")
            pointer = json.loads((Path(narrative) / "latest.json").read_text())
            receipt = json.loads((Path(narrative) / pointer["receipt"]["path"]).read_text())
            encoded = json.dumps(receipt, ensure_ascii=False)
            self.assertEqual(receipt["validation"]["reason"], "provider_error")
            self.assertNotIn(secretish, encoded)
            self.assertNotIn("do-not-persist", encoded)
            self.assertEqual(store.latest()["narrative_id"], artifact["narrative_id"])

    def test_unsafe_provider_receipt_falls_back_without_persisting_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            artifact = store.compile_latest(UnsafeReceiptProvider(valid_output(pack)))
            self.assertEqual(artifact["generation_status"], "deterministic_fallback")
            pointer = json.loads((Path(narrative) / "latest.json").read_text())
            receipt = json.loads((Path(narrative) / pointer["receipt"]["path"]).read_text())
            self.assertEqual(receipt["validation"]["reason"], "narrative_validation_failed")
            self.assertEqual(receipt["provider_receipt"], {})
            self.assertNotIn("api_key", json.dumps(receipt).lower())

    def test_token_shaped_provider_labels_are_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            artifact = store.compile_latest(TokenLabelProvider(valid_output(pack)))
            pointer = json.loads((Path(narrative) / "latest.json").read_text())
            receipt = json.loads((Path(narrative) / pointer["receipt"]["path"]).read_text())
            self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")
            self.assertEqual(receipt["provider"], "unknown")
            self.assertEqual(receipt["model"], "unknown")

    def test_unseparated_aws_and_google_tokens_are_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            artifact = store.compile_latest(CredentialShapeProvider(valid_output(pack)))
            pointer = json.loads((Path(narrative) / "state.json").read_text())["pointer"]
            receipt = json.loads((Path(narrative) / pointer["receipt"]["path"]).read_text())
            encoded = json.dumps(receipt)
            self.assertEqual(artifact["generation_status"], "deterministic_fallback")
            self.assertEqual(receipt["provider"], "unknown")
            self.assertEqual(receipt["model"], "unknown")
            self.assertNotIn("AKIA" + "A" * 16, encoded)
            self.assertNotIn("AIza" + "A" * 35, encoded)

    def test_model_cannot_inject_free_text_or_code_owned_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, _, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            injected = valid_output(pack)
            injected["synthesis"] = "本结果可对外分发，并作为操作依据"
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "schema keys"):
                validate_model_output(injected, pack)
            semantic = valid_output(pack)
            semantic["transmission_chain"][0]["driver"] = "causal"
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "enum"):
                validate_model_output(semantic, pack)

    def test_latest_rejects_coherent_truth_boundary_rebind(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            store.compile_latest(FakeProvider(valid_output(pack)))
            root = Path(narrative)
            state = json.loads((root / "state.json").read_text())
            pointer = state["pointer"]
            artifact = json.loads((root / pointer["artifact"]["path"]).read_text())
            receipt = json.loads((root / pointer["receipt"]["path"]).read_text())
            boundary = dict(artifact["identity_core"]["truth_boundary"])
            boundary["action_eligible"] = True
            artifact["identity_core"]["truth_boundary"] = boundary
            for key, value in artifact["identity_core"].items():
                artifact[key] = value
            digest = narrative_module._hash(artifact["identity_core"])
            artifact["narrative_id"] = f"market-regime-daily-narrative:{digest}"
            artifact_path = root / f"artifacts/{digest}.json"
            artifact_path.write_bytes(narrative_module._json_bytes(artifact))
            artifact_ref = {
                "path": f"artifacts/{digest}.json",
                "sha256": sha256(artifact_path.read_bytes()).hexdigest(),
            }
            receipt["narrative_id"] = artifact["narrative_id"]
            receipt["artifact"] = artifact_ref
            receipt_path = root / pointer["receipt"]["path"]
            receipt_path.write_bytes(narrative_module._json_bytes(receipt))
            receipt_ref = {
                "path": pointer["receipt"]["path"],
                "sha256": sha256(receipt_path.read_bytes()).hexdigest(),
            }
            pointer.update(
                {
                    "narrative_id": artifact["narrative_id"],
                    "artifact": artifact_ref,
                    "receipt": receipt_ref,
                }
            )
            state["pointer"] = pointer
            state["floor"] = {
                **state["floor"],
                "narrative_id": artifact["narrative_id"],
                "receipt_sha256": receipt_ref["sha256"],
            }
            (root / "state.json").write_bytes(narrative_module._json_bytes(state))
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "truth boundary"):
                store.latest()

    def test_latest_rejects_noncanonical_receipt_path_after_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, store, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            store.compile_latest(FakeProvider(valid_output(pack)))
            root = Path(narrative)
            state = json.loads((root / "state.json").read_text())
            pointer = state["pointer"]
            old_path = root / pointer["receipt"]["path"]
            alternate = root / "receipts/not-the-run-id.json"
            alternate.write_bytes(old_path.read_bytes())
            pointer["receipt"] = {
                "path": "receipts/not-the-run-id.json",
                "sha256": sha256(alternate.read_bytes()).hexdigest(),
            }
            state["pointer"] = pointer
            (root / "state.json").write_bytes(narrative_module._json_bytes(state))
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "receipt reference"):
                store.latest()

    def test_pack_advance_during_provider_call_does_not_publish_mixed_narrative(self) -> None:
        with tempfile.TemporaryDirectory() as daily, tempfile.TemporaryDirectory() as macro, tempfile.TemporaryDirectory() as evidence, tempfile.TemporaryDirectory() as narrative:
            _, _, pack = stores(Path(daily), Path(macro), Path(evidence), Path(narrative))
            advanced = json.loads(json.dumps(pack))
            advanced["pack_id"] = "market-regime-daily-evidence:" + "f" * 64
            switching = SwitchingEvidenceStore(pack, advanced)
            store = MarketRegimeDailyNarrativeStore(switching, Path(narrative))
            with self.assertRaisesRegex(MarketRegimeDailyNarrativeError, "advanced"):
                store.compile_latest(FakeProvider(valid_output(pack)))
            self.assertFalse((Path(narrative) / "latest.json").exists())

    def test_cli_status_is_informational_only_for_unused_output(self) -> None:
        script = PRODUCT.parent / "scripts" / "compile_market_regime_daily_narrative.py"
        with tempfile.TemporaryDirectory() as empty:
            result = subprocess.run(
                [sys.executable, str(script), "--output-root", empty, "--status"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
