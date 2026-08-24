"""Static standard-kline snapshots for Daily asset slots."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .market_regime_weekly_standard_kline import (
    STANDARD_KLINE_COMMIT,
    STANDARD_KLINE_OPTIONS,
    STANDARD_KLINE_RENDERER,
    STANDARD_KLINE_VERSION,
)


SCHEMA_VERSION = "market-regime-daily-chart-snapshot-v1"
SNAPSHOT_ID_PREFIX = "market-regime-daily-chart-snapshot:"
VIEWPORT = {"width": 1280, "height": 900}
DEVICE_SCALE_FACTOR = 2


class DailySnapshotError(RuntimeError):
    """A Daily chart snapshot or receipt failed closed."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _immutable_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise DailySnapshotError("snapshot_immutable_conflict")
        return digest
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


def build_daily_standard_kline_payload(asset: Mapping[str, Any], timeframe: str) -> dict[str, Any]:
    """Project one ready Daily slot into the standard-kline response shape."""

    slots = asset.get("slots")
    slot = slots.get(timeframe) if isinstance(slots, Mapping) else None
    instrument = asset.get("instrument")
    if not isinstance(slot, Mapping) or not isinstance(instrument, Mapping):
        raise DailySnapshotError("daily_snapshot_slot_missing")
    status = str(slot.get("status") or "unavailable")
    series_kind = str(instrument.get("series_kind") or "price")
    render_mode = "line" if series_kind in {"rate_level", "spread"} else "candles"
    options = {
        **STANDARD_KLINE_OPTIONS,
        "indicators": {**STANDARD_KLINE_OPTIONS["indicators"]},
        "renderMode": render_mode,
    }
    if render_mode == "line":
        options.update({"lineColor": "#526779", "lineWidth": 2})
    response_hash = str((slot.get("source_identity") or {}).get("response_sha256") or _digest(slot.get("bars") or []))
    return {
        "schema_version": "kline-candles-v1",
        "status": status,
        "ticker": instrument.get("canonical_symbol"),
        "symbol": instrument.get("canonical_symbol"),
        "asset_key": asset.get("asset_key"),
        "asset_class": instrument.get("asset_class"),
        "series_kind": series_kind,
        "render_mode": render_mode,
        "unit": instrument.get("unit"),
        "price_basis": instrument.get("price_basis"),
        "semantic_role": instrument.get("semantic_role"),
        "timeframe": timeframe,
        "latest_timestamp": slot.get("latest_timestamp"),
        "completion_state": slot.get("completion_state"),
        "is_provisional": bool(slot.get("is_provisional", False)),
        "provider": slot.get("provider", ""),
        "source_mode": slot.get("source_mode", ""),
        "requested_source": slot.get("requested_source", ""),
        "selected_source": slot.get("selected_source", ""),
        "quality_flags": list(slot.get("quality_flags") or []),
        "access_issues": list(slot.get("access_issues") or []),
        "reject_reason": slot.get("reject_reason"),
        "source_identity": dict(slot.get("source_identity") or {}),
        "candle_response_hash": response_hash,
        "candles": [dict(row) for row in slot.get("bars") or []],
        "renderer": STANDARD_KLINE_RENDERER,
        "renderer_version": STANDARD_KLINE_VERSION,
        "renderer_commit": STANDARD_KLINE_COMMIT,
        "renderer_options": options,
    }


def _vendor_text(root: Path, prefix: str) -> str:
    matches = sorted(root.glob(prefix))
    if not matches:
        raise DailySnapshotError(f"standard_kline_vendor_missing:{prefix}")
    return matches[-1].read_text(encoding="utf-8")


