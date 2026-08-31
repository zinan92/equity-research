#!/usr/bin/env python3
"""Run the independent Weekly K-line report and deliver it to Feishu."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Mapping


PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_weekly_feishu import (  # noqa: E402
    DEFAULT_ENV_FILE,
    WeeklyFeishuDeliveryError,
    send_weekly_markdown,
)
from data_core.market_regime_weekly_feishu_cli import (  # noqa: E402
    DEFAULT_WEEKLY_ENV_FILE,
    WeeklyFeishuCliError,
    send_weekly_rich_posts,
)
from data_core.market_regime_weekly_runtime import WeeklyRuntimeError  # noqa: E402
from run_market_regime_weekly import run_weekly_runtime  # noqa: E402


DELIVERY_SCHEMA_VERSION = "market-regime-weekly-feishu-delivery-v2"
DELIVERY_ID_PREFIX = "market-regime-weekly-feishu-delivery:"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with open(descriptor, "w", encoding="utf-8", closefd=True) as handle:
            handle.write(_canonical(value) + "\n")
            handle.flush()
        Path(temporary).replace(path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def _write_delivery_receipt(runtime_root: Path, delivery: dict[str, object]) -> dict[str, object]:
    core = {
        "schema_version": DELIVERY_SCHEMA_VERSION,
        "week_end": delivery["week_end"],
        "report_id": delivery["report_id"],
        "content_sha256": delivery["content_sha256"],
        "chunk_count": delivery.get("chunk_count", delivery.get("post_count", 0)),
        "sent_at": delivery["sent_at"],
    }
    if delivery.get("error_code"):
        core["error_code"] = delivery["error_code"]
    for field in ("mode", "post_count", "image_count"):
        if delivery.get(field) is not None:
            core[field] = delivery[field]
    delivery_id = f"{DELIVERY_ID_PREFIX}{_digest(core)}"
    receipt = {**core, "delivery_id": delivery_id, "status": delivery["status"]}
    digest = delivery_id.removeprefix(DELIVERY_ID_PREFIX)
    receipt_path = runtime_root / "delivery" / "feishu" / "receipts" / f"{digest}.json"
    _atomic_json(receipt_path, receipt)
    latest = {"schema_version": DELIVERY_SCHEMA_VERSION, "delivery_id": delivery_id, "receipt_path": str(receipt_path)}
    _atomic_json(runtime_root / "delivery" / "feishu" / "latest.json", latest)
    return receipt


def _record_delivery_status(runtime_root: Path, receipt: Mapping[str, object]) -> None:
    """Bind delivery outcome to the already-published runtime status."""

    path = runtime_root / "status.json"
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if not isinstance(status, dict) or not isinstance(status.get("last_success"), dict):
        return
    success = status["last_success"]
    if success.get("report_id") != receipt.get("report_id"):
        return
    success.update(
        {
            "delivery_status": receipt.get("status"),
            "delivery_id": receipt.get("delivery_id"),
            "delivery_mode": receipt.get("mode"),
            "delivery_post_count": receipt.get("post_count", receipt.get("chunk_count", 0)),
            "delivery_image_count": receipt.get("image_count", 0),
        }
    )
    if receipt.get("status") == "failed":
        status["state"] = "failed"
        status["last_failure"] = {
            "at": receipt.get("sent_at"),
            "code": receipt.get("error_code") or "feishu_delivery_failed",
            "phase": "delivery",
        }
    else:
        status["state"] = "idle"
        status["last_failure"] = None
    _atomic_json(path, status)


def run_and_deliver(
    *,
    now: datetime | None,
    week_end: date | None,
    datafeed_url: str,
    runtime_root: Path,
    output_root: Path,
    archive_root: Path,
    key_file: Path,
    model: str,
    codex_model: str | None,
    feishu_env_file: Path,
    feishu_mode: str = "rich",
) -> dict[str, object]:
    result = run_weekly_runtime(
        now=now,
        week_end=week_end,
        datafeed_url=datafeed_url,
        runtime_root=runtime_root,
        output_root=output_root,
        key_file=key_file,
        model=model,
        codex_model=codex_model,
    )
    report = result["report"]
    markdown_path = output_root / "latest.md"
    markdown = markdown_path.read_text(encoding="utf-8")
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_path = archive_root / f"{report.get('week_end')}-market-regime-kline-newsletter.md"
    if archive_path.exists() and archive_path.read_text(encoding="utf-8") != markdown:
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:12]
        archive_path = archive_root / f"{report.get('week_end')}-market-regime-kline-newsletter-{digest}.md"
    archive_path.write_text(markdown, encoding="utf-8")
    sent_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    week_end_text = str(report.get("week_end") or "")
    report_id = str(report.get("report_id") or "")
    try:
        if feishu_mode == "rich":
            delivery = send_weekly_rich_posts(
                report,
                output_root=output_root,
                env_file=feishu_env_file,
            )
        elif feishu_mode == "text":
            delivery = send_weekly_markdown(
                markdown,
                week_end=week_end_text,
                report_id=report_id,
                output_root=output_root,
                archive_path=archive_path,
                env_file=feishu_env_file,
            )
        else:
            raise WeeklyFeishuCliError("feishu_mode_invalid")
    except (WeeklyFeishuDeliveryError, WeeklyFeishuCliError) as exc:
        failed = {
            "status": "failed",
            "week_end": week_end_text,
            "report_id": report_id,
            "chunk_count": 0,
            "content_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "sent_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "error_code": str(exc)[:160],
        }
        failed_receipt = _write_delivery_receipt(runtime_root, failed)
        _record_delivery_status(runtime_root, failed_receipt)
        raise
    delivery.update({"status": "sent", "sent_at": sent_at})
    receipt = _write_delivery_receipt(runtime_root, delivery)
    _record_delivery_status(runtime_root, receipt)
    return {
        "status": "completed",
        "week_end": report.get("week_end"),
        "report_id": report.get("report_id"),
        "html": str(output_root / "latest.html"),
        "markdown": str(markdown_path),
        "archive": str(archive_path),
        "feishu": receipt,
        "chart_coverage": report.get("chart_coverage"),
        "feishu_mode": delivery.get("mode"),
        "feishu_post_count": delivery.get("post_count", delivery.get("chunk_count", 0)),
        "feishu_image_count": delivery.get("image_count", 0),
        "chart_slots": len(report.get("chart_slots") or []),
        "chart_snapshots": sum(1 for slot in report.get("chart_slots") or [] if isinstance(slot, dict) and isinstance(slot.get("snapshot"), dict)),
        "assets": len(report.get("cards") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path.home()
    support = home / "Library" / "Application Support"
    parser.add_argument("--now")
    parser.add_argument("--week-end")
    parser.add_argument("--datafeed-url", default="http://127.0.0.1:8100")
    parser.add_argument("--runtime-root", type=Path, default=support / "ParkWeeklyMacroKline" / "runtime")
    parser.add_argument("--output-root", type=Path, default=home / "Desktop" / "宏观K线周报")
    parser.add_argument("--archive-root", type=Path, default=home / "park-hands" / "008_finance weekly newsletter")
    parser.add_argument("--key-file", type=Path, default=home / "park-hands" / "_secrets" / "deepseek-key")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--codex-model", default=None)
    parser.add_argument("--feishu-env-file", type=Path, default=DEFAULT_WEEKLY_ENV_FILE)
    parser.add_argument("--feishu-mode", choices=("rich", "text"), default="rich")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
    if now is not None and now.tzinfo is None:
        parser.error("--now requires a timezone")
    week_end = date.fromisoformat(args.week_end) if args.week_end else None
    try:
        result = run_and_deliver(
            now=now,
            week_end=week_end,
            datafeed_url=args.datafeed_url,
            runtime_root=args.runtime_root.expanduser().resolve(),
            output_root=args.output_root.expanduser().resolve(),
            archive_root=args.archive_root.expanduser().resolve(),
            key_file=args.key_file.expanduser().resolve(),
            model=args.model,
            codex_model=args.codex_model,
            feishu_env_file=args.feishu_env_file.expanduser().resolve(),
            feishu_mode=args.feishu_mode,
        )
    except (WeeklyRuntimeError, WeeklyFeishuDeliveryError, WeeklyFeishuCliError) as exc:
        print(json.dumps({"status": "failed", "code": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
