"""Explicit company/universe identity crosswalks for canonical research.

The input archive is an audit-only snapshot.  This module never treats a name
match as an identity match: code + market produces a candidate, and conflicts
remain ``ambiguous`` or ``unmapped`` for a human/canonical-source resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Any, Iterable, Mapping


VALID_STATUSES = {"matched", "ambiguous", "unmapped"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _alias(value: Any) -> str:
    return re.sub(r"\s+", "", _text(value)).upper()


def _market_key(value: Any) -> str:
    raw = _text(value).upper()
    if raw in {"A", "A股", "SSE", "SZSE", "BSE"}:
        return "CN"
    if raw in {"HK", "港股"}:
        return "HK"
    if raw in {"US", "美股", "NASDAQ", "NYSE"}:
        return "US"
    if raw in {"JP", "日本", "TSE"}:
        return "JP"
    return raw


def _infer_market(code: str, declared_market: Any) -> str:
    market = _market_key(declared_market)
    if market:
        return market
    return "CN" if re.fullmatch(r"\d{6}", _text(code)) else ""


def _canonical_ticker(code: str, market: str) -> str | None:
    raw = _text(code).upper()
    if not raw:
        return None
    if market == "CN":
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 6:
            return None
        if digits.startswith(("6", "68")):
            return f"{digits}.SH"
        if digits.startswith(("0", "3")):
            return f"{digits}.SZ"
        if digits.startswith(("4", "8", "92")):
            return f"{digits}.BJ"
        return None
    if market == "HK":
        digits = re.sub(r"\D", "", raw)
        return f"{digits.zfill(5)}.HK" if digits else None
    if market == "JP":
        digits = re.sub(r"\D", "", raw)
        return f"{digits}.T" if len(digits) == 4 else None
    if market == "US":
        return raw if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", raw) else None
    return None


def _company_id(ticker: str) -> str:
    return "company-v1:" + sha256(ticker.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class CrosswalkRecord:
    source_universe: str
    source_code: str
    source_name: str
    source_market: str
    status: str
    ticker: str | None
    company_id: str | None
    reason: str | None
    source_ref: str
    known_at: str
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class CrosswalkResolution:
    query: str
    status: str
    candidates: tuple[CrosswalkRecord, ...]
    data_kind: str


class UniverseCrosswalk:
    """Read-only resolver that fails closed on alias collisions."""

    def __init__(self, records: Iterable[CrosswalkRecord], *, data_kind: str = "fixture") -> None:
        materialized = tuple(records)
        if not materialized:
            raise ValueError("crosswalk records are required")
        self.records = materialized
        if data_kind not in {"fixture", "cached", "real", "runtime_only_audit"}:
            raise ValueError("invalid crosswalk data kind")
        self.data_kind = data_kind
        self._by_ticker: dict[str, list[CrosswalkRecord]] = {}
        self._by_alias: dict[str, list[CrosswalkRecord]] = {}
        for record in materialized:
            if record.ticker:
                self._by_ticker.setdefault(_alias(record.ticker), []).append(record)
            for value in (record.source_code, record.source_name, *record.aliases):
                key = _alias(value)
                if key:
                    self._by_alias.setdefault(key, []).append(record)

    def resolve(self, query: str) -> CrosswalkResolution:
        key = _alias(query)
        candidates = tuple(self._by_ticker.get(key, self._by_alias.get(key, ())))
        matched = tuple(item for item in candidates if item.status == "matched")
        unique_companies = {item.company_id for item in matched if item.company_id}
        if len(unique_companies) == 1:
            return CrosswalkResolution(query=query, status="matched", candidates=matched, data_kind=self.data_kind)
        if candidates:
            return CrosswalkResolution(query=query, status="ambiguous", candidates=candidates, data_kind=self.data_kind)
        return CrosswalkResolution(query=query, status="unmapped", candidates=(), data_kind=self.data_kind)


def build_crosswalk(
    main_records: Iterable[Mapping[str, Any]],
    levels_records: Iterable[Mapping[str, Any]],
    *,
    source_ref: str = "fixture",
    known_at: str = "fixture",
) -> tuple[CrosswalkRecord, ...]:
    """Build rows from audit-only universe records without name-based joins."""
    grouped: dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]] = {}
    for universe, records in (("main", main_records), ("levels", levels_records)):
        for row in records:
            code = _text(row.get("code"))
            market = _infer_market(code, row.get("market"))
            grouped.setdefault((code, market), []).append((universe, row))

    output: list[CrosswalkRecord] = []
    for (code, market), entries in sorted(grouped.items()):
        ticker = _canonical_ticker(code, market)
        names = {_alias(row.get("name")) for _, row in entries if _alias(row.get("name"))}
        if ticker is None:
            status, company, reason = "unmapped", None, "unsupported_or_missing_code_market"
        elif len(names) > 1:
            status, company, reason = "ambiguous", None, "conflicting_names_for_code_market"
        else:
            status, company, reason = "matched", _company_id(ticker), None
        for universe, row in entries:
            output.append(CrosswalkRecord(
                source_universe=universe,
                source_code=code,
                source_name=_text(row.get("name")),
                source_market=market,
                status=status,
                ticker=ticker,
                company_id=company,
                reason=reason,
                source_ref=source_ref,
                known_at=known_at,
            ))
    return tuple(output)


def apply_code_migrations(
    records: Iterable[CrosswalkRecord], migrations: Iterable[Mapping[str, Any]],
) -> tuple[CrosswalkRecord, ...]:
    """Promote CNINFO's current code while retaining its historical code as an alias.

    Migration facts must already be backed by the official top-search raw hash.
    This updates the existing E1-S1 crosswalk representation; it is not a
    second identity table.
    """
    by_old = {
        _text(item.get("old_code")): item
        for item in migrations
        if _text(item.get("old_code")) and _text(item.get("current_code"))
    }
    output: list[CrosswalkRecord] = []
    for record in records:
        migration = by_old.get(record.source_code)
        if not migration or record.source_market != "CN":
            output.append(record)
            continue
        current_code = _text(migration["current_code"])
        ticker = _canonical_ticker(current_code, "CN")
        if ticker is None:
            raise ValueError("code migration current_code is not a supported mainland ticker")
        aliases = tuple(sorted({_alias(record.source_code), _alias(record.ticker), *(_alias(item) for item in record.aliases)} - {""}))
        output.append(CrosswalkRecord(
            source_universe=record.source_universe,
            source_code=current_code,
            source_name=record.source_name,
            source_market=record.source_market,
            status="matched",
            ticker=ticker,
            company_id=_company_id(ticker),
            reason=None,
            source_ref=record.source_ref,
            known_at=record.known_at,
            aliases=aliases,
        ))
    return tuple(output)
