"""Deterministic 100-ticker identity-contract receipt for the A4 resolver."""
from __future__ import annotations

import json
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1] / "product"
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

from data_core.ashare import normalize_ashare_ticker


PREFIXES = (("600", "SH"), ("601", "SH"), ("603", "SH"), ("605", "SH"), ("688", "SH"),
            ("000", "SZ"), ("001", "SZ"), ("002", "SZ"), ("003", "SZ"), ("300", "SZ"),
            ("301", "SZ"), ("830", "BJ"), ("831", "BJ"), ("832", "BJ"), ("920", "BJ"))


def verify() -> dict:
    tickers = []
    for index in range(100):
        prefix, suffix = PREFIXES[index % len(PREFIXES)]
        code = prefix + f"{index:03d}"
        instrument = normalize_ashare_ticker(code)
        assert instrument.ticker.endswith("." + suffix)
        tickers.append({"input": code, "ticker": instrument.ticker, "exchange": instrument.exchange, "board": instrument.board})
    return {"schema_version": "ashare-resolver-contract-corpus-v1", "count": len(tickers),
            "markets": sorted({row["exchange"] for row in tickers}), "tickers": tickers}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, sort_keys=True))
