"""Explicit event-to-trigger proposals for versioned research objects.

The module deliberately produces a proposed next revision only. Persistence is
left to :class:`ResearchObjectStore`, so an event can never silently rewrite a
prior thesis, catalyst, falsifier, or investment decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .event_intelligence import IntelligenceEvent
from .research_objects import ResearchObject, ResearchObjectType


TRIGGER_STATUSES = frozenset({"pending", "fulfilled", "delayed", "broken"})
TRIGGER_DIRECTIONS = frozenset({"up", "down", "neutral"})


@dataclass(frozen=True)
class TriggerEventMatch:
    """An audit record for one explicit proposed event interpretation."""

    trigger_object_id: str
    trigger_revision: int
    event_id: str
    status: str
    matched_evidence_refs: tuple[str, ...]
    reason: str


def _validate_trigger(item: ResearchObject) -> None:
    item.validate()
    if item.object_type not in {ResearchObjectType.CATALYST, ResearchObjectType.FALSIFIER}:
        raise ValueError("only catalyst and falsifier objects can receive trigger events")
    if not all(str(item.facts.get(field, "")).strip() for field in ("thesis_ref", "threshold", "time_window")):
        raise ValueError("trigger requires thesis_ref, threshold, and time_window")
    if item.facts.get("direction") not in TRIGGER_DIRECTIONS:
        raise ValueError("trigger direction must be up, down, or neutral")
    if item.facts.get("trigger_status") not in TRIGGER_STATUSES:
        raise ValueError("trigger status is invalid")


def propose_event_match(
    item: ResearchObject,
    event: IntelligenceEvent,
    *,
    status: str,
    evidence_refs: Iterable[str],
    reason: str,
) -> TriggerEventMatch:
    """Validate an evidence-bound match without mutating or persisting it."""
    _validate_trigger(item)
    if status not in TRIGGER_STATUSES - {"pending"}:
        raise ValueError("event transition status must be fulfilled, delayed, or broken")
    refs = tuple(sorted({str(ref).strip() for ref in evidence_refs if str(ref).strip()}))
    if not refs:
        raise ValueError("event transition requires evidence references")
    if not set(refs).intersection(event.evidence_ids):
        raise ValueError("event transition evidence must include an event evidence identity")
    if not str(reason).strip():
        raise ValueError("event transition reason is required")
    return TriggerEventMatch(item.object_id, item.revision, event.event_id, status, refs, reason.strip())


def propose_trigger_revision(
    item: ResearchObject,
    match: TriggerEventMatch,
    *,
    source_ref: str,
    known_at: str,
    confidence: str,
    raw_hashes: tuple[str, ...],
    snapshot_id: str,
    model_version: str,
) -> ResearchObject:
    """Build, but do not append, the next evidence-bound trigger revision."""
    _validate_trigger(item)
    if match.trigger_object_id != item.object_id or match.trigger_revision != item.revision:
        raise ValueError("event match does not bind the current trigger revision")
    if not str(model_version).strip():
        raise ValueError("event transition requires a model or rule version")
    facts = dict(item.facts)
    facts.update({
        "trigger_status": match.status,
        "status_event_id": match.event_id,
        "status_evidence_refs": list(match.matched_evidence_refs),
    })
    judgments = {"event_match": {"status": match.status, "reason": match.reason}}
    return ResearchObject(
        object_id=item.object_id,
        object_type=item.object_type,
        revision=item.revision + 1,
        revision_of=item.object_hash,
        state="accepted",
        source_ref=source_ref,
        known_at=known_at,
        confidence=confidence,
        evidence_refs=match.matched_evidence_refs,
        raw_hashes=raw_hashes,
        snapshot_id=snapshot_id,
        facts=facts,
        judgments=judgments,
        model_version=model_version,
    )
