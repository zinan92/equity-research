"""Evidence-bound sell-side viewpoint, disagreement, and revision matrix."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from .consensus_history import BrokerEstimate, ConsensusSnapshot, build_consensus_snapshot
from .document_intelligence import (
    DocumentParseResult,
    PageCitation,
    ReportClaim,
    validate_publication_citations,
)


VIEWPOINT_MATRIX_SCHEMA_VERSION = "park-sell-side-viewpoint-matrix-v1"
VALID_STANCES = {"bullish", "bearish", "neutral"}
VALID_CLAIM_STRENGTHS = {"tentative", "explicit"}
RATING_SCORES = {
    "强烈推荐": 3,
    "买入": 3,
    "推荐": 3,
    "增持": 2,
    "outperform": 2,
    "overweight": 2,
    "持有": 1,
    "中性": 1,
    "neutral": 1,
    "减持": 0,
    "underperform": 0,
    "卖出": -1,
    "sell": -1,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _iso_date(value: str, *, field: str) -> str:
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO YYYY-MM-DD") from exc


def _sha(value: str, *, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _finite(value: float | None, *, field: str) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def _rating_score(value: str | None) -> int | None:
    if not value:
        return None
    return RATING_SCORES.get(value.strip().lower(), RATING_SCORES.get(value.strip()))


@dataclass(frozen=True)
class ViewpointClaim:
    claim_id: str
    topic: str
    stance: str
    text: str
    strength: str
    citations: tuple[PageCitation, ...]

    def validate(self) -> None:
        for field in ("claim_id", "topic", "text"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"claim {field} is required")
        if self.stance not in VALID_STANCES:
            raise ValueError("claim stance must be bullish, bearish, or neutral")
        if self.strength not in VALID_CLAIM_STRENGTHS:
            raise ValueError("claim strength must be tentative or explicit")
        if not isinstance(self.citations, tuple):
            raise ValueError("claim citations must be immutable")

    def canonical(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "topic": self.topic,
            "stance": self.stance,
            "text": self.text,
            "strength": self.strength,
            "citations": [asdict(item) for item in self.citations],
        }


@dataclass(frozen=True)
class SellSideViewpoint:
    ticker: str
    report_id: str
    report_title: str
    document_id: str
    raw_hash: str
    broker: str
    analyst: str | None
    report_date: str
    rating: str | None
    target_price: float | None
    currency: str
    estimates: tuple[BrokerEstimate, ...]
    claims: tuple[ViewpointClaim, ...]

    def validate(self) -> None:
        for field in ("ticker", "report_id", "report_title", "document_id", "broker", "currency"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"viewpoint {field} is required")
        _sha(self.raw_hash, field="viewpoint raw_hash")
        _iso_date(self.report_date, field="report_date")
        _finite(self.target_price, field="target_price")
        if not isinstance(self.estimates, tuple) or not isinstance(self.claims, tuple):
            raise ValueError("viewpoint estimates and claims must be immutable")
        if not (self.estimates or self.claims or self.rating or self.target_price is not None):
            raise ValueError("viewpoint must contain a rating, target, estimate, or claim")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("viewpoint claim IDs must be unique")
        for claim in self.claims:
            claim.validate()
            for citation in claim.citations:
                if citation.document_id != self.document_id or citation.raw_hash != self.raw_hash:
                    raise ValueError("claim citation must bind the viewpoint document and raw hash")
        for estimate in self.estimates:
            estimate.validate()
            if (
                estimate.ticker != self.ticker.upper()
                or estimate.report_id != self.report_id
                or estimate.broker != self.broker
                or estimate.report_date != self.report_date
                or estimate.raw_hash != self.raw_hash
            ):
                raise ValueError("estimate identity does not match its viewpoint report")
            if self.analyst and estimate.analyst and estimate.analyst != self.analyst:
                raise ValueError("estimate analyst does not match its viewpoint report")
            if estimate.target_price is not None and estimate.target_price != self.target_price:
                raise ValueError("estimate target price does not match its viewpoint report")

    def canonical(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker.upper(),
            "report_id": self.report_id,
            "report_title": self.report_title,
            "document_id": self.document_id,
            "raw_hash": self.raw_hash,
            "broker": self.broker,
            "analyst": self.analyst,
            "report_date": self.report_date,
            "rating": self.rating,
            "target_price": self.target_price,
            "currency": self.currency,
            "estimates": [item.canonical() for item in self.estimates],
            "claims": [item.canonical() for item in self.claims],
        }


@dataclass(frozen=True)
class ViewpointRow:
    report_id: str
    broker: str
    analyst: str | None
    report_date: str
    rating: str | None
    target_price: float | None
    currency: str
    latest_for_broker: bool
    estimate_ids: tuple[str, ...]
    published_claim_ids: tuple[str, ...]
    blocked_claim_ids: tuple[str, ...]
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class BlockedViewpointClaim:
    report_id: str
    broker: str
    claim_id: str
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ViewpointRevision:
    broker: str
    previous_report_id: str
    current_report_id: str
    previous_date: str
    current_date: str
    dimension: str
    fiscal_year: int | None
    previous_value: str | float | None
    current_value: str | float | None
    direction: str


@dataclass(frozen=True)
class TopicEvidence:
    topic: str
    bullish_claim_ids: tuple[str, ...]
    bearish_claim_ids: tuple[str, ...]
    neutral_claim_ids: tuple[str, ...]
    contributing_brokers: tuple[str, ...]
    evidence_level: str
    allowed_summary_language: str


@dataclass(frozen=True)
class ViewpointCoverage:
    report_count: int
    broker_count: int
    reports_with_page_evidence: int
    published_claim_count: int
    blocked_claim_count: int
    reports_with_estimates: int
    coverage_level: str


@dataclass(frozen=True)
class SellSideViewpointMatrix:
    matrix_id: str
    schema_version: str
    ticker: str
    as_of: str
    input_hash: str
    rows: tuple[ViewpointRow, ...]
    consensus: ConsensusSnapshot
    revisions: tuple[ViewpointRevision, ...]
    topics: tuple[TopicEvidence, ...]
    blocked_claims: tuple[BlockedViewpointClaim, ...]
    coverage: ViewpointCoverage

    def to_report_inputs(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "broker_estimates": [asdict(item) for item in self.rows],
            "consensus_history": [
                {
                    "matrix_id": self.matrix_id,
                    "snapshot_id": self.consensus.snapshot_id,
                    "points": [asdict(item) for item in self.consensus.points],
                    "quarantine": [asdict(item) for item in self.consensus.quarantine],
                    "revisions": [asdict(item) for item in self.revisions],
                    "topics": [asdict(item) for item in self.topics],
                    "coverage": asdict(self.coverage),
                }
            ],
        }


def _numeric_direction(previous: float | None, current: float | None) -> str:
    if previous is None and current is not None:
        return "initiated"
    if previous is not None and current is None:
        return "withdrawn"
    if previous == current:
        return "unchanged"
    return "increased" if current is not None and previous is not None and current > previous else "decreased"


def _rating_direction(previous: str | None, current: str | None) -> str:
    if previous == current:
        return "unchanged"
    if previous is None and current is not None:
        return "initiated"
    if previous is not None and current is None:
        return "withdrawn"
    old_score, new_score = _rating_score(previous), _rating_score(current)
    if old_score is None or new_score is None:
        return "changed_unclassified"
    if new_score == old_score:
        return "label_changed_same_band"
    return "upgraded" if new_score > old_score else "downgraded"


def _estimate_values(viewpoint: SellSideViewpoint) -> dict[tuple[str, int], float]:
    values: dict[tuple[str, int], float] = {}
    for estimate in viewpoint.estimates:
        for metric in ("eps", "revenue", "net_profit"):
            value = getattr(estimate, metric)
            if value is not None:
                values[(metric, estimate.fiscal_year)] = value
    return values


def _build_revisions(viewpoints: Sequence[SellSideViewpoint]) -> tuple[ViewpointRevision, ...]:
    by_broker: dict[str, list[SellSideViewpoint]] = {}
    for viewpoint in viewpoints:
        by_broker.setdefault(viewpoint.broker, []).append(viewpoint)
    revisions: list[ViewpointRevision] = []
    for broker, reports in sorted(by_broker.items()):
        ordered = sorted(reports, key=lambda item: (item.report_date, item.report_id))
        for previous, current in zip(ordered, ordered[1:]):
            revisions.append(
                ViewpointRevision(
                    broker, previous.report_id, current.report_id,
                    previous.report_date, current.report_date,
                    "rating", None, previous.rating, current.rating,
                    _rating_direction(previous.rating, current.rating),
                )
            )
            revisions.append(
                ViewpointRevision(
                    broker, previous.report_id, current.report_id,
                    previous.report_date, current.report_date,
                    "target_price", None, previous.target_price, current.target_price,
                    _numeric_direction(previous.target_price, current.target_price),
                )
            )
            old_values, new_values = _estimate_values(previous), _estimate_values(current)
            for metric, fiscal_year in sorted(set(old_values) | set(new_values)):
                old, new = old_values.get((metric, fiscal_year)), new_values.get((metric, fiscal_year))
                revisions.append(
                    ViewpointRevision(
                        broker, previous.report_id, current.report_id,
                        previous.report_date, current.report_date,
                        metric, fiscal_year, old, new, _numeric_direction(old, new),
                    )
                )
    return tuple(revisions)


def _topic_evidence(
    viewpoints: Sequence[SellSideViewpoint], published_claim_ids: set[str]
) -> tuple[TopicEvidence, ...]:
    grouped: dict[str, list[tuple[str, ViewpointClaim]]] = {}
    for viewpoint in viewpoints:
        for claim in viewpoint.claims:
            if claim.claim_id in published_claim_ids:
                grouped.setdefault(claim.topic, []).append((viewpoint.broker, claim))
    topics = []
    for topic, rows in sorted(grouped.items()):
        by_stance = {
            stance: tuple(sorted(claim.claim_id for _, claim in rows if claim.stance == stance))
            for stance in VALID_STANCES
        }
        brokers = tuple(sorted({broker for broker, _ in rows}))
        explicit = [(broker, claim) for broker, claim in rows if claim.strength == "explicit"]
        explicit_brokers = {broker for broker, _ in explicit}
        stance_counts = {
            stance: len({broker for broker, claim in explicit if claim.stance == stance})
            for stance in VALID_STANCES
        }
        dominant = max(stance_counts.values(), default=0)
        ratio = dominant / len(explicit_brokers) if explicit_brokers else 0.0
        if len(explicit_brokers) >= 4 and ratio >= 0.80:
            level, language = "broad", "broadly_shared_view"
        elif len(explicit_brokers) >= 2:
            level = "multi_broker"
            language = "documented_disagreement" if stance_counts["bullish"] and stance_counts["bearish"] else "multiple_reports_indicate"
        elif len(explicit_brokers) == 1:
            level, language = "single_report", "one_report_says"
        else:
            level, language = "tentative_only", "tentative_report_language_only"
        topics.append(
            TopicEvidence(
                topic=topic,
                bullish_claim_ids=by_stance["bullish"],
                bearish_claim_ids=by_stance["bearish"],
                neutral_claim_ids=by_stance["neutral"],
                contributing_brokers=brokers,
                evidence_level=level,
                allowed_summary_language=language,
            )
        )
    return tuple(topics)


def build_sell_side_viewpoint_matrix(
    ticker: str,
    viewpoints: Iterable[SellSideViewpoint],
    corpus: Mapping[str, DocumentParseResult],
    *,
    as_of: str,
) -> SellSideViewpointMatrix:
    """Compile frozen report evidence without network or model calls."""

    ticker = ticker.upper()
    cutoff = _iso_date(as_of, field="as_of")
    supplied = tuple(viewpoints)
    for item in supplied:
        item.validate()
    selected = tuple(
        sorted(
            (item for item in supplied if item.ticker.upper() == ticker and item.report_date <= cutoff),
            key=lambda item: (item.report_date, item.broker, item.report_id),
        )
    )
    if not selected:
        raise ValueError("at least one in-scope sell-side viewpoint is required")
    report_ids = [item.report_id for item in selected]
    if len(report_ids) != len(set(report_ids)):
        raise ValueError("report IDs must be unique")
    claim_ids = [claim.claim_id for item in selected for claim in item.claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("claim IDs must be unique across the matrix")

    currencies = {item.currency for item in selected}
    if len(currencies) != 1:
        raise ValueError("viewpoint matrix cannot mix currencies")
    for viewpoint in selected:
        document = corpus.get(viewpoint.document_id)
        if document is None or document.raw_hash != viewpoint.raw_hash:
            raise ValueError("viewpoint document is missing or has a raw-hash mismatch")

    report_claims = [
        ReportClaim(claim.claim_id, claim.text, claim.citations)
        for viewpoint in selected for claim in viewpoint.claims
    ]
    gate = validate_publication_citations(report_claims, corpus)
    published_ids = {claim.claim_id for claim in gate.published_claims}
    errors_by_claim: dict[str, set[str]] = {}
    for check in gate.checks:
        if not check.valid:
            errors_by_claim.setdefault(check.claim_id, set()).update(check.errors)
    report_by_claim = {
        claim.claim_id: viewpoint
        for viewpoint in selected for claim in viewpoint.claims
    }
    blocked = tuple(
        BlockedViewpointClaim(
            report_id=report_by_claim[claim.claim_id].report_id,
            broker=report_by_claim[claim.claim_id].broker,
            claim_id=claim.claim_id,
            errors=tuple(sorted(errors_by_claim.get(claim.claim_id, {"citation gate failed"}))),
        )
        for claim in sorted(gate.blocked_claims, key=lambda item: item.claim_id)
    )

    latest_report = {
        broker: max(
            (item for item in selected if item.broker == broker),
            key=lambda item: (item.report_date, item.report_id),
        ).report_id
        for broker in {item.broker for item in selected}
    }
    blocked_ids = {item.claim_id for item in blocked}
    rows = tuple(
        ViewpointRow(
            report_id=item.report_id,
            broker=item.broker,
            analyst=item.analyst,
            report_date=item.report_date,
            rating=item.rating,
            target_price=item.target_price,
            currency=item.currency,
            latest_for_broker=latest_report[item.broker] == item.report_id,
            estimate_ids=tuple(sorted(estimate.estimate_id for estimate in item.estimates)),
            published_claim_ids=tuple(sorted(claim.claim_id for claim in item.claims if claim.claim_id in published_ids)),
            blocked_claim_ids=tuple(sorted(claim.claim_id for claim in item.claims if claim.claim_id in blocked_ids)),
            missing_fields=tuple(
                field for field, missing in (
                    ("analyst", not item.analyst),
                    ("rating", not item.rating),
                    ("target_price", item.target_price is None),
                    ("estimates", not item.estimates),
                    ("claims", not item.claims),
                ) if missing
            ),
        )
        for item in selected
    )
    estimates = tuple(estimate for item in selected for estimate in item.estimates)
    consensus = build_consensus_snapshot(ticker, estimates, as_of=cutoff)
    revisions = _build_revisions(selected)
    topics = _topic_evidence(selected, published_ids)
    reports_with_evidence = len({report_by_claim[claim_id].report_id for claim_id in published_ids})
    broker_count = len({item.broker for item in selected})
    coverage_level = (
        "broad" if broker_count >= 4 and reports_with_evidence >= 4
        else "multi_broker" if broker_count >= 2 and reports_with_evidence >= 2
        else "single_report" if reports_with_evidence
        else "insufficient"
    )
    coverage = ViewpointCoverage(
        report_count=len(selected),
        broker_count=broker_count,
        reports_with_page_evidence=reports_with_evidence,
        published_claim_count=len(published_ids),
        blocked_claim_count=len(blocked),
        reports_with_estimates=sum(bool(item.estimates) for item in selected),
        coverage_level=coverage_level,
    )
    input_payload = {
        "schema_version": VIEWPOINT_MATRIX_SCHEMA_VERSION,
        "ticker": ticker,
        "as_of": cutoff,
        "viewpoints": [item.canonical() for item in selected],
        "corpus": [
            {
                "document_id": document_id,
                "raw_hash": document.raw_hash,
                "parser_version": document.parser_version,
                "parse_id": document.parse_id,
            }
            for document_id, document in sorted(corpus.items())
            if document_id in {item.document_id for item in selected}
        ],
    }
    input_hash = _digest(input_payload)
    identity = {
        "input_hash": input_hash,
        "rows": [asdict(item) for item in rows],
        "consensus_snapshot_id": consensus.snapshot_id,
        "revisions": [asdict(item) for item in revisions],
        "topics": [asdict(item) for item in topics],
        "blocked_claims": [asdict(item) for item in blocked],
        "coverage": asdict(coverage),
    }
    return SellSideViewpointMatrix(
        matrix_id="viewpoint_matrix_" + _digest(identity)[:40],
        schema_version=VIEWPOINT_MATRIX_SCHEMA_VERSION,
        ticker=ticker,
        as_of=cutoff,
        input_hash=input_hash,
        rows=rows,
        consensus=consensus,
        revisions=revisions,
        topics=topics,
        blocked_claims=blocked,
        coverage=coverage,
    )
