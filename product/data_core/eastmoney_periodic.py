"""Polite Eastmoney adapters for periodic A-share research facts.

These adapters deliberately sit beside (rather than inside) the quote and
financial-statement collector.  The two feeds have different freshness and
availability semantics:

* ``BusinessAnalysis/PageAjax`` is a company-level F10 snapshot.  It exposes
  a reported business composition, but does not expose the original filing's
  publication timestamp.  The adapter therefore records the observation time
  explicitly and does not pretend it is a filing notice date.
* ``RPT_PUBLIC_BS_APPOIN`` is a report-period-wide calendar.  Its 500-row
  pages are preserved individually; only the collection helper may present
  every successful page as a complete universe.

They use the existing immutable RawCapture/RecordEnvelope boundary.  No Ainiu
archive content, ratings, or scores is embedded here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import threading
import time
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode

from .ashare import HttpGet, default_http_get, normalize_ashare_ticker
from .contracts import RawCapture, RecordDomain, RecordEnvelope, SourceManifest
from .ingestion import (
    AdapterRegistry,
    AuthoritySink,
    FetchRequest,
    FetchedPayload,
    IngestionOutcome,
    IngestionRuntime,
    QualityPolicy,
    SourceChoice,
)


EASTMONEY_BUSINESS_COMPOSITION_SOURCE = "eastmoney_f10_business_composition_v1"
EASTMONEY_EARNINGS_CALENDAR_SOURCE = "eastmoney_earnings_calendar_v1"

_BUSINESS_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/PageAjax"
_CALENDAR_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_A_SHARE_TYPES = ("058001001", "058001008")
_REPORT_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class EastmoneyPeriodicPayloadError(ValueError):
    """A periodic provider response is incomplete or cannot be normalized."""


class _RateLimiter:
    """Process-local, thread-safe spacing for a provider endpoint.

    It intentionally reserves slots before sleeping so simultaneous callers do
    not create a burst.  It is not a bypass/retry mechanism: HTTP failures
    propagate directly into the existing failed-ingestion receipt.
    """

    def __init__(self, minimum_interval_seconds: float) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must be non-negative")
        self.minimum_interval_seconds = minimum_interval_seconds
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.minimum_interval_seconds
        if delay:
            time.sleep(delay)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_date(value: Any, *, field: str) -> str:
    match = _REPORT_DATE.match(str(value or "").strip())
    if not match:
        raise EastmoneyPeriodicPayloadError(f"{field} is missing or invalid")
    return match.group(0)


def _optional_date(value: Any) -> str | None:
    try:
        return _iso_date(value, field="provider date")
    except EastmoneyPeriodicPayloadError:
        return None


def _number(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _assert_business_identity(row: Mapping[str, Any], *, ticker: str, code: str) -> None:
    secucode = str(row.get("SECUCODE") or "").upper()
    security_code = str(row.get("SECURITY_CODE") or "")
    if secucode and secucode != ticker:
        raise EastmoneyPeriodicPayloadError(
            f"business composition identity mismatch: expected {ticker}, got {secucode}"
        )
    if security_code and security_code != code:
        raise EastmoneyPeriodicPayloadError(
            f"business composition code mismatch: expected {code}, got {security_code}"
        )
    if not secucode and not security_code:
        raise EastmoneyPeriodicPayloadError("business composition row is missing security identity")


def _appointment_date(row: Mapping[str, Any]) -> str | None:
    # The display date follows Eastmoney's current appointment date first; the
    # individual change timestamps remain in payload for an audit trail.
    for field in (
        "APPOINT_PUBLISH_DATE",
        "THIRD_CHANGE_DATE",
        "SECOND_CHANGE_DATE",
        "FIRST_CHANGE_DATE",
        "FIRST_APPOINT_DATE",
    ):
        parsed = _optional_date(row.get(field))
        if parsed:
            return parsed
    return None


class EastmoneyBusinessCompositionAdapter:
    """F10 reported business-composition rows for one A-share company."""

    def __init__(
        self,
        *,
        http_get: HttpGet = default_http_get,
        minimum_interval_seconds: float = 0.5,
    ) -> None:
        self.http_get = http_get
        self._rate_limiter = _RateLimiter(minimum_interval_seconds)
        self.manifest = SourceManifest(
            source_key=EASTMONEY_BUSINESS_COMPOSITION_SOURCE,
            domain_scope=RecordDomain.FUNDAMENTAL.value,
            authority_tier="supplementary_only",
            provider_version="eastmoney-f10-business-analysis-2026-07",
            schema_version="eastmoney-f10-business-composition-v1",
            license_status="configured_internal_use",
            source_url=_BUSINESS_URL,
            quality_flags=(
                "vendor_f10",
                "polite_rate_limited",
                "provider_notice_time_not_exposed",
            ),
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        url = _BUSINESS_URL + "?" + urlencode({"code": instrument.provider_symbol.upper()})

        def fetch_bytes() -> bytes:
            self._rate_limiter.wait()
            return self.http_get(url, "utf-8")

        body = await asyncio.to_thread(fetch_bytes)
        fetched_at = _utc_now()
        return FetchedPayload(
            body=body,
            source_url=url,
            fetched_at=fetched_at,
            known_at=fetched_at,
            mime_type="application/json",
            data_kind="real",
        )

    def parse(
        self,
        request: FetchRequest,
        fetched: FetchedPayload,
        raw: RawCapture,
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        try:
            payload = json.loads(fetched.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EastmoneyPeriodicPayloadError("business composition payload is not JSON") from exc
        rows = payload.get("zygcfx")
        if not isinstance(rows, list):
            raise EastmoneyPeriodicPayloadError("business composition payload has no zygcfx rows")

        category_names = {"1": "industry", "2": "product", "3": "geography"}
        metrics = (
            ("MAIN_BUSINESS_INCOME", "segment_revenue", "CNY"),
            ("MBI_RATIO", "segment_revenue_share", "pct"),
            ("MAIN_BUSINESS_COST", "segment_cost", "CNY"),
            ("MBC_RATIO", "segment_cost_share", "pct"),
            ("MAIN_BUSINESS_RPOFIT", "segment_profit", "CNY"),
            ("MBR_RATIO", "segment_profit_share", "pct"),
            ("GROSS_RPOFIT_RATIO", "segment_gross_margin", "pct"),
        )
        records: list[RecordEnvelope] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            _assert_business_identity(row, ticker=instrument.ticker, code=instrument.ticker[:6])
            report_period = _iso_date(row.get("REPORT_DATE"), field="REPORT_DATE")
            segment_name = str(row.get("ITEM_NAME") or "").strip()
            if not segment_name:
                continue
            category_code = str(row.get("MAINOP_TYPE") or "").strip()
            category = category_names.get(category_code, "other")
            identity = f"{instrument.instrument_id}:segment:{report_period}:{category}:{segment_name}"
            for provider_key, metric, unit in metrics:
                value = _number(row.get(provider_key))
                if value is None:
                    continue
                records.append(
                    RecordEnvelope.accepted(
                        domain=RecordDomain.FUNDAMENTAL,
                        entity_key=f"{identity}:{metric}",
                        payload={
                            "instrument_id": instrument.instrument_id,
                            "report_period": report_period,
                            # Eastmoney does not expose the original filing time
                            # in this response.  This is the observation time,
                            # retained as such below rather than claimed as one.
                            "announced_at": raw.known_at,
                            "metric": metric,
                            "value": value,
                            "unit": unit,
                            "ticker": instrument.ticker,
                            "segment_name": segment_name,
                            "segment_category": category,
                            "provider_category_code": category_code or None,
                            "observed_at": raw.known_at,
                            "availability_time_kind": "provider_observation",
                        },
                        manifest=self.manifest,
                        raw=raw,
                    )
                )
        if not records:
            raise EastmoneyPeriodicPayloadError("business composition has no usable numeric rows")
        return tuple(records)


class EastmoneyEarningsCalendarAdapter:
    """One provenance-preserving A-share appointment-calendar page per request.

    Eastmoney currently caps the feed at 500 rows.  ``collect_*calendar``
    below is the only helper that may claim a complete report-period universe:
    it walks every page sequentially, leaving each provider page as its own raw
    capture and failed run if one request breaks.
    """

    def __init__(
        self,
        *,
        http_get: HttpGet = default_http_get,
        minimum_interval_seconds: float = 0.5,
        page_size: int = 500,
    ) -> None:
        if not 1 <= page_size <= 500:
            raise ValueError("page_size must be between 1 and 500")
        self.http_get = http_get
        self._rate_limiter = _RateLimiter(minimum_interval_seconds)
        self.page_size = page_size
        self.manifest = SourceManifest(
            source_key=EASTMONEY_EARNINGS_CALENDAR_SOURCE,
            domain_scope=RecordDomain.EVENT.value,
            authority_tier="supplementary_only",
            provider_version="eastmoney-appointment-calendar-2026-07",
            schema_version="eastmoney-earnings-calendar-v1",
            license_status="configured_internal_use",
            source_url=_CALENDAR_URL,
            quality_flags=("vendor_calendar", "polite_rate_limited", "complete_run_required"),
        )

    @staticmethod
    def _report_period(request: FetchRequest) -> str:
        value = request.parameters.get("report_period")
        if not isinstance(value, str):
            raise ValueError("earnings calendar request requires report_period=YYYY-MM-DD")
        return _iso_date(value, field="report_period")

    @staticmethod
    def _page_number(request: FetchRequest) -> int:
        value = request.parameters.get("page_number", 1)
        if type(value) is not int or value < 1:
            raise ValueError("earnings calendar page_number must be a positive integer")
        return value

    def _page_size(self, request: FetchRequest) -> int:
        value = request.parameters.get("page_size", self.page_size)
        if type(value) is not int or not 1 <= value <= 500:
            raise ValueError("earnings calendar page_size must be an integer from 1 to 500")
        return value

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        report_period = self._report_period(request)
        page_number = self._page_number(request)
        a_share_types = ",".join('"' + value + '"' for value in _A_SHARE_TYPES)
        params = {
            "sortColumns": "FIRST_APPOINT_DATE,SECURITY_CODE",
            "sortTypes": "1,1",
            "pageSize": str(self._page_size(request)),
            "pageNumber": str(page_number),
            "reportName": "RPT_PUBLIC_BS_APPOIN",
            "columns": "ALL",
            "filter": (
                f"(SECURITY_TYPE_CODE in ({a_share_types}))"
                '(TRADE_MARKET_CODE!="069001017")'
                f"(REPORT_DATE='{report_period}')"
            ),
        }
        url = _CALENDAR_URL + "?" + urlencode(params)

        def fetch_bytes() -> bytes:
            self._rate_limiter.wait()
            return self.http_get(url, "utf-8")

        body = await asyncio.to_thread(fetch_bytes)
        fetched_at = _utc_now()
        return FetchedPayload(
            body=body,
            source_url=url,
            fetched_at=fetched_at,
            known_at=fetched_at,
            mime_type="application/json",
            data_kind="real",
        )

    def parse(
        self,
        request: FetchRequest,
        fetched: FetchedPayload,
        raw: RawCapture,
    ) -> Iterable[RecordEnvelope]:
        expected_period = self._report_period(request)
        requested_page = self._page_number(request)
        try:
            payload = json.loads(fetched.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EastmoneyPeriodicPayloadError("earnings calendar payload is not JSON") from exc
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise EastmoneyPeriodicPayloadError("earnings calendar payload has no result")
        pages = result.get("pages")
        if not isinstance(pages, int) or pages < requested_page:
            raise EastmoneyPeriodicPayloadError(
                "earnings calendar response has an invalid page count"
            )
        rows = result.get("data")
        if not isinstance(rows, list):
            raise EastmoneyPeriodicPayloadError("earnings calendar payload has no data rows")

        records: list[RecordEnvelope] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            code = str(row.get("SECURITY_CODE") or "").strip()
            try:
                instrument = normalize_ashare_ticker(code)
            except ValueError:
                continue
            row_period = _iso_date(row.get("REPORT_DATE"), field="REPORT_DATE")
            if row_period != expected_period:
                raise EastmoneyPeriodicPayloadError(
                    f"earnings calendar report-period mismatch: expected {expected_period}, got {row_period}"
                )
            scheduled_date = _appointment_date(row)
            actual_date = _optional_date(row.get("ACTUAL_PUBLISH_DATE"))
            if not scheduled_date and not actual_date:
                continue
            date_kind = "actual" if actual_date else "appointment"
            effective_date = actual_date or scheduled_date
            assert effective_date is not None
            records.append(
                RecordEnvelope.accepted(
                    domain=RecordDomain.EVENT,
                    entity_key=f"{instrument.instrument_id}:earnings-calendar:{row_period}",
                    payload={
                        "event_id": f"eastmoney-earnings-{instrument.ticker}-{row_period}",
                        "instrument_id": instrument.instrument_id,
                        # This is the time the calendar row became known to this
                        # collector.  The future calendar date is explicit below.
                        "occurred_at": raw.known_at,
                        "event_type": "earnings_disclosure_calendar",
                        "title": f"{instrument.ticker} {row_period} earnings {date_kind}",
                        "evidence_ids": [f"raw:{raw.raw_hash}"],
                        "ticker": instrument.ticker,
                        "report_period": row_period,
                        "scheduled_disclosure_date": scheduled_date,
                        "actual_disclosure_date": actual_date,
                        "effective_disclosure_date": effective_date,
                        "calendar_status": date_kind,
                        "observed_at": raw.known_at,
                        "first_appointment_date": _optional_date(row.get("FIRST_APPOINT_DATE")),
                        "first_change_date": _optional_date(row.get("FIRST_CHANGE_DATE")),
                        "second_change_date": _optional_date(row.get("SECOND_CHANGE_DATE")),
                        "third_change_date": _optional_date(row.get("THIRD_CHANGE_DATE")),
                        "provider_page_number": requested_page,
                        "provider_page_count": pages,
                    },
                    manifest=self.manifest,
                    raw=raw,
                )
            )
        if not records:
            raise EastmoneyPeriodicPayloadError("earnings calendar has no usable A-share rows")
        return tuple(records)


@dataclass
class MemoryAttemptSink:
    """Small default sink for local probes; production injects SupabaseAuthoritySink."""

    attempts: list[Any]

    def __init__(self) -> None:
        self.attempts = []

    def persist_attempt(self, attempt: Any) -> None:
        self.attempts.append(attempt)


@dataclass(frozen=True)
class EarningsCalendarCollection:
    """Complete-period result assembled from individually auditable page runs."""

    report_period: str
    total_pages: int
    status: str
    publishable: bool
    outcomes: tuple[IngestionOutcome, ...]
    records: tuple[RecordEnvelope, ...]


def build_eastmoney_periodic_registry(
    *,
    http_get: HttpGet = default_http_get,
    minimum_interval_seconds: float = 0.5,
) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(
        EastmoneyBusinessCompositionAdapter(
            http_get=http_get, minimum_interval_seconds=minimum_interval_seconds
        )
    )
    registry.register(
        EastmoneyEarningsCalendarAdapter(
            http_get=http_get, minimum_interval_seconds=minimum_interval_seconds
        )
    )
    return registry


def build_eastmoney_periodic_runtime(
    *,
    http_get: HttpGet = default_http_get,
    authority_sink: AuthoritySink | None = None,
    minimum_interval_seconds: float = 0.5,
) -> IngestionRuntime:
    return IngestionRuntime(
        build_eastmoney_periodic_registry(
            http_get=http_get, minimum_interval_seconds=minimum_interval_seconds
        ),
        authority_sink or MemoryAttemptSink(),
        quality_policy=QualityPolicy(min_accepted=1),
        timeout_seconds=20.0,
    )


async def collect_eastmoney_earnings_calendar_async(
    report_period: str,
    *,
    runtime: IngestionRuntime | None = None,
    http_get: HttpGet = default_http_get,
) -> EarningsCalendarCollection:
    runtime = runtime or build_eastmoney_periodic_runtime(http_get=http_get)
    normalized_period = _iso_date(report_period, field="report_period")

    def request_for(page_number: int) -> FetchRequest:
        return FetchRequest.create(
            request_id=f"eastmoney-earnings-calendar-{normalized_period}-page-{page_number}",
            domain=RecordDomain.EVENT,
            entity_key="CN:A-SHARE-UNIVERSE",
            parameters={"report_period": normalized_period, "page_number": page_number},
        )

    first = await runtime.run(
        request_for(1), (SourceChoice(EASTMONEY_EARNINGS_CALENDAR_SOURCE, "primary"),)
    )
    outcomes = [first]
    if not first.publishable or not first.attempts or first.attempts[-1].fetched is None:
        return EarningsCalendarCollection(
            report_period=normalized_period, total_pages=0, status="failed", publishable=False,
            outcomes=tuple(outcomes), records=(),
        )
    try:
        response = json.loads(first.attempts[-1].fetched.body.decode("utf-8"))
        total_pages = response["result"]["pages"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise EastmoneyPeriodicPayloadError("successful calendar page lacks page metadata") from exc
    if type(total_pages) is not int or total_pages < 1:
        raise EastmoneyPeriodicPayloadError("successful calendar page has invalid page metadata")
    for page_number in range(2, total_pages + 1):
        outcome = await runtime.run(
            request_for(page_number),
            (SourceChoice(EASTMONEY_EARNINGS_CALENDAR_SOURCE, "primary"),),
        )
        outcomes.append(outcome)
        if not outcome.publishable:
            return EarningsCalendarCollection(
                report_period=normalized_period, total_pages=total_pages, status="failed", publishable=False,
                outcomes=tuple(outcomes), records=(),
            )
    return EarningsCalendarCollection(
        report_period=normalized_period,
        total_pages=total_pages,
        status="success",
        publishable=True,
        outcomes=tuple(outcomes),
        records=tuple(record for outcome in outcomes for record in outcome.records),
    )


def collect_eastmoney_earnings_calendar(
    report_period: str,
    *,
    runtime: IngestionRuntime | None = None,
    http_get: HttpGet = default_http_get,
) -> EarningsCalendarCollection:
    return asyncio.run(
        collect_eastmoney_earnings_calendar_async(
            report_period, runtime=runtime, http_get=http_get
        )
    )
