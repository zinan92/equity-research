"""Small reader renderer for the V4/Ainiu dossier contract."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any

from v4_dossier_contract import assert_valid_v4_dossier
from v4_dossier_generator import generate_v4_dossier


PUBLICATION_SCHEMA_VERSION = "park-v4-publication-receipt-v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inline(value: str) -> str:
    escaped = html.escape(value)
    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_v4_html(markdown: str, *, title: str) -> str:
    """Render only the stable V4 Markdown subset; no legacy report model."""
    assert_valid_v4_dossier(markdown)
    out = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>",
        "<style>body{max-width:980px;margin:0 auto;padding:28px 24px 72px;background:#f7f4ee;color:#27231f;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;line-height:1.75}main{background:#fff;padding:28px 34px;box-shadow:0 8px 30px #2d24120d}h1{font-size:30px;margin:0 0 12px;color:#191613}h2{font-size:23px;margin:44px 0 12px;color:#513c26;border-bottom:2px solid #ddc49d;padding-bottom:7px}h3{color:#79562f;margin-top:28px}p{margin:11px 0}blockquote{margin:18px 0;padding:12px 16px;background:#fff4dc;border-left:4px solid #b47b31;color:#63451e}table{width:100%;border-collapse:collapse;margin:16px 0;font-size:14px}th,td{border:1px solid #dfd7ca;padding:8px 10px;text-align:left;vertical-align:top}th{background:#f3eadc}code{overflow-wrap:anywhere;color:#72552f}a{color:#27608a}footer{margin-top:30px;color:#70665b;font-size:12px}</style></head><body><main>",
    ]
    in_frontmatter = False
    table: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table
        if not table:
            return
        rows = [row for row in table if not all(set(cell.replace(":", "")) <= {"-"} for cell in row)]
        if rows:
            out.append("<table>")
            for index, row in enumerate(rows):
                tag = "th" if index == 0 else "td"
                out.append("<tr>" + "".join(f"<{tag}>{_inline(cell)}</{tag}>" for cell in row) + "</tr>")
            out.append("</table>")
        table = []

    for line in markdown.splitlines():
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        if line.startswith("|") and line.endswith("|"):
            table.append([item.strip() for item in line.strip("|").split("|")])
            continue
        flush_table()
        if not line.strip():
            continue
        if line.startswith("# "):
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        elif line.startswith("- "):
            out.append(f"<p>• {_inline(line[2:])}</p>")
        else:
            out.append(f"<p>{_inline(line)}</p>")
    flush_table()
    out.append("</main><footer>Park V4 · Ainiu/Round 7 reader contract · pending human review</footer></body></html>")
    return "".join(out)


def _index(rows: list[dict[str, Any]]) -> str:
    cards = []
    for row in rows:
        cards.append(
            f"<article><h2><a href='{html.escape(row['relative_html'])}'>{html.escape(row['ticker'])}</a></h2>"
            f"<p>{row['reader_characters']} reader chars · {row['source_count']} official source URLs</p>"
            "<p class='notice'>含未审阅研究判断 · 不提供目标价、仓位或买卖建议</p></article>"
        )
    return "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Park V4 dossiers</title><style>body{max-width:960px;margin:0 auto;padding:40px 24px;background:#f7f4ee;color:#27231f;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}article{background:#fff;border:1px solid #dfd7ca;border-radius:12px;padding:18px 22px;margin:16px 0}a{color:#79562f}.notice{color:#87551c}</style><h1>Park V4 · Ainiu/Round 7 dossiers</h1><p>同一整档契约、官方页级证据绑定；两份档案均待人工审阅。</p>" + "".join(cards) + "</html>"


def build_v4_publication(*, source_root: Path, output_root: Path, tickers: tuple[str, ...] = ("300750.SZ", "600519.SH")) -> dict[str, Any]:
    source_receipt = json.loads((source_root / "receipt.json").read_text(encoding="utf-8"))
    by_ticker = {str(row["ticker"]): row for row in source_receipt.get("companies", [])}
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        source_path = source_root / f"{ticker}.md"
        source_row = by_ticker.get(ticker)
        if not source_path.is_file() or not source_row:
            raise FileNotFoundError(f"missing V4 source output for {ticker}")
        company_dir = output_root / ticker
        company_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = company_dir / "evidence-manifest.json"
        manifest_path.write_text(json.dumps({"ticker": ticker, "source_urls": source_row["source_urls"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt = generate_v4_dossier(
            ticker=ticker,
            output_dir=company_dir,
            completed_markdown_path=source_path,
            evidence_manifest_path=manifest_path,
        )
        markdown = (company_dir / f"{ticker}.md").read_text(encoding="utf-8")
        html_path = company_dir / "report.html"
        html_path.write_text(render_v4_html(markdown, title=f"{ticker} · Park V4 公司档案"), encoding="utf-8")
        rows.append({
            "ticker": ticker,
            "markdown_path": str(company_dir / f"{ticker}.md"),
            "html_path": str(html_path),
            "relative_html": f"{ticker}/report.html",
            "markdown_sha256": _sha(company_dir / f"{ticker}.md"),
            "html_sha256": _sha(html_path),
            "reader_characters": receipt["reader_characters"],
            "source_count": len(receipt["source_urls"]),
            "status": receipt["status"],
            "tier_credit": receipt["tier_credit"],
        })
    index_path = output_root / "index.html"
    index_path.write_text(_index(rows), encoding="utf-8")
    publication = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "status": "passed",
        "contract_schema_version": "park-v4-dossier-v1",
        "source_receipt": str(source_root / "receipt.json"),
        "source_receipt_sha256": _sha(source_root / "receipt.json"),
        "index_path": str(index_path),
        "index_sha256": _sha(index_path),
        "companies": rows,
        "fresh_model_calls": 0,
        "new_official_documents": 0,
        "is_live_research": False,
        "tier_credit": "none",
        "boundary": "Reader publication only; pending human review and no investment action fields.",
    }
    (output_root / "publication-receipt.json").write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return publication
