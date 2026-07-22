"""Incremental Eastmoney sell-side catalog and content-addressed PDF archive."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from .ashare import MemoryAuthoritySink, normalize_ashare_ticker
from .contracts import RawCapture, RecordDomain, RecordEnvelope, SourceManifest
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
from .official_filings import HttpResponse, HttpTransport, default_http_transport


EASTMONEY_SELL_SIDE_CATALOG_SOURCE = "eastmoney_sell_side_catalog_v1"
EASTMONEY_SELL_SIDE_PDF_SOURCE = "eastmoney_sell_side_pdf_v1"
CATALOG_URL = "https://reportapi.eastmoney.com/report/list"
PDF_TEMPLATE = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str | None:
    cleaned = " ".join(str(value or "").split()).strip()
    return cleaned or None


def _published_at(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10:
        text = text[:19].replace(" ", "T")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _integer(value: Any) -> int | None:
    try:
        result = int(value)
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result and result not in {float("inf"), float("-inf")} else None
    except (TypeError, ValueError):
        return None


class RetryableHttpError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"retryable HTTP status {status_code}")


class RateLimitedRetryTransport:
    """Serialize Eastmoney calls and retry only transient network/status failures."""

    def __init__(
        self,
        transport: HttpTransport = default_http_transport,
        *,
        min_interval: float = 1.0,
        max_attempts: int = 3,
        backoff_seconds: float = 0.6,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval < 0 or max_attempts < 1 or backoff_seconds < 0:
            raise ValueError("invalid rate-limit or retry policy")
        self.transport = transport
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.monotonic = monotonic
        self.sleep = sleep
        self._lock = threading.Lock()
        self._last_call: float | None = None

    def __call__(self, url: str, headers: Mapping[str, str]) -> HttpResponse:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            with self._lock:
                now = self.monotonic()
                if self._last_call is not None:
                    wait = self.min_interval - (now - self._last_call)
                    if wait > 0:
                        self.sleep(wait)
                try:
                    response = self.transport(url, headers)
                    if response.status_code in {429, 500, 502, 503, 504}:
                        raise RetryableHttpError(response.status_code)
                    return response
                except HTTPError as exc:
                    if exc.code not in {429, 500, 502, 503, 504}:
                        raise
                    last_error = exc
                except (RetryableHttpError, TimeoutError, OSError) as exc:
                    last_error = exc
                finally:
                    self._last_call = self.monotonic()
            if attempt < self.max_attempts:
                self.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(f"Eastmoney request exhausted retry budget: {last_error}")


def _manifest(source_key: str, domain: RecordDomain, source_url: str) -> SourceManifest:
    return SourceManifest(
        source_key=source_key,
        domain_scope=domain.value,
        authority_tier="supplementary_only",
        provider_version="2026-07-22",
        schema_version="eastmoney-sell-side-v1",
        license_status="public_catalog_internal_research_use",
        source_url=source_url,
    )


class EastmoneySellSideCatalogAdapter:
    def __init__(self, *, transport: HttpTransport) -> None:
        self.transport = transport
        self.manifest = _manifest(
            EASTMONEY_SELL_SIDE_CATALOG_SOURCE, RecordDomain.EVENT, CATALOG_URL
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        page = int(request.parameters.get("page") or 1)
        params = {
            "industryCode": "*", "pageSize": str(int(request.parameters.get("page_size") or 50)),
            "industry": "*", "rating": "*", "ratingChange": "*",
            "beginTime": str(request.parameters.get("start_date") or "2000-01-01"),
            "endTime": str(request.parameters.get("end_date") or datetime.now().date()),
            "pageNo": str(page), "qType": "0", "orgCode": "",
            "code": instrument.ticker[:6], "rcode": "", "p": str(page),
            "pageNum": str(page), "pageNumber": str(page),
        }
        url = CATALOG_URL + "?" + urlencode(params)
        response = await asyncio.to_thread(
            self.transport, url, {"Accept": "application/json", "Referer": "https://data.eastmoney.com/"}
        )
        if urlsplit(response.final_url).hostname != "reportapi.eastmoney.com":
            raise ValueError("Eastmoney catalog redirect left reportapi host")
        fetched_at = _utc_now()
        return FetchedPayload(
            response.body, response.final_url, fetched_at, fetched_at, "application/json",
            status_code=response.status_code, response_headers=response.headers,
            redirect_chain=response.redirect_chain or (response.final_url,),
        )

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        response = json.loads(fetched.body.decode("utf-8"))
        rows = response.get("data") or []
        response_year = _integer(response.get("currentYear"))
        records = []
        for row in rows:
            report_id = _text(row.get("infoCode"))
            title = _text(row.get("title"))
            publish_date = _text(row.get("publishDate"))
            if not report_id or not title or not publish_date:
                continue
            published_at = _published_at(publish_date)
            base_year = response_year or int(published_at[:4])
            pdf_url = PDF_TEMPLATE.format(info_code=report_id)
            forecast_years = []
            for offset, eps_key, pe_key in (
                (0, "predictThisYearEps", "predictThisYearPe"),
                (1, "predictNextYearEps", "predictNextYearPe"),
                (2, "predictNextTwoYearEps", "predictNextTwoYearPe"),
            ):
                eps = _number(row.get(eps_key))
                pe = _number(row.get(pe_key))
                if eps is not None or pe is not None:
                    forecast_years.append(
                        {"fiscal_year": base_year + offset, "eps": eps, "pe": pe}
                    )
            payload = {
                "event_id": f"sell-side-catalog:{report_id}",
                "instrument_id": instrument.instrument_id,
                "event_type": "sell_side_report_cataloged",
                "occurred_at": published_at,
                "title": title,
                "evidence_ids": [f"sell-side-report:{report_id}"],
                "report_id": report_id,
                "ticker": instrument.ticker,
                "broker": _text(row.get("orgSName")) or _text(row.get("orgName")),
                "analyst": _text(row.get("researcher")),
                "published_at": published_at,
                "rating": _text(row.get("emRatingName")) or _text(row.get("sRatingName")),
                "pages": _integer(row.get("attachPages")),
                "forecast_years": forecast_years,
                "target_price_low": _number(row.get("indvAimPriceL")),
                "target_price_high": _number(row.get("indvAimPriceT")),
                "pdf_url": pdf_url,
                "canonical_url": pdf_url,
                "pdf_available": bool(report_id),
                "source_role": "sell_side_catalog",
            }
            records.append(
                RecordEnvelope.accepted(
                    domain=RecordDomain.EVENT,
                    entity_key=f"{instrument.instrument_id}:sell-side:{report_id}",
                    payload=payload, manifest=self.manifest, raw=raw,
                )
            )
        return tuple(records)


class EastmoneySellSidePdfAdapter:
    def __init__(self, *, transport: HttpTransport) -> None:
        self.transport = transport
        self.manifest = _manifest(
            EASTMONEY_SELL_SIDE_PDF_SOURCE, RecordDomain.DOCUMENT, "https://pdf.dfcfw.com/"
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        url = str(request.parameters.get("pdf_url") or "")
        if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "pdf.dfcfw.com":
            raise ValueError("sell-side PDF URL must use the Eastmoney archive host")
        response = await asyncio.to_thread(
            self.transport, url, {"Accept": "application/pdf", "Referer": "https://data.eastmoney.com/"}
        )
        if urlsplit(response.final_url).hostname != "pdf.dfcfw.com":
            raise ValueError("sell-side PDF redirect left archive host")
        if not response.body.startswith(b"%PDF"):
            raise ValueError("sell-side archive response is not PDF")
        fetched_at = _utc_now()
        return FetchedPayload(
            response.body, response.final_url, fetched_at, fetched_at, "application/pdf",
            status_code=response.status_code, response_headers=response.headers,
            redirect_chain=response.redirect_chain or (response.final_url,),
        )

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        metadata = dict(request.parameters.get("metadata") or {})
        report_id = str(metadata.get("report_id") or "").strip()
        if not report_id:
            raise ValueError("sell-side report ID is required")
        payload = {
            "document_id": f"sell-side-report:{report_id}",
            "instrument_id": instrument.instrument_id,
            "document_type": "sell_side_research_report",
            "published_at": metadata["published_at"],
            "content_hash": raw.raw_hash,
            "storage_uri": raw.storage_uri,
            "title": metadata.get("title"),
            "broker": metadata.get("broker"),
            "analyst": metadata.get("analyst"),
            "rating": metadata.get("rating"),
            "pages": metadata.get("pages"),
            "canonical_url": metadata.get("canonical_url"),
            "source_role": "independent_sell_side",
            "http_status": fetched.status_code,
            "mime_type": fetched.mime_type,
        }
        return (
            RecordEnvelope.accepted(
                domain=RecordDomain.DOCUMENT,
                entity_key=f"{instrument.instrument_id}:sell-side-pdf:{report_id}",
                payload=payload, manifest=self.manifest, raw=raw,
            ),
        )


def build_sell_side_runtime(
    *, transport: HttpTransport, authority_sink: AuthoritySink | None = None
) -> IngestionRuntime:
    registry = AdapterRegistry()
    registry.register(EastmoneySellSideCatalogAdapter(transport=transport))
    registry.register(EastmoneySellSidePdfAdapter(transport=transport))
    return IngestionRuntime(
        registry, authority_sink or MemoryAuthoritySink(),
        quality_policy=QualityPolicy(min_accepted=1), timeout_seconds=30.0,
    )


@dataclass(frozen=True)
class SellSideArchiveItem:
    report_id: str
    ticker: str
    title: str
    broker: str | None
    analyst: str | None
    published_at: str
    rating: str | None
    pages: int | None
    canonical_url: str | None
    archive_status: str
    raw_hash: str | None = None
    storage_uri: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SellSideArchiveBatch:
    ticker: str
    items: tuple[SellSideArchiveItem, ...]
    catalog_outcomes: tuple[IngestionOutcome, ...]
    pdf_outcomes: Mapping[str, IngestionOutcome]

    def query(
        self, *, broker: str | None = None, analyst: str | None = None,
        rating: str | None = None, status: str | None = None,
        published_after: str | None = None, published_before: str | None = None,
        min_pages: int | None = None,
    ) -> tuple[SellSideArchiveItem, ...]:
        return tuple(
            item for item in self.items
            if (not broker or item.broker == broker)
            and (not analyst or item.analyst == analyst)
            and (not rating or item.rating == rating)
            and (not status or item.archive_status == status)
            and (not published_after or item.published_at >= published_after)
            and (not published_before or item.published_at <= published_before)
            and (min_pages is None or (item.pages is not None and item.pages >= min_pages))
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "report_count": len(self.items),
            "status_counts": {
                status: sum(item.archive_status == status for item in self.items)
                for status in sorted({item.archive_status for item in self.items})
            },
            "items": [item.__dict__ for item in self.items],
        }


async def sync_sell_side_archive_async(
    ticker: str, *, runtime: IngestionRuntime,
    start_date: str = "2020-01-01", end_date: str | None = None,
    page_size: int = 50, max_pages: int = 1,
    known_report_ids: Iterable[str] = (), known_canonical_urls: Iterable[str] = (),
    known_raw_hashes: Iterable[str] = (),
) -> SellSideArchiveBatch:
    instrument = normalize_ashare_ticker(ticker)
    token = uuid4().hex[:12]
    known_ids = {str(value) for value in known_report_ids}
    known_urls = {str(value) for value in known_canonical_urls}
    seen_hashes = {str(value) for value in known_raw_hashes}
    catalog_outcomes = []
    metadata_rows: dict[str, dict[str, Any]] = {}
    for page in range(1, max_pages + 1):
        request = FetchRequest.create(
            request_id=f"sell-side-{token}-catalog-{page}", domain=RecordDomain.EVENT,
            entity_key=instrument.ticker,
            parameters={"page": page, "page_size": page_size, "start_date": start_date,
                        "end_date": end_date or str(datetime.now().date())},
        )
        outcome = await runtime.run(
            request, (SourceChoice(EASTMONEY_SELL_SIDE_CATALOG_SOURCE, "primary"),)
        )
        catalog_outcomes.append(outcome)
        if not outcome.publishable:
            break
        for record in outcome.records:
            metadata_rows[str(record.payload["report_id"])] = record.payload
        if len(outcome.records) < page_size:
            break

    items = []
    pdf_outcomes: dict[str, IngestionOutcome] = {}
    for report_id, metadata in metadata_rows.items():
        base = dict(
            report_id=report_id, ticker=instrument.ticker, title=str(metadata["title"]),
            broker=metadata.get("broker"), analyst=metadata.get("analyst"),
            published_at=str(metadata["published_at"]), rating=metadata.get("rating"),
            pages=metadata.get("pages"), canonical_url=metadata.get("canonical_url"),
        )
        if report_id in known_ids or metadata.get("canonical_url") in known_urls:
            items.append(SellSideArchiveItem(**base, archive_status="duplicate_url"))
            continue
        if not metadata.get("pdf_available") or not metadata.get("pdf_url"):
            items.append(SellSideArchiveItem(**base, archive_status="metadata_only"))
            continue
        request = FetchRequest.create(
            request_id=f"sell-side-{token}-pdf-{report_id}", domain=RecordDomain.DOCUMENT,
            entity_key=instrument.ticker,
            parameters={"pdf_url": metadata["pdf_url"], "metadata": metadata},
        )
        outcome = await runtime.run(
            request, (SourceChoice(EASTMONEY_SELL_SIDE_PDF_SOURCE, "primary"),)
        )
        pdf_outcomes[report_id] = outcome
        if not outcome.publishable:
            error = outcome.attempts[-1].error if outcome.attempts else "PDF unavailable"
            items.append(SellSideArchiveItem(**base, archive_status="metadata_only", error=error))
            continue
        attempt = outcome.attempts[-1]
        assert attempt.raw is not None
        if attempt.raw.raw_hash in seen_hashes:
            items.append(SellSideArchiveItem(
                **base, archive_status="duplicate_sha", raw_hash=attempt.raw.raw_hash,
                storage_uri=attempt.raw.storage_uri,
            ))
            continue
        seen_hashes.add(attempt.raw.raw_hash)
        items.append(SellSideArchiveItem(
            **base, archive_status="archived_pdf", raw_hash=attempt.raw.raw_hash,
            storage_uri=attempt.raw.storage_uri,
        ))
    return SellSideArchiveBatch(
        ticker=instrument.ticker, items=tuple(items),
        catalog_outcomes=tuple(catalog_outcomes), pdf_outcomes=pdf_outcomes,
    )


def sync_sell_side_archive(ticker: str, **kwargs: Any) -> SellSideArchiveBatch:
    return asyncio.run(sync_sell_side_archive_async(ticker, **kwargs))
