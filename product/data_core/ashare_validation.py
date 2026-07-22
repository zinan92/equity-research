from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlencode
from uuid import uuid4

from .ashare import (
    AShareDataPacket,
    AShareInstrument,
    MemoryAuthoritySink,
    collect_ashare_packet_async,
    default_http_get,
    normalize_ashare_ticker,
)
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


HttpGet = Callable[[str, str], bytes]

EASTMONEY_QUOTE_SOURCE = "eastmoney_quote_crosscheck_v1"
SINA_KLINE_SOURCE = "sina_daily_crosscheck_v1"
CNINFO_CORPORATE_ACTION_SOURCE = "cninfo_corporate_action_documents_v1"


@dataclass(frozen=True)
class AShareSecurityMasterEntry:
    instrument_id: str
    ticker: str
    exchange: str
    board: str
    name: str
    aliases: tuple[str, ...]

    def resolves(self, value: str) -> bool:
        normalized = str(value or "").strip().upper().replace(" ", "")
        return normalized in {alias.upper().replace(" ", "") for alias in self.aliases}


@dataclass(frozen=True)
class AShareSourceConflict:
    check: str
    severity: str
    reason: str
    primary: Any
    secondary: Any


@dataclass(frozen=True)
class AShareValidatedPacket:
    packet: AShareDataPacket
    security_master: AShareSecurityMasterEntry
    secondary_quote: Mapping[str, Any] | None
    secondary_daily_bars: tuple[dict[str, Any], ...]
    corporate_actions: tuple[dict[str, Any], ...]
    validation_outcomes: Mapping[str, IngestionOutcome]
    conflicts: tuple[AShareSourceConflict, ...]

    @property
    def publishable(self) -> bool:
        required = ("secondary_quote", "secondary_daily_bars", "corporate_actions")
        return (
            self.packet.publishable
            and all(
                self.validation_outcomes.get(key)
                and self.validation_outcomes[key].publishable
                for key in required
            )
            and not any(item.severity == "blocking" for item in self.conflicts)
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "packet": self.packet.to_summary(),
            "security_master": self.security_master.__dict__,
            "secondary_quote": dict(self.secondary_quote or {}),
            "secondary_daily_bars": list(self.secondary_daily_bars),
            "corporate_actions": list(self.corporate_actions),
            "conflicts": [item.__dict__ for item in self.conflicts],
            "publishable": self.publishable,
            "validation_sources": {
                key: {
                    "status": outcome.status,
                    "publishable": outcome.publishable,
                    "accepted_records": len(outcome.records),
                    "raw_hash": (
                        outcome.attempts[-1].raw.raw_hash
                        if outcome.attempts and outcome.attempts[-1].raw
                        else None
                    ),
                    "source_url": (
                        outcome.attempts[-1].raw.source_url
                        if outcome.attempts and outcome.attempts[-1].raw
                        else None
                    ),
                }
                for key, outcome in self.validation_outcomes.items()
            },
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _eastmoney_secid(instrument: AShareInstrument) -> str:
    market = "1" if instrument.ticker.endswith(".SH") else "0"
    return f"{market}.{instrument.ticker[:6]}"


def _record(
    *,
    domain: RecordDomain,
    entity_key: str,
    payload: dict[str, Any],
    manifest: SourceManifest,
    raw: RawCapture,
) -> RecordEnvelope:
    return RecordEnvelope.accepted(
        domain=domain,
        entity_key=entity_key,
        payload=payload,
        manifest=manifest,
        raw=raw,
    )


class EastmoneyQuoteCrosscheckAdapter:
    def __init__(self, *, http_get: HttpGet = default_http_get) -> None:
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=EASTMONEY_QUOTE_SOURCE,
            domain_scope=RecordDomain.MARKET.value,
            authority_tier="official",
            provider_version="2026-07-22",
            schema_version="eastmoney-push2-quote-v1",
            license_status="configured_internal_use",
            source_url="https://push2delay.eastmoney.com/api/qt/stock/get",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        params = {
            "secid": _eastmoney_secid(instrument),
            "fields": "f43,f44,f45,f46,f57,f58,f116,f117,f162,f167",
        }
        url = self.manifest.source_url + "?" + urlencode(params)
        body = await asyncio.to_thread(self.http_get, url, "utf-8")
        fetched_at = _utc_now()
        return FetchedPayload(body, url, fetched_at, fetched_at, "application/json")

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        data = json.loads(fetched.body.decode("utf-8")).get("data") or {}
        if str(data.get("f57") or "") != instrument.ticker[:6]:
            raise ValueError("Eastmoney quote identity mismatch")
        observed_at = fetched.known_at
        name = str(data.get("f58") or "").strip()
        metrics = {
            "last_price": (data.get("f43"), 100.0, "CNY/share"),
            "high": (data.get("f44"), 100.0, "CNY/share"),
            "low": (data.get("f45"), 100.0, "CNY/share"),
            "open": (data.get("f46"), 100.0, "CNY/share"),
            "market_cap": (data.get("f116"), 1.0, "CNY"),
            "circulating_market_cap": (data.get("f117"), 1.0, "CNY"),
            "pe_ttm": (data.get("f162"), 100.0, "multiple"),
            "pb": (data.get("f167"), 100.0, "multiple"),
        }
        records: list[RecordEnvelope] = []
        for metric, (raw_value, scale, unit) in metrics.items():
            if raw_value in (None, "", "-"):
                continue
            value = float(raw_value) / scale
            records.append(
                _record(
                    domain=RecordDomain.MARKET,
                    entity_key=f"{instrument.instrument_id}:eastmoney-quote:{metric}",
                    payload={
                        "instrument_id": instrument.instrument_id,
                        "observed_at": observed_at,
                        "metric": metric,
                        "value": value,
                        "unit": unit,
                        "ticker": instrument.ticker,
                        "name": name,
                    },
                    manifest=self.manifest,
                    raw=raw,
                )
            )
        if not records:
            raise ValueError("Eastmoney quote had no usable metrics")
        return tuple(records)


class SinaDailyBarCrosscheckAdapter:
    def __init__(self, *, http_get: HttpGet = default_http_get, limit: int = 320) -> None:
        self.http_get = http_get
        self.limit = limit
        self.manifest = SourceManifest(
            source_key=SINA_KLINE_SOURCE,
            domain_scope=RecordDomain.MARKET.value,
            authority_tier="official",
            provider_version="2026-07-22",
            schema_version="sina-cn-kline-v1",
            license_status="configured_internal_use",
            source_url="https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20park=/CN_MarketDataService.getKLineData",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        params = {
            "symbol": instrument.provider_symbol,
            "scale": "240",
            "ma": "no",
            "datalen": str(int(request.parameters.get("limit") or self.limit)),
        }
        url = self.manifest.source_url + "?" + urlencode(params)
        body = await asyncio.to_thread(self.http_get, url, "utf-8")
        fetched_at = _utc_now()
        return FetchedPayload(body, url, fetched_at, fetched_at, "application/json")

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        text = fetched.body.decode("utf-8")
        match = re.search(r"=\((\[.*\])\);\s*$", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Sina K-line payload was not recognized")
        rows = json.loads(match.group(1))
        records: list[RecordEnvelope] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            trade_date = str(row.get("day") or "")[:10]
            if not trade_date:
                continue
            observed_at = min(
                datetime.fromisoformat(f"{trade_date}T15:00:00+08:00").astimezone(timezone.utc),
                datetime.fromisoformat(fetched.known_at.replace("Z", "+00:00")),
            ).isoformat().replace("+00:00", "Z")
            values = {
                "open": (row.get("open"), "CNY/share"),
                "close": (row.get("close"), "CNY/share"),
                "high": (row.get("high"), "CNY/share"),
                "low": (row.get("low"), "CNY/share"),
                "volume": (row.get("volume"), "shares"),
            }
            for metric, (raw_value, unit) in values.items():
                if raw_value in (None, "", "-"):
                    continue
                records.append(
                    _record(
                        domain=RecordDomain.MARKET,
                        entity_key=(
                            f"{instrument.instrument_id}:sina-bar:{trade_date}:{metric}"
                        ),
                        payload={
                            "instrument_id": instrument.instrument_id,
                            "observed_at": observed_at,
                            "metric": "daily_" + metric,
                            "value": float(raw_value),
                            "unit": unit,
                            "trade_date": trade_date,
                            "adjustment": "qfq",
                        },
                        manifest=self.manifest,
                        raw=raw,
                    )
                )
        if not records:
            raise ValueError("Sina K-line had no usable rows")
        return tuple(records)


class CninfoCorporateActionAdapter:
    def __init__(self, *, http_get: HttpGet = default_http_get) -> None:
        self.http_get = http_get
        self.manifest = SourceManifest(
            source_key=CNINFO_CORPORATE_ACTION_SOURCE,
            domain_scope=RecordDomain.EVENT.value,
            authority_tier="official",
            provider_version="2026-07-22",
            schema_version="cninfo-fulltext-search-v1",
            license_status="public_disclosure_internal_use",
            source_url="https://www.cninfo.com.cn/new/fulltextSearch/full",
        )

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        instrument = normalize_ashare_ticker(request.entity_key)
        params = {
            "searchkey": f"{instrument.ticker[:6]} 权益分派实施公告",
            "sdate": str(request.parameters.get("start_date") or "2020-01-01"),
            "edate": str(request.parameters.get("end_date") or datetime.now().date()),
            "isfulltext": "false",
            "sortName": "time",
            "sortType": "desc",
            "pageNum": "1",
            "pageSize": str(int(request.parameters.get("limit") or 20)),
            "type": "",
        }
        url = self.manifest.source_url + "?" + urlencode(params)
        body = await asyncio.to_thread(self.http_get, url, "utf-8")
        fetched_at = _utc_now()
        return FetchedPayload(body, url, fetched_at, fetched_at, "application/json")

    def parse(
        self, request: FetchRequest, fetched: FetchedPayload, raw: RawCapture
    ) -> Iterable[RecordEnvelope]:
        instrument = normalize_ashare_ticker(request.entity_key)
        announcements = json.loads(fetched.body.decode("utf-8")).get("announcements") or []
        records: list[RecordEnvelope] = []
        for row in announcements:
            if str(row.get("secCode") or "") != instrument.ticker[:6]:
                raise ValueError("CNINFO announcement identity mismatch")
            title = unescape(re.sub(r"<[^>]+>", "", str(row.get("announcementTitle") or "")))
            if "权益分派" not in title or "实施公告" not in title:
                continue
            announcement_id = str(row.get("announcementId") or "").strip()
            adjunct = str(row.get("adjunctUrl") or "").lstrip("/")
            millis = int(row.get("announcementTime") or 0)
            if not announcement_id or not adjunct or millis <= 0:
                continue
            occurred_at = datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
            pdf_url = "https://static.cninfo.com.cn/" + adjunct
            records.append(
                _record(
                    domain=RecordDomain.EVENT,
                    entity_key=f"{instrument.instrument_id}:corporate-action:{announcement_id}",
                    payload={
                        "event_id": "cninfo:" + announcement_id,
                        "instrument_id": instrument.instrument_id,
                        "event_type": "corporate_action_implementation_announcement",
                        "occurred_at": occurred_at,
                        "title": title,
                        "evidence_ids": ["cninfo:" + announcement_id],
                        "document_url": pdf_url,
                        "ticker": instrument.ticker,
                    },
                    manifest=self.manifest,
                    raw=raw,
                )
            )
        if not records:
            raise ValueError("CNINFO returned no usable corporate-action announcements")
        return tuple(records)


def build_validation_runtime(
    *, http_get: HttpGet = default_http_get, authority_sink: AuthoritySink | None = None
) -> IngestionRuntime:
    registry = AdapterRegistry()
    registry.register(EastmoneyQuoteCrosscheckAdapter(http_get=http_get))
    registry.register(SinaDailyBarCrosscheckAdapter(http_get=http_get))
    registry.register(CninfoCorporateActionAdapter(http_get=http_get))
    return IngestionRuntime(
        registry,
        authority_sink or MemoryAuthoritySink(),
        quality_policy=QualityPolicy(min_accepted=1),
        timeout_seconds=15.0,
    )


async def collect_validated_ashare_packet_async(
    ticker: str,
    *,
    http_get: HttpGet = default_http_get,
    bar_limit: int = 320,
    fundamental_periods: int = 12,
) -> AShareValidatedPacket:
    packet = await collect_ashare_packet_async(
        ticker,
        http_get=http_get,
        bar_limit=bar_limit,
        fundamental_periods=fundamental_periods,
    )
    validation = await _collect_validation_outcomes(
        ticker, http_get=http_get, bar_limit=bar_limit
    )
    secondary_quote = _quote_from_records(validation["secondary_quote"].records)
    secondary_bars = _bars_from_records(validation["secondary_daily_bars"].records)
    actions = tuple(record.payload for record in validation["corporate_actions"].records)
    security_master = _security_master(packet, secondary_quote)
    conflicts = _cross_source_conflicts(packet, secondary_quote, secondary_bars, actions)
    return AShareValidatedPacket(
        packet=packet,
        security_master=security_master,
        secondary_quote=secondary_quote,
        secondary_daily_bars=secondary_bars,
        corporate_actions=actions,
        validation_outcomes=validation,
        conflicts=conflicts,
    )


def collect_validated_ashare_packet(
    ticker: str,
    *,
    http_get: HttpGet = default_http_get,
    bar_limit: int = 320,
    fundamental_periods: int = 12,
) -> AShareValidatedPacket:
    return asyncio.run(
        collect_validated_ashare_packet_async(
            ticker,
            http_get=http_get,
            bar_limit=bar_limit,
            fundamental_periods=fundamental_periods,
        )
    )


async def _collect_validation_outcomes(
    ticker: str, *, http_get: HttpGet, bar_limit: int
) -> dict[str, IngestionOutcome]:
    instrument = normalize_ashare_ticker(ticker)
    runtime = build_validation_runtime(http_get=http_get)
    token = uuid4().hex[:12]
    requests = {
        "secondary_quote": FetchRequest.create(
            request_id=f"ashare-validation-{token}-quote",
            domain=RecordDomain.MARKET,
            entity_key=instrument.ticker,
            parameters={"kind": "quote"},
        ),
        "secondary_daily_bars": FetchRequest.create(
            request_id=f"ashare-validation-{token}-bars",
            domain=RecordDomain.MARKET,
            entity_key=instrument.ticker,
            parameters={"kind": "daily_bars", "limit": bar_limit},
        ),
        "corporate_actions": FetchRequest.create(
            request_id=f"ashare-validation-{token}-actions",
            domain=RecordDomain.EVENT,
            entity_key=instrument.ticker,
            parameters={"kind": "corporate_actions", "limit": 20},
        ),
    }
    sources = {
        "secondary_quote": EASTMONEY_QUOTE_SOURCE,
        "secondary_daily_bars": SINA_KLINE_SOURCE,
        "corporate_actions": CNINFO_CORPORATE_ACTION_SOURCE,
    }
    values = []
    for key, request in requests.items():
        values.append(
            await runtime.run(request, (SourceChoice(sources[key], "primary"),))
        )
    return dict(zip(requests, values))


def _quote_from_records(records: Iterable[RecordEnvelope]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for record in records:
        payload = record.payload
        result[str(payload["metric"])] = payload["value"]
        result["observed_at"] = payload["observed_at"]
        result["name"] = payload.get("name")
    return result or None


def _bars_from_records(records: Iterable[RecordEnvelope]) -> tuple[dict[str, Any], ...]:
    rows: dict[str, dict[str, Any]] = {}
    for record in records:
        payload = record.payload
        date = str(payload.get("trade_date") or "")
        metric = str(payload.get("metric") or "").removeprefix("daily_")
        if not date or not metric:
            continue
        row = rows.setdefault(date, {"trade_date": date})
        row[metric] = payload["value"]
    return tuple(rows[key] for key in sorted(rows))


def _security_master(
    packet: AShareDataPacket, secondary_quote: Mapping[str, Any] | None
) -> AShareSecurityMasterEntry:
    name = str((packet.identity or {}).get("name") or "").strip()
    aliases = {
        packet.instrument.ticker,
        packet.instrument.ticker[:6],
        packet.instrument.provider_symbol,
        packet.instrument.instrument_id,
        name,
    }
    if secondary_quote and secondary_quote.get("name"):
        aliases.add(str(secondary_quote["name"]))
    return AShareSecurityMasterEntry(
        instrument_id=packet.instrument.instrument_id,
        ticker=packet.instrument.ticker,
        exchange=packet.instrument.exchange,
        board=packet.instrument.board,
        name=name,
        aliases=tuple(sorted(item for item in aliases if item)),
    )


def _relative_difference(left: float, right: float) -> float:
    denominator = max(abs(left), abs(right), 1e-12)
    return abs(left - right) / denominator


def _cross_source_conflicts(
    packet: AShareDataPacket,
    secondary_quote: Mapping[str, Any] | None,
    secondary_bars: tuple[dict[str, Any], ...],
    actions: tuple[dict[str, Any], ...],
) -> tuple[AShareSourceConflict, ...]:
    conflicts: list[AShareSourceConflict] = []
    primary_name = str((packet.identity or {}).get("name") or "")
    secondary_name = str((secondary_quote or {}).get("name") or "")
    if not secondary_name or primary_name != secondary_name:
        conflicts.append(
            AShareSourceConflict(
                "security_identity", "blocking", "provider names disagree", primary_name, secondary_name
            )
        )

    for metric in ("pe_ttm", "pb"):
        primary_value = (packet.quote or {}).get(metric)
        secondary_value = (secondary_quote or {}).get(metric)
        if primary_value is None or secondary_value is None:
            conflicts.append(
                AShareSourceConflict(
                    "valuation_" + metric,
                    "blocking",
                    "valuation metric missing from one source",
                    primary_value,
                    secondary_value,
                )
            )
        elif _relative_difference(float(primary_value), float(secondary_value)) > 0.10:
            conflicts.append(
                AShareSourceConflict(
                    "valuation_" + metric,
                    "blocking",
                    "valuation sources differ by more than 10%",
                    primary_value,
                    secondary_value,
                )
            )

    primary_by_date = {row["trade_date"]: row for row in packet.daily_bars}
    secondary_by_date = {row["trade_date"]: row for row in secondary_bars}
    primary_dates = sorted(primary_by_date)[-2:]
    secondary_dates = sorted(secondary_by_date)[-2:]
    if len(primary_dates) < 2 or primary_dates != secondary_dates:
        conflicts.append(
            AShareSourceConflict(
                "trading_calendar",
                "blocking",
                "latest two provider trading dates disagree",
                primary_dates,
                secondary_dates,
            )
        )
    for trade_date in sorted(set(primary_dates).intersection(secondary_dates)):
        primary_close = float(primary_by_date[trade_date]["close"])
        secondary_close = float(secondary_by_date[trade_date]["close"])
        if _relative_difference(primary_close, secondary_close) > 0.005:
            conflicts.append(
                AShareSourceConflict(
                    "daily_close:" + trade_date,
                    "blocking",
                    "adjusted closes differ by more than 0.5%",
                    primary_close,
                    secondary_close,
                )
            )
    if not actions:
        conflicts.append(
            AShareSourceConflict(
                "corporate_actions",
                "blocking",
                "no official implementation announcement anchors qfq history",
                "qfq",
                0,
            )
        )
    return tuple(conflicts)
