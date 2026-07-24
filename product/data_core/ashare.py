from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from .contracts import RawCapture, RecordDomain, RecordEnvelope, SourceManifest, digest
from .ingestion import (
    AdapterRegistry,
    AuthoritySink,
    FetchedPayload,
    FetchCache,
    FetchRequest,
    IngestionOutcome,
    IngestionRuntime,
    QualityPolicy,
    SourceChoice,
)


HttpGet = Callable[[str, str], bytes]

TENCENT_QUOTE_SOURCE = "tencent_quote_single_v1"
TENCENT_KLINE_SOURCE = "tencent_qfq_daily_single_v1"
EASTMONEY_FUNDAMENTAL_SOURCE = "eastmoney_f10_main_single_v1"
EASTMONEY_BALANCE_SOURCE = "eastmoney_f10_balance_single_v1"
EASTMONEY_INCOME_SOURCE = "eastmoney_f10_income_single_v1"
EASTMONEY_CASHFLOW_SOURCE = "eastmoney_f10_cashflow_single_v1"


class AShareTickerError(ValueError):
    """Ticker cannot be mapped to exactly one mainland equity instrument."""


@dataclass(frozen=True)
class AShareInstrument:
    ticker: str
    instrument_id: str
    exchange: str
    board: str
    provider_symbol: str
    secucode: str


@dataclass(frozen=True)
class AShareDataGap:
    domain: str
    source_key: str | None
    reason: str
    publishable: bool


@dataclass(frozen=True)
class AShareDataPacket:
    instrument: AShareInstrument
    identity: dict[str, Any] | None
    quote: dict[str, Any] | None
    daily_bars: tuple[dict[str, Any], ...]
    fundamentals: tuple[dict[str, Any], ...]
    outcomes: Mapping[str, IngestionOutcome]
    data_gaps: tuple[AShareDataGap, ...]

    @property
    def publishable(self) -> bool:
        required = (
            "quote",
            "daily_bars",
            "fundamentals",
            "balance_sheet",
            "income_statement",
            "cash_flow",
        )
        return (
            not self.data_gaps
            and not _packet_requirement_gaps(
                identity=self.identity,
                quote=self.quote,
                daily_bars=self.daily_bars,
                fundamentals=self.fundamentals,
            )
            and all(self.outcomes.get(key) and self.outcomes[key].publishable for key in required)
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument.__dict__,
            "identity": self.identity,
            "quote": self.quote,
            "daily_bars": list(self.daily_bars),
            "fundamentals": list(self.fundamentals),
            "publishable": self.publishable,
            "data_gaps": [gap.__dict__ for gap in self.data_gaps],
            "sources": {
                key: {
                    "status": outcome.status,
                    "selected_source": outcome.selected_source,
                    "data_kind": outcome.data_kind,
                    "publishable": outcome.publishable,
                    "accepted_records": len(outcome.records),
                    "manifest_hash": (
                        outcome.attempts[-1].manifest.manifest_hash
                        if outcome.attempts else None
                    ),
                    "capture_id": (
                        outcome.attempts[-1].capture_id if outcome.attempts else None
                    ),
                    "raw_hash": (
                        outcome.attempts[-1].raw.raw_hash
                        if outcome.attempts and outcome.attempts[-1].raw else None
                    ),
                    "source_url": (
                        outcome.attempts[-1].raw.source_url
                        if outcome.attempts and outcome.attempts[-1].raw else None
                    ),
                    "known_at": (
                        outcome.attempts[-1].raw.known_at
                        if outcome.attempts and outcome.attempts[-1].raw else None
                    ),
                }
                for key, outcome in self.outcomes.items()
            },
        }


