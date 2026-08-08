#!/usr/bin/env python3
"""Capture a bounded, non-gating observation of proposed intraday sources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_data import (  # noqa: E402
    HttpCapture,
    SAFE_RESPONSE_HEADERS,
    http_get_capture,
)


SCHEMA_VERSION = "market-regime-live-source-probe-v1"
PROBES: tuple[tuple[str, str], ...] = (
    ("tencent_a_share_quote_batch", "https://qt.gtimg.cn/q=sh000001,sh000688,sh000015"),
    ("tencent_shanghai_m5", "https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh000001,m5,,80"),
    ("yahoo_query1_es_m5", "https://query1.finance.yahoo.com/v8/finance/chart/ES=F?interval=5m&range=1d"),
    ("yahoo_query2_es_m5", "https://query2.finance.yahoo.com/v8/finance/chart/ES=F?interval=5m&range=1d"),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _excerpt(body: bytes, limit: int = 320) -> str | None:
    if not body:
        return None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("gb18030", errors="replace")
    return " ".join(text.replace("\x00", " ").split())[:limit]


def _write_exclusive(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


class _RedirectRecorder(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.locations: list[str] = []

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        self.locations.append(str(newurl))
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _safe_headers(headers) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:  # type: ignore[no-untyped-def]
    kept: dict[str, str] = {}
    dropped: set[str] = set()
    for name, value in headers.items():
        key = str(name).strip().lower()
        clean = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
        if key in SAFE_RESPONSE_HEADERS and clean:
            kept[key] = clean
        elif key:
            dropped.add(key)
    return tuple(sorted(kept.items())), tuple(sorted(dropped))


def http_get_plain_capture(url: str, *, timeout: float = 20.0) -> HttpCapture:
    """Preserve one no-product-User-Agent observation for fallback evidence."""

    fetched_at = _iso(_utc_now())
    redirects = _RedirectRecorder()
    opener = build_opener(redirects)
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
            safe, dropped = _safe_headers(response.headers)
            final_url = response.geturl()
            chain = tuple([url, *redirects.locations])
            if chain[-1] != final_url:
                chain = (*chain, final_url)
            return HttpCapture("GET", url, final_url, int(response.status), safe, dropped, chain, body, fetched_at)
    except HTTPError as exc:
        body = exc.read()
        safe, dropped = _safe_headers(exc.headers)
        final_url = exc.geturl() or url
        chain = tuple([url, *redirects.locations])
        if chain[-1] != final_url:
            chain = (*chain, final_url)
        return HttpCapture(
            "GET", url, final_url, int(exc.code), safe, dropped, chain, body,
            fetched_at, f"HTTPError: {exc.reason}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        return HttpCapture(
            "GET", url, url, None, (), (), (url,), b"", fetched_at,
            f"{type(exc).__name__}: {exc}",
        )


def collect_probe(
    root: Path,
    *,
    transport: Callable[[str], HttpCapture] = http_get_capture,
    plain_transport: Callable[[str], HttpCapture] = http_get_plain_capture,
    clock: Callable[[], datetime] = _utc_now,
    run_id: str | None = None,
) -> dict[str, object]:
    """Issue only the frozen requests and retain complete raw bodies locally."""

    resolved = root.expanduser().resolve()
    started_at = clock().astimezone(timezone.utc)
    identity = run_id or f"market-regime-live-probe-{started_at:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    results: list[dict[str, object]] = []
    for key, url in PROBES:
        requested_at = clock().astimezone(timezone.utc)
        selected_transport = plain_transport if key == "yahoo_query2_es_m5" else transport
        capture = selected_transport(url)
        received_at = clock().astimezone(timezone.utc)
        suffix = ".json" if capture.content_type == "application/json" else ".bin"
        raw_relative = f"intraday-probes/raw/{identity}/{key}{suffix}"
        if capture.body:
            _write_exclusive(resolved / raw_relative, capture.body)
        results.append(
            {
                "key": key,
                "method": capture.method,
                "requested_url": capture.requested_url,
                "final_url": capture.final_url,
                "redirect_chain": list(capture.redirect_chain),
                "status_code": capture.status_code,
                "content_type": capture.content_type,
                "response_headers": dict(capture.response_headers),
                "dropped_header_names": list(capture.dropped_header_names),
                "request_started_at": _iso(requested_at),
                "received_at": _iso(received_at),
                "transport_fetched_at": capture.fetched_at,
                "body_bytes": len(capture.body),
                "raw_sha256": capture.raw_sha256,
                "raw_capture_locator": f"local-runtime:{raw_relative}" if capture.body else None,
                "bounded_raw_excerpt": _excerpt(capture.body),
                "transport_error": capture.error,
                "observation_only": True,
                "reliability_proven": False,
                "exchange_realtime_proven": False,
                "redistribution_rights_proven": False,
            }
        )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": identity,
        "generated_at": _iso(clock()),
        "purpose": "bounded_non_gate_local_reachability_observation",
        "deployment_mode": "local_prototype",
        "license_status": "local_evaluation_only",
        "publication_eligible": False,
        "action_eligible": False,
        "probe_count": len(results),
        "probes": results,
        "limitations": [
            "one observation does not establish reliability or latency",
            "HTTP 200 does not establish valid market data",
            "a provider error does not establish source unavailability",
            "the Saturday run cannot establish market-open behavior",
            "the probe grants no private, public or commercial redistribution right",
        ],
    }
    payload["receipt_sha256"] = sha256(_canonical(payload)).hexdigest()
    _write_exclusive(resolved / "intraday-probes" / "receipts" / f"{identity}.json", _canonical(payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.getenv("PARK_MARKET_REGIME_ROOT", PRODUCT / "runtime" / "market-regime")),
    )
    args = parser.parse_args()
    print(json.dumps(collect_probe(args.root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
