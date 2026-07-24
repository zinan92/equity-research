"""Runtime-only A-share security-master captures for E4 acceptance.

This is an identity directory, not a filing/market/fundamental evidence source.
Raw directory responses are written only to ``product/runtime`` (or another
caller-supplied external runtime) and never become report facts by themselves.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .ashare import AShareTickerError, normalize_ashare_ticker
from .contracts import digest


SECURITY_MASTER_SCHEMA_VERSION = "ashare-security-master-v1"
SINA_DIRECTORY_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/jsonp_v2.php/var%20data=/Market_Center.getHQNodeDataSimple"
MARKET_NODES = {
    "SH": "sh_a",
    "SZ": "sz_a",
    # Sina's documented bj_a node currently returns null; hs_a is symbol-sorted
    # and exposes BSE rows first, while the parser still rejects a non-bj row.
    "BJ": "hs_a",
}
HttpGet = Callable[[str], bytes]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_http_get(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ParkResearch/1.0 security-master acceptance"})
    with urlopen(request, timeout=20) as response:  # nosec B310 - fixed public endpoint above
        return response.read()


@dataclass(frozen=True)
class SecurityMasterRecord:
    code: str
    ticker: str
    name: str
    exchange: str
    board: str
    listing_date: str | None
    source_url: str
    raw_hash: str
    observed_at: str
    data_kind: str = "real"


@dataclass(frozen=True)
class SecurityMasterCapture:
    records: tuple[SecurityMasterRecord, ...]
    captures: tuple[dict[str, str], ...]
    raw_bodies: tuple[tuple[str, bytes], ...]
    observed_at: str
    data_kind: str

    def receipt(self) -> dict[str, Any]:
        exchanges = sorted({record.exchange for record in self.records})
        payload = {
            "schema_version": SECURITY_MASTER_SCHEMA_VERSION,
            "observed_at": self.observed_at,
            "data_kind": self.data_kind,
            "record_count": len(self.records),
            "exchanges": exchanges,
            "captures": list(self.captures),
            "records": [asdict(record) for record in self.records],
            "truth_boundary": {
                "identity_only": True,
                "counts_as_report_model_coverage": False,
                "counts_as_evidence_coverage": False,
                "counts_as_tier_a_or_b": False,
            },
        }
        payload["receipt_hash"] = digest(payload)
        return payload


def _directory_url(market: str, *, page: int, page_size: int) -> str:
    if market not in MARKET_NODES:
        raise ValueError("unsupported security-master market")
    return SINA_DIRECTORY_URL + "?" + urlencode({
        "num": page_size, "page": page, "sort": "symbol", "asc": 1,
        "node": MARKET_NODES[market], "symbol": "", "_s_r_a": "page",
    })


def _listing_date(value: object) -> str | None:
    digits = str(value or "").strip()
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return None


def _parse_page(body: bytes, *, market: str, source_url: str, observed_at: str) -> tuple[SecurityMasterRecord, ...]:
    try:
        text = body.decode("utf-8")
        start, end = text.index("["), text.rindex("]") + 1
        rows = json.loads(text[start:end])
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("security-master response is invalid") from exc
    if not isinstance(rows, list):
        raise ValueError("security-master rows are invalid")
    raw_hash = sha256(body).hexdigest()
    output: list[SecurityMasterRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("security-master row is invalid")
        code, name = str(row.get("code") or "").strip(), str(row.get("name") or "").strip()
        if not code or not name:
            raise ValueError("security-master row is missing code or name")
        symbol = str(row.get("symbol") or "").strip().upper()
        expected_symbol = market.lower() + code
        try:
            if symbol.lower() != expected_symbol:
                raise AShareTickerError("provider symbol does not match declared market")
            instrument = normalize_ashare_ticker(f"{code}.{market}")
        except AShareTickerError as exc:
            raise ValueError(f"security-master exchange mismatch for {code}: {market}") from exc
        output.append(SecurityMasterRecord(
            code=code, ticker=instrument.ticker, name=name, exchange=instrument.exchange,
            board=instrument.board, listing_date=None,
            source_url=source_url, raw_hash=raw_hash, observed_at=observed_at,
        ))
    return tuple(output)


def collect_security_master(
    *, http_get: HttpGet = _default_http_get, now: str | None = None,
    per_market: int = 40, markets: Iterable[str] = ("SH", "SZ", "BJ"),
) -> SecurityMasterCapture:
    """Collect a bounded directory sample; fail closed on duplicate identities."""
    if not isinstance(per_market, int) or not 1 <= per_market <= 200:
        raise ValueError("per_market must be 1-200")
    observed_at = now or _now()
    records: list[SecurityMasterRecord] = []
    captures: list[dict[str, str]] = []
    raw_bodies: list[tuple[str, bytes]] = []
    for market in markets:
        url = _directory_url(market, page=1, page_size=per_market)
        body = http_get(url)
        rows = _parse_page(body, market=market, source_url=url, observed_at=observed_at)
        if not rows:
            raise ValueError(f"security-master returned no rows for {market}")
        records.extend(rows)
        raw_hash = sha256(body).hexdigest()
        captures.append({"market": market, "source_url": url, "raw_hash": raw_hash})
        raw_bodies.append((raw_hash, body))
    by_ticker = {record.ticker: record for record in records}
    if len(by_ticker) != len(records):
        raise ValueError("security-master contains duplicate canonical tickers")
    return SecurityMasterCapture(tuple(sorted(records, key=lambda record: record.ticker)), tuple(captures), tuple(raw_bodies), observed_at, "real")


def write_runtime_capture(capture: SecurityMasterCapture, root: Path) -> dict[str, Any]:
    """Write only identity receipts to a caller-controlled runtime directory."""
    receipt = capture.receipt()
    root.mkdir(parents=True, exist_ok=True)
    raw_root = root / "raw"
    raw_root.mkdir(exist_ok=True)
    for raw_hash, body in capture.raw_bodies:
        raw_path = raw_root / f"{raw_hash}.json"
        if raw_path.exists() and raw_path.read_bytes() != body:
            raise ValueError("security-master raw hash collision")
        if not raw_path.exists():
            raw_path.write_bytes(body)
    path = root / f"security-master-{receipt['receipt_hash'][:16]}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    latest = root / "security-master-latest.json"
    latest_temporary = latest.with_suffix(".tmp")
    latest_temporary.write_text(json.dumps({"receipt": path.name, "receipt_hash": receipt["receipt_hash"]}, sort_keys=True) + "\n", encoding="utf-8")
    latest_temporary.replace(latest)
    return {"path": str(path), "receipt": receipt}
