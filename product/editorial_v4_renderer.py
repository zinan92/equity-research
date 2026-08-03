"""Deterministic Markdown/HTML renderer for review-only editorial V4."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Mapping


def _md_inline(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _body_html(body: str) -> str:
    chunks: list[str] = []
    for raw in str(body).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            chunks.append(f"<li>{_md_inline(line[2:])}</li>")
        else:
            chunks.append(f"<p>{_md_inline(line)}</p>")
    if any(chunk.startswith("<li>") for chunk in chunks):
        # Keep paragraphs and bullet items readable without guessing markdown.
        return "<div>" + "".join(chunks) + "</div>"
    return "".join(chunks)


def render_markdown(dossier: Mapping[str, Any], packet: Mapping[str, Any]) -> str:
    name = dossier.get("issuer_name") or packet.get("issuer_name") or dossier.get("ticker")
    lines = [
        f"**📊 V4审阅草稿｜{name}（{dossier.get('ticker')}）**",
        "（仅使用官方 PDF 页级证据；公司披露已标注；未通过真人审阅，不产生 Tier/行动/公开发布资格）",
        "",
        f"# {name}({dossier.get('ticker')}) 深度研究档案",
        "",
        str(dossier.get("latest_card") or "输入未提供可靠最新数据"),
        "",
    ]
    for row in dossier.get("sections") or []:
        lines.extend([f"## {row.get('title')}", "", str(row.get("body") or "").strip(), ""])
    lines.extend(["## Sources / 生产记录", "", "### 来源", ""])
    for index, source in enumerate(packet.get("sources") or [], start=1):
        lines.append(
            f"- [S-{index:02d}] {source.get('title')}｜{source.get('report_period')}｜"
            f"document_id={source.get('document_id')}｜pages={source.get('page_count')}｜"
            f"raw_sha256={source.get('raw_sha256')}｜{source.get('source_url')}"
        )
    lines.extend(["", "### 证据边界", "", "- 官方年报/季报是公司披露，不等于独立验证。", "- 未绑定页级 evidence 的数字、客户、排名、订单、估值与行动保持缺失。", "", "### 生产记录", "", "```json", json.dumps(dossier.get("production_record") or {}, ensure_ascii=False, indent=2), "```", "", "### 研究结论", "", str(dossier.get("overall_conclusion") or ""), ""])
    return "\n".join(lines).rstrip() + "\n"


def render_html(dossier: Mapping[str, Any], packet: Mapping[str, Any], markdown: str) -> str:
    name = html.escape(str(dossier.get("issuer_name") or packet.get("issuer_name") or dossier.get("ticker")))
    ticker = html.escape(str(dossier.get("ticker") or ""))
    sections = []
    for row in dossier.get("sections") or []:
        sections.append(f"<section><h2>{html.escape(str(row.get('title') or ''))}</h2>{_body_html(str(row.get('body') or ''))}</section>")
    source_items = []
    for index, source in enumerate(packet.get("sources") or [], start=1):
        source_items.append(
            f"<li><code>[S-{index:02d}]</code> {html.escape(str(source.get('title') or ''))} · "
            f"{html.escape(str(source.get('report_period') or ''))} · "
            f"p{html.escape(str(source.get('page_count') or '?'))} · "
            f"<a href=\"{html.escape(str(source.get('source_url') or ''))}\">官方 PDF</a></li>"
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{name} V4 Editorial</title>
<style>body{{margin:0;background:#f4f0e8;color:#1f2933;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif;line-height:1.75}}main{{max-width:860px;margin:0 auto;background:#fff;padding:28px 22px 72px;box-sizing:border-box}}.badge{{display:inline-block;background:#fff1d6;border:1px solid #e4bd76;padding:4px 9px;border-radius:999px;font-size:12px;color:#7a4b00}}h1{{font-size:28px;line-height:1.25;margin:18px 0 10px}}h2{{font-size:22px;border-left:4px solid #b7791f;padding-left:10px;margin-top:34px}}h3{{font-size:16px;margin-top:26px}}p{{margin:10px 0}}section{{border-top:1px solid #ece7dc;padding-top:5px}}.card{{background:#18232f;color:#fff;padding:16px;border-radius:12px;margin:16px 0;font-size:17px}}.sources{{background:#faf9f5;padding:12px 18px;border-radius:10px;font-size:13px}}a{{color:#8a4b08}}code{{font-size:.9em}}@media(max-width:600px){{main{{padding:20px 15px 54px}}h1{{font-size:24px}}h2{{font-size:20px}}.card{{font-size:15px}}}}</style></head>
<body><main><span class="badge">V4 editorial · review-only · 未通过真人审阅</span><h1>{name}({ticker}) 深度研究档案</h1><div class="card">{_md_inline(str(dossier.get('latest_card') or '输入未提供可靠最新数据'))}</div>{''.join(sections)}<section class="sources"><h2>Sources / 生产记录</h2><p>官方 PDF 页级证据；公司披露已显式降级，不产生 Tier、行动或公开发布资格。</p><h3>来源</h3><ul>{''.join(source_items)}</ul><h3>结论</h3><p>{_md_inline(str(dossier.get('overall_conclusion') or ''))}</p><h3>生产记录</h3><pre>{html.escape(json.dumps(dossier.get('production_record') or {{}}, ensure_ascii=False, indent=2))}</pre></section></main></body></html>"""


def render_dossier(dossier: Mapping[str, Any], packet: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(dossier, packet)
    html_text = render_html(dossier, packet, markdown)
    md_path = out_dir / "report.md"
    html_path = out_dir / "report.html"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    return {"markdown_path": str(md_path), "html_path": str(html_path), "markdown_chars": str(len(markdown)), "html_bytes": str(len(html_text.encode("utf-8")))}
