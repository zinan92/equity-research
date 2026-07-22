"""Immutable evidence-set, conflict, freshness, and coverage gate.

This is the only boundary allowed to turn canonical B1-B5/A5 observations into
research context.  It does not write reports and it never fetches providers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .contracts import RecordEnvelope, RecordStatus, SourceManifest


EVIDENCE_GATE_SCHEMA_VERSION = "park-evidence-gate-v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _instant(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class EvidenceRole(str, Enum):
    PRIMARY = "primary"
    INDEPENDENT = "independent"
    LEAD = "lead"


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence_id: str
    ticker: str
    component: str
    role: EvidenceRole
    source_key: str
    source_family: str
    authority_tier: str
    independent_of_subject: bool
    status: str
    known_at: str
    effective_at: str
    manifest_hash: str
    raw_hash: str
    record_hash: str
    quality_flags: tuple[str, ...] = ()

    @classmethod
    def from_record(
        cls,
        record: RecordEnvelope,
        manifest: SourceManifest,
        *,
        ticker: str,
        component: str,
        role: EvidenceRole,
        source_family: str,
        effective_at: str,
        independent_of_subject: bool = False,
        evidence_id: str | None = None,
    ) -> "EvidenceCandidate":
        if record.provenance.source_manifest_hash != manifest.manifest_hash:
            raise ValueError("record is not bound to the supplied source manifest")
        return cls(
            evidence_id=evidence_id or "evidence_" + record.record_hash[:40],
            ticker=ticker.upper(),
            component=component,
            role=role,
            source_key=manifest.source_key,
            source_family=source_family,
            authority_tier=manifest.authority_tier,
            independent_of_subject=independent_of_subject,
            status=record.status.value,
            known_at=record.provenance.known_at,
            effective_at=effective_at,
            manifest_hash=manifest.manifest_hash,
            raw_hash=record.provenance.raw_hash,
            record_hash=record.record_hash,
            quality_flags=tuple(sorted(set(record.quality_flags + manifest.quality_flags))),
        )

    def validate(self) -> None:
        required = {
            "evidence_id": self.evidence_id,
            "ticker": self.ticker,
            "component": self.component,
            "source_key": self.source_key,
            "source_family": self.source_family,
            "authority_tier": self.authority_tier,
            "status": self.status,
            "manifest_hash": self.manifest_hash,
            "raw_hash": self.raw_hash,
            "record_hash": self.record_hash,
        }
        invalid = [key for key, value in required.items() if not str(value).strip()]
        if invalid:
            raise ValueError("candidate fields are required: " + ", ".join(invalid))
        if type(self.independent_of_subject) is not bool:
            raise ValueError("independent_of_subject must be a bool")
        if self.status not in {item.value for item in RecordStatus}:
            raise ValueError("candidate status is invalid")
        if self.authority_tier not in {"canonical", "official", "supplementary_only"}:
            raise ValueError("candidate authority_tier is invalid")
        if not isinstance(self.role, EvidenceRole):
            raise ValueError("candidate role must be an EvidenceRole")
        for field in ("manifest_hash", "raw_hash", "record_hash"):
            value = getattr(self, field)
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"candidate {field} must be SHA-256")
        _instant(self.known_at, field="known_at")
        _instant(self.effective_at, field="effective_at")
        if not isinstance(self.quality_flags, tuple):
            raise ValueError("quality_flags must be immutable")

    def role_violation(self) -> str | None:
        if self.role is EvidenceRole.PRIMARY and self.authority_tier not in {"canonical", "official"}:
            return "primary role requires canonical or official authority"
        if self.role is EvidenceRole.INDEPENDENT and not self.independent_of_subject:
            return "independent role requires subject-independent provenance"
        if self.role is EvidenceRole.LEAD and self.authority_tier != "supplementary_only":
            return "lead role must remain supplementary-only"
        return None

    def identity_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["role"] = self.role.value
        value["quality_flags"] = list(self.quality_flags)
        return value


@dataclass(frozen=True)
class EvidenceRequirement:
    component: str
    min_primary: int = 0
    min_independent: int = 0
    min_total: int = 1

    def validate(self) -> None:
        if not self.component.strip():
            raise ValueError("requirement component is required")
        for field in ("min_primary", "min_independent", "min_total"):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise ValueError(f"requirement {field} must be a nonnegative int")
        if self.min_total < self.min_primary + self.min_independent:
            raise ValueError("min_total cannot be lower than required role counts")


@dataclass(frozen=True)
class EvidenceGatePolicy:
    as_of: str
    requirements: tuple[EvidenceRequirement, ...]
    max_age_days: tuple[tuple[str, int], ...] = (
        (EvidenceRole.PRIMARY.value, 180),
        (EvidenceRole.INDEPENDENT.value, 365),
        (EvidenceRole.LEAD.value, 30),
    )
    blocking_conflict_severities: tuple[str, ...] = ("blocking",)
    blocking_quality_flags: tuple[str, ...] = ("fixture", "mock", "sample")
    subject_source_families: tuple[str, ...] = ()
    policy_version: str = EVIDENCE_GATE_SCHEMA_VERSION

    def validate(self) -> None:
        _instant(self.as_of, field="as_of")
        if not self.policy_version.strip() or not self.requirements:
            raise ValueError("policy version and requirements are required")
        components = [item.component for item in self.requirements]
        if len(components) != len(set(components)):
            raise ValueError("requirements cannot repeat a component")
        for requirement in self.requirements:
            requirement.validate()
        ages = dict(self.max_age_days)
        if set(ages) != {role.value for role in EvidenceRole}:
            raise ValueError("max_age_days must define primary, independent, and lead")
        if any(type(days) is not int or days < 0 for days in ages.values()):
            raise ValueError("max_age_days values must be nonnegative ints")
        if not self.blocking_conflict_severities:
            raise ValueError("at least one blocking conflict severity is required")
        if not all(value.strip() for value in self.subject_source_families):
            raise ValueError("subject_source_families must contain non-empty strings")

    @property
    def policy_hash(self) -> str:
        self.validate()
        return _digest(self.identity_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "as_of": _utc(_instant(self.as_of, field="as_of")),
            "requirements": [asdict(item) for item in self.requirements],
            "max_age_days": [list(item) for item in self.max_age_days],
            "blocking_conflict_severities": list(self.blocking_conflict_severities),
            "blocking_quality_flags": list(self.blocking_quality_flags),
            "subject_source_families": list(self.subject_source_families),
        }


@dataclass(frozen=True)
class EvidenceConflict:
    conflict_id: str
    component: str
    severity: str
    evidence_ids: tuple[str, ...]
    reason: str

    def validate(self) -> None:
        if not all((self.conflict_id.strip(), self.component.strip(), self.severity.strip(), self.reason.strip())):
            raise ValueError("conflict identity fields are required")
        if not self.evidence_ids or not all(value.strip() for value in self.evidence_ids):
            raise ValueError("conflict evidence_ids are required")


@dataclass(frozen=True)
class SourceCoverageGap:
    source_key: str
    component: str
    reason: str
    required: bool = False

    def validate(self) -> None:
        if not all((self.source_key.strip(), self.component.strip(), self.reason.strip())):
            raise ValueError("source coverage gap fields are required")


@dataclass(frozen=True)
class RejectedEvidence:
    evidence_id: str
    component: str
    reason: str


@dataclass(frozen=True)
class CoverageRequirementResult:
    component: str
    required_primary: int
    actual_primary: int
    required_independent: int
    actual_independent: int
    required_total: int
    actual_total: int
    missing: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class CoverageReport:
    requirements: tuple[CoverageRequirementResult, ...]
    source_gaps: tuple[SourceCoverageGap, ...]

    @property
    def missing(self) -> tuple[str, ...]:
        values = [
            f"{item.component}:{reason}"
            for item in self.requirements
            for reason in item.missing
        ]
        values.extend(f"{item.component}:source:{item.source_key}:{item.reason}" for item in self.source_gaps)
        return tuple(values)

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.requirements) and not any(
            item.required for item in self.source_gaps
        )


@dataclass(frozen=True)
class EvidenceGateReceipt:
    status: str
    policy_hash: str
    evidence_manifest_hash: str
    accepted_ids: tuple[str, ...]
    rejected: tuple[RejectedEvidence, ...]
    conflicts: tuple[EvidenceConflict, ...]
    blocking_conflict_ids: tuple[str, ...]
    coverage: CoverageReport
    gate_hash: str


@dataclass(frozen=True)
class ImmutableEvidenceSet:
    evidence_set_id: str
    ticker: str
    as_of: str
    policy_version: str
    manifest_hash: str
    candidates: tuple[EvidenceCandidate, ...]
    conflicts: tuple[EvidenceConflict, ...]
    receipt: EvidenceGateReceipt

    @property
    def publishable(self) -> bool:
        return self.receipt.status == "passed"


@dataclass(frozen=True)
class ResearchContextPack:
    evidence_set_id: str
    ticker: str
    as_of: str
    manifest_hash: str
    evidence: tuple[EvidenceCandidate, ...]
    coverage: CoverageReport
    index: Mapping[str, EvidenceCandidate]


def _candidate_rejection(candidate: EvidenceCandidate, policy: EvidenceGatePolicy) -> str | None:
    candidate.validate()
    if candidate.status != RecordStatus.ACCEPTED.value:
        return f"record_status:{candidate.status}"
    violation = candidate.role_violation()
    if violation:
        return "role_violation:" + violation
    if (
        candidate.role is EvidenceRole.INDEPENDENT
        and candidate.source_family in policy.subject_source_families
    ):
        return "role_violation:independent source family is subject-controlled"
    if set(candidate.quality_flags).intersection(policy.blocking_quality_flags):
        return "blocking_quality_flag"
    cutoff = _instant(policy.as_of, field="as_of")
    known_at = _instant(candidate.known_at, field="known_at")
    effective_at = _instant(candidate.effective_at, field="effective_at")
    if known_at > cutoff:
        return "known_at_after_as_of"
    if effective_at > known_at:
        return "effective_at_after_known_at"
    age_days = (cutoff - effective_at).total_seconds() / 86400
    max_age = dict(policy.max_age_days)[candidate.role.value]
    if age_days > max_age:
        return f"stale>{max_age}d"
    if candidate.role is EvidenceRole.LEAD:
        return "lead_only_not_evidence"
    return None


def _coverage(
    candidates: Sequence[EvidenceCandidate],
    policy: EvidenceGatePolicy,
    source_gaps: Sequence[SourceCoverageGap],
) -> CoverageReport:
    results = []
    for requirement in policy.requirements:
        matching = [item for item in candidates if item.component == requirement.component]
        primary = sum(item.role is EvidenceRole.PRIMARY for item in matching)
        independent = sum(item.role is EvidenceRole.INDEPENDENT for item in matching)
        missing = []
        if primary < requirement.min_primary:
            missing.append(f"primary<{requirement.min_primary}")
        if independent < requirement.min_independent:
            missing.append(f"independent<{requirement.min_independent}")
        if len(matching) < requirement.min_total:
            missing.append(f"total<{requirement.min_total}")
        results.append(
            CoverageRequirementResult(
                component=requirement.component,
                required_primary=requirement.min_primary,
                actual_primary=primary,
                required_independent=requirement.min_independent,
                actual_independent=independent,
                required_total=requirement.min_total,
                actual_total=len(matching),
                missing=tuple(missing),
            )
        )
    return CoverageReport(requirements=tuple(results), source_gaps=tuple(source_gaps))


def build_evidence_set(
    *,
    ticker: str,
    candidates: Iterable[EvidenceCandidate],
    policy: EvidenceGatePolicy,
    conflicts: Iterable[EvidenceConflict] = (),
    source_gaps: Iterable[SourceCoverageGap] = (),
) -> ImmutableEvidenceSet:
    policy.validate()
    normalized_ticker = ticker.upper()
    materialized = tuple(sorted(candidates, key=lambda item: item.evidence_id))
    ids = [item.evidence_id for item in materialized]
    if len(ids) != len(set(ids)):
        raise ValueError("evidence candidate IDs must be unique")
    if any(item.ticker.upper() != normalized_ticker for item in materialized):
        raise ValueError("evidence candidate ticker mismatch")

    materialized_conflicts = tuple(sorted(conflicts, key=lambda item: item.conflict_id))
    materialized_gaps = tuple(sorted(source_gaps, key=lambda item: (item.component, item.source_key)))
    for conflict in materialized_conflicts:
        conflict.validate()
        unknown = set(conflict.evidence_ids).difference(ids)
        if unknown:
            raise ValueError("conflict references unknown evidence: " + ", ".join(sorted(unknown)))
    for gap in materialized_gaps:
        gap.validate()

    accepted = []
    rejected = []
    for candidate in materialized:
        reason = _candidate_rejection(candidate, policy)
        if reason:
            rejected.append(RejectedEvidence(candidate.evidence_id, candidate.component, reason))
        else:
            accepted.append(candidate)

    coverage = _coverage(accepted, policy, materialized_gaps)
    blocking_conflicts = tuple(
        conflict.conflict_id
        for conflict in materialized_conflicts
        if conflict.severity in policy.blocking_conflict_severities
    )
    manifest = {
        "schema_version": EVIDENCE_GATE_SCHEMA_VERSION,
        "ticker": normalized_ticker,
        "as_of": _utc(_instant(policy.as_of, field="as_of")),
        "policy_hash": policy.policy_hash,
        "accepted": [item.identity_payload() for item in accepted],
    }
    manifest_hash = _digest(manifest)
    status = "passed" if coverage.passed and not blocking_conflicts else "insufficient"
    gate_payload = {
        "status": status,
        "policy_hash": policy.policy_hash,
        "evidence_manifest_hash": manifest_hash,
        "accepted_ids": [item.evidence_id for item in accepted],
        "rejected": [asdict(item) for item in rejected],
        "conflicts": [asdict(item) for item in materialized_conflicts],
        "blocking_conflict_ids": list(blocking_conflicts),
        "coverage": {
            "requirements": [asdict(item) for item in coverage.requirements],
            "source_gaps": [asdict(item) for item in coverage.source_gaps],
        },
    }
    receipt = EvidenceGateReceipt(
        status=status,
        policy_hash=policy.policy_hash,
        evidence_manifest_hash=manifest_hash,
        accepted_ids=tuple(item.evidence_id for item in accepted),
        rejected=tuple(rejected),
        conflicts=materialized_conflicts,
        blocking_conflict_ids=blocking_conflicts,
        coverage=coverage,
        gate_hash=_digest(gate_payload),
    )
    return ImmutableEvidenceSet(
        evidence_set_id="evidence_set_" + manifest_hash[:40],
        ticker=normalized_ticker,
        as_of=manifest["as_of"],
        policy_version=policy.policy_version,
        manifest_hash=manifest_hash,
        candidates=tuple(accepted),
        conflicts=materialized_conflicts,
        receipt=receipt,
    )


def verify_evidence_set(
    evidence_set: ImmutableEvidenceSet,
    *,
    candidates: Iterable[EvidenceCandidate],
    policy: EvidenceGatePolicy,
    conflicts: Iterable[EvidenceConflict] = (),
    source_gaps: Iterable[SourceCoverageGap] = (),
) -> bool:
    rebuilt = build_evidence_set(
        ticker=evidence_set.ticker,
        candidates=candidates,
        policy=policy,
        conflicts=conflicts,
        source_gaps=source_gaps,
    )
    return rebuilt == evidence_set


def build_context_pack(evidence_set: ImmutableEvidenceSet) -> ResearchContextPack:
    if not evidence_set.publishable:
        raise ValueError("evidence set did not pass coverage and conflict gates")
    accepted = evidence_set.candidates
    accepted_ids = {item.evidence_id for item in accepted}
    if accepted_ids != set(evidence_set.receipt.accepted_ids):
        raise ValueError("evidence set receipt does not match immutable candidates")
    rejected_ids = {item.evidence_id for item in evidence_set.receipt.rejected}
    if accepted_ids.intersection(rejected_ids):
        raise ValueError("rejected evidence cannot enter a Context Pack")
    return ResearchContextPack(
        evidence_set_id=evidence_set.evidence_set_id,
        ticker=evidence_set.ticker,
        as_of=evidence_set.as_of,
        manifest_hash=evidence_set.manifest_hash,
        evidence=accepted,
        coverage=evidence_set.receipt.coverage,
        index=MappingProxyType({item.evidence_id: item for item in accepted}),
    )
