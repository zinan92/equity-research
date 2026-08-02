"""Small reader renderer for the V4/Ainiu dossier contract."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any, Mapping

from v4_dossier_contract import assert_valid_v4_dossier
from v4_quality_gate import CANONICAL_SOURCE_DIR, REPO_ROOT, evaluate_round7_quality, portable_path, write_quality_gate_receipt


PUBLICATION_SCHEMA_VERSION = "park-v4-publication-receipt-v1"
_TICKER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reader_characters(markdown: str) -> int:
    starts = [markdown.find(f"## {heading}") for heading in (
        "一句话定位", "身份、创始人与治理", "技术来源与发展史",
        "商业模式与业务线", "财务与经营时间序列", "护城河的证据链",
        "风险、反题材与观察触发器", "研究结论与待补问题",
    )]
    starts = [value for value in starts if value >= 0]
    end = markdown.find("## 9. 生产记录")
    return max(0, (end if end >= 0 else len(markdown)) - min(starts, default=0))


def _inline(value: str) -> str:
    escaped = html.escape(value)
    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_v4_html(markdown: str, *, title: str, review_status: str = "pending_human_review") -> str:
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
    footer = "pending human review" if review_status != "human_reviewed" else "human review recorded"
    out.append(f"</main><footer>Park V4 · Ainiu/Round 7 reader contract · {footer}</footer></body></html>")
    return "".join(out)


def _index(rows: list[dict[str, Any]], *, output_root: Path | None = None) -> str:
    cards = []
    for row in rows:
        # The index is a second independent fail-closed boundary.  Callers
        # cannot accidentally smuggle a pending/blocked row into public HTML.
        if row.get("publication_eligible") is not True:
            continue
        relative_html = str(row.get("relative_html") or "")
        ticker = str(row.get("ticker") or "")
        expected_relative = f"{ticker}/report.html"
        quality_path = str(row.get("quality_gate_path") or "")
        quality_sha = str(row.get("quality_gate_sha256") or "")
        if (
            not _TICKER_RE.fullmatch(ticker)
            or
            row.get("status") != "passed"
            or not row.get("publication_eligible") is True
            or not quality_path
            or not re.fullmatch(r"[0-9a-f]{64}", quality_sha)
            or relative_html != expected_relative
            or not re.fullmatch(r"[A-Za-z0-9._-]+/report\.html", relative_html)
        ):
            continue
        if output_root is not None:
            if not public_row_is_current(row, output_root=output_root):
                continue
        elif row.get("quality_gate_verified") is not True:
            # Direct callers must opt into a verified row; production callers
            # pass output_root so the receipt/file/hash checks run here.
            continue
        cards.append(
            f"<article><h2><a href='{html.escape(relative_html)}'>{html.escape(ticker)}</a></h2>"
            f"<p>{row['reader_characters']} reader chars · {row['source_count']} official source URLs</p>"
            "<p class='notice'>Round 7 canonical dossier · publication quality gate passed · no action fields</p></article>"
        )
    notice = (
        "可公开档案仅在 canonical Round 7 结构、证据绑定与质量闸门全部通过后出现。"
        if cards
        else "暂无可公开档案；pending/blocked 详情只在 publication-receipt.json 的 review_queue 中。"
    )
    return "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Park V4 dossiers</title><style>body{max-width:960px;margin:0 auto;padding:40px 24px;background:#f7f4ee;color:#27231f;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}article{background:#fff;border:1px solid #dfd7ca;border-radius:12px;padding:18px 22px;margin:16px 0}a{color:#79562f}.notice{color:#87551c}</style><h1>Park V4 · Ainiu/Round 7 canonical dossiers</h1><p>" + notice + "</p>" + "".join(cards) + "</html>"


def public_row_is_current(row: Mapping[str, Any], *, output_root: Path) -> bool:
    """Validate a retained public row before a single-ticker update.

    A publication update must not preserve a stale previously-passed link when
    its HTML or quality receipt was deleted/tampered after the last build.
    """
    if row.get("status") != "passed" or row.get("publication_eligible") is not True:
        return False
    ticker = str(row.get("ticker") or "")
    relative_html = str(row.get("relative_html") or "")
    if not _TICKER_RE.fullmatch(ticker) or relative_html != f"{ticker}/report.html":
        return False
    html_path = (output_root / relative_html).resolve()
    try:
        html_path.relative_to(output_root.resolve())
    except ValueError:
        return False
    if not html_path.is_file() or str(row.get("html_sha256") or "") != _sha(html_path):
        return False
    quality_value = str(row.get("quality_gate_path") or "")
    quality_sha = str(row.get("quality_gate_sha256") or "")
    if not quality_value:
        return False
    quality_candidates = []
    declared_quality_path = Path(quality_value)
    if declared_quality_path.is_absolute():
        quality_candidates.append(declared_quality_path.resolve())
    for base in (output_root.resolve(), REPO_ROOT.resolve()):
        candidate = (base / quality_value).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            continue
        quality_candidates.append(candidate)
    quality_path = next(
        (
            candidate
            for candidate in quality_candidates
            if candidate.is_file()
            and any(
                _is_within(candidate, base)
                for base in (output_root.resolve(), REPO_ROOT.resolve())
            )
        ),
        None,
    )
    if quality_path is None or not re.fullmatch(r"[0-9a-f]{64}", quality_sha) or _sha(quality_path) != quality_sha:
        return False
    try:
        gate = json.loads(quality_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        gate.get("ticker") == ticker
        and gate.get("status") == "passed"
        and gate.get("publication_eligible") is True
        and not gate.get("blockers")
        and re.fullmatch(r"[0-9a-f]{64}", str(gate.get("receipt_hash") or ""))
        and gate.get("receipt_hash") == hashlib.sha256(
            json.dumps({key: value for key, value in gate.items() if key != "receipt_hash"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        and gate.get("html_sha256") == row.get("html_sha256")
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _quarantine_stale_company_dir(*, output_root: Path, ticker: str) -> str | None:
    """Move a previously public company directory out of the public namespace.

    A failed refresh must not leave an older ``ticker/report.html`` reachable
    by guessed URL.  The move is recoverable: canonical publication uses the
    repository's legacy evidence root; temporary/test outputs use a hidden
    sibling inside that output root.
    """
    company_dir = output_root / ticker
    if not company_dir.is_dir():
        return None
    canonical_public_root = (REPO_ROOT / "artifacts" / "v4-reports").resolve()
    if output_root.resolve() == canonical_public_root:
        quarantine_root = REPO_ROOT / "artifacts" / "v4-reports-legacy"
    else:
        quarantine_root = output_root / ".blocked-history"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    target = quarantine_root / ticker
    if target.exists():
        marker = "stale"
        report = company_dir / "report.html"
        if report.is_file():
            marker = f"stale-{_sha(report)[:12]}"
        target = quarantine_root / f"{ticker}.{marker}"
        suffix = 1
        while target.exists():
            target = quarantine_root / f"{ticker}.{marker}.{suffix}"
            suffix += 1
    company_dir.rename(target)
    return portable_path(target)


def build_v4_publication(*, source_root: Path, output_root: Path, tickers: tuple[str, ...] = ("000001.SZ", "300750.SZ", "600519.SH")) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if source_root != CANONICAL_SOURCE_DIR.resolve():
        raise ValueError(
            "V4 publication only accepts the canonical Round 7 source root "
            f"{CANONICAL_SOURCE_DIR}; legacy mapped outputs are review-only"
        )
    try:
        output_root.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise ValueError("V4 publication output must not be inside canonical Round 7 source root")
    output_root.mkdir(parents=True, exist_ok=True)
    normalized_tickers = tuple(str(ticker).upper() for ticker in tickers)
    if len(set(normalized_tickers)) != len(normalized_tickers):
        raise ValueError("publication ticker set must be unique")
    rows: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []
    source_receipts: list[dict[str, Any]] = []
    for ticker in normalized_tickers:
        if not _TICKER_RE.fullmatch(ticker):
            raise ValueError(f"unsafe ticker: {ticker}")
        source_path = source_root / f"{ticker}.md"
        html_source = source_root / f"{ticker}.html"
        receipt_path = source_root / f"{ticker}.receipt.json"
        if not source_path.is_file() or not html_source.is_file() or not receipt_path.is_file():
            raise FileNotFoundError(f"missing canonical Round 7 output for {ticker}")
        gate = evaluate_round7_quality(
            dossier_path=receipt_path,
            markdown_path=source_path,
            html_path=html_source,
            require_canonical_root=True,
            expected_ticker=ticker,
        )
        gate_path = output_root / f"{ticker}.quality-gate.json"
        write_quality_gate_receipt(gate, gate_path)
        source_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        source_receipts.append({"ticker": ticker, "path": portable_path(receipt_path), "sha256": _sha(receipt_path), "run_id": (source_receipt.get("production_record") or {}).get("run_id"), "quality_gate": portable_path(gate_path), "quality_gate_sha256": _sha(gate_path)})
        if gate["publication_eligible"] is True:
            company_dir = output_root / ticker
            company_dir.mkdir(parents=True, exist_ok=True)
            output_md = company_dir / f"{ticker}.md"
            output_html = company_dir / "report.html"
            output_md.write_bytes(source_path.read_bytes())
            output_html.write_bytes(html_source.read_bytes())
            rows.append({
                "ticker": ticker,
                "markdown_path": str(output_md),
                "html_path": str(output_html),
                "relative_html": f"{ticker}/report.html",
                "markdown_sha256": _sha(output_md),
                "html_sha256": _sha(output_html),
                "reader_characters": _reader_characters(source_path.read_text(encoding="utf-8")),
                "source_count": len({str(item.get("source_url") or "") for item in source_receipt.get("source_manifest", []) if isinstance(item, Mapping) and item.get("source_url")}),
                "status": "passed",
                "tier_credit": "none",
                "publication_eligible": True,
                "quality_gate_path": portable_path(gate_path),
                "quality_gate_sha256": _sha(gate_path),
            })
        else:
            stale_path = _quarantine_stale_company_dir(output_root=output_root, ticker=ticker)
            review_queue.append({
                "ticker": ticker,
                "status": gate["status"],
                "quality_gate_path": portable_path(gate_path),
                "quality_gate_sha256": _sha(gate_path),
                "source_receipt_path": portable_path(receipt_path),
                "source_receipt_sha256": _sha(receipt_path),
                "run_id": (source_receipt.get("production_record") or {}).get("run_id"),
                "blocker_count": len(gate.get("blockers") or []),
                "blockers": gate.get("blockers") or [],
                "stale_publication_quarantined": stale_path,
            })
    index_path = output_root / "index.html"
    index_path.write_text(_index(rows, output_root=output_root), encoding="utf-8")
    review_payload = {"schema_version": "park-v4-publication-review-queue-v1", "items": review_queue}
    review_payload["receipt_hash"] = hashlib.sha256(json.dumps(review_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    (output_root / "review-queue.json").write_text(json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    overall_status = "passed" if rows and not review_queue else ("blocked" if any(item["status"] == "blocked" for item in review_queue) else "review_queue")
    publication = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "status": overall_status,
        "contract_schema_version": "park-v4-dossier-v1",
        "canonical_source_root": portable_path(source_root),
        "source_receipts": source_receipts,
        "index_path": portable_path(index_path),
        "index_sha256": _sha(index_path),
        "companies": rows,
        "review_queue": review_queue,
        "fresh_model_calls": 0,
        "new_official_documents": 0,
        "is_live_research": False,
        "tier_credit": "none",
        "boundary": "Reader publication only; blocked/pending canonical dossiers are review-only and never receive a public index/mobile link.",
    }
    publication["receipt_hash"] = hashlib.sha256(json.dumps(publication, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    (output_root / "publication-receipt.json").write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return publication
