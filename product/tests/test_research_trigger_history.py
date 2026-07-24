from __future__ import annotations

import sys
from pathlib import Path

import pytest

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from data_core.event_intelligence import IntelligenceEvent  # noqa: E402
from data_core.research_objects import ResearchObject, ResearchObjectType  # noqa: E402
from data_core.research_trigger_history import propose_event_match, propose_trigger_revision  # noqa: E402


def catalyst() -> ResearchObject:
    return ResearchObject(
        object_id="research-v1:catalyst:catl", object_type=ResearchObjectType.CATALYST,
        revision=1, state="accepted", source_ref="source:official:1", known_at="2026-07-25T00:00:00Z",
        confidence="high", evidence_refs=("event-evidence-1",), raw_hashes=("a" * 64,), snapshot_id="snapshot-1",
        facts={"company_id": "company-v1:catl", "thesis_ref": "research-v1:thesis:catl", "title": "capacity ramp", "direction": "up", "threshold": "capacity > 100GWh", "time_window": "2026H2", "trigger_status": "pending", "time_horizon": "12m"}, judgments={},
    )


def event() -> IntelligenceEvent:
    return IntelligenceEvent("event-1", "300750.SZ", "CN:300750.SZ", "Capacity update", "2026-07-25T00:00:00Z", "2026-07-25T00:00:00Z", ("event-evidence-1",), ("official",))


def test_event_match_returns_a_proposal_not_a_mutation() -> None:
    original = catalyst()
    match = propose_event_match(original, event(), status="fulfilled", evidence_refs=("event-evidence-1",), reason="reported capacity crossed threshold")
    next_revision = propose_trigger_revision(original, match, source_ref="source:official:2", known_at="2026-07-25T01:00:00Z", confidence="high", raw_hashes=("b" * 64,), snapshot_id="snapshot-2", model_version="trigger-rule-v1")
    assert original.revision == 1
    assert original.facts["trigger_status"] == "pending"
    assert next_revision.revision == 2
    assert next_revision.revision_of == original.object_hash
    assert next_revision.facts["trigger_status"] == "fulfilled"
    assert next_revision.facts["status_event_id"] == "event-1"
    assert next_revision.model_version == "trigger-rule-v1"


def test_unmatched_event_and_missing_trigger_shape_fail_closed() -> None:
    with pytest.raises(ValueError, match="include an event evidence identity"):
        propose_event_match(catalyst(), event(), status="delayed", evidence_refs=("other",), reason="unrelated")
    bad = catalyst()
    object.__setattr__(bad, "facts", {**bad.facts, "direction": "maybe"})
    with pytest.raises(ValueError, match="direction"):
        propose_event_match(bad, event(), status="broken", evidence_refs=("event-evidence-1",), reason="bad shape")
