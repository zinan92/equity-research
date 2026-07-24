"""Official A-share filing discovery and immutable PDF ingestion adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
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


CNINFO_FILING_INDEX_SOURCE = "cninfo_official_filing_index_v1"
SSE_FILING_INDEX_SOURCE = "sse_official_filing_index_v1"
CNINFO_FILING_DOCUMENT_SOURCE = "cninfo_official_filing_document_v1"
SSE_FILING_DOCUMENT_SOURCE = "sse_official_filing_document_v1"
SZSE_FILING_DOCUMENT_SOURCE = "szse_official_filing_document_v1"
BSE_FILING_DOCUMENT_SOURCE = "bse_official_filing_document_v1"

OFFICIAL_SOURCE_HOSTS: dict[str, frozenset[str]] = {
    CNINFO_FILING_INDEX_SOURCE: frozenset({"www.cninfo.com.cn"}),
    SSE_FILING_INDEX_SOURCE: frozenset({"query.sse.com.cn"}),
    CNINFO_FILING_DOCUMENT_SOURCE: frozenset({"static.cninfo.com.cn"}),
    SSE_FILING_DOCUMENT_SOURCE: frozenset({"static.sse.com.cn", "www.sse.com.cn"}),
    SZSE_FILING_DOCUMENT_SOURCE: frozenset({"disc.static.szse.cn", "www.szse.cn"}),
    BSE_FILING_DOCUMENT_SOURCE: frozenset({"www.bse.cn", "static.bse.cn"}),
}

DOCUMENT_SOURCE_BY_HOST = {
    host: source_key
    for source_key, hosts in OFFICIAL_SOURCE_HOSTS.items()
    if source_key not in {CNINFO_FILING_INDEX_SOURCE, SSE_FILING_INDEX_SOURCE}
    for host in hosts
}

HTTP_HEADER_ALLOWLIST = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "content-disposition"}
)


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    final_url: str
    status_code: int
    headers: tuple[tuple[str, str], ...]
    redirect_chain: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.body:
            raise ValueError("official filing response body is empty")
        if urlsplit(self.final_url).scheme != "https":
            raise ValueError("official filing final URL must use HTTPS")
        if not 200 <= self.status_code < 300:
            raise ValueError(f"official filing HTTP status is {self.status_code}")
        FetchedPayload(
            body=self.body,
            source_url=self.final_url,
            fetched_at="2026-01-01T00:00:00Z",
            known_at="2026-01-01T00:00:00Z",
            mime_type="application/pdf" if self.body.startswith(b"%PDF") else "application/json",
            status_code=self.status_code,
            response_headers=self.headers,
            redirect_chain=self.redirect_chain or (self.final_url,),
        ).validate()


HttpTransport = Callable[[str, Mapping[str, str]], HttpResponse]


def _host(url: str) -> str:
    parsed = urlsplit(str(url))
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("official source URL must be absolute HTTPS")
    return parsed.hostname.lower().rstrip(".")


def validate_official_source_role(
    manifest: SourceManifest,
    source_url: str,
    *,
    role: str = "primary",
) -> None:
    """Prevent a news/aggregator URL from being promoted as official primary."""

    manifest.validate()
    if role != "primary":
        raise ValueError("official filing adapters only support primary raw evidence")
    allowed = OFFICIAL_SOURCE_HOSTS.get(manifest.source_key)
    if manifest.authority_tier != "official" or not allowed:
        raise ValueError("primary filing source must use a registered official manifest")
    if _host(manifest.source_url) not in allowed or _host(source_url) not in allowed:
        raise ValueError("aggregator or cross-source URL cannot act as official primary")


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.redirect_chain: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        target = urljoin(req.full_url, newurl)
        if _host(target) not in self.allowed_hosts:
            raise ValueError("official filing redirect left the source allowlist")
        self.redirect_chain.append(target)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_http_transport(url: str, request_headers: Mapping[str, str]) -> HttpResponse:
    allowed_hosts = frozenset({_host(url)})
    redirect_handler = _AllowlistedRedirectHandler(allowed_hosts)
    redirect_handler.redirect_chain.append(url)
    opener = build_opener(redirect_handler)
    request = Request(
        url,
        headers={"User-Agent": "ParkEquityResearch/1.0", **dict(request_headers)},
    )
    with opener.open(request, timeout=15.0) as response:
        final_url = response.geturl()
        if _host(final_url) not in allowed_hosts:
            raise ValueError("official filing final URL left the source allowlist")
        headers = tuple(
            sorted(
                {
                    (str(key).lower(), str(value).strip())
                    for key, value in response.headers.items()
                    if str(key).lower() in HTTP_HEADER_ALLOWLIST and str(value).strip()
                }
            )
        )
        chain = list(redirect_handler.redirect_chain)
        if chain[-1] != final_url:
            chain.append(final_url)
        result = HttpResponse(
            response.read(), final_url, int(response.status), headers, tuple(chain)
        )
        result.validate()
        return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _published_at(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text + "T00:00:00Z"
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_title(value: Any) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", str(value or "")))).strip()


def classify_filing_title(title: str) -> str:
    compact = re.sub(r"\s+", "", _clean_title(title))
    if "半年度报告摘要" in compact:
        return "semiannual_report_summary"
    if "半年度报告" in compact:
        return "semiannual_report"
    if "年度报告摘要" in compact:
        return "annual_report_summary"
    if "年度报告" in compact:
        return "annual_report"
    if re.search(r"第[一三]季度报告|季度报告", compact):
        return "quarterly_report"
    if any(
        keyword in compact
        for keyword in (
            "重大", "重组", "收购", "出售资产", "担保", "诉讼", "仲裁",
            "股权激励", "回购", "增持", "减持", "权益分派", "业绩预告",
            "业绩快报", "风险提示", "异常波动",
        )
    ):
        return "major_announcement"
    return "other_announcement"


def _manifest(source_key: str, domain: RecordDomain, source_url: str) -> SourceManifest:
    return SourceManifest(
        source_key=source_key,
        domain_scope=domain.value,
        authority_tier="official",
        provider_version="2026-07-22",
        schema_version="official-a-share-filing-v1",
        license_status="public_disclosure_internal_use",
        source_url=source_url,
    )


class CninfoFilingIndexAdapter:
    def __init__(self, *, transport: HttpTransport = default_http_transport) -> None:
        self.transport = transport
        self.manifest = _manifest(
            CNINFO_FILING_INDEX_SOURCE,
            RecordDomain.EVENT,
            "https://www.cninfo.com.cn/new/fulltextSearch/full",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        params = {
            "searchkey": instrument.ticker[:6],
            "sdate": str(request.parameters.get("start_date") or "2020-01-01"),
            "edate": str(request.parameters.get("end_date") or datetime.now().date()),
            "isfulltext": "false",
            "sortName": "time",
            "sortType": "desc",
            "pageNum": str(int(request.parameters.get("page") or 1)),
            "pageSize": str(int(request.parameters.get("limit") or 30)),
            "type": "",
        }
        url = self.manifest.source_url + "?" + urlencode(params)
        response = await asyncio.to_thread(self.transport, url, {"Accept": "application/json"})
        response.validate()
        validate_official_source_role(self.manifest, response.final_url)
        fetched_at = _utc_now()
        return FetchedPayload(
            response.body,
            response.final_url,
            fetched_at,
            fetched_at,
            "application/json",
            status_code=response.status_code,
            response_headers=response.headers,
            redirect_chain=response.redirect_chain or (response.final_url,),
        )

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        payload = json.loads(fetched.body.decode("utf-8"))
        announcements = payload.get("announcements") or []
        records: list[RecordEnvelope] = []
        for row in announcements:
            if str(row.get("secCode") or "") != instrument.ticker[:6]:
                raise ValueError("CNINFO filing index returned another security")
            document_id = str(row.get("announcementId") or "").strip()
            if not document_id:
                continue
            adjunct = str(row.get("adjunctUrl") or "").strip()
            title = _clean_title(row.get("announcementTitle"))
            if not adjunct or not title:
                continue
            document_url = (
                adjunct if adjunct.startswith("https://")
                else "https://static.cninfo.com.cn/" + adjunct.lstrip("/")
            )
            source_key = DOCUMENT_SOURCE_BY_HOST.get(_host(document_url))
            if not source_key:
                raise ValueError("CNINFO filing points outside registered official document hosts")
            published_at = _published_at(row.get("announcementTime"))
            payload_value = {
                "event_id": f"cninfo-discovery:{document_id}",
                "instrument_id": instrument.instrument_id,
                "event_type": "official_filing_discovered",
                "occurred_at": published_at,
                "title": title,
                "evidence_ids": [f"official-filing:{document_id}"],
                "document_id": document_id,
                "document_url": document_url,
                "document_type": classify_filing_title(title),
                "document_source_key": source_key,
                "source_role": "official_index",
                "ticker": instrument.ticker,
            }
            records.append(
                RecordEnvelope.accepted(
                    domain=RecordDomain.EVENT,
                    entity_key=f"{instrument.instrument_id}:filing-discovery:{document_id}",
                    payload=payload_value,
                    manifest=self.manifest,
                    raw=raw,
                )
            )
        return tuple(records)


class SseFilingIndexAdapter:
    """Discover SH issuer filing links from the official SSE bulletin index.

    The SSE index exposes the PDF path in each result row.  We only turn that
    declared path into a canonical static.sse.com.cn URL; missing or off-host
    values are rejected rather than guessed.
    """

    def __init__(self, *, transport: HttpTransport = default_http_transport) -> None:
        self.transport = transport
        self.manifest = _manifest(
            SSE_FILING_INDEX_SOURCE,
            RecordDomain.EVENT,
            "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        if instrument.exchange != "SSE":
            raise ValueError("SSE filing index only accepts SH tickers")
        params = {
            "isPagination": "true",
            "productId": instrument.ticker[:6],
            "securityType": "0101,120100,020100,020200,120200",
            "reportType": "ALL",
            "reportType2": "DQGG",
            "beginDate": str(request.parameters.get("start_date") or "2020-01-01"),
            "endDate": str(request.parameters.get("end_date") or datetime.now().date()),
            "pageHelp.pageSize": str(int(request.parameters.get("limit") or 30)),
            "pageHelp.pageNo": str(int(request.parameters.get("page") or 1)),
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
        }
        url = self.manifest.source_url + "?" + urlencode(params)
        response = await asyncio.to_thread(
            self.transport,
            url,
            {"Accept": "application/json", "Referer": "https://www.sse.com.cn/"},
        )
        response.validate()
        validate_official_source_role(self.manifest, response.final_url)
        fetched_at = _utc_now()
        return FetchedPayload(
            response.body, response.final_url, fetched_at, fetched_at, "application/json",
            status_code=response.status_code,
            response_headers=response.headers,
            redirect_chain=response.redirect_chain or (response.final_url,),
        )

    @staticmethod
    def _row_value(row: Mapping[str, Any], *names: str) -> Any:
        for name in names:
            if name in row and row[name] not in (None, ""):
                return row[name]
        return None

    @staticmethod
    def _document_url(value: Any) -> str:
        declared = str(value or "").strip()
        if not declared:
            raise ValueError("SSE filing index row has no declared document URL")
        if declared.startswith("https://"):
            url = declared
        elif declared.startswith("/"):
            url = "https://static.sse.com.cn" + declared
        else:
            raise ValueError("SSE filing index document URL must be absolute HTTPS or a root path")
        if _host(url) not in OFFICIAL_SOURCE_HOSTS[SSE_FILING_DOCUMENT_SOURCE]:
            raise ValueError("SSE filing index points outside official SSE document hosts")
        return url

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        payload = json.loads(fetched.body.decode("utf-8"))
        rows = payload.get("result") or payload.get("results") or []
        if not isinstance(rows, list):
            raise ValueError("SSE filing index result must be a list")
        records: list[RecordEnvelope] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("SSE filing index row must be an object")
            row_ticker = str(self._row_value(row, "SECURITY_CODE", "securityCode", "PRODUCT_ID") or "")
            if row_ticker and row_ticker[:6] != instrument.ticker[:6]:
                raise ValueError("SSE filing index returned another security")
            title = _clean_title(self._row_value(row, "TITLE", "title", "BULLETIN_TITLE"))
            if not title:
                continue
            document_url = self._document_url(self._row_value(row, "URL", "url", "FILE_URL"))
            declared_id = str(self._row_value(row, "BULLETIN_ID", "bulletinId", "ID") or "").strip()
            document_id = declared_id or "sse-" + hashlib.sha256(
                document_url.encode("utf-8")
            ).hexdigest()[:24]
            published_at = _published_at(
                self._row_value(row, "SSEDATE", "publishDate", "PUBLISH_DATE", "date")
            )
            records.append(RecordEnvelope.accepted(
                domain=RecordDomain.EVENT,
                entity_key=f"{instrument.instrument_id}:filing-discovery:{document_id}",
                payload={
                    "event_id": f"sse-discovery:{document_id}",
                    "instrument_id": instrument.instrument_id,
                    "event_type": "official_filing_discovered",
                    "occurred_at": published_at,
                    "title": title,
                    "evidence_ids": [f"official-filing:{document_id}"],
                    "document_id": document_id,
                    "document_url": document_url,
                    "document_type": classify_filing_title(title),
                    "document_source_key": SSE_FILING_DOCUMENT_SOURCE,
                    "source_role": "official_index",
                    "ticker": instrument.ticker,
                },
                manifest=self.manifest,
                raw=raw,
            ))
        return tuple(records)


class OfficialFilingDocumentAdapter:
    def __init__(
        self,
        source_key: str,
        *,
        source_url: str,
        transport: HttpTransport = default_http_transport,
    ) -> None:
        if source_key not in DOCUMENT_SOURCE_BY_HOST.values():
            raise ValueError("document adapter source is not a registered official platform")
        self.transport = transport
        self.manifest = _manifest(source_key, RecordDomain.DOCUMENT, source_url)

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        url = str(request.parameters.get("document_url") or "")
        validate_official_source_role(self.manifest, url)
        response = await asyncio.to_thread(self.transport, url, {"Accept": "application/pdf"})
        response.validate()
        validate_official_source_role(self.manifest, response.final_url)
        if not response.body.startswith(b"%PDF"):
            raise ValueError("official filing document is not a PDF capture")
        fetched_at = _utc_now()
        return FetchedPayload(
            response.body,
            response.final_url,
            fetched_at,
            fetched_at,
            "application/pdf",
            status_code=response.status_code,
            response_headers=response.headers,
            redirect_chain=response.redirect_chain or (response.final_url,),
        )

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        document_id = str(request.parameters.get("document_id") or "").strip()
        title = _clean_title(request.parameters.get("title"))
        published_at = _published_at(request.parameters.get("published_at"))
        if not document_id or not title:
            raise ValueError("official filing identity and title are required")
        headers = {
            key: value for key, value in fetched.response_headers if key in HTTP_HEADER_ALLOWLIST
        }
        payload = {
            "document_id": f"official-filing:{self.manifest.source_key}:{document_id}",
            "instrument_id": instrument.instrument_id,
            "document_type": classify_filing_title(title),
            "published_at": published_at,
            "content_hash": raw.raw_hash,
            "storage_uri": raw.storage_uri,
            "title": title,
            "ticker": instrument.ticker,
            "source_role": "official_primary",
            "official_platform": self.manifest.source_key,
            "http_metadata": {
                "status_code": fetched.status_code,
                "mime_type": fetched.mime_type,
                "source_url": raw.source_url,
                "initial_url": fetched.redirect_chain[0] if fetched.redirect_chain else raw.source_url,
                "final_url": raw.source_url,
                "redirect_chain": list(fetched.redirect_chain or (raw.source_url,)),
                "fetched_at": raw.fetched_at,
                "headers": headers,
            },
        }
        return (
            RecordEnvelope.accepted(
                domain=RecordDomain.DOCUMENT,
                entity_key=f"{instrument.instrument_id}:official-filing:{document_id}",
                payload=payload,
                manifest=self.manifest,
                raw=raw,
            ),
        )


def build_official_filing_registry(
    *, transport: HttpTransport = default_http_transport
) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(CninfoFilingIndexAdapter(transport=transport))
    registry.register(SseFilingIndexAdapter(transport=transport))
    registry.register(
        OfficialFilingDocumentAdapter(
            CNINFO_FILING_DOCUMENT_SOURCE,
            source_url="https://static.cninfo.com.cn/",
            transport=transport,
        )
    )
    registry.register(
        OfficialFilingDocumentAdapter(
            SSE_FILING_DOCUMENT_SOURCE,
            source_url="https://static.sse.com.cn/",
            transport=transport,
        )
    )
    registry.register(
        OfficialFilingDocumentAdapter(
            SZSE_FILING_DOCUMENT_SOURCE,
            source_url="https://disc.static.szse.cn/",
            transport=transport,
        )
    )
    registry.register(
        OfficialFilingDocumentAdapter(
            BSE_FILING_DOCUMENT_SOURCE,
            source_url="https://www.bse.cn/",
            transport=transport,
        )
    )
    return registry


def build_official_filing_runtime(
    *,
    transport: HttpTransport = default_http_transport,
    authority_sink: AuthoritySink | None = None,
) -> IngestionRuntime:
    return IngestionRuntime(
        build_official_filing_registry(transport=transport),
        authority_sink or MemoryAuthoritySink(),
        quality_policy=QualityPolicy(min_accepted=1),
        timeout_seconds=20.0,
    )


@dataclass(frozen=True)
class OfficialFilingBatch:
    ticker: str
    discovery: IngestionOutcome
    documents: Mapping[str, IngestionOutcome]
    skipped_document_ids: tuple[str, ...]

    @property
    def publishable(self) -> bool:
        return self.discovery.publishable and all(
            outcome.publishable for outcome in self.documents.values()
        )

    def to_summary(self) -> dict[str, Any]:
        captures = {}
        for document_id, outcome in self.documents.items():
            attempt = outcome.attempts[-1] if outcome.attempts else None
            record = outcome.records[0] if outcome.records else None
            captures[document_id] = {
                "status": outcome.status,
                "publishable": outcome.publishable,
                "source_key": outcome.selected_source,
                "document_type": record.payload.get("document_type") if record else None,
                "raw_hash": attempt.raw.raw_hash if attempt and attempt.raw else None,
                "storage_uri": attempt.raw.storage_uri if attempt and attempt.raw else None,
                "mime_type": attempt.raw.mime_type if attempt and attempt.raw else None,
                "http_status": attempt.fetched.status_code if attempt and attempt.fetched else None,
                "source_url": attempt.raw.source_url if attempt and attempt.raw else None,
            }
        return {
            "ticker": self.ticker,
            "status": "success" if self.publishable else "degraded",
            "publishable": self.publishable,
            "discovered": len(self.discovery.records),
            "captured": len(self.documents),
            "skipped_document_ids": list(self.skipped_document_ids),
            "captures": captures,
        }


async def sync_cninfo_filings_async(
    ticker: str,
    *,
    runtime: IngestionRuntime | None = None,
    transport: HttpTransport = default_http_transport,
    authority_sink: AuthoritySink | None = None,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    limit: int = 30,
    known_document_ids: Iterable[str] = (),
    financial_reports_only: bool = False,
    max_documents: int | None = None,
) -> OfficialFilingBatch:
    instrument = normalize_ashare_ticker(ticker)
    active_runtime = runtime or build_official_filing_runtime(
        transport=transport, authority_sink=authority_sink
    )
    known_ids = tuple(sorted({str(value) for value in known_document_ids}))
    request_token = uuid4().hex[:12]
    discovery_request = FetchRequest.create(
        request_id=f"filing-{request_token}-index",
        domain=RecordDomain.EVENT,
        entity_key=instrument.ticker,
        parameters={
            "start_date": start_date,
            "end_date": end_date or str(datetime.now().date()),
            "limit": limit,
            "known_document_ids": list(known_ids),
        },
    )
    discovery = await active_runtime.run(
        discovery_request, (SourceChoice(CNINFO_FILING_INDEX_SOURCE, "primary"),)
    )
    documents: dict[str, IngestionOutcome] = {}
    skipped: list[str] = []
    if max_documents is not None and max_documents < 1:
        raise ValueError("max_documents must be positive when provided")
    if discovery.publishable:
        discovered_records = tuple(discovery.records)
        if financial_reports_only:
            discovered_records = tuple(
                record for record in discovered_records
                if record.payload.get("document_type") in {
                    "annual_report", "semiannual_report", "quarterly_report",
                }
            )
        if max_documents is not None:
            discovered_records = discovered_records[:max_documents]
        for record in discovered_records:
            event = record.payload
            document_id = str(event["document_id"])
            if document_id in known_ids:
                skipped.append(document_id)
                continue
            source_key = str(event["document_source_key"])
            request = FetchRequest.create(
                request_id=f"filing-{request_token}-document-{document_id}",
                domain=RecordDomain.DOCUMENT,
                entity_key=instrument.ticker,
                parameters={
                    "document_id": document_id,
                    "document_url": event["document_url"],
                    "title": event["title"],
                    "published_at": event["occurred_at"],
                },
            )
            documents[document_id] = await active_runtime.run(
                request, (SourceChoice(source_key, "primary"),)
            )
    return OfficialFilingBatch(
        ticker=instrument.ticker,
        discovery=discovery,
        documents=documents,
        skipped_document_ids=tuple(sorted(skipped)),
    )


def sync_cninfo_filings(ticker: str, **kwargs: Any) -> OfficialFilingBatch:
    return asyncio.run(sync_cninfo_filings_async(ticker, **kwargs))


async def sync_sse_filings_async(
    ticker: str,
    *,
    runtime: IngestionRuntime | None = None,
    transport: HttpTransport = default_http_transport,
    authority_sink: AuthoritySink | None = None,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    limit: int = 30,
    known_document_ids: Iterable[str] = (),
    financial_reports_only: bool = False,
    max_documents: int | None = None,
) -> OfficialFilingBatch:
    instrument = normalize_ashare_ticker(ticker)
    if instrument.exchange != "SSE":
        raise ValueError("sync_sse_filings only accepts SH tickers")
    active_runtime = runtime or build_official_filing_runtime(
        transport=transport, authority_sink=authority_sink
    )
    known_ids = tuple(sorted({str(value) for value in known_document_ids}))
    request_token = uuid4().hex[:12]
    discovery_request = FetchRequest.create(
        request_id=f"filing-{request_token}-index",
        domain=RecordDomain.EVENT,
        entity_key=instrument.ticker,
        parameters={
            "start_date": start_date,
            "end_date": end_date or str(datetime.now().date()),
            "limit": limit,
            "known_document_ids": list(known_ids),
        },
    )
    discovery = await active_runtime.run(
        discovery_request, (SourceChoice(SSE_FILING_INDEX_SOURCE, "primary"),)
    )
    documents: dict[str, IngestionOutcome] = {}
    skipped: list[str] = []
    if max_documents is not None and max_documents < 1:
        raise ValueError("max_documents must be positive when provided")
    if discovery.publishable:
        discovered_records = tuple(discovery.records)
        if financial_reports_only:
            discovered_records = tuple(
                record for record in discovered_records
                if record.payload.get("document_type") in {
                    "annual_report", "semiannual_report", "quarterly_report",
                }
            )
        if max_documents is not None:
            discovered_records = discovered_records[:max_documents]
        for record in discovered_records:
            event = record.payload
            document_id = str(event["document_id"])
            if document_id in known_ids:
                skipped.append(document_id)
                continue
            documents[document_id] = await active_runtime.run(
                FetchRequest.create(
                    request_id=f"filing-{request_token}-document-{document_id}",
                    domain=RecordDomain.DOCUMENT,
                    entity_key=instrument.ticker,
                    parameters={
                        "document_id": document_id,
                        "document_url": event["document_url"],
                        "title": event["title"],
                        "published_at": event["occurred_at"],
                    },
                ),
                (SourceChoice(SSE_FILING_DOCUMENT_SOURCE, "primary"),),
            )
    return OfficialFilingBatch(
        ticker=instrument.ticker,
        discovery=discovery,
        documents=documents,
        skipped_document_ids=tuple(sorted(skipped)),
    )


def sync_sse_filings(ticker: str, **kwargs: Any) -> OfficialFilingBatch:
    return asyncio.run(sync_sse_filings_async(ticker, **kwargs))


async def sync_exchange_filings_async(ticker: str, **kwargs: Any) -> OfficialFilingBatch:
    """Select the registered exchange index; never silently fall back."""
    instrument = normalize_ashare_ticker(ticker)
    if instrument.exchange == "SSE":
        return await sync_sse_filings_async(ticker, **kwargs)
    if instrument.exchange in {"SZSE", "BSE"}:
        return await sync_cninfo_filings_async(ticker, **kwargs)
    raise ValueError(f"no official filing index registered for {instrument.exchange}")


def sync_exchange_filings(ticker: str, **kwargs: Any) -> OfficialFilingBatch:
    return asyncio.run(sync_exchange_filings_async(ticker, **kwargs))