def _slot_html(payload: Mapping[str, Any], *, title: str) -> str:
    vendor = Path(__file__).resolve().parents[1] / "vendor"
    lightweight = _vendor_text(vendor, "lightweight-charts.*.standalone.js")
    standard = _vendor_text(vendor, "standard-kline.*.js")
    encoded = _canonical(payload).replace("</", "<\\/")
    options = _canonical(payload.get("renderer_options") or {}).replace("</", "<\\/")
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>{title}</title><style>html,body{{margin:0;background:#fffefa}}#chart{{width:1280px;height:900px;overflow:hidden}}</style></head><body><div id=\"chart\"></div><script>{lightweight}</script><script>{standard}</script><script>const payload={encoded};const options={{...{options},trustPolicy:{{allowSynthetic:false}}}};const chart=new StandardKline.StandardKlineChart(document.querySelector('#chart'),options);chart.setDatafeedResponse(payload);window.__dailyReady=true;</script></body></html>"""


class DailyChartSnapshotPort:
    """Render available Daily slots to immutable PNGs with standard-kline."""

    def __init__(self, *, runtime_root: Path | str, output_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    def render(self, source_bundle: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        slots: list[tuple[Mapping[str, Any], str]] = []
        for asset in source_bundle.get("assets") or []:
            for timeframe in ("daily", "four_hour", "thirty_minute"):
                slot = (asset.get("slots") or {}).get(timeframe)
                if isinstance(slot, Mapping) and slot.get("status") == "ready":
                    slots.append((asset, timeframe))
        if not slots:
            return {}
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - environment dependency
            raise DailySnapshotError("playwright_unavailable") from exc
        results: dict[str, dict[str, Any]] = {}
        with tempfile.TemporaryDirectory(prefix="daily-chart-snapshot-") as directory:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch()
                except Exception as exc:  # pragma: no cover - environment dependency
                    raise DailySnapshotError("chromium_unavailable") from exc
                try:
                    page = browser.new_page(viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE_FACTOR)
                    for asset, timeframe in slots:
                        payload = build_daily_standard_kline_payload(asset, timeframe)
                        slot_id = f"{asset['asset_key']}:{timeframe}"
                        core = {
                            "schema_version": SCHEMA_VERSION,
                            "slot_id": slot_id,
                            "asset_key": asset["asset_key"],
                            "timeframe": timeframe,
                            "candle_response_hash": payload["candle_response_hash"],
                            "source_identity": payload["source_identity"],
                            "cutoff_at": source_bundle.get("cutoff_at"),
                            "renderer": payload["renderer"],
                            "renderer_version": payload["renderer_version"],
                            "renderer_options": payload["renderer_options"],
                            "viewport": dict(VIEWPORT),
                            "device_scale_factor": DEVICE_SCALE_FACTOR,
                        }
                        snapshot_digest = _digest(core)
                        snapshot_id = f"{SNAPSHOT_ID_PREFIX}{snapshot_digest}"
                        html_path = Path(directory) / f"{snapshot_digest}.html"
                        html_path.write_text(_slot_html(payload, title=f"Daily K 线 · {asset['display_name']} · {timeframe}"), encoding="utf-8")
                        page.goto(html_path.as_uri(), wait_until="load")
                        page.wait_for_timeout(120)
                        if not page.evaluate("Boolean(window.__dailyReady)"):
                            raise DailySnapshotError(f"snapshot_chart_not_ready:{slot_id}")
                        image_bytes = page.locator("#chart").screenshot(type="png")
                        asset_relative = f"snapshots/{snapshot_digest}.png"
                        image_hash = _immutable_bytes(self.output_root / asset_relative, image_bytes)
                        receipt_core = {**core, "snapshot_id": snapshot_id, "asset": {"path": asset_relative, "sha256": image_hash}}
                        receipt = {**receipt_core, "receipt_hash": _digest(receipt_core)}
                        receipt_relative = f"chart_snapshots/receipts/{snapshot_digest}.json"
                        receipt_bytes = (_canonical(receipt) + "\n").encode("utf-8")
                        receipt_hash = _immutable_bytes(self.runtime_root / receipt_relative, receipt_bytes)
                        results[slot_id] = {
                            "schema_version": SCHEMA_VERSION,
                            "snapshot_id": snapshot_id,
                            "asset": {"path": asset_relative, "sha256": image_hash},
                            "receipt": {"path": receipt_relative, "sha256": receipt_hash},
                            "candle_response_hash": payload["candle_response_hash"],
                            "source_identity": payload["source_identity"],
                            "cutoff_at": source_bundle.get("cutoff_at"),
                            "renderer": payload["renderer"],
                            "renderer_version": payload["renderer_version"],
                            "renderer_options": payload["renderer_options"],
                        }
                    page.close()
                finally:
                    browser.close()
        return results


__all__ = [
    "DailyChartSnapshotPort",
    "DailySnapshotError",
    "SCHEMA_VERSION",
    "SNAPSHOT_ID_PREFIX",
    "build_daily_standard_kline_payload",
]
