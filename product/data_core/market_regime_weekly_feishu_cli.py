"""Reader-facing Feishu image delivery through the installed lark-cli."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .market_regime_weekly_feishu import _read_env_value, _signature
from .market_regime_weekly_report import _display_name


FEISHU_POST_LIMIT = 28_000
DEFAULT_WEEKLY_ENV_FILE = Path(
    "/Users/wendy/Library/Application Support/ParkWeeklyMacroKline/kline-feishu.env"
)
LARK_CLI_CANDIDATES = (
    "/opt/homebrew/bin/lark-cli",
    "/usr/local/bin/lark-cli",
)
WEEKLY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("钱的价格", ("dxy", "us2y", "us10y", "us2s10s")),
    ("风险资产", ("sp500", "nasdaq", "us_dividend", "vix")),
    ("加密资产永续", ("bitcoin", "ethereum", "hype")),
    ("亚洲与 A 股", ("shanghai", "star50", "china_dividend", "nikkei", "kospi")),
    ("实物资产", ("wti", "gold", "silver")),
)
TIMEFRAME_LABELS = {"weekly": "周线", "daily": "日线", "four_hour": "4 小时"}


class WeeklyFeishuCliError(RuntimeError):
    """CLI upload or rich post delivery failed."""


def _resolve_lark_cli() -> str:
    configured = os.getenv("LARK_CLI_BIN", "").strip()
    if configured:
        if Path(configured).is_file():
            return str(Path(configured).resolve())
        raise WeeklyFeishuCliError("lark_cli_configured_path_missing")
    discovered = shutil.which("lark-cli")
    for candidate in (discovered, *LARK_CLI_CANDIDATES):
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise WeeklyFeishuCliError("lark_cli_missing")


def _parse_cli_json(stdout: str) -> Mapping[str, Any]:
    value = stdout.strip()
    if not value:
        raise WeeklyFeishuCliError("lark_cli_empty_output")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        payload = None
        for line in reversed(value.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, Mapping):
                payload = candidate
                break
    if not isinstance(payload, Mapping):
        raise WeeklyFeishuCliError("lark_cli_output_not_json")
    return payload


def _run_cli(args: list[str], *, cwd: Path, timeout: float = 90.0, retries: int = 2) -> Mapping[str, Any]:
    env = dict(os.environ)
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    last_code: int | None = None
    for attempt in range(max(0, int(retries)) + 1):
        try:
            completed = subprocess.run(
                args,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            if attempt < retries:
                time.sleep(0.5 * (2**attempt))
                continue
            raise WeeklyFeishuCliError("lark_cli_timeout") from exc
        except OSError as exc:
            raise WeeklyFeishuCliError(f"lark_cli_exec:{type(exc).__name__}") from exc
        if completed.returncode == 0:
            payload = _parse_cli_json(completed.stdout)
            if payload.get("ok") is not True:
                error = payload.get("error") if isinstance(payload.get("error"), Mapping) else {}
                raise WeeklyFeishuCliError(f"lark_cli_api:{error.get('type', 'unknown')}")
            return payload
        last_code = completed.returncode
        if attempt < retries:
            time.sleep(0.5 * (2**attempt))
    # Do not persist or expose CLI stderr: it may contain auth metadata.
    raise WeeklyFeishuCliError(f"lark_cli_exit:{last_code}")


def _upload_snapshot(path: Path, *, output_root: Path, cli: str) -> str:
    resolved_root = output_root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise WeeklyFeishuCliError("snapshot_path_outside_output_root") from exc
    if not resolved_path.is_file() or resolved_path.stat().st_size <= 0:
        raise WeeklyFeishuCliError("snapshot_file_missing")
    payload = _run_cli(
        [
            cli,
            "im",
            "images",
            "create",
            "--as",
            "bot",
            "--data",
            '{"image_type":"message"}',
            "--file",
            f"image={relative.as_posix()}",
            "--format",
            "json",
        ],
        cwd=resolved_root,
    )
    data = payload.get("data") if isinstance(payload.get("data"), Mapping) else {}
    image_key = data.get("image_key")
    if not isinstance(image_key, str) or not image_key.startswith("img_"):
        raise WeeklyFeishuCliError("lark_cli_image_key_missing")
    return image_key


def _text(text: str) -> dict[str, str]:
    return {"tag": "text", "text": text}


def _image(image_key: str, alt: str) -> dict[str, Any]:
    return {
        "tag": "img",
        "image_key": image_key,
        "alt": {"tag": "plain_text", "content": alt[:120]},
    }


def _link(text: str, href: str) -> dict[str, str]:
    return {"tag": "a", "text": text, "href": href}


def _line(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return list(items)


def _statement(card: Mapping[str, Any], timeframe: str) -> str:
    analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
    value = analysis.get(timeframe) if isinstance(analysis, Mapping) else None
    if isinstance(value, Mapping) and str(value.get("text") or "").strip():
        return str(value["text"]).strip()
    if analysis.get("failure_code") == "both_providers_failed":
        return "本周期行情图表可用；DeepSeek 与 Codex CLI 均未生成解释。"
    if analysis.get("failure_code") == "source_unavailable":
        return "本周期数据源暂不可用，未使用旧数据替代。"
    return "本周期解释暂缺，图表仍可直接查看。"


def _summary_lines(card: Mapping[str, Any]) -> list[str]:
    analysis = card.get("analysis") if isinstance(card.get("analysis"), Mapping) else {}
    lines: list[str] = []
    for field, label in (("position", "位置"), ("structure", "结构"), ("odds", "赔率"), ("synthesis", "综合结论"), ("theoretical_implication", "市场含义")):
        value = analysis.get(field)
        if isinstance(value, Mapping) and str(value.get("text") or "").strip():
            lines.append(f"{label}：{str(value['text']).strip()}")
    return lines


def _asset_rows(card: Mapping[str, Any], *, image_keys: Mapping[str, str]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    name = str(card.get("display_name") or _display_name(card.get("asset_key")))
    instrument = card.get("instrument") if isinstance(card.get("instrument"), Mapping) else {}
    ticker = str(instrument.get("ticker") or "")
    rows.append(_line(_text(f"{name}{f'（{ticker}）' if ticker else ''}")))
    for slot in card.get("chart_slots") or []:
        if not isinstance(slot, Mapping):
            continue
        timeframe = str(slot.get("timeframe") or "")
        label = TIMEFRAME_LABELS.get(timeframe, timeframe)
        rows.append(_line(_text(label)))
        key = str(slot.get("slot_id") or "")
        image_key = image_keys.get(key)
        if image_key:
            rows.append(_line(_image(image_key, f"{name} {label} K 线")))
        else:
            reason = str((slot.get("feature") or {}).get("failure_code") or "图表不可用") if isinstance(slot.get("feature"), Mapping) else "图表不可用"
            rows.append(_line(_text(f"{label}图表暂缺：{reason}")))
        rows.append(_line(_text(_statement(card, timeframe))))
    for line in _summary_lines(card):
        rows.append(_line(_text(line)))
    rows.append(_line(_text("")))
    return rows


def _post_payload(title: str, rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "timestamp": str(int(time.time())),
        "msg_type": "post",
        "content": {"post": {"zh_cn": {"title": title, "content": rows}}},
    }


def _send_webhook(payload: Mapping[str, Any], *, env_file: Path) -> None:
    webhook = _read_env_value("FEISHU_BOT_WEBHOOK", env_file)
    if not webhook:
        raise WeeklyFeishuCliError("feishu_webhook_missing")
    secret = _read_env_value("FEISHU_BOT_SECRET", env_file)
    body = dict(payload)
    timestamp = str(body.get("timestamp") or int(time.time()))
    body["timestamp"] = timestamp
    if secret:
        body["sign"] = _signature(secret, timestamp)
    request = Request(
        webhook,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise WeeklyFeishuCliError(f"feishu_transport_failed:{type(exc).__name__}") from exc
    code = result.get("code", result.get("StatusCode", 0)) if isinstance(result, Mapping) else None
    if code not in (0, "0"):
        raise WeeklyFeishuCliError(f"feishu_rejected:code_{code}")


def send_weekly_rich_posts(
    report: Mapping[str, Any],
    *,
    output_root: Path,
    env_file: Path,
) -> dict[str, Any]:
    """Upload current snapshots with lark-cli and send grouped rich posts."""

    cli = _resolve_lark_cli()
    cards = {
        str(card.get("asset_key")): card
        for card in report.get("cards") or []
        if isinstance(card, Mapping) and card.get("asset_key")
    }
    image_keys: dict[str, str] = {}
    uploaded = 0
    for card in cards.values():
        for slot in card.get("chart_slots") or []:
            if not isinstance(slot, Mapping) or slot.get("status") != "complete":
                continue
            snapshot = slot.get("snapshot") if isinstance(slot.get("snapshot"), Mapping) else None
            asset = snapshot.get("asset") if isinstance(snapshot, Mapping) and isinstance(snapshot.get("asset"), Mapping) else None
            relative = str(asset.get("path") or "") if asset else ""
            if not relative:
                continue
            image_keys[str(slot.get("slot_id"))] = _upload_snapshot(output_root / relative, output_root=output_root, cli=cli)
            uploaded += 1

    coverage = report.get("chart_coverage") if isinstance(report.get("chart_coverage"), Mapping) else {}
    cover_rows = [
        _line(_text(f"宏观 K 线周报｜{report.get('week_end')}")),
        _line(_text("本报告只基于周线、日线和已声明的 4 小时 K 线。")),
        _line(_text(f"图表覆盖：{int(coverage.get('ready') or 0)}/{int(coverage.get('expected') or 0)}，缺失 {int(coverage.get('missing') or 0)}")),
    ]
    _send_webhook(_post_payload(f"宏观 K 线周报｜{report.get('week_end')}", cover_rows), env_file=env_file)
    post_count = 1
    for group_name, keys in WEEKLY_GROUPS:
        rows: list[list[dict[str, Any]]] = []
        for key in keys:
            card = cards.get(key)
            if card:
                rows.extend(_asset_rows(card, image_keys=image_keys))
        if not rows:
            continue
        # Keep each category within Feishu's practical rich-post size.
        current: list[list[dict[str, Any]]] = []
        part = 1
        for row in rows:
            candidate = current + [row]
            encoded = json.dumps(_post_payload(group_name, candidate), ensure_ascii=False)
            if current and len(encoded) > FEISHU_POST_LIMIT:
                _send_webhook(_post_payload(f"{group_name}｜第 {part} 部分", current), env_file=env_file)
                post_count += 1
                part += 1
                current = [row]
            else:
                current = candidate
        if current:
            _send_webhook(_post_payload(group_name if part == 1 else f"{group_name}｜第 {part} 部分", current), env_file=env_file)
            post_count += 1
    content_hash = hashlib.sha256(
        json.dumps({"report_id": report.get("report_id"), "image_keys": sorted(image_keys), "post_count": post_count}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "status": "sent",
        "mode": "lark_cli_rich_post",
        "week_end": report.get("week_end"),
        "report_id": report.get("report_id"),
        "post_count": post_count,
        "image_count": uploaded,
        "content_sha256": content_hash,
    }


__all__ = ["DEFAULT_WEEKLY_ENV_FILE", "WeeklyFeishuCliError", "send_weekly_rich_posts"]
