from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

from data_store import DB_PATH, DEMO_POSITIONS, save_market_quotes


SOURCE_KEY = "tencent_quote"
BASE_URL = "https://qt.gtimg.cn/q="


def provider_symbol(ticker: str) -> str:
    code, exchange = ticker.split(".")
    return f"{'sh' if exchange == 'SH' else 'sz'}{code}"


def ticker_from_provider(symbol: str) -> str:
    exchange = "SH" if symbol.startswith("sh") else "SZ"
    return f"{symbol[2:]}.{exchange}"


def parse_response(raw: bytes, source_url: str) -> list[dict]:
    text = raw.decode("gbk", errors="replace")
    fetched_at = datetime.now(timezone.utc).isoformat()
    quotes = []
    for line in text.splitlines():
        match = re.match(r'v_([a-z]{2}\d{6})="(.*)";', line.strip())
        if not match:
            continue
        provider, payload = match.groups()
        fields = payload.split("~")
        if len(fields) < 35:
            continue
        try:
            price = float(fields[3])
            change_pct = float(fields[32])
            high = float(fields[33])
            low = float(fields[34])
        except (TypeError, ValueError):
            continue
        provider_time = fields[30]
        if price <= 0 or not re.fullmatch(r"\d{14}", provider_time):
            continue
        quote_time = datetime.strptime(provider_time, "%Y%m%d%H%M%S").replace(
            tzinfo=timezone(timedelta(hours=8))
        ).isoformat()
        quotes.append({
            "ticker": ticker_from_provider(provider),
            "name": fields[1],
            "price": price,
            "change_pct": change_pct,
            "high": high,
            "low": low,
            "pe_ttm": float(fields[39]) if len(fields) > 39 and fields[39] not in ("", "-") else None,
            "circulating_cap_yi": float(fields[44]) if len(fields) > 44 and fields[44] not in ("", "-") else None,
            "market_cap_yi": float(fields[45]) if len(fields) > 45 and fields[45] not in ("", "-") else None,
            "pb": float(fields[46]) if len(fields) > 46 and fields[46] not in ("", "-") else None,
            "quote_time": quote_time,
            "source_key": SOURCE_KEY,
            "source_url": source_url,
            "raw_hash": hashlib.sha256(line.encode("utf-8")).hexdigest(),
            "fetched_at": fetched_at,
        })
    return quotes


def fetch_quotes(timeout: float = 8.0) -> list[dict]:
    symbols = [provider_symbol(item["ticker"]) for item in DEMO_POSITIONS]
    source_url = BASE_URL + ",".join(symbols)
    request = Request(source_url, headers={"User-Agent": "ParkResearchDashboard/0.1"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    quotes = parse_response(raw, source_url)
    if len(quotes) != len(symbols):
        raise RuntimeError(f"quote coverage incomplete: {len(quotes)}/{len(symbols)}")
    return quotes


def main() -> None:
    quotes = fetch_quotes()
    accepted = save_market_quotes(quotes, DB_PATH)
    if accepted != len(DEMO_POSITIONS):
        raise SystemExit(f"Quote ingestion rejected records: accepted={accepted}/{len(DEMO_POSITIONS)}")
    newest = max(quote["quote_time"] for quote in quotes)
    print(f"REAL_QUOTE_INGEST_OK accepted={accepted} quote_time={newest} source={SOURCE_KEY}")


if __name__ == "__main__":
    main()
