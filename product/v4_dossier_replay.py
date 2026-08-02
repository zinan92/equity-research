"""Package already-produced canonical Round 7 dossiers through V4.

Replay intentionally does not regenerate prose.  It accepts only the exact
nine-chapter canonical reader contract; the retired seven-section mapped
artifact fails validation and remains a historical failure sample.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from v4_dossier_contract import V4_HEADINGS, validate_v4_dossier


REPLAY_SCHEMA_VERSION = "park-v4-replay-receipt-v2"
_SOURCE_ROW_RE = re.compile(r"^\|\s*S-\d+\s+\|", re.MULTILINE)


@dataclass(frozen=True)
class V4ReplaySample:
    ticker: str
    industry: str
    path: str
    sha256: str
    characters: int
    reader_characters: int
    source_rows: int
    source_ids: tuple[str, ...]
    validation: str
    validation_errors: tuple[str, ...]
    generation_mode: str = "replay_canonical_round7"
    is_live_research: bool = False


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reader_characters(text: str) -> int:
    start = min((text.find(f"## {heading}") for heading in V4_HEADINGS if text.find(f"## {heading}") >= 0), default=0)
    production = text.find("## 9. 生产记录")
    if production < 0:
        production = text.find("## 生产记录")
    end = production if production >= 0 else len(text)
    return len(text[start:end].strip()) if end > start else 0


def _source_ids(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\[S-\d{2}\]", text)))


def replay_sample(*, ticker: str, industry: str, path: Path, preview_only: bool = False) -> V4ReplaySample:
    text = path.read_text(encoding="utf-8")
    errors = list(validate_v4_dossier(text, preview_only=preview_only))
    frontmatter = re.search(r"\A---\n.*?^ticker:\s*([^\s]+)\s*$.*?\n---", text, re.MULTILINE | re.DOTALL)
    declared_ticker = str(frontmatter.group(1)).strip().strip('"\'').upper() if frontmatter else ""
    if not declared_ticker:
        errors.append("replay frontmatter ticker missing")
    elif declared_ticker != ticker.upper():
        errors.append(f"replay ticker mismatch: expected {ticker.upper()}, got {declared_ticker}")
    return V4ReplaySample(
        ticker=ticker.upper(),
        industry=industry,
        path=str(path),
        sha256=_sha256(text),
        characters=len(text),
        reader_characters=_reader_characters(text),
        source_rows=len(_SOURCE_ROW_RE.findall(text)),
        source_ids=_source_ids(text),
        validation="passed" if not errors else "failed",
        validation_errors=tuple(errors),
    )


def build_replay_receipt(samples: Iterable[V4ReplaySample]) -> dict[str, object]:
    rows = tuple(samples)
    if not rows:
        raise ValueError("at least one V4 sample is required")
    if len({row.ticker for row in rows}) != len(rows):
        raise ValueError("ticker must be unique in a V4 replay set")
    if any(row.validation != "passed" for row in rows):
        raise ValueError("V4 replay set contains a failed sample")
    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "contract_schema_version": "park-v4-dossier-v1",
        "generation_mode": "replay_canonical_round7",
        "is_live_research": False,
        "fresh_model_calls": 0,
        "new_official_documents": 0,
        "sample_count": len(rows),
        "shared_reader_contract": list(V4_HEADINGS),
        "samples": [asdict(row) for row in rows],
        "boundary": "Replay proves cross-company reader compatibility only; it creates no new facts, recommendation, target, position or action.",
    }


def build_reader_index(receipt: dict[str, object], *, title: str = "Park V4 · Cross-company reader index") -> str:
    rows = receipt.get("samples") or []
    buttons = []
    panels = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        active = " active" if index == 0 else ""
        ticker = str(row.get("ticker") or "")
        buttons.append(f'<button class="tab{active}" data-target="panel-{index}">{ticker} · {row.get("industry", "")}</button>')
        source = Path(str(row.get("path") or ""))
        body = source.read_text(encoding="utf-8") if source.is_file() else "档案路径不可读：" + str(source)
        panels.append(
            f'<section id="panel-{index}" class="panel{active}"><div class="meta">{ticker} · {row.get("industry", "")} · {row.get("reader_characters", 0)} reader chars · {row.get("source_rows", 0)} source rows · replay only</div><pre>{_escape(body)}</pre></section>'
        )
    payload = json.dumps(receipt, ensure_ascii=False, indent=2)
    return """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><title>Park V4 · Cross-company reader index</title>
<style>body{font-family:ui-sans-serif,system-ui;margin:0;background:#f4f1eb;color:#24211d}header{padding:28px 7vw;background:#171614;color:#fff}h1{margin:0 0 8px;font-size:28px}.notice{color:#e9c78d}.tabs{display:flex;gap:8px;flex-wrap:wrap;padding:20px 7vw 0}.tab{border:1px solid #b6aa99;background:#fff6e7;border-radius:999px;padding:10px 16px;cursor:pointer}.tab.active{background:#222;color:#fff}.panel{display:none;margin:20px 7vw 50px;background:#fff;border:1px solid #d8d0c4;border-radius:14px;overflow:hidden}.panel.active{display:block}.meta{padding:14px 18px;background:#f0e9df;font-size:13px;color:#655b51}pre{margin:0;padding:24px;white-space:pre-wrap;line-height:1.65;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}footer{padding:20px 7vw;color:#6d645a;font-size:12px}</style>
<header><h1>Park V4 · Cross-company reader index</h1><div class="notice">同一 Ainiu/Round 7 reader contract；以下是既有档案回放，不是新模型生成，也不是 live research。</div></header>
<nav class="tabs">__BUTTONS__</nav>__PANELS__
<footer>receipt: <code>__RECEIPT__</code></footer>
<script>document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.target).classList.add('active')})</script>
</html>""".replace("__BUTTONS__", "".join(buttons)).replace("__PANELS__", "".join(panels)).replace("__RECEIPT__", _escape(payload))


def _escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
