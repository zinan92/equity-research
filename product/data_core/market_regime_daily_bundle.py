"""Immutable Daily v2 bundle over the verified S3/S4 artifacts.

This module is deliberately a projection layer.  It never fetches a provider,
calculates a market score, or invents narrative text.  S3 owns the evidence
facts and S4 owns the constrained narrative; this store only verifies both
identities, builds a stable publication artifact, and keeps an atomic served
pointer with provenance receipts.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping
from uuid import uuid4

from .market_regime_daily_evidence import (
    MarketRegimeDailyEvidenceError,
    MarketRegimeDailyEvidenceStore,
)
from .market_regime_daily_lock import daily_publication_lock
from .market_regime_daily_narrative import (
    MarketRegimeDailyNarrativeError,
    MarketRegimeDailyNarrativeStore,
)


SCHEMA_VERSION = "market-regime-daily-bundle-v1"
STATE_SCHEMA_VERSION = "market-regime-daily-bundle-state-v1"
RECEIPT_SCHEMA_VERSION = "market-regime-daily-bundle-receipt-v1"
PACK_ID_PREFIX = "market-regime-daily-evidence:"
NARRATIVE_ID_PREFIX = "market-regime-daily-narrative:"
BUNDLE_ID_PREFIX = "market-regime-daily-bundle:"
OUTPUT_KEYS = frozenset(
    {
        "posture",
        "posture_evidence_ids",
        "theme",
        "theme_evidence_ids",
        "transmission_chain",
        "contradictions",
        "falsifiers",
        "synthesis",
        "synthesis_evidence_ids",
        "confidence_explanation",
        "confidence_evidence_ids",
        "source_boundary",
        "source_boundary_evidence_ids",
    }
)
FALLBACK_OUTPUT_KEYS = OUTPUT_KEYS | {"fallback_reason_code"}
BUNDLE_KEYS = frozenset(
    {
        "schema_version",
        "bundle_id",
        "publication_identity",
        "pack_id",
        "narrative_id",
        "generation_status",
        "evidence",
        "narrative",
        "truth_boundary",
        "publication_eligible",
        "action_eligible",
    }
)
IDENTITY_KEYS = frozenset(
    {
        "schema_version",
        "pack_id",
        "narrative_id",
        "evidence_artifact_sha256",
        "narrative_artifact_sha256",
        "evidence_schema_version",
        "narrative_schema_version",
        "narrative_compiler_version",
        "narrative_prompt_version",
        "generation_status",
        "projection_hashes",
        "truth_boundary",
    }
)
REF_KEYS = frozenset({"path", "sha256"})
STATE_KEYS = frozenset({"schema_version", "served", "latest_check_receipt"})
SERVED_KEYS = frozenset({"bundle_id", "artifact", "completion_receipt"})
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "event",
        "receipt_id",
        "bundle_id",
        "publication_identity",
        "evidence",
        "narrative",
        "publication_eligible",
        "action_eligible",
    }
)
RECEIPT_SIDE_KEYS = frozenset({"artifact", "receipt"})


class MarketRegimeDailyBundleError(RuntimeError):
    """A Daily bundle, provenance receipt, or state contract failed closed."""


class MarketRegimeDailyBundleRace(MarketRegimeDailyBundleError):
    """The S3/S4 candidate changed before Daily publication could commit."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _hash(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _read_json(path: Path, *, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MarketRegimeDailyBundleError(error) from exc
    except json.JSONDecodeError as exc:
        raise MarketRegimeDailyBundleError(error) from exc
    if not isinstance(value, dict):
        raise MarketRegimeDailyBundleError(error)
    return value


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> str:
    encoded = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != encoded:
            raise MarketRegimeDailyBundleError(f"immutable identity collision: {path.name}")
        return _sha256_bytes(existing)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return _sha256_bytes(encoded)


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> bytes:
    encoded = _json_bytes(payload)
    _write_bytes_atomic(path, encoded)
    return encoded


