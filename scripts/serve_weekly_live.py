#!/usr/bin/env python3
"""Serve the live Weekly mockup with a reader-safe API and real snapshots."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import mimetypes
from urllib.parse import unquote, urlparse


DISPLAY_NAMES = {
    "dxy": "美元指数", "us2y": "美国国债 2Y", "us10y": "美国国债 10Y", "us2s10s": "美国国债 2s10s",
    "sp500": "S&P 500", "nasdaq": "Nasdaq Composite", "us_dividend": "美股红利 ETF", "vix": "VIX", "bitcoin": "Bitcoin",
    "shanghai": "上证指数", "star50": "科创 50", "china_dividend": "上证红利", "nikkei": "Nikkei 225", "kospi": "KOSPI",
    "wti": "WTI 原油", "gold": "黄金", "silver": "白银",
}
TIMEFRAME_LABELS = {"weekly": "周线", "daily": "日线", "four_hour": "4小时"}
POSITION = {"high": "高位", "middle": "中位", "low": "低位", "unavailable": "不可用"}
STRUCTURE = {"continuation": "延续", "weakening": "走弱", "reversal": "反转", "mixed": "分歧", "unknown": "未知"}
ODDS = {"favorable": "有利", "unfavorable": "不利", "not_ready": "未形成", "unknown": "未知"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _number(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _last_candle(points: list[dict], kind: str) -> dict[str, str]:
    if not points:
        return {"label": "不可用", "tone": "unavailable"}
    last = points[-1]
    open_value = _number(last.get("open")); close_value = _number(last.get("close"))
    high_value = _number(last.get("high")); low_value = _number(last.get("low"))
    if open_value is None or close_value is None:
        return {"label": "不可用", "tone": "unavailable"}
    if kind != "price":
        if close_value > open_value: return {"label": "上行", "tone": "up"}
        if close_value < open_value: return {"label": "下行", "tone": "down"}
        return {"label": "横盘", "tone": "flat"}
    span = max((high_value or close_value) - (low_value or close_value), 0.0)
    body = abs(close_value - open_value)
    prefix = "阳" if close_value > open_value else "阴" if close_value < open_value else "十字"
    size = "大" if span and body / span >= .67 else "中" if span and body / span >= .34 else "小"
    return {"label": prefix if prefix == "十字" else size + prefix, "tone": "up" if close_value > open_value else "down" if close_value < open_value else "flat"}


def _trend_marker(structure: dict) -> dict[str, str]:
    state = str(structure.get("state") or "")
    bias = str(structure.get("bias") or "")
    if state == "continuation" and bias == "bullish": return {"marker": "↗", "label": "走强", "tone": "up"}
    if state in {"continuation", "weakening"} and bias == "bearish": return {"marker": "↘", "label": "走弱", "tone": "down"}
    if state == "weakening": return {"marker": "↘", "label": "走弱", "tone": "down"}
    if state == "reversal": return {"marker": "↗" if bias == "bullish" else "↘", "label": "反转", "tone": "up" if bias == "bullish" else "down"}
    return {"marker": "→", "label": "分歧", "tone": "flat"}


class WeeklyLiveHandler(BaseHTTPRequestHandler):
    static_root: Path
    runtime_root: Path
    output_root: Path

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, value: dict) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8")

    def _load_report(self) -> dict:
        pointer = _read_json(self.runtime_root / "latest.json")
        report_id = str(pointer.get("report_id") or "")
        digest = report_id.removeprefix("market-regime-weekly-report:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("weekly_report_identity_invalid")
        report = _read_json(self.runtime_root / "reports" / "artifacts" / f"{digest}.json")
        if report.get("report_id") != report_id:
            raise ValueError("weekly_report_artifact_identity_invalid")
        return report

    @staticmethod
    def _statement(analysis: dict, field: str, fallback: str) -> str:
        value = analysis.get(field)
        return str(value.get("text") or fallback) if isinstance(value, dict) else fallback

    def _report_payload(self) -> dict:
        report = self._load_report()
        assets = []
        unavailable: list[str] = []
        for card in report.get("cards") or []:
            key = str(card.get("asset_key") or "")
            analysis = card.get("analysis") if isinstance(card.get("analysis"), dict) else {}
            status = "已验证" if card.get("analysis_status") == "validated" else "数据不可用"
            if status != "已验证": unavailable.append(key)
            slots = {}
            for slot in card.get("chart_slots") or []:
                if not isinstance(slot, dict): continue
                snapshot = slot.get("snapshot") if isinstance(slot.get("snapshot"), dict) else {}
                asset = snapshot.get("asset") if isinstance(snapshot.get("asset"), dict) else {}
                path = str(asset.get("path") or "")
                if not path.startswith("snapshots/"): continue
                timeframe = str(slot.get("timeframe"))
                points = [point for point in slot.get("points") or [] if isinstance(point, dict)]
                mini_points = points[-20:]
                latest = _number(mini_points[-1].get("close")) if mini_points else None
                previous = _number(mini_points[-2].get("close")) if len(mini_points) > 1 else None
                change = latest - previous if latest is not None and previous is not None else None
                kind = str(slot.get("kind") or "price")
                slots[timeframe] = {
                    "label": TIMEFRAME_LABELS.get(timeframe, timeframe),
                    "text": self._statement(analysis, timeframe, "当前该周期分析不可用。"),
                    "image_url": "/snapshots/" + path.removeprefix("snapshots/"),
                    "unit": slot.get("unit"),
                    "kind": kind,
                    "mini_points": mini_points,
                    "chart_points": points[-80:],
                    "latest_value": latest,
                    "change": change,
                    "change_pct": (change / previous * 100) if kind == "price" and change is not None and previous else None,
                    "last_candle": _last_candle(mini_points, kind),
                }
            position = analysis.get("position") if isinstance(analysis.get("position"), dict) else {}
            structure = analysis.get("structure") if isinstance(analysis.get("structure"), dict) else {}
            odds = analysis.get("odds") if isinstance(analysis.get("odds"), dict) else {}
            weekly_mini = slots.get("weekly") or {}
            assets.append({
                "asset_key": key,
                "display_name": DISPLAY_NAMES.get(key, key),
                "analysis_status": card.get("analysis_status"),
                "status_label": status,
                "position": POSITION.get(str(position.get("state")), "不可用"),
                "structure": STRUCTURE.get(str(structure.get("state")), "未知"),
                "odds": ODDS.get(str(odds.get("state")), "未形成"),
                "trend": _trend_marker(structure),
                "position_state": str(position.get("state") or "unavailable"),
                "mini_chart": weekly_mini,
                "weekly": self._statement(analysis, "weekly", "当前分析不可用。"),
                "daily": self._statement(analysis, "daily", "当前分析不可用。"),
                "four_hour": self._statement(analysis, "four_hour", "当前4小时上下文不可用。"),
                "synthesis": self._statement(analysis, "synthesis", "当前多周期分析不可用。"),
                "theoretical_implication": self._statement(analysis, "theoretical_implication", "当前机制解释不可用。"),
                "slots": slots,
            })
        validated = sum(item["status_label"] == "已验证" for item in assets)
        return {
            "report_id": report.get("report_id"),
            "source_snapshot_id": report.get("source_snapshot_id"),
            "week_end": report.get("week_end"),
            "cutoff_at": report.get("cutoff_at"),
            "source_status": report.get("source_status"),
            "analysis_validated": validated,
            "unavailable_assets": unavailable,
            "assets": assets,
        }

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/health":
                self._json(200, {"status": "ok", "runtime_root": str(self.runtime_root)})
                return
            if path == "/api/weekly-report":
                self._json(200, self._report_payload())
                return
            if path.startswith("/snapshots/"):
                filename = Path(path.removeprefix("/snapshots/")).name
                if filename != path.removeprefix("/snapshots/") or not filename.endswith(".png"):
                    self._json(400, {"error": "snapshot_path_invalid"}); return
                target = (self.output_root / "snapshots" / filename).resolve()
                if self.output_root.resolve() not in target.parents or not target.is_file():
                    self._json(404, {"error": "snapshot_not_found"}); return
                self._send(200, target.read_bytes(), "image/png")
                return
            relative = path.removeprefix("/") or "index.html"
            target = (self.static_root / relative).resolve()
            if self.static_root.resolve() not in target.parents or not target.is_file():
                self._json(404, {"error": "static_not_found"}); return
            self._send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            self._json(503, {"error": "weekly_report_unavailable", "detail": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[weekly-live] {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the live Weekly mockup")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8907)
    parser.add_argument("--runtime-root", type=Path, default=Path.home() / "Library/Application Support/ParkWeeklyMacroKline/runtime")
    parser.add_argument("--output-root", type=Path, default=Path.home() / "Desktop/宏观K线周报")
    args = parser.parse_args()
    handler = type("ConfiguredWeeklyLiveHandler", (WeeklyLiveHandler,), {"static_root": Path(__file__).resolve().parents[1] / "product/static/weekly-live", "runtime_root": args.runtime_root.expanduser().resolve(), "output_root": args.output_root.expanduser().resolve()})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Weekly live prototype: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
