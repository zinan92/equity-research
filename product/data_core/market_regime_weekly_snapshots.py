"""Immutable browser snapshots for the Weekly standard-kline reader."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .market_regime_weekly_report import render_weekly_html


SNAPSHOT_SCHEMA_VERSION = "market-regime-weekly-chart-snapshot-v1"
SNAPSHOT_ID_PREFIX = "market-regime-weekly-chart-snapshot:"
SNAPSHOT_VIEWPORT = {"width": 1280, "height": 900}


class WeeklyChartSnapshotError(RuntimeError):
    """Snapshot rendering or immutable receipt failed."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _immutable_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256(payload).hexdigest()
    if path.exists():
        if sha256(path.read_bytes()).hexdigest() != digest:
            raise WeeklyChartSnapshotError("snapshot_immutable_conflict")
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


def _snapshot_core(slot: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    payload = slot.get("standard_kline")
    if not isinstance(payload, Mapping):
        raise WeeklyChartSnapshotError("snapshot_payload_missing")
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "slot_id": slot.get("slot_id"),
        "asset_key": slot.get("asset_key"),
        "timeframe": slot.get("timeframe"),
        "candle_response_hash": payload.get("candle_response_hash"),
        "source_identity": payload.get("source_identity"),
        "cutoff_at": payload.get("cutoff_at") or report.get("cutoff_at"),
        "renderer": payload.get("renderer"),
        "renderer_version": payload.get("renderer_version"),
        "reader_renderer_version": report.get("renderer_version"),
        "renderer_options": payload.get("renderer_options"),
        "viewport": dict(SNAPSHOT_VIEWPORT),
    }


class PlaywrightWeeklyChartSnapshotPort:
    """Render every eligible slot with the same HTML standard-kline reader."""

    def __init__(self, *, runtime_root: Path | str, output_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    def __call__(
        self,
        *,
        report: Mapping[str, Any],
        candle_responses: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        slots = [slot for slot in report.get("chart_slots") or [] if isinstance(slot, Mapping) and isinstance(slot.get("standard_kline"), Mapping)]
        if not slots:
            return {}
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - environment dependency
            raise WeeklyChartSnapshotError("playwright_unavailable") from exc

        results: dict[str, dict[str, Any]] = {}
        for slot in slots:
            slot_id = str(slot.get("slot_id"))
            payload = slot.get("standard_kline") or {}
            response = candle_responses.get(slot_id)
            if not isinstance(response, Mapping) or _digest(response) != payload.get("candle_response_hash"):
                raise WeeklyChartSnapshotError(f"snapshot_candle_response_mismatch:{slot_id}")
        with tempfile.TemporaryDirectory(prefix="weekly-chart-snapshot-") as directory:
            html_path = Path(directory) / "reader.html"
            html_path.write_text(render_weekly_html(report), encoding="utf-8")
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch()
                except Exception as exc:  # pragma: no cover - environment dependency
                    raise WeeklyChartSnapshotError("chromium_unavailable") from exc
                try:
                    page = browser.new_page(viewport=SNAPSHOT_VIEWPORT)
                    browser_errors: list[str] = []
                    page.on("pageerror", lambda error: browser_errors.append(str(error)))
                    page.on("console", lambda message: browser_errors.append(message.text) if message.type == "error" else None)
                    page.goto(html_path.as_uri(), wait_until="load")
                    page.wait_for_timeout(150)
                    slots_by_asset: dict[str, list[Mapping[str, Any]]] = {}
                    for slot in slots:
                        slots_by_asset.setdefault(str(slot.get("asset_key")), []).append(slot)
                    for asset_key, asset_slots in slots_by_asset.items():
                        page.locator(f'[data-asset-nav="{asset_key}"]').click()
                        page.wait_for_timeout(100)
                        for slot in asset_slots:
                            slot_id = str(slot.get("slot_id"))
                            mount = page.locator(f'[data-chart="{slot_id}"]')
                            if mount.count() != 1:
                                raise WeeklyChartSnapshotError(f"snapshot_mount_missing:{slot_id}")
                            page.wait_for_timeout(50)
                            render_state = mount.evaluate("""node => {
                              const chart = node._standardKline;
                              const payload = chart?.current?.meta || {};
                              return {
                                chart: Boolean(chart?.chart),
                                candleSeries: Boolean(chart?.candleSeries),
                                lineSeries: Boolean(chart?.lineSeries),
                                overlay: node.querySelector('[data-standard-kline-overlay]')?.dataset.state || '',
                                status: payload.status || '',
                                mode: payload.render_mode || '',
                              };
                            }""")
                            expected_mode = str((slot.get("standard_kline") or {}).get("render_mode") or "candles")
                            if not render_state["chart"]:
                                raise WeeklyChartSnapshotError(f"snapshot_chart_missing:{slot_id}")
                            if render_state["status"] == "ready" and ((expected_mode == "line" and not render_state["lineSeries"]) or (expected_mode != "line" and not render_state["candleSeries"])):
                                raise WeeklyChartSnapshotError(f"snapshot_series_missing:{slot_id}")
                            if render_state["status"] != "ready" and render_state["overlay"] == "ready":
                                raise WeeklyChartSnapshotError(f"snapshot_unavailable_overlay_missing:{slot_id}")
                            image_bytes = mount.screenshot(type="png")
                            core = _snapshot_core(slot, report)
                            snapshot_digest = _digest(core)
                            snapshot_id = f"{SNAPSHOT_ID_PREFIX}{snapshot_digest}"
                            asset_relative = f"snapshots/{snapshot_digest}.png"
                            image_hash = _immutable_bytes(self.output_root / asset_relative, image_bytes)
                            receipt_core = {
                                **core,
                                "snapshot_id": snapshot_id,
                                "asset": {"path": asset_relative, "sha256": image_hash},
                            }
                            receipt_hash = _digest(receipt_core)
                            receipt = {**receipt_core, "receipt_hash": receipt_hash}
                            receipt_relative = f"chart_snapshots/receipts/{snapshot_digest}.json"
                            _immutable_bytes(self.runtime_root / receipt_relative, (_canonical(receipt) + "\n").encode("utf-8"))
                            results[slot_id] = {
                                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                                "snapshot_id": snapshot_id,
                                "asset": {"path": asset_relative, "sha256": image_hash},
                                "receipt": {"path": receipt_relative, "sha256": sha256((_canonical(receipt) + "\n").encode("utf-8")).hexdigest()},
                                "candle_response_hash": core["candle_response_hash"],
                                "source_identity": core["source_identity"],
                                "cutoff_at": core["cutoff_at"],
                                "renderer": core["renderer"],
                                "renderer_version": core["renderer_version"],
                                "renderer_options": core["renderer_options"],
                            }
                    page.close()
                    if browser_errors:
                        raise WeeklyChartSnapshotError("snapshot_browser_error")
                finally:
                    browser.close()
        expected = {str(slot.get("slot_id")) for slot in slots}
        if set(results) != expected:
            raise WeeklyChartSnapshotError("snapshot_slot_set_incomplete")
        return results


__all__ = [
    "PlaywrightWeeklyChartSnapshotPort",
    "SNAPSHOT_ID_PREFIX",
    "SNAPSHOT_SCHEMA_VERSION",
    "WeeklyChartSnapshotError",
]
