"""Deterministic company dossier compiler over accepted research inputs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable

from .company_positions import CompanyPosition
from .evidence_gate import ResearchContextPack
from .industry_catalysts import IndustryCatalystProfile


DOSSIER_SCHEMA_VERSION = "park-company-dossier-v1"
DOSSIER_SECTIONS = ("identity", "industry_position", "evidence_coverage", "catalysts", "unknowns", "method")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class DossierSection:
    name: str
    status: str
    payload: dict[str, object]


@dataclass(frozen=True)
class CompanyDossier:
    dossier_id: str
    schema_version: str
    ticker: str
    as_of: str
    context_manifest_hash: str
    input_hash: str
    sections: tuple[DossierSection, ...]
    generation_mode: str
    model_version: str | None
    cost_units: int

    def validate(self) -> None:
        date.fromisoformat(self.as_of[:10])
        if self.schema_version != DOSSIER_SCHEMA_VERSION or self.generation_mode != "deterministic_template":
            raise ValueError("unsupported dossier contract")
        if self.model_version is not None or self.cost_units != 0:
            raise ValueError("deterministic dossier cannot claim model or token cost")
        if tuple(section.name for section in self.sections) != DOSSIER_SECTIONS:
            raise ValueError("dossier sections must use canonical order")
        if self.dossier_id != "dossier_" + self.input_hash[:40]:
            raise ValueError("dossier identity does not match inputs")


def compile_dossier(
    context: ResearchContextPack,
    position: CompanyPosition,
    catalyst_profile: IndustryCatalystProfile,
) -> CompanyDossier:
    """Compile an evidence-only dossier. No network or prose-model calls occur."""
    if position.status != "accepted" or position.citation is None:
        raise ValueError("dossier requires an accepted company industry position")
    if position.ticker.upper() != context.ticker.upper():
        raise ValueError("company position ticker does not match Context Pack")
    if catalyst_profile.segment_id != position.segment_id:
        raise ValueError("catalyst profile does not match company industry segment")
    catalyst_profile.validate()
    accepted_raw_hashes = {item.raw_hash for item in context.evidence}
    position_url, position_page, position_raw_hash = position.citation
    if position_raw_hash not in accepted_raw_hashes:
        raise ValueError("company position citation is not accepted Context Pack evidence")
    catalyst_facts = [section for section in catalyst_profile.sections if section.state == "fact" and set(section.raw_hashes).issubset(accepted_raw_hashes)]
    catalyst_status = "available" if catalyst_facts else "missing_evidence"
    unknowns = [
        {"section": section.name, "reason": "missing_evidence"}
        for section in catalyst_profile.sections if section.state == "missing_evidence"
    ]
    sections = (
        DossierSection("identity", "available", {"ticker": position.ticker, "name": position.name, "market": position.market}),
        DossierSection("industry_position", "available", {"segment_id": position.segment_id, "role": position.role, "product_keyword": position.product_keyword, "citation": {"url": position_url, "page": position_page, "raw_hash": position_raw_hash}}),
        DossierSection("evidence_coverage", "available", {"evidence_set_id": context.evidence_set_id, "manifest_hash": context.manifest_hash, "accepted_evidence_ids": tuple(item.evidence_id for item in context.evidence)}),
        DossierSection("catalysts", catalyst_status, {"fact_sections": tuple({"name": item.name, "evidence_ids": item.evidence_ids, "raw_hashes": item.raw_hashes} for item in catalyst_facts), "reason": None if catalyst_facts else "no catalyst evidence in Context Pack"}),
        DossierSection("unknowns", "available", {"gaps": tuple(unknowns)}),
        DossierSection("method", "available", {"generation_mode": "deterministic_template", "model_version": None, "cost_units": 0, "rule": "facts require Context Pack evidence; unavailable inputs remain gaps"}),
    )
    payload = {"schema_version": DOSSIER_SCHEMA_VERSION, "ticker": context.ticker.upper(), "as_of": context.as_of, "context_manifest_hash": context.manifest_hash, "position": asdict(position), "catalyst_profile_id": catalyst_profile.profile_id, "sections": [asdict(item) for item in sections]}
    identity = _digest(payload)
    dossier = CompanyDossier("dossier_" + identity[:40], DOSSIER_SCHEMA_VERSION, context.ticker.upper(), context.as_of, context.manifest_hash, identity, sections, "deterministic_template", None, 0)
    dossier.validate()
    return dossier
