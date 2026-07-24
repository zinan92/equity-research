"""Point-in-time resolver layered on A4 ticker normalization, never a second master."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .ashare import AShareTickerError, normalize_ashare_ticker


@dataclass(frozen=True)
class SecurityAlias:
    ticker: str
    value: str
    valid_from: str
    valid_to: str | None = None


@dataclass(frozen=True)
class SecurityStatus:
    ticker: str
    as_of: str
    status: str


class AShareResolver:
    def __init__(self, aliases: Iterable[SecurityAlias], statuses: Iterable[SecurityStatus]) -> None:
        self.aliases = tuple(aliases)
        self.statuses = tuple(statuses)

    def resolve(self, query: str, *, as_of: str) -> dict:
        try:
            instrument = normalize_ashare_ticker(query)
            return self._resolved(instrument.ticker, as_of)
        except AShareTickerError:
            pass
        day = date.fromisoformat(as_of)
        candidates = sorted({item.ticker for item in self.aliases if item.value.strip().upper() == query.strip().upper()
                             and date.fromisoformat(item.valid_from) <= day
                             and (item.valid_to is None or day <= date.fromisoformat(item.valid_to))})
        if len(candidates) != 1:
            return {"status": "ambiguous" if candidates else "unmapped", "query": query, "candidates": candidates}
        return self._resolved(candidates[0], as_of)

    def _resolved(self, ticker: str, as_of: str) -> dict:
        statuses = [item.status for item in self.statuses if item.ticker == ticker and item.as_of <= as_of]
        return {"status": "matched", "ticker": ticker, "as_of": as_of, "trading_status": statuses[-1] if statuses else "unknown"}