def normalize_ashare_ticker(value: str) -> AShareInstrument:
    raw = str(value or "").strip().upper()
    compact = raw.replace(" ", "").replace("_", ".").replace("-", ".")
    match = re.fullmatch(r"(?:(SH|SZ|BJ)\.?)?(\d{6})(?:\.(SH|SZ|BJ))?", compact)
    if not match:
        raise AShareTickerError(f"unsupported A-share ticker format: {value!r}")
    prefix, code, suffix = match.groups()
    if prefix and suffix and prefix != suffix:
        raise AShareTickerError(f"conflicting ticker exchanges: {value!r}")
    exchange_suffix = suffix or prefix or _infer_exchange_suffix(code)
    if exchange_suffix is None:
        raise AShareTickerError(f"ambiguous A-share ticker without exchange suffix: {value!r}")
    if not _exchange_matches_code(code, exchange_suffix):
        raise AShareTickerError(f"ticker code does not belong to {exchange_suffix}: {value!r}")
    exchange = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}[exchange_suffix]
    board = _infer_board(code, exchange_suffix)
    provider_prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[exchange_suffix]
    ticker = f"{code}.{exchange_suffix}"
    return AShareInstrument(
        ticker=ticker,
        instrument_id=f"CN:{ticker}",
        exchange=exchange,
        board=board,
        provider_symbol=f"{provider_prefix}{code}",
        secucode=ticker,
    )


def _infer_exchange_suffix(code: str) -> str | None:
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZ"
    if code.startswith(("4", "8", "92")):
        return "BJ"
    return None


def _exchange_matches_code(code: str, suffix: str) -> bool:
    return _infer_exchange_suffix(code) == suffix


def _infer_board(code: str, suffix: str) -> str:
    if suffix == "BJ":
        return "BSE"
    if suffix == "SH" and code.startswith("688"):
        return "STAR"
    if suffix == "SZ" and code.startswith(("300", "301")):
        return "CHINEXT"
    return "MAIN"


