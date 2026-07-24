"""Evidence-gated catalyst profiles for the self-owned industry ontology."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Iterable

from .industry_graph import EvidenceCapture, audited_candidates
from .industry_ontology import IndustrySegment, build_ontology


CATALYST_PROFILE_SCHEMA_VERSION = "park-industry-catalyst-profile-v1"
SECTION_NAMES = ("current_state", "driver", "catalyst", "leading_indicator", "risk_falsifier", "time_horizon")
SECTION_STATES = frozenset({"fact", "research_judgment", "missing_evidence"})


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class CatalystSection:
    name: str
    state: str
    text: str
    evidence_ids: tuple[str, ...] = ()
    raw_hashes: tuple[str, ...] = ()
    model_version: str | None = None

    def validate(self) -> None:
        if self.name not in SECTION_NAMES or self.state not in SECTION_STATES:
            raise ValueError("unsupported catalyst section")
        if not self.text.strip():
            raise ValueError("catalyst section text is required")
        if self.state == "fact":
            if not self.evidence_ids or not self.raw_hashes or self.model_version is not None:
                raise ValueError("fact section requires evidence IDs/raw hashes and no model version")
        elif self.state == "research_judgment":
            if not self.model_version or self.evidence_ids or self.raw_hashes:
                raise ValueError("research judgment must have a model version and no source identity")
        elif self.evidence_ids or self.raw_hashes or self.model_version:
            raise ValueError("missing-evidence section cannot carry a source or model identity")


@dataclass(frozen=True)
class IndustryCatalystProfile:
    profile_id: str
    segment_id: str
    as_of: str
    sections: tuple[CatalystSection, ...]
    input_hash: str

    def validate(self) -> None:
        date.fromisoformat(self.as_of)
        names = tuple(section.name for section in self.sections)
        if names != SECTION_NAMES:
            raise ValueError("catalyst profile requires the canonical section order")
        for section in self.sections:
            section.validate()
        if self.profile_id != "catalyst_" + self.input_hash[:40]:
            raise ValueError("catalyst profile ID does not match input identity")

    @property
    def status(self) -> str:
        return "available" if any(section.state == "fact" for section in self.sections) else "missing_evidence"


def _missing_sections() -> tuple[CatalystSection, ...]:
    return tuple(CatalystSection(name, "missing_evidence", "No accepted current evidence is available for this section.") for name in SECTION_NAMES)


def build_catalyst_profiles(captures: Iterable[EvidenceCapture], *, as_of: str) -> tuple[IndustryCatalystProfile, ...]:
    """Create all ontology profiles without inventing content for uncovered segments."""
    date.fromisoformat(as_of)
    cutoff = date.fromisoformat(as_of)
    capture_by_url = {item.source_url: item for item in captures}
    for capture in capture_by_url.values():
        fetched = datetime.fromisoformat(capture.fetched_at.replace("Z", "+00:00")).date()
        if fetched > cutoff:
            raise ValueError("catalyst evidence is future-visible")
        if (cutoff - fetched).days > 7:
            raise ValueError("catalyst evidence is stale")
    evidence_by_segment: dict[str, EvidenceCapture] = {}
    for edge in audited_candidates():
        capture = capture_by_url.get(edge.evidence_url)
        if capture:
            evidence_by_segment.setdefault(edge.source_id, capture)
            evidence_by_segment.setdefault(edge.target_id, capture)
    _, segments = build_ontology()
    profiles = []
    for segment in segments:
        capture = evidence_by_segment.get(segment.segment_id)
        if capture is None:
            sections = _missing_sections()
        else:
            source_id = f"raw:{capture.raw_hash}"
            sections = (
                CatalystSection("current_state", "fact", "Accepted first-party relationship evidence covers this segment.", (source_id,), (capture.raw_hash,)),
                CatalystSection("driver", "missing_evidence", "No accepted current evidence is available for this section."),
                CatalystSection("catalyst", "missing_evidence", "No accepted current evidence is available for this section."),
                CatalystSection("leading_indicator", "missing_evidence", "No accepted current evidence is available for this section."),
                CatalystSection("risk_falsifier", "missing_evidence", "No accepted current evidence is available for this section."),
                CatalystSection("time_horizon", "missing_evidence", "No accepted current evidence is available for this section."),
            )
        payload = {"schema_version": CATALYST_PROFILE_SCHEMA_VERSION, "segment_id": segment.segment_id, "as_of": as_of, "sections": [asdict(item) for item in sections]}
        identity = _digest(payload)
        profile = IndustryCatalystProfile("catalyst_" + identity[:40], segment.segment_id, as_of, sections, identity)
        profile.validate()
        profiles.append(profile)
    return tuple(profiles)


def catalyst_coverage(profiles: Iterable[IndustryCatalystProfile]) -> dict[str, int]:
    rows = tuple(profiles)
    return {"total": len(rows), "available": sum(item.status == "available" for item in rows), "missing_evidence": sum(item.status == "missing_evidence" for item in rows), "fact_sections": sum(section.state == "fact" for item in rows for section in item.sections)}
