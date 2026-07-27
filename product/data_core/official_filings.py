"""Official A-share filing discovery and immutable PDF ingestion adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlencode, urljoin, urlsplit
from uuid import uuid4

import requests

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
        parsed = urlsplit(self.final_url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname == "www.cninfo.com.cn"
        ):
            raise ValueError("official filing final URL must use HTTPS (except CNINFO structured index)")
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


HttpTransport = Callable[..., HttpResponse]


def _host(url: str) -> str:
    parsed = urlsplit(str(url))
    if not parsed.hostname or (
        parsed.scheme != "https"
        and not (parsed.scheme == "http" and parsed.hostname.lower().rstrip(".") == "www.cninfo.com.cn")
    ):
        raise ValueError("official source URL must be HTTPS, except CNINFO structured index HTTP")
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


class OfficialTransportError(RuntimeError):
    """A bounded official-host request failure with its actual attempt count."""

    def __init__(self, detail: str, *, attempts: int, status_code: int | None = None) -> None:
        self.attempts = attempts
        self.status_code = status_code
        super().__init__(f"{detail}; attempts={attempts}")


class OfficialHttpTransport:
    """Sequential, reusable-session transport for every registered official host."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        max_attempts: int = 4,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        timeout_seconds: float = 15.0,
        min_request_interval_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 3 <= max_attempts <= 5:
            raise ValueError("official transport max_attempts must be 3-5")
        if base_delay_seconds <= 0 or max_delay_seconds < base_delay_seconds:
            raise ValueError("official transport backoff bounds are invalid")
        if timeout_seconds <= 0 or min_request_interval_seconds < 0:
            raise ValueError("official transport timeout/interval is invalid")
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "ParkEquityResearch/1.0", "Connection": "keep-alive"})
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.timeout_seconds = timeout_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self.sleep = sleep
        self.jitter = jitter
        self.monotonic = monotonic
        self._last_request_at: float | None = None

    def _pace(self) -> None:
        if self._last_request_at is None or not self.min_request_interval_seconds:
            return
        remaining = self.min_request_interval_seconds - (self.monotonic() - self._last_request_at)
        if remaining > 0:
            self.sleep(remaining)

    @staticmethod
    def _retry_after_seconds(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            except ValueError:
                return None
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())

    def _retry_delay(self, attempt: int, retry_after: str | None = None) -> float:
        server_delay = self._retry_after_seconds(retry_after)
        if server_delay is not None:
            return min(self.max_delay_seconds, server_delay)
        ceiling = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 1)))
        return self.jitter(0.0, ceiling)

    @staticmethod
    def _allowed_redirect_chain(response: requests.Response, allowed_hosts: frozenset[str]) -> tuple[str, ...]:
        chain = tuple(item.url for item in (*response.history, response))
        if not chain or any(_host(item) not in allowed_hosts for item in chain):
            raise ValueError("official filing redirect left the source allowlist")
        return chain

    def request(
        self,
        url: str,
        request_headers: Mapping[str, str],
        *,
        method: str = "GET",
        data: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        allowed_hosts = frozenset({_host(url)})
        if method not in {"GET", "POST"}:
            raise ValueError("official transport only supports GET and POST")
        last_detail = "official transport exhausted retries"
        last_status: int | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._pace()
            try:
                response = self.session.request(
                    method,
                    url,
                    headers={"Accept": "*/*", **dict(request_headers)},
                    data=dict(data) if data is not None else None,
                    timeout=self.timeout_seconds,
                    allow_redirects=True,
                )
                self._last_request_at = self.monotonic()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.SSLError) as exc:
                last_detail = f"official transport {type(exc).__name__}: {exc}"
                if attempt == self.max_attempts:
                    raise OfficialTransportError(last_detail, attempts=attempt) from exc
                self.sleep(self._retry_delay(attempt))
                continue

            last_status = int(response.status_code)
            if response.status_code in {401, 403, 404}:
                raise OfficialTransportError(
                    f"official transport terminal HTTP {response.status_code}",
                    attempts=attempt,
                    status_code=response.status_code,
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_detail = f"official transport HTTP {response.status_code}"
                if attempt == self.max_attempts:
                    raise OfficialTransportError(last_detail, attempts=attempt, status_code=response.status_code)
                self.sleep(self._retry_delay(attempt, response.headers.get("Retry-After")))
                continue
            if not 200 <= response.status_code < 300:
                raise OfficialTransportError(
                    f"official transport terminal HTTP {response.status_code}",
                    attempts=attempt,
                    status_code=response.status_code,
                )
            chain = self._allowed_redirect_chain(response, allowed_hosts)
            headers = tuple(sorted({
                (str(key).lower(), str(value).strip())
                for key, value in response.headers.items()
                if str(key).lower() in HTTP_HEADER_ALLOWLIST and str(value).strip()
            }))
            result = HttpResponse(response.content, response.url, int(response.status_code), headers, chain)
            result.validate()
            return result
        raise OfficialTransportError(last_detail, attempts=self.max_attempts, status_code=last_status)

    def __call__(
        self,
        url: str,
        request_headers: Mapping[str, str],
        *,
        method: str = "GET",
        data: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return self.request(url, request_headers, method=method, data=data)


_DEFAULT_OFFICIAL_TRANSPORT = OfficialHttpTransport()


def default_http_transport(
    url: str,
    request_headers: Mapping[str, str],
    *,
    method: str = "GET",
    data: Mapping[str, str] | None = None,
) -> HttpResponse:
    return _DEFAULT_OFFICIAL_TRANSPORT.request(url, request_headers, method=method, data=data)


def _transport_request(
    transport: HttpTransport,
    url: str,
    request_headers: Mapping[str, str],
    *,
    method: str,
    data: Mapping[str, str] | None = None,
) -> HttpResponse:
    """Use the shared extended transport while retaining lightweight test seams."""
    return transport(url, request_headers, method=method, data=data)


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


def _cninfo_org_id(body: bytes, code: str) -> str:
    """Resolve one and only one exact security match from CNINFO top search."""
    payload = json.loads(body.decode("utf-8"))
    candidates: list[Mapping[str, Any]] = []
    if isinstance(payload, list):
        candidates.extend(item for item in payload if isinstance(item, Mapping))
    elif isinstance(payload, Mapping):
        for key in ("keyBoardList", "results", "result", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, Mapping))
            elif isinstance(value, Mapping):
                nested = value.get("list") or value.get("results")
                if isinstance(nested, list):
                    candidates.extend(item for item in nested if isinstance(item, Mapping))
    else:
        raise ValueError("CNINFO top search returned an invalid payload")
    matches = [
        item for item in candidates
        if str(item.get("code") or item.get("secCode") or item.get("stockCode") or "").strip() == code
    ]
    if not matches:
        raise ValueError("CNINFO top search returned no exact security match")
    if len(matches) != 1:
        raise ValueError("CNINFO top search returned multiple exact security matches")
    org_id = str(matches[0].get("orgId") or matches[0].get("orgid") or "").strip()
    if not org_id:
        raise ValueError("CNINFO top search exact security match has no orgId")
    return org_id


class CninfoFilingIndexAdapter:
    def __init__(self, *, transport: HttpTransport = default_http_transport) -> None:
        self.transport = transport
        self.manifest = _manifest(
            CNINFO_FILING_INDEX_SOURCE,
            RecordDomain.EVENT,
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        code = instrument.ticker[:6]
        top_search_url = "http://www.cninfo.com.cn/new/information/topSearch/query"
        top_search = await asyncio.to_thread(
            _transport_request,
            self.transport,
            top_search_url,
            {"Accept": "application/json"},
            method="POST",
            data={"keyWord": code, "maxNum": "10"},
        )
        top_search.validate()
        org_id = _cninfo_org_id(top_search.body, code)
        params = {
            "stock": f"{code},{org_id}",
            "column": {"SSE": "sse", "SZSE": "szse", "BSE": "bj"}[instrument.exchange],
            "tabName": "fulltext",
            "seDate": f"{request.parameters.get('start_date') or '2020-01-01'}~{request.parameters.get('end_date') or datetime.now().date()}",
            "pageNum": str(int(request.parameters.get("page") or 1)),
            "pageSize": str(int(request.parameters.get("limit") or 30)),
        }
        response = await asyncio.to_thread(
            _transport_request,
            self.transport,
            self.manifest.source_url,
            {"Accept": "application/json"},
            method="POST",
            data=params,
        )
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
    discovery_pages: tuple[IngestionOutcome, ...] = ()

    @property
    def publishable(self) -> bool:
        return self.discovery.publishable and all(item.publishable for item in self.discovery_pages) and all(
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
            "discovered": sum(len(item.records) for item in self.discovery_pages or (self.discovery,)),
            "discovery_pages": [
                {
                    "status": item.status,
                    "publishable": item.publishable,
                    "source_key": item.selected_source,
                    "source_url": item.attempts[-1].raw.source_url if item.attempts and item.attempts[-1].raw else None,
                    "raw_hash": item.attempts[-1].raw.raw_hash if item.attempts and item.attempts[-1].raw else None,
                }
                for item in (self.discovery_pages or (self.discovery,))
            ],
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
    max_discovery_pages: int = 1,
) -> OfficialFilingBatch:
    instrument = normalize_ashare_ticker(ticker)
    active_runtime = runtime or build_official_filing_runtime(
        transport=transport, authority_sink=authority_sink
    )
    known_ids = tuple(sorted({str(value) for value in known_document_ids}))
    request_token = uuid4().hex[:12]
    if not isinstance(max_discovery_pages, int) or max_discovery_pages < 1:
        raise ValueError("max_discovery_pages must be positive")
    discovery_pages: list[IngestionOutcome] = []
    discovered_records: tuple[RecordEnvelope, ...] = ()
    discovery: IngestionOutcome | None = None
    for page in range(1, max_discovery_pages + 1):
        discovery_request = FetchRequest.create(
            request_id=f"filing-{request_token}-index-{page}", domain=RecordDomain.EVENT,
            entity_key=instrument.ticker,
            parameters={"start_date": start_date, "end_date": end_date or str(datetime.now().date()), "limit": limit, "page": page, "known_document_ids": list(known_ids)},
        )
        discovery = await active_runtime.run(discovery_request, (SourceChoice(CNINFO_FILING_INDEX_SOURCE, "primary"),))
        discovery_pages.append(discovery)
        if not discovery.publishable:
            break
        page_records = tuple(discovery.records)
        if financial_reports_only:
            page_records = tuple(record for record in page_records if record.payload.get("document_type") in {"annual_report", "semiannual_report", "quarterly_report"})
        discovered_records = page_records
        if page_records or not financial_reports_only:
            break
    assert discovery is not None
    documents: dict[str, IngestionOutcome] = {}
    skipped: list[str] = []
    if max_documents is not None and max_documents < 1:
        raise ValueError("max_documents must be positive when provided")
    if discovery.publishable:
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
        discovery_pages=tuple(discovery_pages),
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
    max_discovery_pages: int = 1,
) -> OfficialFilingBatch:
    instrument = normalize_ashare_ticker(ticker)
    if instrument.exchange != "SSE":
        raise ValueError("sync_sse_filings only accepts SH tickers")
    active_runtime = runtime or build_official_filing_runtime(
        transport=transport, authority_sink=authority_sink
    )
    known_ids = tuple(sorted({str(value) for value in known_document_ids}))
    request_token = uuid4().hex[:12]
    if not isinstance(max_discovery_pages, int) or max_discovery_pages < 1:
        raise ValueError("max_discovery_pages must be positive")
    discovery_pages: list[IngestionOutcome] = []
    discovered_records: tuple[RecordEnvelope, ...] = ()
    discovery: IngestionOutcome | None = None
    for page in range(1, max_discovery_pages + 1):
        discovery_request = FetchRequest.create(
            request_id=f"filing-{request_token}-index-{page}", domain=RecordDomain.EVENT,
            entity_key=instrument.ticker,
            parameters={"start_date": start_date, "end_date": end_date or str(datetime.now().date()), "limit": limit, "page": page, "known_document_ids": list(known_ids)},
        )
        discovery = await active_runtime.run(discovery_request, (SourceChoice(SSE_FILING_INDEX_SOURCE, "primary"),))
        discovery_pages.append(discovery)
        if not discovery.publishable:
            break
        page_records = tuple(discovery.records)
        if financial_reports_only:
            page_records = tuple(record for record in page_records if record.payload.get("document_type") in {"annual_report", "semiannual_report", "quarterly_report"})
        discovered_records = page_records
        if page_records or not financial_reports_only:
            break
    assert discovery is not None
    documents: dict[str, IngestionOutcome] = {}
    skipped: list[str] = []
    if max_documents is not None and max_documents < 1:
        raise ValueError("max_documents must be positive when provided")
    if discovery.publishable:
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
        discovery_pages=tuple(discovery_pages),
    )


def sync_sse_filings(ticker: str, **kwargs: Any) -> OfficialFilingBatch:
    return asyncio.run(sync_sse_filings_async(ticker, **kwargs))


async def sync_exchange_filings_async(ticker: str, **kwargs: Any) -> OfficialFilingBatch:
    """Use the registered official index for every A-share exchange.

    CNINFO is the designated unified disclosure platform for SH, SZ, and BJ.
    SSE's own bulletin endpoint remains an explicit adapter, but a transient
    SSE transport failure must not make the official evidence chain unavailable.
    """
    instrument = normalize_ashare_ticker(ticker)
    if instrument.exchange in {"SSE", "SZSE", "BSE"}:
        return await sync_cninfo_filings_async(ticker, **kwargs)
    raise ValueError(f"no official filing index registered for {instrument.exchange}")


def sync_exchange_filings(ticker: str, **kwargs: Any) -> OfficialFilingBatch:
    return asyncio.run(sync_exchange_filings_async(ticker, **kwargs))
