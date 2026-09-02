#!/usr/bin/env python3
"""Run the Daily K-line runtime and deliver its reader output to Feishu."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


PRODUCT = Path(__file__).resolve().parents[1] / "product"
sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_daily_feishu_cli import (  # noqa: E402
    DEFAULT_DAILY_ENV_FILE,
    DailyFeishuCliError,
    send_daily_rich_posts,
)
from data_core.market_regime_daily_runtime import DailyKlineRuntime, DailyRuntimeError  # noqa: E402


SCHEMA_VERSION = "market-regime-daily-feishu-delivery-v1"
DELIVERY_ID_PREFIX = "market-regime-daily-feishu-delivery:"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(_canonical(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_receipt(runtime_root: Path, delivery: dict[str, object]) -> dict[str, object]:
    core = {
        "schema_version": SCHEMA_VERSION,
        "report_date": delivery.get("report_date"),
        "analysis_bundle_id": delivery.get("analysis_bundle_id"),
        "post_count": delivery.get("post_count", 0),
        "image_count": delivery.get("image_count", 0),
        "content_sha256": delivery.get("content_sha256"),
        "status": delivery.get("status"),
    }
    delivery_id = f"{DELIVERY_ID_PREFIX}{_digest(core)}"
    receipt = {**core, "delivery_id": delivery_id, "sent_at": delivery.get("sent_at"), "error_code": delivery.get("error_code")}
    digest = delivery_id.removeprefix(DELIVERY_ID_PREFIX)
    receipt_path = runtime_root / "delivery" / "feishu" / "receipts" / f"{digest}.json"
    _atomic_json(receipt_path, receipt)
    latest = {
        "schema_version": SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "receipt_path": str(receipt_path),
        "status": delivery.get("status"),
    }
    _atomic_json(runtime_root / "delivery" / "feishu" / "latest.json", latest)
    return receipt


def _defaults() -> tuple[Path, Path, Path, Path, str, Path]:
    home = Path.home()
    return (
        Path(os.getenv("PARK_KLINE_DAILY_RUNTIME", home / "Library" / "Application Support" / "ParkKlineDaily" / "runtime")),
        Path(os.getenv("PARK_KLINE_DAILY_OUTPUT", home / "Desktop" / "K线日报")),
        Path(os.getenv("PARK_KLINE_DAILY_ARCHIVE", home / "park-hands" / "007_kline daily newsletter")),
        Path(os.getenv("DEEPSEEK_API_KEY_FILE", home / "park-hands" / "_secrets" / "deepseek-key")),
        os.getenv("PARK_DATAFEED_URL", "http://127.0.0.1:8100"),
        Path(os.getenv("PARK_KLINE_DAILY_FEISHU_ENV", DEFAULT_DAILY_ENV_FILE)),
    )


def main() -> int:
    runtime_default, output_default, archive_default, key_default, datafeed_default, feishu_default = _defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=runtime_default)
    parser.add_argument("--output-root", type=Path, default=output_default)
    parser.add_argument("--archive-root", type=Path, default=archive_default)
    parser.add_argument("--key-file", type=Path, default=key_default)
    parser.add_argument("--datafeed-url", default=datafeed_default)
    parser.add_argument("--feishu-env-file", type=Path, default=feishu_default)
    parser.add_argument("--max-runtime-seconds", type=float, default=20 * 60)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-snapshots", action="store_true")
    args = parser.parse_args()
    runtime = DailyKlineRuntime(
        runtime_root=args.runtime_root,
        output_root=args.output_root,
        archive_root=args.archive_root,
        key_file=args.key_file,
        datafeed_url=args.datafeed_url,
        max_runtime_seconds=args.max_runtime_seconds,
        no_llm=args.no_llm,
        no_snapshots=args.no_snapshots,
    )
    try:
        result = runtime.run_once()
        delivery = send_daily_rich_posts(
            result["analysis"],
            result["thesis"],
            output_root=args.output_root,
            env_file=args.feishu_env_file,
        )
        delivery["sent_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        receipt = _write_receipt(args.runtime_root, delivery)
        print(json.dumps({"state": "sent", "daily": result.get("status"), "delivery": receipt}, ensure_ascii=False, indent=2))
        return 0
    except DailyRuntimeError as exc:
        print(json.dumps({"state": "failed", "phase": "daily_runtime", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    except DailyFeishuCliError as exc:
        failed = _write_receipt(
            args.runtime_root,
            {
                "status": "failed",
                "report_date": datetime.now(timezone.utc).date().isoformat(),
                "analysis_bundle_id": None,
                "post_count": 0,
                "image_count": 0,
                "content_sha256": None,
                "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "error_code": str(exc),
            },
        )
        print(json.dumps({"state": "failed", "phase": "feishu_delivery", "error": str(exc), "delivery": failed}, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
