"""Read-only CLI for kline-regime-v1."""

from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .contract import build_regime, validate_contract


def _get_bars(base_url: str, ticker: str, timeframe: str) -> list[dict]:
    query = urlencode({"timeframe": timeframe, "limit": 600, "cache_policy": "bypass", "quality": "strict", "fallback_policy": "none"})
    request = Request(f"{base_url.rstrip('/')}/api/candles/commodity/{ticker}?{query}", method="GET")
    with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed local HTTP GET endpoint
        payload = json.loads(response.read().decode("utf-8"))
    return payload["candles"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build research-only kline-regime-v1 from Datafeed 8100")
    parser.add_argument("asset", help="asset alias, for example XAU")
    parser.add_argument("--from-8100", action="store_true", required=True, help="read closed bars with GET from local Datafeed")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        daily = _get_bars(args.base_url, "GOLD" if args.asset.upper() == "XAU" else args.asset, "1d")
        four_hour = _get_bars(args.base_url, "GOLD" if args.asset.upper() == "XAU" else args.asset, "4h")
        result = build_regime(args.asset, daily, four_hour)
    except Exception as exc:  # network/upstream failure is an explicit unavailable result
        result = build_regime(args.asset, [], [])
        result["reason"] = f"8100 GET failed: {exc}"
    validate_contract(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
