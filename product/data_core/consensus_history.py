"""Broker estimate normalization, robust consensus snapshots, and revisions."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

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
from .official_filings import HttpTransport


CONSENSUS_SCHEMA_VERSION = "park-consensus-v1"
THS_FORECAST_SOURCE = "ths_broker_forecast_v1"
THS_FORECAST_URL = "https://basic.10jqka.com.cn/{code}/worth.html"
METRICS = ("eps", "revenue", "net_profit", "target_price")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _date(value: str) -> str:
    text = str(value).strip()[:10]
    parsed = datetime.fromisoformat(text)
    return parsed.date().isoformat()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _scaled_number(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    multiplier = 1.0
    if text.endswith("万亿"):
        text, multiplier = text[:-2], 1e12
    elif text.endswith("亿"):
        text, multiplier = text[:-1], 1e8
    elif text.endswith("万"):
        text, multiplier = text[:-1], 1e4
    elif text.endswith("%"):
        text, multiplier = text[:-1], 0.01
    value_number = _number(text)
    return value_number * multiplier if value_number is not None else None


def _flatten_column(value: Any) -> str:
    if isinstance(value, tuple):
        return "".join(str(item) for item in value if not str(item).startswith("Unnamed"))
    return str(value)


def _broker_key(value: str) -> str:
    return re.sub(r"股份有限公司|有限责任公司|证券|\s+", "", str(value))


def _ths_manifest() -> SourceManifest:
    return SourceManifest(
        source_key=THS_FORECAST_SOURCE,
        domain_scope=RecordDomain.EVENT.value,
        authority_tier="supplementary_only",
        provider_version="2026-07-22",
        schema_version="ths-broker-forecast-v1",
        license_status="public_page_internal_research_use",
        source_url="https://basic.10jqka.com.cn/",
    )


class ThsForecastAdapter:
    """THS per-broker EPS/profit rows plus provider consensus metric references."""

    def __init__(self, *, transport: HttpTransport) -> None:
        self.transport = transport
        self.manifest = _ths_manifest()

    async def fetch(self, request: FetchRequest) -> FetchedPayload:
        import asyncio

        instrument = normalize_ashare_ticker(request.entity_key)
        url = THS_FORECAST_URL.format(code=instrument.ticker[:6])
        response = await asyncio.to_thread(
            self.transport,
            url,
            {
                "Accept": "text/html",
                "Referer": "https://basic.10jqka.com.cn/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
            },
        )
        if urlsplit(response.final_url).hostname != "basic.10jqka.com.cn":
            raise ValueError("THS forecast redirect left approved host")
        fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return FetchedPayload(
            response.body,
            response.final_url,
            fetched_at,
            fetched_at,
            "text/html",
            status_code=response.status_code,
            response_headers=response.headers,
            redirect_chain=response.redirect_chain or (response.final_url,),
        )

    def parse(
        self,
        request: FetchRequest,
        fetched: FetchedPayload,
        raw: RawCapture,
    ) -> Iterable[RecordEnvelope]:
        import pandas as pd

        instrument = normalize_ashare_ticker(request.entity_key)
        as_of = _date(str(request.parameters.get("as_of") or fetched.known_at[:10]))
        html = fetched.body.decode("gb18030", errors="replace")
        tables = pd.read_html(io.StringIO(html))
        records = []
        for table_index, table in enumerate(tables):
            table = table.copy()
            table.columns = [_flatten_column(column) for column in table.columns]
            columns = list(table.columns)
            broker_column = next((column for column in columns if "机构名称" in column), None)
            date_column = next((column for column in columns if "报告日期" in column), None)
            if broker_column and date_column:
                analyst_column = next((column for column in columns if "研究员" in column), None)
                for row_index, row in table.iterrows():
                    broker_value = row.get(broker_column)
                    date_value = row.get(date_column)
                    if pd.isna(broker_value) or pd.isna(date_value):
                        continue
                    broker = " ".join(str(broker_value).split())
                    try:
                        report_date = _date(str(date_value))
                    except (TypeError, ValueError):
                        continue
                    if not broker or report_date > as_of:
                        continue
                    analyst_value = row.get(analyst_column) if analyst_column else None
                    analyst = (
                        " ".join(str(analyst_value).split())
                        if analyst_value is not None and not pd.isna(analyst_value)
                        else None
                    )
                    years = sorted(
                        {
                            int(match.group(1))
                            for column in columns
                            for match in [re.search(r"(20\d{2})", column)]
                            if match and "预测" in column
                        }
                    )
                    for year in years:
                        eps_column = next(
                            (column for column in columns if str(year) in column and "每股收益" in column),
                            None,
                        )
                        profit_column = next(
                            (column for column in columns if str(year) in column and "净利润" in column),
                            None,
                        )
                        eps = _scaled_number(row.get(eps_column)) if eps_column else None
                        net_profit = _scaled_number(row.get(profit_column)) if profit_column else None
                        if eps is None and net_profit is None:
                            continue
                        event_id = f"ths-broker:{raw.raw_hash}:{table_index}:{row_index}:{year}"
                        payload = {
                            "event_id": event_id,
                            "instrument_id": instrument.instrument_id,
                            "event_type": "broker_estimate_observed",
                            "occurred_at": report_date + "T00:00:00Z",
                            "title": f"{broker} {year} forecast",
                            "evidence_ids": [event_id],
                            "record_kind": "broker_estimate",
                            "ticker": instrument.ticker,
                            "broker": broker,
                            "analyst": analyst,
                            "report_date": report_date,
                            "fiscal_year": year,
                            "eps": eps,
                            "net_profit": net_profit,
                        }
                        records.append(
                            RecordEnvelope.accepted(
                                domain=RecordDomain.EVENT,
                                entity_key=f"{instrument.instrument_id}:{event_id}",
                                payload=payload,
                                manifest=self.manifest,
                                raw=raw,
                            )
                        )
                continue
            metric_column = next((column for column in columns if "预测指标" in column), None)
            if not metric_column:
                continue
            for row_index, row in table.iterrows():
                label = str(row.get(metric_column) or "")
                metric = "revenue" if "营业收入" in label and "增长" not in label else None
                if "净利润" in label and "增长" not in label:
                    metric = "net_profit"
                if not metric:
                    continue
                for column in columns:
                    match = re.search(r"预测(20\d{2}).*平均", column)
                    if not match:
                        continue
                    value = _scaled_number(row.get(column))
                    if value is None:
                        continue
                    year = int(match.group(1))
                    event_id = f"ths-consensus:{raw.raw_hash}:{metric}:{year}"
                    payload = {
                        "event_id": event_id,
                        "instrument_id": instrument.instrument_id,
                        "event_type": "provider_consensus_observed",
                        "occurred_at": as_of + "T00:00:00Z",
                        "title": f"THS {year} {metric} consensus",
                        "evidence_ids": [event_id],
                        "record_kind": "provider_consensus",
                        "ticker": instrument.ticker,
                        "metric": metric,
                        "fiscal_year": year,
                        "mean": value,
                        "as_of": as_of,
                    }
                    records.append(
                        RecordEnvelope.accepted(
                            domain=RecordDomain.EVENT,
                            entity_key=f"{instrument.instrument_id}:{event_id}",
                            payload=payload,
                            manifest=self.manifest,
                            raw=raw,
                        )
                    )
        return tuple(records)


def build_ths_forecast_runtime(
    *,
    transport: HttpTransport,
    authority_sink: AuthoritySink | None = None,
) -> IngestionRuntime:
    registry = AdapterRegistry()
    registry.register(ThsForecastAdapter(transport=transport))
    return IngestionRuntime(
        registry,
        authority_sink or MemoryAuthoritySink(),
        quality_policy=QualityPolicy(min_accepted=1),
        timeout_seconds=30.0,
    )


@dataclass(frozen=True)
class ProviderConsensusReference:
    metric: str
    fiscal_year: int
    mean: float
    as_of: str
    raw_hash: str
    source_key: str


def ths_consensus_references(
    outcome: IngestionOutcome,
) -> tuple[ProviderConsensusReference, ...]:
    if not outcome.publishable or not outcome.attempts or outcome.attempts[-1].raw is None:
        return ()
    raw_hash = outcome.attempts[-1].raw.raw_hash
    return tuple(
        ProviderConsensusReference(
            metric=str(record.payload["metric"]),
            fiscal_year=int(record.payload["fiscal_year"]),
            mean=float(record.payload["mean"]),
            as_of=str(record.payload["as_of"]),
            raw_hash=raw_hash,
            source_key=record.provenance.source_key,
        )
        for record in outcome.records
        if record.payload.get("record_kind") == "provider_consensus"
    )


@dataclass(frozen=True)
class BrokerEstimate:
    estimate_id: str
    ticker: str
    broker: str
    analyst: str | None
    report_id: str
    report_date: str
    raw_hash: str
    fiscal_year: int
    eps: float | None = None
    revenue: float | None = None
    net_profit: float | None = None
    target_price: float | None = None
    rating: str | None = None
    source_key: str = "eastmoney_sell_side_catalog_v1"
    supporting_raw_hashes: tuple[str, ...] = ()

    def validate(self) -> None:
        for name in ("estimate_id", "ticker", "broker", "report_id", "raw_hash", "source_key"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if len(self.raw_hash) != 64 or any(character not in "0123456789abcdef" for character in self.raw_hash):
            raise ValueError("raw_hash must be a lowercase SHA-256")
        if any(
            len(raw_hash) != 64
            or any(character not in "0123456789abcdef" for character in raw_hash)
            for raw_hash in self.supporting_raw_hashes
        ):
            raise ValueError("supporting_raw_hashes must contain lowercase SHA-256 values")
        if self.fiscal_year < 1990 or self.fiscal_year > 2200:
            raise ValueError("fiscal_year is invalid")
        if _date(self.report_date) != self.report_date:
            raise ValueError("report_date must be ISO YYYY-MM-DD")
        if all(getattr(self, metric) is None for metric in METRICS):
            raise ValueError("estimate must contain at least one normalized metric")
        for metric in METRICS:
            value = getattr(self, metric)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{metric} must be finite")

    def canonical(self) -> dict[str, Any]:
        return self.__dict__


def normalize_broker_estimate(
    *,
    ticker: str,
    broker: str,
    analyst: str | None,
    report_id: str,
    report_date: str,
    raw_hash: str,
    fiscal_year: int,
    eps: Any = None,
    revenue: Any = None,
    net_profit: Any = None,
    target_price: Any = None,
    rating: str | None = None,
    source_key: str = "eastmoney_sell_side_catalog_v1",
    supporting_raw_hashes: Iterable[str] = (),
) -> BrokerEstimate:
    values = {
        "ticker": ticker.upper(),
        "broker": " ".join(str(broker).split()),
        "analyst": " ".join(str(analyst).split()) if analyst else None,
        "report_id": str(report_id).strip(),
        "report_date": _date(report_date),
        "raw_hash": raw_hash,
        "fiscal_year": int(fiscal_year),
        "eps": _number(eps),
        "revenue": _number(revenue),
        "net_profit": _number(net_profit),
        "target_price": _number(target_price),
        "rating": " ".join(str(rating).split()) if rating else None,
        "source_key": source_key,
        "supporting_raw_hashes": tuple(sorted(set(supporting_raw_hashes))),
    }
    estimate = BrokerEstimate(
        estimate_id="estimate_" + _digest(values)[:40],
        **values,
    )
    estimate.validate()
    return estimate


def estimates_from_catalog_outcomes(
    outcomes: Iterable[IngestionOutcome],
) -> tuple[BrokerEstimate, ...]:
    """Convert B2 catalog records into report-bound, forecast-year estimates."""

    estimates = []
    for outcome in outcomes:
        if not outcome.publishable or not outcome.attempts:
            continue
        attempt = outcome.attempts[-1]
        if attempt.raw is None:
            continue
        for record in outcome.records:
            payload = record.payload
            low = _number(payload.get("target_price_low"))
            high = _number(payload.get("target_price_high"))
            target = statistics.mean([value for value in (low, high) if value is not None]) if low is not None or high is not None else None
            forecast_years = list(payload.get("forecast_years") or [])
            for index, forecast in enumerate(forecast_years):
                estimate = normalize_broker_estimate(
                    ticker=str(payload["ticker"]),
                    broker=str(payload.get("broker") or "unknown"),
                    analyst=payload.get("analyst"),
                    report_id=str(payload["report_id"]),
                    report_date=str(payload["published_at"])[:10],
                    raw_hash=attempt.raw.raw_hash,
                    fiscal_year=int(forecast["fiscal_year"]),
                    eps=forecast.get("eps"),
                    target_price=target if index == 0 else None,
                    rating=payload.get("rating"),
                    source_key=record.provenance.source_key,
                )
                estimates.append(estimate)
    return tuple(estimates)


def reconcile_ths_broker_estimates(
    estimates: Iterable[BrokerEstimate],
    ths_outcome: IngestionOutcome,
) -> tuple[BrokerEstimate, ...]:
    """Attach THS net-profit fields only when broker/date/year resolves to a report."""

    base = tuple(estimates)
    ths_rows = [
        record.payload for record in ths_outcome.records
        if record.payload.get("record_kind") == "broker_estimate"
    ] if ths_outcome.publishable else []
    ths_raw_hash = (
        ths_outcome.attempts[-1].raw.raw_hash
        if ths_outcome.publishable
        and ths_outcome.attempts
        and ths_outcome.attempts[-1].raw is not None
        else None
    )
    reconciled = []
    for estimate in base:
        matches = [
            row for row in ths_rows
            if _broker_key(str(row.get("broker") or "")) == _broker_key(estimate.broker)
            and str(row.get("report_date")) == estimate.report_date
            and int(row.get("fiscal_year")) == estimate.fiscal_year
        ]
        if len(matches) != 1:
            reconciled.append(estimate)
            continue
        row = matches[0]
        reconciled.append(
            normalize_broker_estimate(
                ticker=estimate.ticker,
                broker=estimate.broker,
                analyst=estimate.analyst,
                report_id=estimate.report_id,
                report_date=estimate.report_date,
                raw_hash=estimate.raw_hash,
                fiscal_year=estimate.fiscal_year,
                eps=estimate.eps if estimate.eps is not None else row.get("eps"),
                revenue=estimate.revenue,
                net_profit=row.get("net_profit"),
                target_price=estimate.target_price,
                rating=estimate.rating,
                source_key=estimate.source_key + "+" + THS_FORECAST_SOURCE,
                supporting_raw_hashes=(
                    *estimate.supporting_raw_hashes,
                    *([ths_raw_hash] if ths_raw_hash else []),
                ),
            )
        )
    return tuple(reconciled)


@dataclass(frozen=True)
class EstimateQuarantine:
    estimate_id: str
    metric: str
    fiscal_year: int
    value: float
    reason: str


@dataclass(frozen=True)
class ConsensusPoint:
    metric: str
    fiscal_year: int
    mean: float
    median: float
    minimum: float
    maximum: float
    contributor_count: int
    excluded_count: int
    estimate_ids: tuple[str, ...]


@dataclass(frozen=True)
class ConsensusSnapshot:
    snapshot_id: str
    ticker: str
    as_of: str
    schema_version: str
    input_digest: str
    estimates: tuple[BrokerEstimate, ...]
    points: tuple[ConsensusPoint, ...]
    quarantine: tuple[EstimateQuarantine, ...]

    def point(self, metric: str, fiscal_year: int) -> ConsensusPoint | None:
        return next(
            (point for point in self.points if point.metric == metric and point.fiscal_year == fiscal_year),
            None,
        )

    def replay_valid(self) -> bool:
        rebuilt = build_consensus_snapshot(self.ticker, self.estimates, as_of=self.as_of)
        return rebuilt.snapshot_id == self.snapshot_id and rebuilt.input_digest == self.input_digest


def _outlier_ids(rows: Sequence[tuple[BrokerEstimate, float]]) -> set[str]:
    if len(rows) < 4:
        return set()
    values = [value for _, value in rows]
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)
    if mad > 0:
        return {
            estimate.estimate_id
            for estimate, value in rows
            if 0.6745 * abs(value - median) / mad > 3.5
        }
    denominator = max(abs(median), 1e-9)
    return {
        estimate.estimate_id
        for estimate, value in rows
        if abs(value - median) / denominator > 0.50
    }


def build_consensus_snapshot(
    ticker: str,
    estimates: Iterable[BrokerEstimate],
    *,
    as_of: str,
) -> ConsensusSnapshot:
    cutoff = _date(as_of)
    selected = tuple(
        sorted(
            (
                estimate for estimate in estimates
                if estimate.ticker.upper() == ticker.upper() and estimate.report_date <= cutoff
            ),
            key=lambda item: (item.report_date, item.report_id, item.fiscal_year, item.estimate_id),
        )
    )
    for estimate in selected:
        estimate.validate()
    latest_by_broker_year: dict[tuple[str, int], BrokerEstimate] = {}
    for estimate in selected:
        latest_by_broker_year[(estimate.broker, estimate.fiscal_year)] = estimate
    active = tuple(latest_by_broker_year.values())
    active_ids = {estimate.estimate_id for estimate in active}
    grouped: dict[tuple[str, int], list[tuple[BrokerEstimate, float]]] = {}
    superseded_counts: dict[tuple[str, int], int] = {}
    quarantined = []
    for estimate in selected:
        for metric in METRICS:
            value = getattr(estimate, metric)
            if value is None:
                continue
            if estimate.estimate_id in active_ids:
                grouped.setdefault((metric, estimate.fiscal_year), []).append((estimate, value))
            else:
                superseded_counts[(metric, estimate.fiscal_year)] = (
                    superseded_counts.get((metric, estimate.fiscal_year), 0) + 1
                )
                quarantined.append(
                    EstimateQuarantine(
                        estimate.estimate_id,
                        metric,
                        estimate.fiscal_year,
                        value,
                        "superseded by the broker's later report before aggregate",
                    )
                )
    points = []
    for (metric, fiscal_year), rows in sorted(grouped.items()):
        outlier_ids = _outlier_ids(rows)
        included = [(estimate, value) for estimate, value in rows if estimate.estimate_id not in outlier_ids]
        for estimate, value in rows:
            if estimate.estimate_id in outlier_ids:
                quarantined.append(
                    EstimateQuarantine(
                        estimate.estimate_id,
                        metric,
                        fiscal_year,
                        value,
                        "robust outlier excluded before aggregate",
                    )
                )
        if not included:
            continue
        values = [value for _, value in included]
        points.append(
            ConsensusPoint(
                metric=metric,
                fiscal_year=fiscal_year,
                mean=statistics.fmean(values),
                median=statistics.median(values),
                minimum=min(values),
                maximum=max(values),
                contributor_count=len(values),
                excluded_count=(
                    len(rows) - len(values) + superseded_counts.get((metric, fiscal_year), 0)
                ),
                estimate_ids=tuple(sorted(estimate.estimate_id for estimate, _ in included)),
            )
        )
    input_payload = [estimate.canonical() for estimate in selected]
    input_digest = _digest(input_payload)
    snapshot_identity = {
        "ticker": ticker.upper(),
        "as_of": cutoff,
        "schema_version": CONSENSUS_SCHEMA_VERSION,
        "input_digest": input_digest,
        "points": [point.__dict__ for point in points],
        "quarantine": [item.__dict__ for item in quarantined],
    }
    return ConsensusSnapshot(
        snapshot_id="consensus_" + _digest(snapshot_identity)[:40],
        ticker=ticker.upper(),
        as_of=cutoff,
        schema_version=CONSENSUS_SCHEMA_VERSION,
        input_digest=input_digest,
        estimates=selected,
        points=tuple(points),
        quarantine=tuple(quarantined),
    )


@dataclass(frozen=True)
class ConsensusRevision:
    metric: str
    fiscal_year: int
    previous_mean: float | None
    current_mean: float | None
    absolute_change: float | None
    percent_change: float | None
    previous_contributors: int
    current_contributors: int


def compare_consensus_snapshots(
    previous: ConsensusSnapshot,
    current: ConsensusSnapshot,
) -> tuple[ConsensusRevision, ...]:
    if previous.ticker != current.ticker or previous.as_of > current.as_of:
        raise ValueError("consensus snapshots are not comparable")
    keys = sorted(
        {(point.metric, point.fiscal_year) for point in previous.points}
        | {(point.metric, point.fiscal_year) for point in current.points}
    )
    revisions = []
    for metric, fiscal_year in keys:
        old = previous.point(metric, fiscal_year)
        new = current.point(metric, fiscal_year)
        absolute = new.mean - old.mean if old and new else None
        percent = absolute / abs(old.mean) * 100 if absolute is not None and old.mean else None
        revisions.append(
            ConsensusRevision(
                metric,
                fiscal_year,
                old.mean if old else None,
                new.mean if new else None,
                absolute,
                percent,
                old.contributor_count if old else 0,
                new.contributor_count if new else 0,
            )
        )
    return tuple(revisions)
