"""Read-only live validator for the shared 16-asset kline-regime-v1 sample."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .contract import build_regime, validate_contract


BASE_URL = "http://127.0.0.1:8100"
WATCHLIST = (
    ("UUP", "etf"),
    ("SPY", "etf"),
    ("QQQ", "etf"),
    ("SCHD", "etf"),
    ("^VIX", "index"),
    ("BTC", "crypto"),
    ("ETH", "crypto"),
    ("HYPE", "crypto"),
    ("sh000001", "index"),
    ("sh000688", "index"),
    ("sh000015", "index"),
    ("^N225", "index"),
    ("^KS11", "index"),
    ("CL=F", "commodity"),
    ("GC=F", "commodity"),
    ("SI=F", "commodity"),
)
TIMEFRAMES = ("1d", "4h")


@dataclass(frozen=True)
class FetchResult:
    timeframe: str
    url: str
    bars: list[dict] | None
    status: str
    raw_response: str = ""
    error: str = ""


def _request_url(base_url: str, asset_class: str, ticker: str, timeframe: str) -> str:
    query = urlencode(
        {
            "timeframe": timeframe,
            "limit": 600,
            "cache_policy": "bypass",
            "quality": "strict",
            "fallback_policy": "none",
        }
    )
    return f"{base_url.rstrip('/')}/api/candles/{asset_class}/{quote(ticker, safe='')}?{query}"


def _error_reason(status: int, body: str) -> str:
    try:
        detail = json.loads(body).get("detail", {})
        if isinstance(detail, dict):
            error = detail.get("error") or "http_error"
            explanation = detail.get("detail") or ""
            return f"HTTP {status} {error}: {explanation}".rstrip(": ")
    except (TypeError, ValueError):
        pass
    return f"HTTP {status}: {body[:240]}".rstrip()


def fetch_bars(base_url: str, ticker: str, asset_class: str, timeframe: str) -> FetchResult:
    url = _request_url(base_url, asset_class, ticker, timeframe)
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed read-only local endpoint
            body = response.read().decode("utf-8")
            payload = json.loads(body)
        candles = payload.get("candles")
        if not isinstance(candles, list):
            return FetchResult(timeframe, url, None, "unavailable", body, "response candles is not a list")
        return FetchResult(timeframe, url, candles, "ready", body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return FetchResult(timeframe, url, None, "unavailable", body, _error_reason(exc.code, body))
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return FetchResult(timeframe, url, None, "unavailable", str(exc), f"GET failed: {exc}")


def validate_asset(base_url: str, ticker: str, asset_class: str) -> dict:
    fetched = {timeframe: fetch_bars(base_url, ticker, asset_class, timeframe) for timeframe in TIMEFRAMES}
    daily = fetched["1d"].bars
    four_hour = fetched["4h"].bars
    if daily is None or four_hour is None:
        failed = [f"{timeframe}: {fetched[timeframe].error}" for timeframe in TIMEFRAMES if fetched[timeframe].bars is None]
        result = build_regime(ticker, daily or [], four_hour or [])
        result["reason"] = "8100 source unavailable; " + "; ".join(failed)
    else:
        result = build_regime(ticker, daily, four_hour)
    validate_contract(result)
    result["_fetch"] = fetched
    return result


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(results: list[dict], *, base_url: str) -> str:
    fetch_by_asset = {result["asset"]: result["_fetch"] for result in results}
    lines = [
        "# kline-regime-v1 live validation",
        "",
        f"- Source: read-only `GET` from `{base_url}`; `cache_policy=bypass`, `quality=strict`, `fallback_policy=none`.",
        f"- Watchlist: {len(results)} shared assets; each row was fetched at both `1d` and `4h`.",
        "- `unavailable` is a source observation, not a fallback or synthetic result.",
        "",
        "| Asset | 1d bars | 4h bars | Regime | Range | Confidence | as_of | Schema | Reason |",
        "|---|---:|---:|---|---|---:|---|---|---|",
    ]
    for result in results:
        fetched = fetch_by_asset[result["asset"]]
        daily_count = len(fetched["1d"].bars or []) if fetched["1d"].bars is not None else "—"
        four_hour_count = len(fetched["4h"].bars or []) if fetched["4h"].bars is not None else "—"
        bounds = "—" if result["range_low"] is None else f"{result['range_low']:.6g}–{result['range_high']:.6g}"
        reason = result.get("reason", "")
        lines.append(
            "| "
            + " | ".join(
                map(
                    _cell,
                    (
                        result["asset"],
                        daily_count,
                        four_hour_count,
                        result["regime"],
                        bounds,
                        result["confidence"],
                        result["as_of"] or "—",
                        "PASS",
                        reason or "—",
                    ),
                )
            )
            + " |"
        )
    unavailable = [result for result in results if result["regime"] == "unavailable"]
    lines += ["", "## Unavailable source evidence", ""]
    if not unavailable:
        lines.append("None.")
    else:
        lines.append("The following complete HTTP response bodies were captured from the corresponding read-only requests:")
        for result in unavailable:
            lines += ["", f"### `{result['asset']}`", ""]
            fetched = fetch_by_asset[result["asset"]]
            for timeframe in TIMEFRAMES:
                item = fetched[timeframe]
                if item.bars is None:
                    lines += [f"- `{timeframe}` URL: `{item.url}`", "", "```json", item.raw_response, "```"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live 16-asset kline-regime-v1 output from Datafeed 8100")
    parser.add_argument("--all", action="store_true", required=True, help="validate the fixed shared 16-asset watchlist")
    parser.add_argument("--base-url", default=BASE_URL, help=argparse.SUPPRESS)
    args = parser.parse_args()
    results = [validate_asset(args.base_url, ticker, asset_class) for ticker, asset_class in WATCHLIST]
    print(render_markdown(results, base_url=args.base_url), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
