from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import urlsplit

from .contracts import (
    RawCapture,
    RecordDomain,
    RecordEnvelope,
    RecordStatus,
    SourceManifest,
    canonical_json,
    digest,
    validate_adapter_output,
)
from .storage_layout import raw_storage_key


class AdapterContractError(ValueError):
    """A provider bridge violated the canonical ingestion contract."""


@dataclass(frozen=True)
class FetchRequest:
    request_id: str
    domain: RecordDomain
    entity_key: str
    parameters_json: str = "{}"

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        domain: RecordDomain,
        entity_key: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> "FetchRequest":
        request = cls(
            request_id=request_id,
            domain=domain,
            entity_key=entity_key,
            parameters_json=canonical_json(dict(parameters or {})),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if not isinstance(self.domain, RecordDomain):
            raise ValueError("request domain must be a RecordDomain")
        for name, value in (("request_id", self.request_id), ("entity_key", self.entity_key)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        try:
            parameters = json.loads(self.parameters_json)
        except json.JSONDecodeError as exc:
            raise ValueError("parameters_json must be valid JSON") from exc
        if not isinstance(parameters, dict) or canonical_json(parameters) != self.parameters_json:
            raise ValueError("parameters_json must be a canonical JSON object")

    @property
    def parameters(self) -> dict[str, Any]:
        return json.loads(self.parameters_json)

    def cache_key(self, source_key: str) -> str:
        return digest(
            {
                "source_key": source_key,
                "domain": self.domain.value,
                "entity_key": self.entity_key,
                "parameters": self.parameters,
            }
        )


@dataclass(frozen=True)
class FetchedPayload:
    body: bytes
    source_url: str
    fetched_at: str
    known_at: str
    mime_type: str
    status_code: int = 200
    data_kind: str = "real"
    response_headers: tuple[tuple[str, str], ...] = ()
    redirect_chain: tuple[str, ...] = ()

    def validate(self) -> None:
        if not isinstance(self.body, bytes):
            raise ValueError("fetched body must be immutable bytes")
        if not self.body:
            raise ValueError("fetched body must not be empty")
        if self.mime_type not in {"application/json", "text/html", "application/pdf"}:
            raise ValueError(f"unsupported fetched MIME type: {self.mime_type}")
        if self.data_kind not in {"real", "fixture", "cached"}:
            raise ValueError(f"unsupported data_kind: {self.data_kind}")
        if not isinstance(self.status_code, int) or not 200 <= self.status_code < 300:
            raise ValueError(f"upstream status is not successful: {self.status_code}")
        if not isinstance(self.response_headers, tuple):
            raise ValueError("response_headers must be an immutable tuple")
        normalized_headers = []
        for item in self.response_headers:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not all(isinstance(value, str) and value.strip() for value in item)
            ):
                raise ValueError("response_headers must contain non-empty string pairs")
            key, value = item
            if key != key.lower() or any(character in key + value for character in "\r\n"):
                raise ValueError("response_headers must be lowercase and single-line")
            normalized_headers.append((key, value))
        if tuple(sorted(set(normalized_headers))) != self.response_headers:
            raise ValueError("response_headers must be sorted and unique")
        if not isinstance(self.redirect_chain, tuple):
            raise ValueError("redirect_chain must be an immutable tuple")
        for url in self.redirect_chain:
            parsed = urlsplit(url)
            cninfo_structured_index = (
                parsed.scheme == "http" and (parsed.hostname or "").lower() == "www.cninfo.com.cn"
            )
            if (parsed.scheme != "https" and not cninfo_structured_index) or not parsed.netloc:
                raise ValueError("redirect_chain must contain HTTPS URLs, except CNINFO structured index HTTP")
        if self.redirect_chain and self.redirect_chain[-1] != self.source_url:
            raise ValueError("redirect_chain must end at source_url")
        RawCapture(
            raw_hash=hashlib.sha256(self.body).hexdigest(),
            storage_uri="pending/storage-key",
            source_url=self.source_url,
            fetched_at=self.fetched_at,
            known_at=self.known_at,
            mime_type=self.mime_type,
            payload_size=len(self.body),
        ).validate()


class SourceAdapter(Protocol):
    @property
    def manifest(self) -> SourceManifest:
        ...

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        ...

    def parse(
        self,
        request: FetchRequest,
        fetched: FetchedPayload,
        raw: RawCapture,
    ) -> Iterable[RecordEnvelope]:
        ...


@dataclass(frozen=True)
class SourceChoice:
    source_key: str
    role: str

    def validate(self) -> None:
        if self.role not in {"primary", "fallback"}:
            raise ValueError("source role must be primary or fallback")
        if not self.source_key.strip():
            raise ValueError("source_key must not be empty")


class AdapterRegistry:
    """Explicit source registry adapted from datafeed; duplicates fail closed."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        adapter.manifest.validate()
        source_key = adapter.manifest.source_key
        if source_key in self._adapters:
            raise AdapterContractError(f"duplicate source adapter: {source_key}")
        self._adapters[source_key] = adapter

    def get(self, source_key: str, domain: RecordDomain) -> SourceAdapter:
        try:
            adapter = self._adapters[source_key]
        except KeyError as exc:
            raise AdapterContractError(f"source adapter is not registered: {source_key}") from exc
        if domain not in adapter.manifest.domains:
            raise AdapterContractError(
                f"source {source_key} is not registered for {domain.value}"
            )
        return adapter

    def source_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


@dataclass(frozen=True)
class QualityPolicy:
    min_accepted: int = 1
    max_rejected_ratio: float = 1.0
    blocking_flags: tuple[str, ...] = ()

    def validate(self) -> None:
        if type(self.min_accepted) is not int or self.min_accepted < 1:
            raise ValueError("min_accepted must be a positive int")
        if not 0 <= self.max_rejected_ratio <= 1:
            raise ValueError("max_rejected_ratio must be between 0 and 1")
        if not all(isinstance(flag, str) and flag.strip() for flag in self.blocking_flags):
            raise ValueError("blocking_flags must contain non-empty strings")


@dataclass(frozen=True)
class BatchQuality:
    passed: bool
    accepted_count: int
    rejected_count: int
    quality_flags: tuple[str, ...]
    reasons: tuple[str, ...]


def evaluate_records(
    records: Iterable[RecordEnvelope],
    *,
    policy: QualityPolicy,
) -> BatchQuality:
    policy.validate()
    materialized = tuple(records)
    accepted = sum(record.status is RecordStatus.ACCEPTED for record in materialized)
    rejected = len(materialized) - accepted
    flags = tuple(sorted({flag for record in materialized for flag in record.quality_flags}))
    reasons: list[str] = []
    if accepted < policy.min_accepted:
        reasons.append(f"accepted_count<{policy.min_accepted}")
    ratio = rejected / len(materialized) if materialized else 1.0
    if ratio > policy.max_rejected_ratio:
        reasons.append(f"rejected_ratio>{policy.max_rejected_ratio}")
    blocked = sorted(set(flags).intersection(policy.blocking_flags))
    if blocked:
        reasons.append("blocking_flags:" + ",".join(blocked))
    return BatchQuality(
        passed=not reasons,
        accepted_count=accepted,
        rejected_count=rejected,
        quality_flags=flags,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class ValidatedFetch:
    request: FetchRequest
    manifest: SourceManifest
    fetched: FetchedPayload
    raw: RawCapture
    records: tuple[RecordEnvelope, ...]
    quality: BatchQuality


def validate_fetched_payload(
    adapter: SourceAdapter,
    request: FetchRequest,
    fetched: FetchedPayload,
    *,
    policy: QualityPolicy | None = None,
    raw: RawCapture | None = None,
) -> ValidatedFetch:
    """Reusable fixture/live adapter contract harness for every provider bridge."""

    request.validate()
    adapter.manifest.validate()
    if request.domain not in adapter.manifest.domains:
        raise AdapterContractError(
            f"source {adapter.manifest.source_key} cannot emit {request.domain.value}"
        )
    fetched.validate()
    expected_raw = build_raw_capture(fetched)
    if raw is None:
        raw = expected_raw
    elif raw != expected_raw:
        raise AdapterContractError("supplied raw capture does not match fetched bytes")
    try:
        records = validate_adapter_output(
            manifest=adapter.manifest,
            raw=raw,
            records=adapter.parse(request, fetched, raw),
        )
    except (TypeError, ValueError) as exc:
        raise AdapterContractError(
            f"adapter {adapter.manifest.source_key} output failed contract: {exc}"
        ) from exc
    wrong_domains = sorted({record.domain.value for record in records if record.domain is not request.domain})
    if wrong_domains:
        raise AdapterContractError(
            f"adapter emitted records outside requested domain: {','.join(wrong_domains)}"
        )
    quality = evaluate_records(records, policy=policy or QualityPolicy())
    return ValidatedFetch(request, adapter.manifest, fetched, raw, records, quality)


def build_raw_capture(fetched: FetchedPayload) -> RawCapture:
    fetched.validate()
    raw_hash = hashlib.sha256(fetched.body).hexdigest()
    key = raw_storage_key(raw_hash=raw_hash)
    raw = RawCapture(
        raw_hash=raw_hash,
        storage_uri=f"{key.bucket}/{key.path}",
        source_url=fetched.source_url,
        fetched_at=fetched.fetched_at,
        known_at=fetched.known_at,
        mime_type=fetched.mime_type,
        payload_size=len(fetched.body),
    )
    raw.validate()
    return raw


@dataclass(frozen=True)
class IngestionAttempt:
    request: FetchRequest
    choice: SourceChoice
    manifest: SourceManifest
    run_id: str
    idempotency_key: str
    attempt: int
    started_at: str
    finished_at: str
    status: str
    data_kind: str
    error: str | None
    fetched: FetchedPayload | None
    raw: RawCapture | None
    records: tuple[RecordEnvelope, ...]
    quality: BatchQuality
    promote: bool

    @property
    def capture_id(self) -> str | None:
        if self.raw is None:
            return None
        return "capture_" + digest(
            {
                "run_id": self.run_id,
                "raw_hash": self.raw.raw_hash,
                "known_at": self.raw.known_at,
            }
        )[:40]


class AuthoritySink(Protocol):
    def persist_attempt(self, attempt: IngestionAttempt) -> None:
        ...


class FetchCache(Protocol):
    authority: bool

    def put(self, source_key: str, request: FetchRequest, fetched: FetchedPayload) -> None:
        ...

    def get(self, source_key: str, request: FetchRequest) -> FetchedPayload | None:
        ...


@dataclass(frozen=True)
class IngestionOutcome:
    status: str
    selected_source: str | None
    data_kind: str | None
    publishable: bool
    attempts: tuple[IngestionAttempt, ...]
    records: tuple[RecordEnvelope, ...]


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("runtime clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class IngestionRuntime:
    """One Port/Adapter runtime for market, fundamental, document, estimate and event."""

    def __init__(
        self,
        registry: AdapterRegistry,
        authority_sink: AuthoritySink,
        *,
        cache: FetchCache | None = None,
        quality_policy: QualityPolicy | None = None,
        timeout_seconds: float = 30.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cache is not None and cache.authority:
            raise ValueError("runtime cache must never be an authority")
        self.registry = registry
        self.authority_sink = authority_sink
        self.cache = cache
        self.quality_policy = quality_policy or QualityPolicy()
        self.quality_policy.validate()
        self.timeout_seconds = timeout_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def run(
        self,
        request: FetchRequest,
        sources: Iterable[SourceChoice],
    ) -> IngestionOutcome:
        request.validate()
        plan = tuple(sources)
        if not plan:
            raise ValueError("at least one source choice is required")
        for choice in plan:
            choice.validate()
        source_keys = [choice.source_key for choice in plan]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("source plan cannot repeat an adapter")
        if plan[0].role != "primary" or any(choice.role != "fallback" for choice in plan[1:]):
            raise ValueError("source plan must contain one primary followed by fallbacks")

        attempts: list[IngestionAttempt] = []
        for choice in plan:
            adapter = self.registry.get(choice.source_key, request.domain)
            attempt = await self._run_live_attempt(request, choice, adapter)
            attempts.append(attempt)
            if attempt.data_kind not in {"cached", "fixture"}:
                self.authority_sink.persist_attempt(attempt)
            if attempt.fetched is not None and self.cache is not None:
                self.cache.put(choice.source_key, request, attempt.fetched)
            if attempt.status == "success" and attempt.promote:
                return IngestionOutcome(
                    status="success",
                    selected_source=choice.source_key,
                    data_kind=attempt.data_kind,
                    publishable=True,
                    attempts=tuple(attempts),
                    records=attempt.records,
                )

        if self.cache is not None:
            for choice in plan:
                cached = self.cache.get(choice.source_key, request)
                if cached is None:
                    continue
                adapter = self.registry.get(choice.source_key, request.domain)
                attempt = self._cached_attempt(request, choice, adapter, cached)
                attempts.append(attempt)
                if attempt.quality.passed:
                    return IngestionOutcome(
                        status="degraded",
                        selected_source=choice.source_key,
                        data_kind="cached",
                        publishable=False,
                        attempts=tuple(attempts),
                        records=attempt.records,
                    )

        return IngestionOutcome(
            status="failed",
            selected_source=None,
            data_kind=None,
            publishable=False,
            attempts=tuple(attempts),
            records=(),
        )

    async def _run_live_attempt(
        self,
        request: FetchRequest,
        choice: SourceChoice,
        adapter: SourceAdapter,
    ) -> IngestionAttempt:
        started_at = _utc(self.clock())
        fetched: FetchedPayload | None = None
        raw: RawCapture | None = None
        validated: ValidatedFetch | None = None
        error: str | None = None
        try:
            fetched = await asyncio.wait_for(adapter.fetch(request), timeout=self.timeout_seconds)
            if fetched.data_kind == "cached":
                raw = build_raw_capture(fetched)
                raise AdapterContractError("live adapter cannot label its response as cached")
            raw = build_raw_capture(fetched)
            validated = validate_fetched_payload(
                adapter, request, fetched, policy=self.quality_policy, raw=raw
            )
        except asyncio.TimeoutError:
            error = f"adapter timeout after {self.timeout_seconds:g}s"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finished_at = _utc(self.clock())
        data_kind = fetched.data_kind if fetched is not None and fetched.data_kind in {"real", "fixture"} else "real"
        quality = validated.quality if validated is not None else BatchQuality(
            False, 0, 0, (), ("adapter_failure",)
        )
        promote = validated is not None and quality.passed and data_kind == "real"
        if promote:
            status = "success"
        elif validated is not None:
            status = "degraded"
            if data_kind != "real" and error is None:
                error = f"{data_kind}_data_is_not_publishable"
        else:
            status = "failed"
        return self._attempt(
            request=request,
            choice=choice,
            adapter=adapter,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            data_kind=data_kind,
            error=error,
            fetched=fetched,
            raw=raw,
            validated=validated,
            promote=promote,
        )

    def _cached_attempt(
        self,
        request: FetchRequest,
        choice: SourceChoice,
        adapter: SourceAdapter,
        cached: FetchedPayload,
    ) -> IngestionAttempt:
        started_at = _utc(self.clock())
        validated: ValidatedFetch | None = None
        raw: RawCapture | None = None
        error: str | None = None
        try:
            raw = build_raw_capture(cached)
            validated = validate_fetched_payload(
                adapter, request, cached, policy=self.quality_policy, raw=raw
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        return self._attempt(
            request=request,
            choice=choice,
            adapter=adapter,
            started_at=started_at,
            finished_at=_utc(self.clock()),
            status="degraded" if validated is not None else "failed",
            data_kind="cached",
            error=error or "local_cache_only_not_publishable",
            fetched=cached,
            raw=raw,
            validated=validated,
            promote=False,
        )

    @staticmethod
    def _attempt(
        *,
        request: FetchRequest,
        choice: SourceChoice,
        adapter: SourceAdapter,
        started_at: str,
        finished_at: str,
        status: str,
        data_kind: str,
        error: str | None,
        fetched: FetchedPayload | None,
        raw: RawCapture | None,
        validated: ValidatedFetch | None,
        promote: bool,
    ) -> IngestionAttempt:
        idempotency_key = digest(
            {
                "request_id": request.request_id,
                "source_key": choice.source_key,
                "domain": request.domain.value,
            }
        )
        run_id = "run_" + digest({"idempotency_key": idempotency_key, "attempt": 1})[:40]
        return IngestionAttempt(
            request=request,
            choice=choice,
            manifest=adapter.manifest,
            run_id=run_id,
            idempotency_key=idempotency_key,
            attempt=1,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            data_kind=data_kind,
            error=error,
            fetched=fetched,
            raw=validated.raw if validated else raw,
            records=validated.records if validated else (),
            quality=validated.quality if validated else BatchQuality(
                False, 0, 0, (), ("adapter_failure",)
            ),
            promote=promote,
        )
