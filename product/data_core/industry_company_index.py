"""Canonical, evidence-gated company-to-industry index for the AI world model.

The index is deliberately a projection of ``company_positions.REVIEW_TARGETS``;
it is not a second company-position store.  Public/fact lookup methods return
only page-cited accepted positions.  Review methods retain explicit gaps so
coverage can be expanded without silently promoting a hypothesis.
"""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Iterable, Mapping

from .company_positions import CompanyPosition, REVIEW_TARGETS, position_coverage
from .industry_ontology import IndustrySegment, build_ontology


INDUSTRY_COMPANY_INDEX_SCHEMA_VERSION = "n3-company-industry-index-v1"


def _digest(value: object) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class IndustryCompanyIndex:
    """A deterministic, read-only view of reviewed company positions."""

    def __init__(
        self,
        positions: Iterable[CompanyPosition],
        segments: Iterable[IndustrySegment],
    ) -> None:
        self._positions = tuple(sorted(positions, key=lambda item: item.ticker))
        self._segments = {segment.segment_id: segment for segment in segments}
        self._by_ticker = {item.ticker.upper(): item for item in self._positions}
        self._by_segment = {
            segment_id: tuple(
                item for item in self._positions if item.segment_id == segment_id
            )
            for segment_id in self._segments
        }
        self._validate()

    def _validate(self) -> None:
        if len(self._positions) != len(self._by_ticker):
            raise ValueError("company position ticker identities must be unique")
        for position in self._positions:
            if position.segment_id not in self._segments:
                raise ValueError("company position references an unknown ontology segment")
            if position.status not in {"accepted", "needs_evidence"}:
                raise ValueError("company position status is invalid for industry index")
            if position.status == "accepted" and position.citation is None:
                raise ValueError("accepted company position requires page citation")
            if position.status != "accepted" and position.citation is not None:
                raise ValueError("unaccepted company position cannot expose a citation as fact")

    @property
    def review_records(self) -> tuple[CompanyPosition, ...]:
        """All reviewed records, including explicit hypotheses and source gaps."""

        return self._positions

    def company(self, ticker: str, *, include_unaccepted: bool = False) -> CompanyPosition | None:
        """Return an evidence-established company fact, unless review access is explicit."""

        position = self._by_ticker.get(str(ticker).upper())
        if position is None or (position.status != "accepted" and not include_unaccepted):
            return None
        return position

    def companies_for_segment(
        self,
        segment_id: str,
        *,
        include_unaccepted: bool = False,
    ) -> tuple[CompanyPosition, ...]:
        """Return deterministic company lookup for one ontology segment."""

        if segment_id not in self._segments:
            raise ValueError("unknown industry segment")
        records = self._by_segment[segment_id]
        if include_unaccepted:
            return records
        return tuple(item for item in records if item.status == "accepted")

    def coverage(self) -> Mapping[str, int]:
        """Reuse the position source of truth for coverage accounting."""

        return position_coverage(self._positions)

    def receipt(self) -> dict[str, object]:
        records = [asdict(item) for item in self._positions]
        payload = {
            "schema_version": INDUSTRY_COMPANY_INDEX_SCHEMA_VERSION,
            "coverage": dict(self.coverage()),
            "review_record_count": len(records),
            "accepted_fact_count": sum(item["status"] == "accepted" for item in records),
            "records": records,
            "truth_boundary": {
                "accepted_only_in_public_lookup": True,
                "unaccepted_are_review_hypotheses": True,
                "not_investment_research": True,
            },
        }
        payload["receipt_hash"] = _digest(payload)
        return payload


def build_industry_company_index(
    positions: Iterable[CompanyPosition] = REVIEW_TARGETS,
) -> IndustryCompanyIndex:
    """Build the canonical projection over the E3-S1 ontology and E3-S3 records."""

    _, segments = build_ontology()
    return IndustryCompanyIndex(positions, segments)