def _write_bytes_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_relative(root: Path, relative: Any, *, prefix: str | None = None) -> Path:
    value = str(relative or "")
    if not value or value.startswith("/") or "\\" in value:
        raise MarketRegimeDailyBundleError("bundle provenance path is invalid")
    if prefix is not None and not value.startswith(prefix):
        raise MarketRegimeDailyBundleError("bundle provenance path is invalid")
    target = (root / value).resolve()
    if root not in target.parents:
        raise MarketRegimeDailyBundleError("bundle provenance path escapes root")
    return target


def _read_hashed(root: Path, reference: Mapping[str, Any], *, prefix: str | None = None) -> tuple[dict[str, Any], bytes]:
    if not REF_KEYS.issubset(set(reference)):
        raise MarketRegimeDailyBundleError("bundle provenance reference schema mismatch")
    expected = str(reference.get("sha256") or "")
    if len(expected) != 64:
        raise MarketRegimeDailyBundleError("bundle provenance hash is invalid")
    target = _safe_relative(root, reference.get("path"), prefix=prefix)
    try:
        encoded = target.read_bytes()
    except FileNotFoundError as exc:
        raise MarketRegimeDailyBundleError("bundle provenance artifact is missing") from exc
    if _sha256_bytes(encoded) != expected:
        raise MarketRegimeDailyBundleError("bundle provenance hash mismatch")
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise MarketRegimeDailyBundleError("bundle provenance artifact is not JSON") from exc
    if not isinstance(payload, dict):
        raise MarketRegimeDailyBundleError("bundle provenance artifact is invalid")
    return payload, encoded


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _truth_boundary(pack: Mapping[str, Any], narrative: Mapping[str, Any]) -> dict[str, Any]:
    pack_boundary = pack.get("truth_boundary")
    narrative_boundary = narrative.get("truth_boundary")
    if not isinstance(pack_boundary, Mapping) or not isinstance(narrative_boundary, Mapping):
        raise MarketRegimeDailyBundleError("daily truth boundary is unavailable")
    if (
        pack_boundary.get("publication_eligible") is not False
        or pack_boundary.get("action_eligible") is not False
        or narrative_boundary.get("publication_eligible") is not False
        or narrative_boundary.get("action_eligible") is not False
    ):
        raise MarketRegimeDailyBundleError("daily truth boundary is not non-actionable")
    return {
        "read_only": True,
        "causal_claims": False,
        "forecast": False,
        "investment_advice": False,
        "publication_eligible": False,
        "action_eligible": False,
        "narrative_generation_status": narrative.get("generation_status"),
    }


