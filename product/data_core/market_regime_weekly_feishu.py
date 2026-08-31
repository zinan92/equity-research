"""Fail-closed Feishu delivery for the independent Weekly K-line report."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_FEISHU_TEXT_CHARS = 15000
DEFAULT_ENV_FILE = Path("/Users/wendy/work/trading-co/park-intel-production/.env")


class WeeklyFeishuDeliveryError(RuntimeError):
    """Feishu delivery could not be completed without ambiguity."""


def _read_env_value(key: str, env_file: Path | None) -> str:
    configured = os.getenv(key, "").strip()
    if configured:
        return configured
    if env_file is None or not env_file.is_file():
        return ""
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    prefix = f"{key}="
    for line in lines:
        value = line.strip()
        if value.startswith("export "):
            value = value[7:].lstrip()
        if not value.startswith(prefix):
            continue
        parsed = value[len(prefix):].strip()
        if len(parsed) >= 2 and parsed[0] == parsed[-1] and parsed[0] in {"'", '"'}:
            parsed = parsed[1:-1]
        return parsed
    return ""


def _signature(secret: str, timestamp: str) -> str:
    message = f"{timestamp}\n{secret}".encode("utf-8")
    return base64.b64encode(hmac.new(message, digestmod=hashlib.sha256).digest()).decode("ascii")


def _chunks(text: str, limit: int = MAX_FEISHU_TEXT_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


def send_weekly_markdown(
    markdown: str,
    *,
    week_end: str,
    report_id: str,
    output_root: Path,
    archive_path: Path | None = None,
    env_file: Path | str | None = DEFAULT_ENV_FILE,
) -> dict[str, Any]:
    """Send the current report as one or more plain-text bot messages.

    The webhook and signing secret are resolved from the process environment
    or an external env file. Neither value is returned, logged, or persisted.
    """

    env_path = Path(env_file).expanduser().resolve() if env_file else None
    webhook = _read_env_value("FEISHU_BOT_WEBHOOK", env_path)
    if not webhook:
        raise WeeklyFeishuDeliveryError("feishu_webhook_missing")
    secret = _read_env_value("FEISHU_BOT_SECRET", env_path)
    header = (
        f"宏观 K 线周报｜{week_end}\n"
        "本报告只基于周线、日线和已声明的 4 小时 K 线。\n"
        f"网页：{output_root / 'latest.html'}\n"
        f"Markdown：{archive_path or (output_root / 'latest.md')}\n"
        f"报告 ID：{report_id}\n\n"
    )
    payload_text = header + markdown.strip()
    chunks = _chunks(payload_text)
    for index, chunk in enumerate(chunks, 1):
        timestamp = str(int(time.time()))
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "msg_type": "text",
            "content": {"text": f"（第 {index}/{len(chunks)} 条）\n{chunk}" if len(chunks) > 1 else chunk},
        }
        if secret:
            payload["sign"] = _signature(secret, timestamp)
        request = Request(
            webhook,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise WeeklyFeishuDeliveryError(f"feishu_transport_failed:{type(exc).__name__}") from exc
        code = response_body.get("code", response_body.get("StatusCode", 0)) if isinstance(response_body, dict) else None
        if code not in (0, "0"):
            raise WeeklyFeishuDeliveryError(f"feishu_rejected:code_{code}")
    return {
        "status": "sent",
        "week_end": week_end,
        "report_id": report_id,
        "chunk_count": len(chunks),
        "content_sha256": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
    }


__all__ = ["DEFAULT_ENV_FILE", "WeeklyFeishuDeliveryError", "send_weekly_markdown"]
