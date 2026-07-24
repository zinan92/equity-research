"""Fail-closed, evidence-bound graph over the self-owned industry ontology."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import subprocess
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from .industry_ontology import IndustrySegment, build_ontology


ALLOWED_RELATIONS = frozenset({"supplies", "enables", "consumes", "competes_with", "depends_on"})


@dataclass(frozen=True)
class IndustryEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation_type: str
    direction: str
    strength: str
    as_of: str
    evidence_id: str | None
    status: str = "accepted"


class IndustryGraph:
    def __init__(self, segments: Iterable[IndustrySegment], edges: Iterable[IndustryEdge]) -> None:
        self.segments = {segment.segment_id: segment for segment in segments}
        self.edges = tuple(edges)
        self._validate()

    def _validate(self) -> None:
        identifiers = [edge.edge_id for edge in self.edges]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("graph edge identities must be unique")
        for edge in self.edges:
            if edge.source_id not in self.segments or edge.target_id not in self.segments:
                raise ValueError("graph edge references unknown segment")
            if edge.source_id == edge.target_id:
                raise ValueError("graph self-loop is not allowed")
            if edge.relation_type not in ALLOWED_RELATIONS or edge.direction not in {"forward", "bidirectional"}:
                raise ValueError("graph edge relation or direction is invalid")
            if edge.strength not in {"high", "medium", "low", "unknown"}:
                raise ValueError("graph edge strength is invalid")
            try:
                date.fromisoformat(edge.as_of)
            except ValueError as exc:
                raise ValueError("graph edge as_of is invalid") from exc
            if edge.status not in {"accepted", "disputed", "unknown", "needs_evidence"}:
                raise ValueError("graph edge status is invalid")
            if edge.status == "accepted" and not edge.evidence_id:
                raise ValueError("accepted graph edge requires evidence identity")
            if edge.status != "accepted" and edge.evidence_id:
                raise ValueError("unaccepted graph edge cannot pretend to have evidence")

    def neighbors(self, segment_id: str, *, direction: str = "both") -> tuple[IndustryEdge, ...]:
        if segment_id not in self.segments:
            raise ValueError("unknown graph segment")
        if direction not in {"upstream", "downstream", "both"}:
            raise ValueError("invalid graph traversal direction")
        chosen = []
        for edge in self.edges:
            if edge.status != "accepted":
                continue
            downstream = edge.source_id == segment_id
            upstream = edge.target_id == segment_id
            if direction == "downstream" and downstream:
                chosen.append(edge)
            elif direction == "upstream" and upstream:
                chosen.append(edge)
            elif direction == "both" and (downstream or upstream):
                chosen.append(edge)
        return tuple(sorted(chosen, key=lambda edge: edge.edge_id))

    def audit(self) -> Mapping[str, int]:
        counts = {status: 0 for status in ("accepted", "disputed", "unknown", "needs_evidence")}
        for edge in self.edges:
            counts[edge.status] += 1
        return {"segment_count": len(self.segments), "edge_count": len(self.edges), **counts}


def empty_industry_graph() -> IndustryGraph:
    _, segments = build_ontology()
    return IndustryGraph(segments, ())


@dataclass(frozen=True)
class EvidenceCapture:
    source_url: str
    raw_hash: str
    fetched_at: str


@dataclass(frozen=True)
class AuditedEdgeCandidate:
    edge_id: str
    source_id: str
    target_id: str
    relation_type: str
    direction: str
    strength: str
    evidence_url: str


ASML = "https://www.asml.com/en/investors/annual-report/2025/strategy-and-stories"
NVIDIA = "https://www.nvidia.com/en-eu/networking/"
NVIDIA_DC = "https://www.nvidia.com/en-us/data-center/"

_CANDIDATES: tuple[AuditedEdgeCandidate, ...] = (
    AuditedEdgeCandidate("asml-1", "ai-compute/semiconductor-equipment/lithography", "ai-compute/manufacturing-packaging/advanced-node", "enables", "forward", "high", ASML),
    AuditedEdgeCandidate("asml-2", "ai-compute/semiconductor-equipment/lithography", "ai-compute/manufacturing-packaging/foundry", "enables", "forward", "high", ASML),
    AuditedEdgeCandidate("asml-3", "ai-compute/semiconductor-equipment/lithography", "ai-compute/manufacturing-packaging/mature-node", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-4", "ai-compute/semiconductor-equipment/metrology", "ai-compute/manufacturing-packaging/advanced-node", "enables", "forward", "high", ASML),
    AuditedEdgeCandidate("asml-5", "ai-compute/semiconductor-equipment/lithography", "ai-compute/chip-design/gpu", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-6", "ai-compute/semiconductor-equipment/lithography", "ai-compute/chip-design/ai-accelerator", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-7", "ai-compute/semiconductor-equipment/lithography", "ai-compute/manufacturing-packaging/3d", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-8", "ai-compute/semiconductor-equipment/lithography", "ai-compute/manufacturing-packaging/2-5d", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-9", "ai-compute/semiconductor-equipment/metrology", "ai-compute/manufacturing-packaging/foundry", "enables", "forward", "high", ASML),
    AuditedEdgeCandidate("asml-10", "ai-compute/semiconductor-equipment/metrology", "ai-compute/manufacturing-packaging/mature-node", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-11", "ai-compute/semiconductor-equipment/lithography", "ai-compute/chip-design/cpu", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-12", "ai-compute/semiconductor-equipment/lithography", "ai-compute/chip-design/dpu", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-13", "ai-compute/semiconductor-equipment/lithography", "ai-compute/chip-design/network-asic", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("asml-14", "ai-compute/semiconductor-equipment/lithography", "ai-compute/chip-design/memory-controller", "enables", "forward", "medium", ASML),
    AuditedEdgeCandidate("nvidia-1", "ai-compute/chip-design/gpu", "ai-compute/compute-systems/ai-server", "enables", "forward", "high", NVIDIA),
    AuditedEdgeCandidate("nvidia-2", "ai-compute/chip-design/dpu", "ai-compute/network-optics/switch", "enables", "forward", "high", NVIDIA),
    AuditedEdgeCandidate("nvidia-3", "ai-compute/chip-design/network-asic", "ai-compute/network-optics/switch", "enables", "forward", "high", NVIDIA),
    AuditedEdgeCandidate("nvidia-4", "ai-compute/network-optics/optical-module", "ai-compute/network-optics/switch", "supplies", "forward", "high", NVIDIA),
    AuditedEdgeCandidate("nvidia-5", "ai-compute/network-optics/switch", "ai-compute/compute-systems/ai-server", "enables", "forward", "high", NVIDIA),
    AuditedEdgeCandidate("nvidia-6", "ai-compute/network-optics/interconnect", "ai-compute/compute-systems/ai-server", "enables", "forward", "high", NVIDIA),
    AuditedEdgeCandidate("nvidia-7", "ai-compute/compute-systems/ai-server", "ai-compute/ai-software/foundation-model", "enables", "forward", "medium", NVIDIA),
    AuditedEdgeCandidate("nvidia-dc-1", "ai-compute/compute-systems/ai-server", "ai-compute/compute-systems/rack", "enables", "forward", "high", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-2", "ai-compute/compute-systems/rack", "ai-compute/data-center/hyperscale", "enables", "forward", "high", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-3", "ai-compute/compute-systems/ai-server", "ai-compute/data-center/colo", "enables", "forward", "medium", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-4", "ai-compute/network-optics/switch", "ai-compute/data-center/hyperscale", "enables", "forward", "high", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-5", "ai-compute/network-optics/interconnect", "ai-compute/data-center/hyperscale", "enables", "forward", "high", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-6", "ai-compute/chip-design/gpu", "ai-compute/ai-software/model-training", "enables", "forward", "high", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-7", "ai-compute/chip-design/gpu", "ai-compute/ai-software/inference", "enables", "forward", "high", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-8", "ai-compute/ai-software/model-training", "ai-compute/ai-software/foundation-model", "enables", "forward", "high", NVIDIA_DC),
    AuditedEdgeCandidate("nvidia-dc-9", "ai-compute/ai-software/inference", "ai-compute/ai-software/application-layer", "enables", "forward", "medium", NVIDIA_DC),
)


def audited_candidates() -> tuple[AuditedEdgeCandidate, ...]:
    return _CANDIDATES


def capture_official_evidence(urls: Iterable[str], *, fetched_at: str) -> tuple[EvidenceCapture, ...]:
    captures = []
    for url in sorted(set(urls)):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("evidence source must be HTTPS")
        response = subprocess.run(
            ["curl", "--location", "--silent", "--show-error", "--fail", "--max-time", "20", "--user-agent", "Mozilla/5.0", url],
            capture_output=True,
            check=False,
        )
        if response.returncode or not response.stdout:
            raise ValueError("evidence source failed provenance capture")
        captures.append(EvidenceCapture(url, sha256(response.stdout).hexdigest(), fetched_at))
    return tuple(captures)


def build_audited_graph(captures: Iterable[EvidenceCapture], *, as_of: str) -> IndustryGraph:
    capture_by_url = {capture.source_url: capture for capture in captures}
    if len(capture_by_url) != len(set(candidate.evidence_url for candidate in _CANDIDATES)):
        raise ValueError("all audited graph sources require immutable captures")
    _, segments = build_ontology()
    edges = tuple(
        IndustryEdge(candidate.edge_id, candidate.source_id, candidate.target_id, candidate.relation_type, candidate.direction, candidate.strength, as_of, f"raw:{capture_by_url[candidate.evidence_url].raw_hash}")
        for candidate in _CANDIDATES
    )
    return IndustryGraph(segments, edges)