def _stable_projection(pack: Mapping[str, Any], narrative: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    output = narrative.get("output")
    expected_output_keys = FALLBACK_OUTPUT_KEYS if narrative.get("generation_status") == "deterministic_fallback" else OUTPUT_KEYS
    if not isinstance(output, Mapping) or set(output) != expected_output_keys:
        raise MarketRegimeDailyBundleError("daily narrative output projection is invalid")
    slots = pack.get("slots")
    evidence_index = pack.get("evidence_index")
    if not isinstance(slots, list) or not isinstance(evidence_index, dict):
        raise MarketRegimeDailyBundleError("daily evidence projection is invalid")
    identity = {
        "schema_version": SCHEMA_VERSION,
        "pack_id": pack.get("pack_id"),
        "narrative_id": narrative.get("narrative_id"),
        "evidence_artifact_sha256": None,
        "narrative_artifact_sha256": None,
        "evidence_schema_version": pack.get("schema_version"),
        "narrative_schema_version": narrative.get("schema_version"),
        "narrative_compiler_version": narrative.get("compiler_version"),
        "narrative_prompt_version": narrative.get("prompt_version"),
        "generation_status": narrative.get("generation_status"),
        "truth_boundary": _truth_boundary(pack, narrative),
    }
    if not identity["pack_id"] or not str(identity["pack_id"]).startswith(PACK_ID_PREFIX):
        raise MarketRegimeDailyBundleError("daily evidence identity is invalid")
    if not identity["narrative_id"] or not str(identity["narrative_id"]).startswith(NARRATIVE_ID_PREFIX):
        raise MarketRegimeDailyBundleError("daily narrative identity is invalid")
    if narrative.get("pack_id") != pack.get("pack_id"):
        raise MarketRegimeDailyBundleRace("daily evidence and narrative packs differ")
    evidence_projection = {
        "quality": _copy_json(pack.get("quality")),
        "coverage": _copy_json(pack.get("coverage")),
        "time": _copy_json(pack.get("time")),
        "agreement_inputs": _copy_json(pack.get("agreement_inputs")),
        "confidence_inputs": _copy_json(pack.get("confidence_inputs")),
        "contradiction_candidates": _copy_json(pack.get("contradiction_candidates")),
        "slots": _copy_json(slots),
        "evidence_index": _copy_json(evidence_index),
        "truth_boundary": _copy_json(pack.get("truth_boundary")),
    }
    narrative_projection = {
        "output": _copy_json(output),
        "generation_status": narrative.get("generation_status"),
        "truth_boundary": _copy_json(narrative.get("truth_boundary")),
    }
    identity["projection_hashes"] = {
        "evidence": _hash(evidence_projection),
        "narrative": _hash(narrative_projection),
    }
    return identity, {"evidence": evidence_projection, "narrative": narrative_projection}


class MarketRegimeDailyBundleStore:
    """Compile and verify one immutable S5 Daily bundle."""

    def __init__(
        self,
        evidence_store: MarketRegimeDailyEvidenceStore,
        narrative_store: MarketRegimeDailyNarrativeStore,
        output_root: Path | str,
    ) -> None:
        self.evidence_store = evidence_store
        self.narrative_store = narrative_store
        self.output_root = Path(output_root).expanduser().resolve()
        self.state_path = self.output_root / "state.json"

    @property
    def publication_lock_root(self) -> Path:
        return self.evidence_store.output_root

    def _source_pointer(self, root: Path, pointer_name: str, *, schema: str, prefix: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        pointer = _read_json(root / pointer_name, error="daily source pointer is unavailable")
        if pointer.get("schema_version") != schema:
            raise MarketRegimeDailyBundleError("daily source pointer schema mismatch")
        artifact_reference = pointer.get("artifact")
        receipt_reference = pointer.get("receipt")
        if not isinstance(artifact_reference, Mapping) or not isinstance(receipt_reference, Mapping):
            raise MarketRegimeDailyBundleError("daily source pointer references are incomplete")
        artifact, _ = _read_hashed(root, artifact_reference, prefix=prefix)
        receipt, _ = _read_hashed(root, receipt_reference, prefix="receipts/")
        return pointer, artifact, {
            "artifact": {"path": str(artifact_reference["path"]), "sha256": str(artifact_reference["sha256"])},
            "receipt": {"path": str(receipt_reference["path"]), "sha256": str(receipt_reference["sha256"])},
        }

    def _evidence_candidate(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            pack = self.evidence_store.latest()
        except MarketRegimeDailyEvidenceError as exc:
            raise MarketRegimeDailyBundleError("daily evidence is unavailable") from exc
        pointer, artifact, references = self._source_pointer(
            self.evidence_store.output_root,
            "latest.json",
            schema=str(pack.get("schema_version") or ""),
            prefix="artifacts/",
        )
        if artifact != pack or pointer.get("pack_id") != pack.get("pack_id"):
            raise MarketRegimeDailyBundleError("daily evidence pointer does not bind latest pack")
        receipt, _ = _read_hashed(
            self.evidence_store.output_root,
            references["receipt"],
            prefix="receipts/",
        )
        if (
            receipt.get("event") != "completed"
            or receipt.get("pack_id") != pack.get("pack_id")
            or receipt.get("artifact") != references["artifact"]
            or receipt.get("publication_eligible") is not False
            or receipt.get("action_eligible") is not False
        ):
            raise MarketRegimeDailyBundleError("daily evidence completion receipt is invalid")
        return pack, references

    def _narrative_candidate(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            narrative = self.narrative_store.latest()
        except MarketRegimeDailyNarrativeError as exc:
            raise MarketRegimeDailyBundleError("daily narrative is unavailable") from exc
        state = _read_json(self.narrative_store.output_root / "state.json", error="daily narrative state is unavailable")
        pointer = state.get("pointer")
        if not isinstance(pointer, Mapping):
            raise MarketRegimeDailyBundleError("daily narrative state is invalid")
        artifact_reference = pointer.get("artifact")
        receipt_reference = pointer.get("receipt")
        if not isinstance(artifact_reference, Mapping) or not isinstance(receipt_reference, Mapping):
            raise MarketRegimeDailyBundleError("daily narrative references are incomplete")
        artifact, _ = _read_hashed(
            self.narrative_store.output_root,
            artifact_reference,
            prefix="artifacts/",
        )
        receipt, _ = _read_hashed(
            self.narrative_store.output_root,
            receipt_reference,
            prefix="receipts/",
        )
        expected = {"path": str(artifact_reference["path"]), "sha256": str(artifact_reference["sha256"])}
        if (
            artifact != narrative
            or pointer.get("narrative_id") != narrative.get("narrative_id")
            or receipt.get("event") != "completed"
            or receipt.get("narrative_id") != narrative.get("narrative_id")
            or receipt.get("pack_id") != narrative.get("pack_id")
            or receipt.get("artifact") != expected
            or receipt.get("publication_eligible") is not False
            or receipt.get("action_eligible") is not False
        ):
            raise MarketRegimeDailyBundleError("daily narrative completion receipt is invalid")
        return narrative, {
            "artifact": expected,
            "receipt": {"path": str(receipt_reference["path"]), "sha256": str(receipt_reference["sha256"])},
        }

    def capture_candidate(self) -> dict[str, Any]:
        pack, evidence_refs = self._evidence_candidate()
        narrative, narrative_refs = self._narrative_candidate()
        identity, projections = _stable_projection(pack, narrative)
        identity["evidence_artifact_sha256"] = evidence_refs["artifact"]["sha256"]
        identity["narrative_artifact_sha256"] = narrative_refs["artifact"]["sha256"]
        if set(identity) != IDENTITY_KEYS:
            raise MarketRegimeDailyBundleError("daily publication identity schema mismatch")
        bundle_id = f"{BUNDLE_ID_PREFIX}{_hash(identity)}"
        artifact = {
            "schema_version": SCHEMA_VERSION,
            "bundle_id": bundle_id,
            "publication_identity": identity,
            "pack_id": identity["pack_id"],
            "narrative_id": identity["narrative_id"],
            "generation_status": identity["generation_status"],
            **projections,
            "truth_boundary": identity["truth_boundary"],
            "publication_eligible": False,
            "action_eligible": False,
        }
        if set(artifact) != BUNDLE_KEYS:
            raise MarketRegimeDailyBundleError("daily bundle artifact schema mismatch")
        return {
            "artifact": artifact,
            "publication_identity": identity,
            "bundle_id": bundle_id,
            "evidence": evidence_refs,
            "narrative": narrative_refs,
        }

    @staticmethod
    def _projection_hashes(artifact: Mapping[str, Any]) -> dict[str, str]:
        return {
            "evidence": _hash(artifact.get("evidence")),
            "narrative": _hash(artifact.get("narrative")),
        }

    def _read_ref(self, reference: Mapping[str, Any], *, prefix: str) -> tuple[dict[str, Any], bytes]:
        if set(reference) != REF_KEYS:
            raise MarketRegimeDailyBundleError("daily bundle reference schema mismatch")
        return _read_hashed(self.output_root, reference, prefix=prefix)

    def _validate_artifact(self, reference: Mapping[str, Any]) -> dict[str, Any]:
        artifact, _ = self._read_ref(reference, prefix="artifacts/")
        if set(artifact) != BUNDLE_KEYS or artifact.get("schema_version") != SCHEMA_VERSION:
            raise MarketRegimeDailyBundleError("daily bundle artifact schema mismatch")
        identity = artifact.get("publication_identity")
        if not isinstance(identity, dict) or set(identity) != IDENTITY_KEYS:
            raise MarketRegimeDailyBundleError("daily bundle publication identity is invalid")
        expected_id = f"{BUNDLE_ID_PREFIX}{_hash(identity)}"
        if artifact.get("bundle_id") != expected_id or reference.get("path") != f"artifacts/{expected_id.removeprefix(BUNDLE_ID_PREFIX)}.json":
            raise MarketRegimeDailyBundleError("daily bundle identity mismatch")
        if artifact.get("publication_eligible") is not False or artifact.get("action_eligible") is not False:
            raise MarketRegimeDailyBundleError("daily bundle truth boundary mismatch")
        if artifact.get("pack_id") != identity.get("pack_id") or artifact.get("narrative_id") != identity.get("narrative_id"):
            raise MarketRegimeDailyBundleError("daily bundle projection identity mismatch")
        if artifact.get("truth_boundary") != identity.get("truth_boundary"):
            raise MarketRegimeDailyBundleError("daily bundle truth boundary projection mismatch")
        if artifact.get("generation_status") != identity.get("generation_status"):
            raise MarketRegimeDailyBundleError("daily bundle generation status mismatch")
        evidence = artifact.get("evidence")
        narrative = artifact.get("narrative")
        if not isinstance(evidence, Mapping) or not isinstance(narrative, Mapping):
            raise MarketRegimeDailyBundleError("daily bundle projections are incomplete")
        output = narrative.get("output")
        expected_output_keys = FALLBACK_OUTPUT_KEYS if artifact.get("generation_status") == "deterministic_fallback" else OUTPUT_KEYS
        if not isinstance(output, Mapping) or set(output) != expected_output_keys:
            raise MarketRegimeDailyBundleError("daily bundle narrative projection is invalid")
        expected_hashes = identity.get("projection_hashes")
        if not isinstance(expected_hashes, Mapping) or expected_hashes != self._projection_hashes(artifact):
            raise MarketRegimeDailyBundleError("daily bundle projection identity mismatch")
        return artifact

    def _validate_source_receipt(
        self,
        source: Mapping[str, Any],
        *,
        artifact: Mapping[str, Any],
        expected_pack_id: str,
        expected_narrative_id: str,
        side: str,
    ) -> None:
        if set(source) != RECEIPT_SIDE_KEYS:
            raise MarketRegimeDailyBundleError("daily bundle provenance side is invalid")
        root = self.evidence_store.output_root if side == "evidence" else self.narrative_store.output_root
        schema_prefix = "receipts/"
        payload, _ = _read_hashed(root, source["receipt"], prefix=schema_prefix)
        if payload.get("event") != "completed":
            raise MarketRegimeDailyBundleError("daily bundle provenance receipt is invalid")
        if side == "evidence":
            if payload.get("pack_id") != expected_pack_id or payload.get("artifact") != source["artifact"]:
                raise MarketRegimeDailyBundleError("daily evidence provenance mismatch")
        else:
            if payload.get("pack_id") != expected_pack_id or payload.get("narrative_id") != expected_narrative_id or payload.get("artifact") != source["artifact"]:
                raise MarketRegimeDailyBundleError("daily narrative provenance mismatch")
        if payload.get("publication_eligible") is not False or payload.get("action_eligible") is not False:
            raise MarketRegimeDailyBundleError("daily provenance truth boundary mismatch")
        artifact_payload, _ = _read_hashed(root, source["artifact"], prefix="artifacts/")
        if side == "evidence" and artifact_payload.get("pack_id") != expected_pack_id:
            raise MarketRegimeDailyBundleError("daily evidence artifact provenance mismatch")
        if side == "narrative" and artifact_payload.get("narrative_id") != expected_narrative_id:
            raise MarketRegimeDailyBundleError("daily narrative artifact provenance mismatch")
        if side == "narrative" and artifact_payload.get("pack_id") != expected_pack_id:
            raise MarketRegimeDailyBundleError("daily narrative pack provenance mismatch")
        if side == "evidence" and artifact_payload.get("pack_id") != artifact.get("pack_id"):
            raise MarketRegimeDailyBundleError("daily evidence artifact does not bind bundle")
        expected_artifact_hash = (
            artifact.get("publication_identity", {}).get("evidence_artifact_sha256")
            if side == "evidence"
            else artifact.get("publication_identity", {}).get("narrative_artifact_sha256")
        )
        if source["artifact"].get("sha256") != expected_artifact_hash:
            raise MarketRegimeDailyBundleError("daily provenance artifact hash does not bind bundle")

    def _validate_source_projections(self, receipt: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
        """Replay North Star projections from the exact S3/S4 refs in a receipt."""
        try:
            evidence_ref = receipt["evidence"]["artifact"]
            narrative_ref = receipt["narrative"]["artifact"]
            pack_payload, _ = _read_hashed(
                self.evidence_store.output_root, evidence_ref, prefix="artifacts/"
            )
            narrative_payload, _ = _read_hashed(
                self.narrative_store.output_root, narrative_ref, prefix="artifacts/"
            )
            expected_identity, expected_projections = _stable_projection(pack_payload, narrative_payload)
            expected_identity["evidence_artifact_sha256"] = evidence_ref["sha256"]
            expected_identity["narrative_artifact_sha256"] = narrative_ref["sha256"]
            if expected_identity != artifact.get("publication_identity"):
                raise MarketRegimeDailyBundleError("daily source projection identity mismatch")
            if expected_projections.get("evidence") != artifact.get("evidence") or expected_projections.get("narrative") != artifact.get("narrative"):
                raise MarketRegimeDailyBundleError("daily source projection mismatch")
        except (KeyError, TypeError, MarketRegimeDailyEvidenceError, MarketRegimeDailyNarrativeError) as exc:
            raise MarketRegimeDailyBundleError("daily source projection is invalid") from exc

    def _validate_completion_receipt(self, reference: Mapping[str, Any], artifact: Mapping[str, Any], *, validate_sources: bool = True) -> dict[str, Any]:
        receipt, _ = self._read_ref(reference, prefix="receipts/completion-")
        if set(receipt) != RECEIPT_KEYS or receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION or receipt.get("event") != "completed":
            raise MarketRegimeDailyBundleError("daily completion receipt schema mismatch")
        if receipt.get("bundle_id") != artifact.get("bundle_id") or receipt.get("publication_identity") != artifact.get("publication_identity"):
            raise MarketRegimeDailyBundleError("daily completion receipt identity mismatch")
        if receipt.get("publication_eligible") is not False or receipt.get("action_eligible") is not False:
            raise MarketRegimeDailyBundleError("daily completion receipt truth boundary mismatch")
        for side in ("evidence", "narrative"):
            value = receipt.get(side)
            if not isinstance(value, Mapping) or set(value) != RECEIPT_SIDE_KEYS:
                raise MarketRegimeDailyBundleError("daily completion receipt provenance is invalid")
            for reference_value in value.values():
                if not isinstance(reference_value, Mapping) or set(reference_value) != REF_KEYS:
                    raise MarketRegimeDailyBundleError("daily completion receipt reference is invalid")
        if validate_sources:
            self._validate_source_receipt(receipt["evidence"], artifact=artifact, expected_pack_id=str(artifact["pack_id"]), expected_narrative_id=str(artifact["narrative_id"]), side="evidence")
            self._validate_source_receipt(receipt["narrative"], artifact=artifact, expected_pack_id=str(artifact["pack_id"]), expected_narrative_id=str(artifact["narrative_id"]), side="narrative")
            self._validate_source_projections(receipt, artifact)
        return receipt

    def _validate_check_receipt(self, reference: Mapping[str, Any], artifact: Mapping[str, Any], *, validate_sources: bool = True) -> dict[str, Any]:
        receipt, _ = self._read_ref(reference, prefix="receipts/check-")
        if set(receipt) != RECEIPT_KEYS or receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION or receipt.get("event") != "check":
            raise MarketRegimeDailyBundleError("daily check receipt schema mismatch")
        if receipt.get("bundle_id") != artifact.get("bundle_id") or receipt.get("publication_identity") != artifact.get("publication_identity"):
            raise MarketRegimeDailyBundleError("daily check receipt identity mismatch")
        if receipt.get("publication_eligible") is not False or receipt.get("action_eligible") is not False:
            raise MarketRegimeDailyBundleError("daily check receipt truth boundary mismatch")
        for side in ("evidence", "narrative"):
            value = receipt.get(side)
            if not isinstance(value, Mapping) or set(value) != RECEIPT_SIDE_KEYS:
                raise MarketRegimeDailyBundleError("daily check receipt provenance is invalid")
            for reference_value in value.values():
                if not isinstance(reference_value, Mapping) or set(reference_value) != REF_KEYS:
                    raise MarketRegimeDailyBundleError("daily check receipt reference is invalid")
        if validate_sources:
            self._validate_source_receipt(receipt["evidence"], artifact=artifact, expected_pack_id=str(artifact["pack_id"]), expected_narrative_id=str(artifact["narrative_id"]), side="evidence")
            self._validate_source_receipt(receipt["narrative"], artifact=artifact, expected_pack_id=str(artifact["pack_id"]), expected_narrative_id=str(artifact["narrative_id"]), side="narrative")
            self._validate_source_projections(receipt, artifact)
        return receipt

    def _read_state(self, *, validate_provenance: bool = True) -> tuple[dict[str, Any], bytes]:
        try:
            encoded = self.state_path.read_bytes()
        except FileNotFoundError as exc:
            raise MarketRegimeDailyBundleError("daily bundle is unavailable") from exc
        try:
            state = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise MarketRegimeDailyBundleError("daily bundle state is not JSON") from exc
        if not isinstance(state, dict) or set(state) != STATE_KEYS or state.get("schema_version") != STATE_SCHEMA_VERSION:
            raise MarketRegimeDailyBundleError("daily bundle state schema mismatch")
        served = state.get("served")
        if not isinstance(served, dict) or set(served) != SERVED_KEYS:
            raise MarketRegimeDailyBundleError("daily served state schema mismatch")
        artifact = self._validate_artifact(served["artifact"])
        if served.get("bundle_id") != artifact.get("bundle_id"):
            raise MarketRegimeDailyBundleError("daily served bundle identity mismatch")
        self._validate_completion_receipt(served["completion_receipt"], artifact, validate_sources=validate_provenance)
        latest_check = state.get("latest_check_receipt")
        if latest_check is not None:
            self._validate_check_receipt(latest_check, artifact, validate_sources=validate_provenance)
        return state, encoded

    def latest(self) -> dict[str, Any]:
        state, _ = self._read_state(validate_provenance=True)
        reference = state["served"]["artifact"]
        return self._validate_artifact(reference)

    def latest_state(self) -> dict[str, Any]:
        state, _ = self._read_state(validate_provenance=True)
        return state

    def _receipt(self, *, event: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
        receipt_id = f"{SCHEMA_VERSION}:{event}:{uuid4().hex}"
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "event": event,
            "receipt_id": receipt_id,
            "bundle_id": candidate["bundle_id"],
            "publication_identity": _copy_json(candidate["publication_identity"]),
            "evidence": _copy_json(candidate["evidence"]),
            "narrative": _copy_json(candidate["narrative"]),
            "publication_eligible": False,
            "action_eligible": False,
        }

    def _commit_state(self, state: Mapping[str, Any], previous: bytes | None) -> None:
        try:
            _write_atomic(self.state_path, state)
            readback = self.state_path.read_bytes()
            if readback != _json_bytes(state):
                raise MarketRegimeDailyBundleError("daily bundle state readback mismatch")
            self._read_state(validate_provenance=True)
        except Exception:
            if previous is None:
                try:
                    self.state_path.unlink()
                except FileNotFoundError:
                    pass
            else:
                _write_bytes_atomic(self.state_path, previous)
            raise

    def publish_candidate(self, candidate: Mapping[str, Any] | None = None) -> dict[str, Any]:
        built = candidate or self.capture_candidate()
        with daily_publication_lock(self.publication_lock_root):
            current = self.capture_candidate()
            if current["publication_identity"] != built["publication_identity"]:
                raise MarketRegimeDailyBundleRace("daily candidate advanced during publication")
            built = current
            previous_state: bytes | None
            try:
                previous_state = self.state_path.read_bytes()
            except FileNotFoundError:
                previous_state = None
            try:
                state, _ = self._read_state(validate_provenance=True) if previous_state is not None else (None, None)
            except MarketRegimeDailyBundleError:
                raise
            if state is not None and state["served"]["bundle_id"] == built["bundle_id"]:
                current_check = state.get("latest_check_receipt")
                if isinstance(current_check, Mapping):
                    check_payload, _ = self._read_ref(current_check, prefix="receipts/check-")
                    if check_payload.get("evidence") == built["evidence"] and check_payload.get("narrative") == built["narrative"]:
                        return {"action": "unchanged", "artifact": self._validate_artifact(state["served"]["artifact"]), "state": state}
                check = self._receipt(event="check", candidate=built)
                check_path = f"receipts/check-{uuid4().hex}.json"
                check_sha = _write_exclusive(self.output_root / check_path, check)
                next_state = {
                    **state,
                    "latest_check_receipt": {"path": check_path, "sha256": check_sha},
                }
                self._commit_state(next_state, previous_state)
                return {"action": "checked", "artifact": self._validate_artifact(state["served"]["artifact"]), "state": next_state}
            artifact = built["artifact"]
            digest = built["bundle_id"].removeprefix(BUNDLE_ID_PREFIX)
            artifact_path = f"artifacts/{digest}.json"
            artifact_sha = _write_exclusive(self.output_root / artifact_path, artifact)
            completion = self._receipt(event="completed", candidate=built)
            completion_path = f"receipts/completion-{uuid4().hex}.json"
            completion_sha = _write_exclusive(self.output_root / completion_path, completion)
            next_state = {
                "schema_version": STATE_SCHEMA_VERSION,
                "served": {
                    "bundle_id": built["bundle_id"],
                    "artifact": {"path": artifact_path, "sha256": artifact_sha},
                    "completion_receipt": {"path": completion_path, "sha256": completion_sha},
                },
                "latest_check_receipt": None,
            }
            self._commit_state(next_state, previous_state)
            return {"action": "published", "artifact": artifact, "state": next_state}


def daily_bundle_payload(
    root: Path | str,
    *,
    evidence_root: Path | str | None = None,
    narrative_root: Path | str | None = None,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    evidence_path = Path(evidence_root or root_path / "daily-v2" / "evidence-packs").expanduser().resolve()
    narrative_path = Path(narrative_root or root_path / "daily-v2" / "narratives").expanduser().resolve()
    evidence_store = MarketRegimeDailyEvidenceStore(root_path, root_path / "macro", evidence_path)
    narrative_store = MarketRegimeDailyNarrativeStore(evidence_store, narrative_path)
    bundle_store = MarketRegimeDailyBundleStore(evidence_store, narrative_store, root_path / "daily-v2" / "bundles")
    return bundle_store.latest()
