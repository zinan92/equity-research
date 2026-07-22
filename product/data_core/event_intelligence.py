"""Canonical A-share news evidence, deterministic event topology, and coverage gaps."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .ashare import MemoryAuthoritySink, normalize_ashare_ticker
from .ashare_validation import AShareSecurityMasterEntry
from .contracts import RawCapture, RecordDomain, RecordEnvelope, RecordStatus, SourceManifest
from .ingestion import (
    AdapterRegistry,
    AuthoritySink,
    FetchedPayload,
    FetchRequest,
    IngestionOutcome,
    IngestionRuntime,
    QualityPolicy,
    SourceChoice,
)


INTELLIGENCE_SCHEMA_VERSION = "park-event-intelligence-v1"
SUPPORTED_SOURCE_TYPES = frozenset({"rss", "google_news", "yahoo_finance", "official_monitor"})
TRACKING_QUERY_KEYS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _instant(value: Any, *, fallback: str | None = None) -> str:
    if value is None or str(value).strip() == "":
        if fallback is None:
            raise ValueError("event timestamp is required")
        return fallback
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_article_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("article URL must be absolute HTTP(S)")
    host = parsed.hostname.lower().rstrip(".")
    port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit((parsed.scheme.lower(), host + port, parsed.path or "/", query, ""))


@dataclass(frozen=True)
class IntelSourceSpec:
    source_key: str
    source_type: str
    display_name: str
    source_url: str
    collector: Callable[[], Sequence[Mapping[str, Any]]]
    provider_version: str
    license_status: str = "configured_internal_research_use"

    def validate(self) -> None:
        if self.source_type not in SUPPORTED_SOURCE_TYPES:
            raise ValueError(f"unsupported intelligence source type: {self.source_type}")
        if not self.source_key.strip() or not self.display_name.strip() or not self.provider_version.strip():
            raise ValueError("source identity fields are required")
        parsed = urlsplit(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("intelligence source URL must be absolute HTTPS")
        if not callable(self.collector):
            raise ValueError("collector must be callable")

    @property
    def manifest(self) -> SourceManifest:
        self.validate()
        return SourceManifest(
            source_key=self.source_key,
            domain_scope=RecordDomain.EVENT.value,
            authority_tier="supplementary_only",
            provider_version=self.provider_version,
            schema_version=INTELLIGENCE_SCHEMA_VERSION,
            license_status=self.license_status,
            source_url=self.source_url,
            quality_flags=("news_discovery_not_official_fact",),
        )


@dataclass(frozen=True)
class EntityResolution:
    instrument_ids: tuple[str, ...]
    tickers: tuple[str, ...]
    matched_aliases: tuple[str, ...]
    ambiguous_aliases: tuple[str, ...]


class AShareEntityResolver:
    """Resolve A-share names/codes against the validated security master."""

    def __init__(self, entries: Iterable[AShareSecurityMasterEntry]) -> None:
        materialized = tuple(entries)
        if not materialized:
            raise ValueError("security master entries are required")
        self.by_ticker = {entry.ticker.upper(): entry for entry in materialized}
        self.aliases: dict[str, set[str]] = {}
        for entry in materialized:
            for alias in {entry.name, *entry.aliases, entry.ticker, entry.ticker[:6]}:
                normalized = self._alias_key(alias)
                if normalized:
                    self.aliases.setdefault(normalized, set()).add(entry.ticker.upper())

    @staticmethod
    def _alias_key(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "").strip()).upper()

    @staticmethod
    def _contains(text: str, alias: str) -> bool:
        if any("\u4e00" <= character <= "\u9fff" for character in alias):
            return alias in text
        return bool(re.search(r"(?<![A-Z0-9])" + re.escape(alias) + r"(?![A-Z0-9])", text))

    def resolve(
        self,
        title: str,
        content: str = "",
        source_tickers: Iterable[str] = (),
    ) -> EntityResolution:
        found: set[str] = set()
        matched: set[str] = set()
        ambiguous: set[str] = set()
        for raw_ticker in source_tickers:
            try:
                ticker = normalize_ashare_ticker(str(raw_ticker)).ticker
            except ValueError:
                continue
            if ticker in self.by_ticker:
                found.add(ticker)
                matched.add(str(raw_ticker))

        text = self._alias_key(f"{title} {(content or '')[:4000]}")
        for code, suffix in re.findall(r"(?<!\d)([0368]\d{5})(?:\.(SH|SZ|BJ))?(?!\d)", text):
            candidates = []
            if suffix:
                candidates.append(f"{code}.{suffix}")
            else:
                candidates.extend(ticker for ticker in self.by_ticker if ticker.startswith(code + "."))
            if len(candidates) == 1 and candidates[0] in self.by_ticker:
                found.add(candidates[0])
                matched.add(code + (f".{suffix}" if suffix else ""))

        for alias, tickers in sorted(self.aliases.items(), key=lambda item: len(item[0]), reverse=True):
            if not alias or not self._contains(text, alias):
                continue
            if len(tickers) == 1:
                found.update(tickers)
                matched.add(alias)
            else:
                ambiguous.add(alias)
        ordered = tuple(sorted(found))
        return EntityResolution(
            instrument_ids=tuple(self.by_ticker[ticker].instrument_id for ticker in ordered),
            tickers=ordered,
            matched_aliases=tuple(sorted(matched)),
            ambiguous_aliases=tuple(sorted(ambiguous)),
        )


class IntelCollectorAdapter:
    """Bridge the Intel Collector interface into the canonical ingestion runtime."""

    def __init__(self, spec: IntelSourceSpec, resolver: AShareEntityResolver) -> None:
        spec.validate()
        self.spec = spec
        self.resolver = resolver
        self.manifest = spec.manifest

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        items = await asyncio.to_thread(self.spec.collector)
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise ValueError("Intel collector must return a sequence of article mappings")
        body = _canonical_json({"source_key": self.spec.source_key, "items": list(items)}).encode("utf-8")
        fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return FetchedPayload(
            body=body,
            source_url=self.spec.source_url,
            fetched_at=fetched_at,
            known_at=fetched_at,
            mime_type="application/json",
        )

    def parse(
        self,
        request: FetchRequest,
        fetched: FetchedPayload,
        raw: RawCapture,
    ) -> Iterable[RecordEnvelope]:
        rows = json.loads(fetched.body.decode("utf-8")).get("items") or []
        records = []
        source_host = urlsplit(self.spec.source_url).hostname or ""
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            title = " ".join(str(row.get("title") or "").split())
            content = " ".join(str(row.get("content") or row.get("summary") or "").split())
            try:
                url = canonical_article_url(str(row.get("url") or ""))
            except ValueError:
                records.append(
                    RecordEnvelope.rejected(
                        domain=RecordDomain.EVENT,
                        entity_key=f"{self.spec.source_key}:rejected:{index}",
                        payload={"title": title, "reason": "invalid_article_url"},
                        manifest=self.manifest,
                        raw=raw,
                        rejection_reason="article URL is invalid",
                        violations=("invalid_article_url",),
                    )
                )
                continue
            if self.spec.source_type == "official_monitor":
                article_host = urlsplit(url).hostname or ""
                if article_host != source_host and not article_host.endswith("." + source_host):
                    records.append(
                        RecordEnvelope.rejected(
                            domain=RecordDomain.EVENT,
                            entity_key=f"{self.spec.source_key}:rejected:{index}",
                            payload={"title": title, "url": url, "reason": "official_host_mismatch"},
                            manifest=self.manifest,
                            raw=raw,
                            rejection_reason="official monitor item left configured host",
                            violations=("official_host_mismatch",),
                        )
                    )
                    continue
            source_tickers = row.get("tickers") if isinstance(row.get("tickers"), list) else []
            resolution = self.resolver.resolve(title, content, source_tickers)
            if not title or not resolution.tickers:
                records.append(
                    RecordEnvelope.rejected(
                        domain=RecordDomain.EVENT,
                        entity_key=f"{self.spec.source_key}:rejected:{index}",
                        payload={
                            "title": title,
                            "url": url,
                            "reason": "unresolved_a_share_entity",
                            "ambiguous_aliases": list(resolution.ambiguous_aliases),
                        },
                        manifest=self.manifest,
                        raw=raw,
                        rejection_reason="article did not resolve to an unambiguous A-share entity",
                        violations=("unresolved_a_share_entity",),
                    )
                )
                continue
            published_at = _instant(row.get("published_at"), fallback=fetched.known_at)
            if published_at > fetched.known_at:
                records.append(
                    RecordEnvelope.rejected(
                        domain=RecordDomain.EVENT,
                        entity_key=f"{self.spec.source_key}:rejected:{index}",
                        payload={"title": title, "url": url, "reason": "future_published_at"},
                        manifest=self.manifest,
                        raw=raw,
                        rejection_reason="article publication time is later than known_at",
                        violations=("future_published_at",),
                    )
                )
                continue
            base_evidence_id = "evidence_" + _digest(
                {
                    "source_key": self.spec.source_key,
                    "source_item_id": row.get("source_id"),
                    "url": url,
                    "title": title,
                    "published_at": published_at,
                }
            )[:40]
            for ticker, instrument_id in zip(resolution.tickers, resolution.instrument_ids):
                event_id = "event_observation_" + _digest(
                    {"evidence_id": base_evidence_id, "ticker": ticker}
                )[:40]
                payload = {
                    "event_id": event_id,
                    "instrument_id": instrument_id,
                    "event_type": "news_observation",
                    "occurred_at": published_at,
                    "title": title,
                    "evidence_ids": [base_evidence_id],
                    "ticker": ticker,
                    "evidence": {
                        "evidence_id": base_evidence_id,
                        "source_key": self.spec.source_key,
                        "source_type": self.spec.source_type,
                        "source_item_id": str(row.get("source_id") or ""),
                        "url": url,
                        "author": str(row.get("author") or "").strip() or None,
                        "excerpt": content[:2000],
                        "published_at": published_at,
                        "collected_at": fetched.known_at,
                        "raw_hash": raw.raw_hash,
                    },
                    "entity_resolution": {
                        "matched_aliases": list(resolution.matched_aliases),
                        "ambiguous_aliases": list(resolution.ambiguous_aliases),
                    },
                    "inference": None,
                    "is_llm_inferred": False,
                }
                records.append(
                    RecordEnvelope.accepted(
                        domain=RecordDomain.EVENT,
                        entity_key=f"{instrument_id}:news:{base_evidence_id}",
                        payload=payload,
                        manifest=self.manifest,
                        raw=raw,
                    )
                )
        return tuple(records)


@dataclass(frozen=True)
class IntelligenceEvidence:
    evidence_id: str
    event_observation_id: str
    instrument_id: str
    ticker: str
    title: str
    occurred_at: str
    source_key: str
    source_type: str
    source_item_id: str
    url: str
    excerpt: str
    raw_hash: str


@dataclass(frozen=True)
class InferenceEnvelope:
    provider: str
    model_id: str
    prompt_id: str
    prompt_version: str
    generated_at: str
    evidence_ids: tuple[str, ...]
    output: Mapping[str, Any]

    def validate(self) -> None:
        for field in ("provider", "model_id", "prompt_id", "prompt_version"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"inference {field} is required")
        _instant(self.generated_at)
        if not self.evidence_ids or not all(str(value).strip() for value in self.evidence_ids):
            raise ValueError("inference evidence_ids are required")
        _canonical_json(dict(self.output))


@dataclass(frozen=True)
class IntelligenceEvent:
    event_id: str
    ticker: str
    instrument_id: str
    title: str
    window_start: str
    window_end: str
    evidence_ids: tuple[str, ...]
    source_keys: tuple[str, ...]
    inference: InferenceEnvelope | None = None

    @property
    def source_count(self) -> int:
        return len(self.source_keys)


@dataclass(frozen=True)
class CoverageGap:
    source_key: str
    source_type: str
    status: str
    reason: str
    manifest_hash: str


@dataclass(frozen=True)
class IntelligenceBatch:
    evidence: tuple[IntelligenceEvidence, ...]
    events: tuple[IntelligenceEvent, ...]
    outcomes: Mapping[str, IngestionOutcome]
    coverage_gaps: tuple[CoverageGap, ...]


def _title_features(title: str) -> set[str]:
    normalized = re.sub(r"\s+-\s+[^-]{2,40}$", "", title.lower())
    latin = set(re.findall(r"[a-z0-9]{2,}", normalized))
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    chinese = {
        run[index : index + 2]
        for run in chinese_runs
        for index in range(max(0, len(run) - 1))
    }
    return latin | chinese


def _similarity(left: IntelligenceEvidence, right: IntelligenceEvidence) -> float:
    if left.url == right.url:
        return 1.0
    left_features = _title_features(left.title)
    right_features = _title_features(right.title)
    if not left_features or not right_features:
        return 0.0
    return len(left_features & right_features) / len(left_features | right_features)


def build_event_topology(
    evidence: Iterable[IntelligenceEvidence],
    *,
    window_hours: int = 48,
    similarity_threshold: float = 0.55,
) -> tuple[IntelligenceEvent, ...]:
    if window_hours < 1 or not 0 <= similarity_threshold <= 1:
        raise ValueError("event topology policy is invalid")
    clusters: list[list[IntelligenceEvidence]] = []
    ordered = sorted(evidence, key=lambda item: (item.ticker, item.occurred_at, item.evidence_id))
    for item in ordered:
        item_time = datetime.fromisoformat(item.occurred_at.replace("Z", "+00:00"))
        best_index = None
        best_score = 0.0
        for index, cluster in enumerate(clusters):
            if cluster[0].ticker != item.ticker:
                continue
            earliest = datetime.fromisoformat(cluster[0].occurred_at.replace("Z", "+00:00"))
            if abs((item_time - earliest).total_seconds()) > window_hours * 3600:
                continue
            score = max(_similarity(item, existing) for existing in cluster)
            if score >= similarity_threshold and score > best_score:
                best_index, best_score = index, score
        if best_index is None:
            clusters.append([item])
        else:
            clusters[best_index].append(item)
    events = []
    for cluster in clusters:
        members = tuple(sorted(cluster, key=lambda item: (item.occurred_at, item.evidence_id)))
        evidence_ids = tuple(sorted({item.evidence_id for item in members}))
        source_keys = tuple(sorted({item.source_key for item in members}))
        events.append(
            IntelligenceEvent(
                event_id="intelligence_event_" + _digest(
                    {"ticker": members[0].ticker, "evidence_ids": evidence_ids}
                )[:40],
                ticker=members[0].ticker,
                instrument_id=members[0].instrument_id,
                title=members[0].title,
                window_start=members[0].occurred_at,
                window_end=members[-1].occurred_at,
                evidence_ids=evidence_ids,
                source_keys=source_keys,
            )
        )
    return tuple(sorted(events, key=lambda item: (item.ticker, item.window_start, item.event_id)))


def attach_event_inference(
    event: IntelligenceEvent,
    *,
    provider: str,
    model_id: str,
    prompt_id: str,
    prompt_version: str,
    generated_at: str,
    output: Mapping[str, Any],
) -> IntelligenceEvent:
    inference = InferenceEnvelope(
        provider=provider,
        model_id=model_id,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        generated_at=_instant(generated_at),
        evidence_ids=event.evidence_ids,
        output=dict(output),
    )
    inference.validate()
    return replace(event, inference=inference)


def _evidence_from_outcome(outcome: IngestionOutcome) -> tuple[IntelligenceEvidence, ...]:
    return tuple(
        IntelligenceEvidence(
            evidence_id=str(record.payload["evidence"]["evidence_id"]),
            event_observation_id=str(record.payload["event_id"]),
            instrument_id=str(record.payload["instrument_id"]),
            ticker=str(record.payload["ticker"]),
            title=str(record.payload["title"]),
            occurred_at=str(record.payload["occurred_at"]),
            source_key=str(record.payload["evidence"]["source_key"]),
            source_type=str(record.payload["evidence"]["source_type"]),
            source_item_id=str(record.payload["evidence"]["source_item_id"]),
            url=str(record.payload["evidence"]["url"]),
            excerpt=str(record.payload["evidence"]["excerpt"]),
            raw_hash=str(record.payload["evidence"]["raw_hash"]),
        )
        for record in outcome.records
        if record.status is RecordStatus.ACCEPTED
    )


async def collect_intelligence_async(
    specs: Sequence[IntelSourceSpec],
    *,
    resolver: AShareEntityResolver,
    authority_sink: AuthoritySink | None = None,
    timeout_seconds: float = 30.0,
) -> IntelligenceBatch:
    registry = AdapterRegistry()
    for spec in specs:
        registry.register(IntelCollectorAdapter(spec, resolver))
    runtime = IngestionRuntime(
        registry,
        authority_sink or MemoryAuthoritySink(),
        quality_policy=QualityPolicy(min_accepted=1, max_rejected_ratio=1.0),
        timeout_seconds=timeout_seconds,
    )
    outcomes: dict[str, IngestionOutcome] = {}
    gaps = []
    evidence = []
    for spec in specs:
        request = FetchRequest.create(
            request_id="intelligence-" + _digest(
                {"source_key": spec.source_key, "source_type": spec.source_type}
            )[:20],
            domain=RecordDomain.EVENT,
            entity_key="CN:INTELLIGENCE",
            parameters={"source_type": spec.source_type},
        )
        outcome = await runtime.run(request, (SourceChoice(spec.source_key, "primary"),))
        outcomes[spec.source_key] = outcome
        if outcome.publishable:
            evidence.extend(_evidence_from_outcome(outcome))
        else:
            reason = (
                outcome.attempts[-1].error
                if outcome.attempts and outcome.attempts[-1].error
                else "source returned no publishable A-share evidence"
            )
            gaps.append(
                CoverageGap(
                    source_key=spec.source_key,
                    source_type=spec.source_type,
                    status=outcome.status,
                    reason=reason,
                    manifest_hash=spec.manifest.manifest_hash,
                )
            )
    unique_evidence = {item.evidence_id: item for item in evidence}
    ordered_evidence = tuple(sorted(unique_evidence.values(), key=lambda item: item.evidence_id))
    return IntelligenceBatch(
        evidence=ordered_evidence,
        events=build_event_topology(ordered_evidence),
        outcomes=outcomes,
        coverage_gaps=tuple(gaps),
    )


def collect_intelligence(specs: Sequence[IntelSourceSpec], **kwargs: Any) -> IntelligenceBatch:
    return asyncio.run(collect_intelligence_async(specs, **kwargs))