def default_http_get(url: str, encoding_hint: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ParkResearchDashboard/0.4"})
    with urlopen(request, timeout=10.0) as response:
        return response.read()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_provider_time(value: str) -> str:
    if not re.fullmatch(r"\d{14}", value or ""):
        raise ValueError("provider quote timestamp is missing")
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(
        tzinfo=timezone(timedelta(hours=8))
    ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _bar_observed_at(trade_date: str, known_at: str) -> str:
    close_time = datetime.fromisoformat(f"{trade_date}T15:00:00+08:00").astimezone(timezone.utc)
    fetch_time = datetime.fromisoformat(known_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    return min(close_time, fetch_time).isoformat().replace("+00:00", "Z")


def _announced_by_known_at(announced_at_date: str, known_at: str) -> bool:
    """Whether an Eastmoney disclosure date was visible at this capture.

    Eastmoney may return scheduled future disclosure rows alongside filed rows.
    They remain in the immutable raw capture but cannot become point-in-time
    facts before their stated notice date.
    """
    return announced_at_date <= known_at[:10]


def _num(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _accepted_record(
    *,
    domain: RecordDomain,
    entity_key: str,
    payload: dict[str, Any],
    manifest: SourceManifest,
    raw: RawCapture,
    quality_flags: tuple[str, ...] = (),
) -> RecordEnvelope:
    return RecordEnvelope.accepted(
        domain=domain,
        entity_key=entity_key,
        payload=payload,
        manifest=manifest,
        raw=raw,
        quality_flags=quality_flags,
    )


def _validate_eastmoney_row_identity(
    row: Mapping[str, Any], instrument: AShareInstrument
) -> None:
    secucode = str(row.get("SECUCODE") or "").strip().upper()
    security_code = str(row.get("SECURITY_CODE") or "").strip()
    if secucode:
        if secucode != instrument.secucode:
            raise ValueError(
                f"Eastmoney row identity mismatch: expected {instrument.secucode}, got {secucode}"
            )
        return
    if security_code:
        if security_code != instrument.ticker[:6]:
            raise ValueError(
                "Eastmoney row identity mismatch: "
                f"expected {instrument.ticker[:6]}, got {security_code}"
            )
        return
    raise ValueError("Eastmoney row is missing security identity")


def _eastmoney_revision_fields(row: Mapping[str, Any]) -> dict[str, str]:
    row_hash = digest(dict(row))
    provider_updated_at = str(
        row.get("UPDATE_DATE") or row.get("NOTICE_DATE") or row.get("REPORT_DATE") or ""
    )[:19]
    return {
        "provider_row_hash": row_hash,
        "revision_id": "eastmoney:" + row_hash[:24],
        "provider_updated_at": provider_updated_at,
    }


class TencentQuoteAdapter:
    def __init__(self, *, http_get: HttpGet = default_http_get) -> None:
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=TENCENT_QUOTE_SOURCE,
            domain_scope=RecordDomain.MARKET.value,
            authority_tier="official",
            provider_version="2026-07-22",
            schema_version="tencent-qt-v1",
            license_status="configured_internal_use",
            source_url="https://qt.gtimg.cn/",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        url = "https://qt.gtimg.cn/q=" + instrument.provider_symbol
        body = await asyncio.to_thread(self.http_get, url, "gbk")
        fetched_at = _utc_now()
        return FetchedPayload(
            body=body,
            source_url=url,
            fetched_at=fetched_at,
            known_at=fetched_at,
            mime_type="text/html",
            data_kind="real",
        )

    def parse(
        self,
        request: FetchRequest,
        fetched: FetchedPayload,
        raw: RawCapture,
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        text = fetched.body.decode("gbk", errors="replace")
        match = re.search(r'v_([a-z]{2}\d{6})="(.*?)";', text)
        if not match:
            raise ValueError("Tencent quote payload did not contain a quote line")
        provider, body = match.groups()
        if provider != instrument.provider_symbol:
            raise ValueError(f"quote payload symbol mismatch: {provider}")
        fields = body.split("~")
        if len(fields) < 35:
            raise ValueError("Tencent quote payload is incomplete")
        observed_at = _parse_provider_time(fields[30])
        identity = {
            "instrument_id": instrument.instrument_id,
            "observed_at": observed_at,
            "metric": "identity_seen",
            "value": 1,
            "unit": "flag",
            "ticker": instrument.ticker,
            "name": fields[1].removeprefix("XD"),
            "exchange": instrument.exchange,
            "board": instrument.board,
            "industry": None,
            "listing_state": "unknown",
        }
        records = [
            _accepted_record(
                domain=RecordDomain.MARKET,
                entity_key=f"{instrument.instrument_id}:identity",
                payload=identity,
                manifest=self.manifest,
                raw=raw,
            )
        ]
        metrics = {
            "last_price": (_num(fields[3]), "CNY/share"),
            "change_pct": (_num(fields[32]), "pct"),
            "high": (_num(fields[33]), "CNY/share"),
            "low": (_num(fields[34]), "CNY/share"),
            "pe_ttm": (_num(fields[39]) if len(fields) > 39 else None, "multiple"),
            "circulating_market_cap": (_num(fields[44]) if len(fields) > 44 else None, "CNY100mn"),
            "market_cap": (_num(fields[45]) if len(fields) > 45 else None, "CNY100mn"),
            "pb": (_num(fields[46]) if len(fields) > 46 else None, "multiple"),
        }
        for metric, (value, unit) in metrics.items():
            if value is None:
                continue
            records.append(
                _accepted_record(
                    domain=RecordDomain.MARKET,
                    entity_key=f"{instrument.instrument_id}:quote:{metric}",
                    payload={
                        "instrument_id": instrument.instrument_id,
                        "observed_at": observed_at,
                        "metric": metric,
                        "value": value,
                        "unit": unit,
                        "ticker": instrument.ticker,
                    },
                    manifest=self.manifest,
                    raw=raw,
                )
            )
        return tuple(records)


class TencentDailyBarAdapter:
    def __init__(self, *, http_get: HttpGet = default_http_get, limit: int = 320) -> None:
        self.http_get = http_get
        self.limit = limit
        self.manifest = SourceManifest(
            source_key=TENCENT_KLINE_SOURCE,
            domain_scope=RecordDomain.MARKET.value,
            authority_tier="official",
            provider_version="2026-07-22",
            schema_version="tencent-fqkline-v1",
            license_status="configured_internal_use",
            source_url="https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        limit = int(request.parameters.get("limit") or self.limit)
        url = (
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param="
            f"{instrument.provider_symbol},day,,,{limit},qfq"
        )
        body = await asyncio.to_thread(self.http_get, url, "utf-8")
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
        payload = json.loads(fetched.body.decode("utf-8"))
        stock = payload.get("data", {}).get(instrument.provider_symbol, {})
        rows = stock.get("qfqday") or stock.get("day") or []
        records: list[RecordEnvelope] = []
        for row in rows:
            if len(row) < 6:
                continue
            trade_date = str(row[0])[:10]
            observed_at = _bar_observed_at(trade_date, fetched.known_at)
            values = {
                "open": (_num(row[1]), "CNY/share"),
                "close": (_num(row[2]), "CNY/share"),
                "high": (_num(row[3]), "CNY/share"),
                "low": (_num(row[4]), "CNY/share"),
                "volume": (_num(row[5]), "lots"),
            }
            for metric, (value, unit) in values.items():
                if value is None:
                    continue
                records.append(
                    _accepted_record(
                        domain=RecordDomain.MARKET,
                        entity_key=f"{instrument.instrument_id}:bar:{trade_date}:{metric}",
                        payload={
                            "instrument_id": instrument.instrument_id,
                            "observed_at": observed_at,
                            "metric": f"daily_{metric}",
                            "value": value,
                            "unit": unit,
                            "trade_date": trade_date,
                            "adjustment": "qfq",
                        },
                        manifest=self.manifest,
                        raw=raw,
                    )
                )
        if not records:
            raise ValueError("Tencent daily bar payload did not contain usable bars")
        return tuple(records)


class EastmoneyFundamentalAdapter:
    def __init__(self, *, http_get: HttpGet = default_http_get) -> None:
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=EASTMONEY_FUNDAMENTAL_SOURCE,
            domain_scope=RecordDomain.FUNDAMENTAL.value,
            authority_tier="official",
            provider_version="2026-07-22",
            schema_version="eastmoney-f10-mainfinance-v1",
            license_status="configured_internal_use",
            source_url="https://datacenter.eastmoney.com/securities/api/data/get",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        params = {
            "type": "RPT_F10_FINANCE_MAINFINADATA",
            "sty": "APP_F10_MAINFINADATA",
            "quoteColumns": "",
            "filter": f'(SECUCODE="{instrument.secucode}")',
            "p": "1",
            "ps": str(int(request.parameters.get("periods") or 12)),
            "sr": "-1",
            "st": "REPORT_DATE",
            "source": "HSF10",
            "client": "PC",
        }
        url = "https://datacenter.eastmoney.com/securities/api/data/get?" + urlencode(params)
        body = await asyncio.to_thread(self.http_get, url, "utf-8")
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
        payload = json.loads(fetched.body.decode("utf-8"))
        rows = payload.get("result", {}).get("data") or []
        records: list[RecordEnvelope] = []
        metric_map = {
            "TOTALOPERATEREVE": ("revenue", "CNY"),
            "PARENTNETPROFIT": ("net_profit_parent", "CNY"),
            "TOTALOPERATEREVETZ": ("revenue_yoy", "pct"),
            "PARENTNETPROFITTZ": ("net_profit_parent_yoy", "pct"),
            "ROEJQ": ("roe", "pct"),
            "XSMLL": ("gross_margin", "pct"),
            "XSJLL": ("net_margin", "pct"),
            "ZCFZL": ("debt_ratio", "pct"),
            "MGJYXJJE": ("operating_cash_per_share", "CNY/share"),
        }
        for row in rows:
            _validate_eastmoney_row_identity(row, instrument)
            report_period = str(row.get("REPORT_DATE") or "")[:10]
            announced_at_date = str(row.get("NOTICE_DATE") or "")[:10]
            if not report_period or not announced_at_date:
                continue
            if not _announced_by_known_at(announced_at_date, fetched.known_at):
                continue
            announced_at = announced_at_date
            report_type = row.get("REPORT_TYPE") or row.get("REPORT_DATE_NAME") or "unknown"
            for provider_key, (metric, unit) in metric_map.items():
                value = _num(row.get(provider_key))
                if value is None:
                    continue
                records.append(
                    _accepted_record(
                        domain=RecordDomain.FUNDAMENTAL,
                        entity_key=f"{instrument.instrument_id}:fundamental:{report_period}:{metric}",
                        payload={
                            "instrument_id": instrument.instrument_id,
                            "report_period": report_period,
                            "announced_at": announced_at,
                            "metric": metric,
                            "value": value,
                            "unit": unit,
                            "ticker": instrument.ticker,
                            "report_type": str(report_type),
                            **_eastmoney_revision_fields(row),
                        },
                        manifest=self.manifest,
                        raw=raw,
                    )
                )
        if not records:
            raise ValueError("Eastmoney fundamental payload did not contain usable rows")
        return tuple(records)


class EastmoneyStatementAdapter:
    """Normalize one Eastmoney point-in-time financial statement feed."""

    REPORTS = {
        "balance_sheet": {
            "source_key": EASTMONEY_BALANCE_SOURCE,
            "report_name": "RPT_DMSK_FN_BALANCE",
            "metrics": {
                "TOTAL_ASSETS": ("total_assets", "CNY"),
                "TOTAL_LIABILITIES": ("total_liabilities", "CNY"),
                "TOTAL_EQUITY": ("total_equity", "CNY"),
                "MONETARYFUNDS": ("monetary_funds", "CNY"),
                "ACCOUNTS_RECE": ("accounts_receivable", "CNY"),
                "INVENTORY": ("inventory", "CNY"),
                "FIXED_ASSET": ("fixed_assets", "CNY"),
            },
        },
        "income_statement": {
            "source_key": EASTMONEY_INCOME_SOURCE,
            "report_name": "RPT_DMSK_FN_INCOME",
            "metrics": {
                "TOTAL_OPERATE_INCOME": ("total_operating_income", "CNY"),
                "TOTAL_OPERATE_COST": ("total_operating_cost", "CNY"),
                "OPERATE_PROFIT": ("operating_profit", "CNY"),
                "TOTAL_PROFIT": ("total_profit", "CNY"),
                "PARENT_NETPROFIT": ("net_profit_parent_statement", "CNY"),
                "DEDUCT_PARENT_NETPROFIT": ("net_profit_parent_deducted", "CNY"),
            },
        },
        "cash_flow": {
            "source_key": EASTMONEY_CASHFLOW_SOURCE,
            "report_name": "RPT_DMSK_FN_CASHFLOW",
            "metrics": {
                "NETCASH_OPERATE": ("net_cash_operating", "CNY"),
                "NETCASH_INVEST": ("net_cash_investing", "CNY"),
                "NETCASH_FINANCE": ("net_cash_financing", "CNY"),
                "CONSTRUCT_LONG_ASSET": ("cash_paid_for_long_term_assets", "CNY"),
            },
        },
    }

    def __init__(self, statement_kind: str, *, http_get: HttpGet = default_http_get) -> None:
        if statement_kind not in self.REPORTS:
            raise ValueError(f"unsupported statement kind: {statement_kind}")
        self.statement_kind = statement_kind
        self.config = self.REPORTS[statement_kind]
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=str(self.config["source_key"]),
            domain_scope=RecordDomain.FUNDAMENTAL.value,
            authority_tier="official",
            provider_version="2026-07-22",
            schema_version=f"eastmoney-{statement_kind}-v1",
            license_status="configured_internal_use",
            source_url="https://datacenter.eastmoney.com/securities/api/data/v1/get",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        params = {
            "reportName": str(self.config["report_name"]),
            "columns": "ALL",
            "filter": f'(SECUCODE="{instrument.secucode}")',
            "pageNumber": "1",
            "pageSize": str(int(request.parameters.get("periods") or 12)),
            "sortTypes": "-1",
            "sortColumns": "REPORT_DATE",
            "source": "HSF10",
            "client": "PC",
        }
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get?" + urlencode(params)
        body = await asyncio.to_thread(self.http_get, url, "utf-8")
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
        payload = json.loads(fetched.body.decode("utf-8"))
        rows = payload.get("result", {}).get("data") or []
        metrics = self.config["metrics"]
        records: list[RecordEnvelope] = []
        for row in rows:
            _validate_eastmoney_row_identity(row, instrument)
            report_period = str(row.get("REPORT_DATE") or "")[:10]
            announced_at_date = str(row.get("NOTICE_DATE") or "")[:10]
            if not report_period or not announced_at_date:
                continue
            if not _announced_by_known_at(announced_at_date, fetched.known_at):
                continue
            announced_at = announced_at_date
            report_type = row.get("REPORT_TYPE") or row.get("DATE_TYPE_CODE") or "unknown"
            for provider_key, (metric, unit) in metrics.items():
                value = _num(row.get(provider_key))
                if value is None:
                    continue
                records.append(
                    _accepted_record(
                        domain=RecordDomain.FUNDAMENTAL,
                        entity_key=(
                            f"{instrument.instrument_id}:{self.statement_kind}:"
                            f"{report_period}:{metric}"
                        ),
                        payload={
                            "instrument_id": instrument.instrument_id,
                            "report_period": report_period,
                            "announced_at": announced_at,
                            "metric": metric,
                            "value": value,
                            "unit": unit,
                            "ticker": instrument.ticker,
                            "report_type": str(report_type),
                            "statement_kind": self.statement_kind,
                            **_eastmoney_revision_fields(row),
                        },
                        manifest=self.manifest,
                        raw=raw,
                    )
                )
        if not records:
            raise ValueError(
                f"Eastmoney {self.statement_kind} payload did not contain usable rows"
            )
        return tuple(records)


class MemoryAuthoritySink:
    def __init__(self) -> None:
        self.attempts = []

    def persist_attempt(self, attempt) -> None:
        self.attempts.append(attempt)


def build_ashare_registry(*, http_get: HttpGet = default_http_get) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(TencentQuoteAdapter(http_get=http_get))
    registry.register(TencentDailyBarAdapter(http_get=http_get))
    registry.register(EastmoneyFundamentalAdapter(http_get=http_get))
    registry.register(EastmoneyStatementAdapter("balance_sheet", http_get=http_get))
    registry.register(EastmoneyStatementAdapter("income_statement", http_get=http_get))
    registry.register(EastmoneyStatementAdapter("cash_flow", http_get=http_get))
    return registry


def build_ashare_runtime(
    *,
    http_get: HttpGet = default_http_get,
    authority_sink: AuthoritySink | None = None,
    cache: FetchCache | None = None,
    quality_policy: QualityPolicy | None = None,
) -> IngestionRuntime:
    return IngestionRuntime(
        build_ashare_registry(http_get=http_get),
        authority_sink or MemoryAuthoritySink(),
        cache=cache,
        quality_policy=quality_policy or QualityPolicy(min_accepted=1),
        timeout_seconds=12.0,
    )


async def collect_ashare_packet_async(
    ticker: str,
    *,
    runtime: IngestionRuntime | None = None,
    http_get: HttpGet = default_http_get,
    bar_limit: int = 320,
    fundamental_periods: int = 12,
) -> AShareDataPacket:
    instrument = normalize_ashare_ticker(ticker)
    runtime = runtime or build_ashare_runtime(http_get=http_get)
    request_id_prefix = (
        re.sub(r"[^A-Z0-9]+", "-", instrument.ticker) + "-" + uuid4().hex[:12]
    )
    requests = {
        "quote": FetchRequest.create(
            request_id=f"ashare-{request_id_prefix}-quote",
            domain=RecordDomain.MARKET,
            entity_key=instrument.ticker,
            parameters={"kind": "quote"},
        ),
        "daily_bars": FetchRequest.create(
            request_id=f"ashare-{request_id_prefix}-daily-bars",
            domain=RecordDomain.MARKET,
            entity_key=instrument.ticker,
            parameters={"kind": "daily_bars", "limit": bar_limit},
        ),
        "fundamentals": FetchRequest.create(
            request_id=f"ashare-{request_id_prefix}-fundamentals",
            domain=RecordDomain.FUNDAMENTAL,
            entity_key=instrument.ticker,
            parameters={"kind": "main_finance", "periods": fundamental_periods},
        ),
        "balance_sheet": FetchRequest.create(
            request_id=f"ashare-{request_id_prefix}-balance-sheet",
            domain=RecordDomain.FUNDAMENTAL,
            entity_key=instrument.ticker,
            parameters={"kind": "balance_sheet", "periods": fundamental_periods},
        ),
        "income_statement": FetchRequest.create(
            request_id=f"ashare-{request_id_prefix}-income-statement",
            domain=RecordDomain.FUNDAMENTAL,
            entity_key=instrument.ticker,
            parameters={"kind": "income_statement", "periods": fundamental_periods},
        ),
        "cash_flow": FetchRequest.create(
            request_id=f"ashare-{request_id_prefix}-cash-flow",
            domain=RecordDomain.FUNDAMENTAL,
            entity_key=instrument.ticker,
            parameters={"kind": "cash_flow", "periods": fundamental_periods},
        ),
    }
    plans = {
        "quote": (SourceChoice(TENCENT_QUOTE_SOURCE, "primary"),),
        "daily_bars": (SourceChoice(TENCENT_KLINE_SOURCE, "primary"),),
        "fundamentals": (SourceChoice(EASTMONEY_FUNDAMENTAL_SOURCE, "primary"),),
        "balance_sheet": (SourceChoice(EASTMONEY_BALANCE_SOURCE, "primary"),),
        "income_statement": (SourceChoice(EASTMONEY_INCOME_SOURCE, "primary"),),
        "cash_flow": (SourceChoice(EASTMONEY_CASHFLOW_SOURCE, "primary"),),
    }
    outcome_values = await asyncio.gather(
        *(runtime.run(request, plans[key]) for key, request in requests.items())
    )
    outcomes = dict(zip(requests, outcome_values))
    identity = _identity_from_records(outcomes["quote"].records)
    quote = _quote_from_records(outcomes["quote"].records)
    daily_bars = _bars_from_records(outcomes["daily_bars"].records)
    fundamentals = _fundamentals_from_records(
        record
        for key in ("fundamentals", "balance_sheet", "income_statement", "cash_flow")
        for record in outcomes[key].records
    )
    provider_gaps = tuple(
        AShareDataGap(
            domain=key,
            source_key=outcome.selected_source,
            reason=_gap_reason(outcome),
            publishable=outcome.publishable,
        )
        for key, outcome in outcomes.items()
        if not outcome.publishable
    )
    requirement_gaps = _packet_requirement_gaps(
        identity=identity,
        quote=quote,
        daily_bars=daily_bars,
        fundamentals=fundamentals,
    )
    return AShareDataPacket(
        instrument=instrument,
        identity=identity,
        quote=quote,
        daily_bars=daily_bars,
        fundamentals=fundamentals,
        outcomes=outcomes,
        data_gaps=provider_gaps + requirement_gaps,
    )


def collect_ashare_packet(
    ticker: str,
    *,
    runtime: IngestionRuntime | None = None,
    http_get: HttpGet = default_http_get,
    bar_limit: int = 320,
    fundamental_periods: int = 12,
) -> AShareDataPacket:
    return asyncio.run(
        collect_ashare_packet_async(
            ticker,
            runtime=runtime,
            http_get=http_get,
            bar_limit=bar_limit,
            fundamental_periods=fundamental_periods,
        )
    )


def _payloads(records: Iterable[RecordEnvelope]) -> list[dict[str, Any]]:
    return [record.payload for record in records]


def _identity_from_records(records: Iterable[RecordEnvelope]) -> dict[str, Any] | None:
    for payload in _payloads(records):
        if payload.get("metric") == "identity_seen":
            return {
                "instrument_id": payload["instrument_id"],
                "ticker": payload.get("ticker"),
                "name": payload.get("name"),
                "exchange": payload.get("exchange"),
                "board": payload.get("board"),
                "industry": payload.get("industry"),
                "listing_state": payload.get("listing_state"),
                "observed_at": payload.get("observed_at"),
            }
    return None


def _quote_from_records(records: Iterable[RecordEnvelope]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    observed_at = None
    for payload in _payloads(records):
        metric = payload.get("metric")
        if not isinstance(metric, str) or metric == "identity_seen":
            continue
        result[metric] = payload.get("value")
        observed_at = payload.get("observed_at") or observed_at
    if not result:
        return None
    result["observed_at"] = observed_at
    return result


def _bars_from_records(records: Iterable[RecordEnvelope]) -> tuple[dict[str, Any], ...]:
    grouped: dict[str, dict[str, Any]] = {}
    for payload in _payloads(records):
        trade_date = payload.get("trade_date")
        metric = str(payload.get("metric") or "")
        if not trade_date or not metric.startswith("daily_"):
            continue
        row = grouped.setdefault(str(trade_date), {"trade_date": str(trade_date), "adjustment": payload.get("adjustment")})
        row[metric.removeprefix("daily_")] = payload.get("value")
    return tuple(grouped[key] for key in sorted(grouped))


def _fundamentals_from_records(records: Iterable[RecordEnvelope]) -> tuple[dict[str, Any], ...]:
    grouped: dict[str, dict[str, Any]] = {}
    for payload in _payloads(records):
        period = payload.get("report_period")
        if not period:
            continue
        row = grouped.setdefault(
            str(period),
            {
                "report_period": str(period),
                "announced_at": payload.get("announced_at"),
                "report_type": payload.get("report_type"),
                "component_revision_ids": [],
            },
        )
        revision_id = payload.get("revision_id")
        if revision_id and revision_id not in row["component_revision_ids"]:
            row["component_revision_ids"].append(revision_id)
        row[str(payload.get("metric"))] = payload.get("value")
    return tuple(grouped[key] for key in sorted(grouped, reverse=True))


def _gap_reason(outcome: IngestionOutcome) -> str:
    if not outcome.attempts:
        return outcome.status
    latest = outcome.attempts[-1]
    if latest.error:
        return latest.error
    if latest.quality.reasons:
        return ",".join(latest.quality.reasons)
    return outcome.status


def _packet_requirement_gaps(
    *,
    identity: dict[str, Any] | None,
    quote: dict[str, Any] | None,
    daily_bars: tuple[dict[str, Any], ...],
    fundamentals: tuple[dict[str, Any], ...],
) -> tuple[AShareDataGap, ...]:
    gaps: list[AShareDataGap] = []
    if not identity or not all(
        identity.get(field) for field in ("instrument_id", "ticker", "name")
    ):
        gaps.append(
            AShareDataGap("identity", None, "missing_required_identity_fields", False)
        )

    quote_fields = ("last_price", "high", "low", "observed_at")
    missing_quote = [field for field in quote_fields if not quote or quote.get(field) is None]
    if missing_quote:
        gaps.append(
            AShareDataGap(
                "quote", None, "missing_quote_fields:" + ",".join(missing_quote), False
            )
        )

    bar_fields = ("trade_date", "open", "close", "high", "low", "volume")
    if len(daily_bars) < 2:
        gaps.append(AShareDataGap("daily_bars", None, "daily_bar_count<2", False))
    elif any(any(row.get(field) is None for field in bar_fields) for row in daily_bars):
        gaps.append(AShareDataGap("daily_bars", None, "incomplete_ohlcv_row", False))

    required_fundamentals = (
        "revenue",
        "net_profit_parent",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "total_operating_income",
        "net_profit_parent_statement",
        "net_cash_operating",
    )
    latest = fundamentals[0] if fundamentals else None
    missing_fundamentals = [
        field for field in required_fundamentals if not latest or latest.get(field) is None
    ]
    if missing_fundamentals:
        gaps.append(
            AShareDataGap(
                "fundamentals",
                None,
                "missing_latest_period_fields:" + ",".join(missing_fundamentals),
                False,
            )
        )
    return tuple(gaps)
