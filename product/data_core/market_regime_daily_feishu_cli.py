"""Reader-facing Feishu image delivery for the Daily K-line Newsletter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .market_regime_reader_projection import project_daily_asset
from .market_regime_weekly_feishu_cli import (
    FEISHU_POST_LIMIT,
    WeeklyFeishuCliError as DailyFeishuCliError,
    _image,
    _line,
    _post_payload,
    _resolve_lark_cli,
    _send_webhook,
    _text,
    _upload_snapshot,
)


DEFAULT_DAILY_ENV_FILE = Path(
    "/Users/wendy/Library/Application Support/ParkKlineDaily/daily-feishu.env"
)
TIMEFRAME_LABELS = {"daily": "日线", "four_hour": "4 小时", "thirty_minute": "30 分钟"}
DAILY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("共有资产 · 钱的价格", ("dxy",)),
    ("共有资产 · 风险资产", ("sp500", "nasdaq", "us_dividend", "vix")),
    ("共有资产 · 加密资产永续", ("bitcoin", "ethereum", "hype")),
    ("共有资产 · 亚洲与 A 股", ("shanghai", "star50", "china_dividend", "nikkei", "kospi")),
    ("共有资产 · 实物资产", ("wti", "gold", "silver")),
    ("美国国债 · 日线并列", ("us2y", "us10y", "us2s10s")),
)


def _asset_map(analysis_bundle: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(asset.get("asset_key")): asset
        for asset in analysis_bundle.get("assets") or []
        if isinstance(asset, Mapping) and asset.get("asset_key")
    }


def _period_key(asset_key: str, timeframe: str) -> str:
    return f"{asset_key}:{timeframe}"


def _upload_all_snapshots(
    analysis_bundle: Mapping[str, Any], *, output_root: Path, cli: str
) -> tuple[dict[str, str], int]:
    image_keys: dict[str, str] = {}
    expected = 0
    for asset in analysis_bundle.get("assets") or []:
        if not isinstance(asset, Mapping):
            continue
        snapshots = asset.get("snapshots") if isinstance(asset.get("snapshots"), Mapping) else {}
        for timeframe, snapshot in snapshots.items():
            if not isinstance(snapshot, Mapping):
                continue
            asset_ref = snapshot.get("asset") if isinstance(snapshot.get("asset"), Mapping) else {}
            relative = str(asset_ref.get("path") or "")
            if not relative:
                continue
            expected += 1
            image_keys[_period_key(str(asset.get("asset_key")), str(timeframe))] = _upload_snapshot(
                output_root / relative,
                output_root=output_root,
                cli=cli,
            )
    if len(image_keys) != expected:
        raise DailyFeishuCliError("daily_feishu_snapshot_upload_incomplete")
    return image_keys, expected


def _statement(projection: Mapping[str, Any], timeframe: str) -> str:
    for period in projection.get("periods") or []:
        if isinstance(period, Mapping) and period.get("timeframe") == timeframe:
            text = str(period.get("text") or "").strip()
            if text:
                return text
    return "本周期文字解读暂缺；图表仍可直接查看。"


def _summary_rows(projection: Mapping[str, Any]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for field, label in (
        ("position", "位置"),
        ("structure", "结构"),
        ("odds", "赔率"),
        ("synthesis", "综合结论"),
        ("market_meaning", "市场含义"),
    ):
        value = projection.get(field)
        if isinstance(value, Mapping) and str(value.get("text") or "").strip():
            rows.append(_line(_text(f"{label}：{str(value['text']).strip()}")))
    return rows


def _asset_rows(
    projection: Mapping[str, Any], *, image_keys: Mapping[str, str]
) -> list[list[dict[str, Any]]]:
    asset_key = str(projection.get("asset_key") or "")
    name = str(projection.get("display_name") or asset_key or "资产")
    caption = str(projection.get("instrument_caption") or "").strip()
    rows: list[list[dict[str, Any]]] = [_line(_text(f"{name}{f'（{caption}）' if caption else ''}"))]
    for period in projection.get("periods") or []:
        if not isinstance(period, Mapping):
            continue
        timeframe = str(period.get("timeframe") or "")
        label = TIMEFRAME_LABELS.get(timeframe, timeframe)
        rows.append(_line(_text(label)))
        image_key = image_keys.get(_period_key(asset_key, timeframe))
        if image_key:
            rows.append(_line(_image(image_key, f"{name} {label} K 线")))
        else:
            rows.append(_line(_text(f"{label}图表暂缺；文字解读仍按实际状态呈现。")))
        rows.append(_line(_text(_statement(projection, timeframe))))
    rows.extend(_summary_rows(projection))
    rows.append(_line(_text("")))
    return rows


def _send_rows(title: str, rows: list[list[dict[str, Any]]], *, env_file: Path) -> int:
    current: list[list[dict[str, Any]]] = []
    post_count = 0
    part = 1
    for row in rows:
        candidate = current + [row]
        encoded = json.dumps(_post_payload(title, candidate), ensure_ascii=False)
        if current and len(encoded) > FEISHU_POST_LIMIT:
            suffix = f"｜第 {part} 部分" if part > 1 else ""
            _send_webhook(_post_payload(f"{title}{suffix}", current), env_file=env_file)
            post_count += 1
            part += 1
            current = [row]
        else:
            current = candidate
    if current:
        suffix = f"｜第 {part} 部分" if part > 1 else ""
        _send_webhook(_post_payload(f"{title}{suffix}", current), env_file=env_file)
        post_count += 1
    return post_count


def _thesis_rows(thesis: Mapping[str, Any]) -> list[list[dict[str, Any]]]:
    output = thesis.get("output") if isinstance(thesis.get("output"), Mapping) else thesis
    if not isinstance(output, Mapping) or output.get("generation_status") != "model_generated_unreviewed":
        return [_line(_text("今日综合结论暂缺；以下保留各资产的真实 K 线与文字解读。"))]
    rows: list[list[dict[str, Any]]] = []
    posture = {"attack": "进攻", "wait": "等待", "defense": "防守", "no_view": "无方向观点"}.get(
        str(output.get("posture")), str(output.get("posture") or "")
    )
    headline = output.get("headline") if isinstance(output.get("headline"), Mapping) else {}
    if str(headline.get("text") or "").strip():
        rows.append(_line(_text(f"今日姿态：{posture} · {str(headline['text']).strip()}")))
    for field, label in (("what_happened", "发生了什么"), ("world_model", "世界模型"), ("capital_migration", "价格关系"), ("actions", "操作框架")):
        value = output.get(field)
        if isinstance(value, Mapping) and str(value.get("text") or "").strip():
            rows.append(_line(_text(f"{label}：{str(value['text']).strip()}")))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping) and str(item.get("text") or "").strip():
                    rows.append(_line(_text(f"{label}：{str(item['text']).strip()}")))
    rows.append(_line(_text("")))
    return rows


def send_daily_rich_posts(
    analysis_bundle: Mapping[str, Any],
    thesis: Mapping[str, Any],
    *,
    output_root: Path,
    env_file: Path = DEFAULT_DAILY_ENV_FILE,
) -> dict[str, Any]:
    """Upload the current Daily snapshots and send grouped reader posts."""

    cli = _resolve_lark_cli()
    image_keys, image_count = _upload_all_snapshots(
        analysis_bundle, output_root=output_root, cli=cli
    )
    assets = _asset_map(analysis_bundle)
    report_date = str(analysis_bundle.get("cutoff_at") or "")[:10]
    total_assets = len(assets)
    source_status = str(analysis_bundle.get("source_status") or "unknown")
    cover_rows = [
        _line(_text(f"宏观 K 线日报｜{report_date}")),
        _line(_text(f"主对照资产：16 个；美国国债：2Y、10Y、2s10s（日线并列）")),
        _line(_text(f"数据状态：{source_status} · 资产数：{total_assets} · 图表：{image_count} 张")),
        *_thesis_rows(thesis),
    ]
    post_count = _send_rows(f"宏观 K 线日报｜{report_date}", cover_rows, env_file=env_file)
    for group_name, keys in DAILY_GROUPS:
        rows: list[list[dict[str, Any]]] = []
        for key in keys:
            projection = project_daily_asset(assets[key]) if key in assets else None
            if projection:
                rows.extend(_asset_rows(projection, image_keys=image_keys))
        if rows:
            post_count += _send_rows(group_name, rows, env_file=env_file)
    content_hash = hashlib.sha256(
        json.dumps(
            {
                "analysis_bundle_id": analysis_bundle.get("bundle_id"),
                "image_keys": sorted(image_keys),
                "post_count": post_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "status": "sent",
        "mode": "lark_cli_rich_post",
        "report_date": report_date,
        "analysis_bundle_id": analysis_bundle.get("bundle_id"),
        "post_count": post_count,
        "image_count": image_count,
        "content_sha256": content_hash,
    }


__all__ = ["DEFAULT_DAILY_ENV_FILE", "DailyFeishuCliError", "send_daily_rich_posts"]
