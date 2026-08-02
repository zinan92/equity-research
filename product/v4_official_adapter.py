"""Adapt official-source Round 7 samples into the V4 reader shape.

This is an evidence-bound shape adapter, not a prose model. It reuses the
already audited official-source sample paragraphs and only changes headings
and chapter grouping. The receipt records that no new fact or model call was
created; M4 owns fresh whole-chapter generation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from v4_dossier_contract import validate_v4_dossier
from data_core.round7_evidence import OFFICIAL_HOSTS, canonical_hash
from data_core.round7_profiles import load_profile


ADAPTER_VERSION = "v4-official-evidence-adapter-v1"
ROUND7_ADAPTER_VERSION = "v4-round7-generated-adapter-v1"
_HEADING_RE = re.compile(r"^##\s+(?:(\d+)\.\s*)?(.+?)\s*$", re.MULTILINE)
_SOURCE_URL_RE = re.compile(r"https://static\.cninfo\.com\.cn/[^)\s|]+")


@dataclass(frozen=True)
class OfficialV4Output:
    ticker: str
    output_path: str
    input_sample_path: str
    input_sample_sha256: str
    narrative_receipt_id: str
    narrative_receipt_hash: str
    financial_receipt_hash: str
    source_urls: tuple[str, ...]
    output_sha256: str
    characters: int
    reader_characters: int
    validation: str
    validation_errors: tuple[str, ...]
    status: str = "pending_human_review"
    generation_mode: str = "official_evidence_adaptation"
    fresh_model_calls: int = 0
    new_official_documents: int = 0
    tier_credit: str = "none"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sections(text: str) -> dict[str, str]:
    matches = list(_HEADING_RE.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(2).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[heading] = text[match.end():end].strip()
    return result


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"')
    return result


def _boundary(body: str) -> str:
    match = re.search(r"^>\s+证据边界：.*$", body, re.MULTILINE)
    value = match.group(0) if match else "> 证据边界：本章只使用官方页级证据；研究判断与公司自述显式区分。"
    return value.replace("爱牛归档未作为事实来源", "未引入二手行业材料")


def _without_boundary(body: str) -> str:
    return re.sub(r"^>\s+证据边界：.*?\n\s*", "", body, count=1, flags=re.MULTILINE).strip()


def _reader_characters(markdown: str) -> int:
    headings = (
        "一句话定位", "产业坐标", "创始人与团队", "发展时间线",
        "技术、产品与商业模式", "财务与估值", "风险与点评",
    )
    starts = [markdown.find(f"## {heading}") for heading in headings]
    starts = [value for value in starts if value >= 0]
    end = markdown.find("## 9. 生产记录")
    return max(0, (end if end >= 0 else len(markdown)) - min(starts, default=0))


def _validate_generated_round7(
    *,
    ticker: str,
    dossier: Mapping[str, object],
    profile: Mapping[str, object] | None,
) -> tuple[str, ...]:
    if dossier.get("data_kind") != "real":
        raise ValueError("Round 7 adapter requires real dossier data")
    if str(dossier.get("ticker") or "").upper() != ticker.upper():
        raise ValueError("Round 7 dossier ticker mismatch")
    if dossier.get("review_status") != "pending_human_review":
        raise ValueError("Round 7 dossier review state is not pending")
    expected_content = canonical_hash(
        {
            key: value
            for key, value in dossier.items()
            if key not in {"content_hash", "artifacts", "receipt_hash"}
        }
    )
    if dossier.get("content_hash") != expected_content:
        raise ValueError("Round 7 dossier content hash mismatch")
    dossier_profile = dossier.get("issuer_profile")
    if profile is not None:
        if not isinstance(dossier_profile, Mapping):
            raise ValueError("Round 7 dossier is missing issuer profile")
        if dossier_profile.get("profile_hash") != profile.get("profile_hash"):
            raise ValueError("Round 7 dossier profile hash mismatch")
    source_receipts = dossier.get("source_receipts")
    if not isinstance(source_receipts, Mapping):
        raise ValueError("Round 7 dossier is missing source receipt bindings")
    for key in (
        "official_narrative_receipt_id",
        "official_narrative_receipt_hash",
        "financial_page_evidence_receipt_hash",
    ):
        if not str(source_receipts.get(key) or ""):
            raise ValueError(f"Round 7 source receipt field missing: {key}")
    production = dossier.get("production_record") or {}
    if profile is not None:
        if source_receipts.get("as_of") != production.get("known_at"):
            raise ValueError("Round 7 source receipt cutoff does not match known_at")
        expected_sources = profile.get("source_receipts") or {}
        actual_sources = {
            "narrative_receipt_hash": source_receipts.get(
                "official_narrative_receipt_hash"
            ),
            "financial_receipt_hash": source_receipts.get(
                "financial_page_evidence_receipt_hash"
            ),
        }
        for key, expected in expected_sources.items():
            if key in actual_sources and actual_sources[key] != expected:
                raise ValueError(f"Round 7 profile receipt binding mismatch: {key}")
    source_urls: list[str] = []
    for item in dossier.get("source_manifest") or ():
        if not isinstance(item, Mapping):
            raise ValueError("Round 7 source manifest row is invalid")
        url = str(item.get("source_url") or "")
        parsed = re.match(r"^https://([^/]+)/", url)
        if not parsed or parsed.group(1) not in OFFICIAL_HOSTS:
            raise ValueError("Round 7 source manifest contains a non-official URL")
        pages = item.get("pages_used")
        if not isinstance(pages, list) or not pages or any(type(page) is not int or page < 1 for page in pages):
            raise ValueError("Round 7 source manifest page binding is invalid")
        if len(str(item.get("raw_hash") or "")) != 64:
            raise ValueError("Round 7 source manifest raw hash is invalid")
        source_urls.append(url)
    if not source_urls:
        raise ValueError("Round 7 source manifest is empty")
    chapters = dossier.get("chapters") or []
    if len(chapters) != 8 or any(item.get("review_status") != "pending_human_review" for item in chapters):
        raise ValueError("Round 7 adapter requires eight pending-review research chapters")
    accepted_ids = list(production.get("accepted_model_request_ids") or [])
    if len(accepted_ids) != len(chapters) or len(set(accepted_ids)) != len(chapters):
        raise ValueError("Round 7 adapter requires one accepted request ID per chapter")
    if int(production.get("accepted_semantic_audits") or 0) != len(chapters):
        raise ValueError("Round 7 adapter requires a passing semantic audit per chapter")
    if not isinstance(production.get("typed_gaps"), list):
        raise ValueError("Round 7 adapter requires structured typed gaps")
    if (dossier.get("degradation") or {}).get("tier") != "B":
        raise ValueError("unreviewed Round 7 dossier must remain Tier B")
    return tuple(dict.fromkeys(source_urls))


def adapt_round7_dossier(
    *,
    ticker: str,
    dossier_path: Path,
    markdown_path: Path,
    profile_path: Path | None = None,
) -> tuple[str, dict[str, object]]:
    """Map a generated Round 7 document into V4 without writing new prose facts."""
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    profile = load_profile(profile_path, ticker=ticker) if profile_path else None
    source_urls = _validate_generated_round7(
        ticker=ticker,
        dossier=dossier,
        profile=profile,
    )
    sample = markdown_path.read_text(encoding="utf-8")
    sections = _sections(sample)
    required = (
        "一句话定位", "身份、创始人与治理", "技术来源与发展史", "商业模式与业务线",
        "财务与经营时间序列", "护城河的证据链", "风险、反题材与观察触发器",
        "研究结论与待补问题", "生产记录", "Sources",
    )
    missing = [heading for heading in required if heading not in sections]
    if missing:
        raise ValueError(f"generated Round 7 dossier missing sections: {missing}")
    if re.search(r"fixture|东财F10|Eastmoney F10|归档", sample, re.IGNORECASE):
        raise ValueError("generated Round 7 dossier contains forbidden fixture/archive wording")
    one_line = _without_boundary(sections["一句话定位"])
    business = _without_boundary(sections["商业模式与业务线"])
    financial = _without_boundary(sections["财务与经营时间序列"])
    valuation_gap = (
        "\n\n**估值待补（证据缺口）**：本次官方页级证据包未提供估值事实，"
        "因此不生成目标价、估值结论或仓位动作。"
    )
    risk = (
        f"{_boundary(sections['护城河的证据链'])}\n\n"
        f"### 护城河与可证伪条件\n\n{_without_boundary(sections['护城河的证据链'])}\n\n"
        f"### 核心风险与观察触发器\n\n{_without_boundary(sections['风险、反题材与观察触发器'])}\n\n"
        f"### 大白话点评\n\n{_without_boundary(sections['研究结论与待补问题'])}"
    )
    front = _frontmatter(sample)
    company = str((dossier.get("issuer") or {}).get("short_name") or front.get("company") or ticker.upper())
    lines = [
        "---",
        "schema_version: park-v4-dossier-v1",
        "status: pending_human_review",
        f"ticker: {ticker.upper()}",
        f"company: {company}",
        "evidence_mode: official_page_bound",
        f"adapter_version: {ROUND7_ADAPTER_VERSION}",
        f"round7_run_id: {dossier.get('production_record', {}).get('run_id')}",
        "---",
        "",
        f"{company}｜V4 公司档案",
        "",
        "> **审阅提示：本档案由一整章一调用的 Round 7 生成结果适配，含未审阅研究判断；不构成目标价、仓位或买卖建议。**",
        "",
    ]
    body_map = (
        ("一句话定位", one_line),
        (
            "产业坐标",
            f"{_boundary(sections['商业模式与业务线'])}\n\n"
            f"**产业链位置（研究判断）**：{business}\n\n"
            f"**大白话逻辑链**：{one_line}",
        ),
        ("创始人与团队", f"{_boundary(sections['身份、创始人与治理'])}\n\n{_without_boundary(sections['身份、创始人与治理'])}"),
        ("发展时间线", f"{_boundary(sections['技术来源与发展史'])}\n\n{_without_boundary(sections['技术来源与发展史'])}"),
        ("技术、产品与商业模式", f"{_boundary(sections['商业模式与业务线'])}\n\n{business}"),
        ("财务与估值", f"{_boundary(sections['财务与经营时间序列'])}\n\n{financial}{valuation_gap}"),
        ("风险与点评", risk),
    )
    for heading, body in body_map:
        lines.extend((f"## {heading}", "", body, ""))
    production = dossier["production_record"]
    source_receipts = dossier["source_receipts"]
    profile_hash = (dossier.get("issuer_profile") or {}).get("profile_hash")
    production_text = (
        "## 9. 生产记录\n\n"
        "> 证据边界：本章是确定性运行元数据，不包含新的模型结论。\n\n"
        "| 项目 | 记录 |\n| --- | --- |\n"
        f"| 运行 ID | `{production.get('run_id')}` |\n"
        f"| 生成器 | `{production.get('generator_version')}` |\n"
        f"| 模型 | {production.get('provider')} / {production.get('model')} |\n"
        f"| 接受的整章调用 | {production.get('accepted_model_calls')} |\n"
        f"| 通过的语义审计 | {production.get('accepted_semantic_audits')} |\n"
        f"| known_at | `{production.get('known_at')}` |\n"
        f"| issuer profile hash | `{profile_hash or 'none'}` |\n"
        f"| narrative receipt | `{source_receipts.get('official_narrative_receipt_id')}` / `{source_receipts.get('official_narrative_receipt_hash')}` |\n"
        f"| financial receipt | `{source_receipts.get('financial_page_evidence_receipt_hash')}` |\n"
        "| 新官方文件 | 0（复用 N1 官方证据包） |\n"
        "| 人工审阅 | pending_human_review |\n"
        "| 复跑策略 | 固定 profile、source receipt、known_at 与整章请求 ID，重跑并比较 hash |\n"
        "| Tier/action credit | none |\n\n"
    )
    output = "\n".join(lines) + production_text + "## Sources\n\n" + sections["Sources"].strip() + "\n"
    errors = tuple(validate_v4_dossier(output))
    record = {
        "ticker": ticker.upper(),
        "input_dossier_path": str(dossier_path),
        "input_dossier_sha256": _sha_bytes(dossier_path.read_bytes()),
        "input_markdown_path": str(markdown_path),
        "input_markdown_sha256": _sha_bytes(sample.encode("utf-8")),
        "round7_run_id": production.get("run_id"),
        "round7_dossier_content_hash": dossier.get("content_hash"),
        "profile_hash": profile_hash,
        "source_receipts": dict(source_receipts),
        "accepted_model_request_ids": list(
            production.get("accepted_model_request_ids") or []
        ),
        "accepted_semantic_audit_request_ids": list(
            production.get("accepted_semantic_audit_request_ids") or []
        ),
        "accepted_semantic_audit_count": int(
            production.get("accepted_semantic_audits") or 0
        ),
        "all_semantic_audit_count": int(
            production.get("all_semantic_audits") or 0
        ),
        "section_contract_statuses": list(
            production.get("section_contract_statuses") or []
        ),
        "typed_gaps": list(production.get("typed_gaps") or []),
        "source_urls": list(source_urls),
        "output_sha256": _sha_bytes(output.encode("utf-8")),
        "characters": len(output),
        "reader_characters": _reader_characters(output),
        "validation": "passed" if not errors else "failed",
        "validation_errors": list(errors),
        "status": "pending_human_review",
        "generation_mode": "round7_generated_whole_dossier_adaptation",
        "fresh_model_calls": int(production.get("accepted_model_calls") or 0),
        "new_official_documents": 0,
        "tier_credit": "none",
    }
    return output, record


def adapt_official_sample(*, ticker: str, sample_path: Path, narrative_receipt_path: Path, financial_receipt_path: Path) -> tuple[str, OfficialV4Output]:
    sample_bytes = sample_path.read_bytes()
    sample = sample_bytes.decode("utf-8")
    sections = _sections(sample)
    required = (
        "一句话定位", "身份、创始人与治理", "技术来源与发展史", "商业模式与业务线",
        "财务与经营时间序列", "护城河的证据链", "风险、反题材与观察触发器",
        "研究结论与待补问题", "生产记录", "Sources",
    )
    missing = [heading for heading in required if heading not in sections]
    if missing:
        raise ValueError(f"official sample missing Round 7 sections: {missing}")
    if re.search(r"fixture|东财F10|Eastmoney F10", sample, re.IGNORECASE):
        raise ValueError("official adapter refuses fixture/F10 input")
    source_urls = tuple(dict.fromkeys(_SOURCE_URL_RE.findall(sections["Sources"])))
    if not source_urls or any("cninfo.com.cn" not in url for url in source_urls):
        raise ValueError("official adapter requires CNINFO source URLs")
    narrative = json.loads(narrative_receipt_path.read_text(encoding="utf-8"))
    financial = json.loads(financial_receipt_path.read_text(encoding="utf-8"))
    if str(narrative.get("ticker") or "").upper() != ticker.upper() or str(financial.get("ticker") or "").upper() != ticker.upper():
        raise ValueError("official receipt ticker mismatch")
    one_line = _without_boundary(sections["一句话定位"])
    industry_source = _without_boundary(sections["商业模式与业务线"])
    industry = (
        f"{_boundary(sections['商业模式与业务线'])}\n\n"
        f"**产业链位置（研究判断）**：{industry_source}\n\n"
        f"**大白话逻辑链**：{one_line}"
    )
    risk = (
        f"{_boundary(sections['护城河的证据链'])}\n\n"
        f"### 护城河与可证伪条件\n\n{_without_boundary(sections['护城河的证据链'])}\n\n"
        f"### 核心风险与观察触发器\n\n{_without_boundary(sections['风险、反题材与观察触发器'])}\n\n"
        f"### 大白话点评\n\n{_without_boundary(sections['研究结论与待补问题'])}"
    )
    ticker_value = ticker.upper()
    front = _frontmatter(sample)
    lines = [
        "---",
        "schema_version: park-v4-dossier-v1",
        "status: pending_human_review",
        f"ticker: {ticker_value}",
        f"company: {front.get('company', front.get('ticker', ticker_value))}",
        "evidence_mode: official_page_bound",
        f"adapter_version: {ADAPTER_VERSION}",
        "---",
        "",
        f"{front.get('company', ticker_value)}｜V4 公司档案",
        "",
        "> **审阅提示：本档案由官方页级证据适配生成，含未审阅研究判断；不构成目标价、仓位或买卖建议。**",
        "",
    ]
    body_map = (
        ("一句话定位", one_line),
        ("产业坐标", industry),
        ("创始人与团队", f"{_boundary(sections['身份、创始人与治理'])}\n\n{_without_boundary(sections['身份、创始人与治理'])}"),
        ("发展时间线", f"{_boundary(sections['技术来源与发展史'])}\n\n{_without_boundary(sections['技术来源与发展史'])}"),
        ("技术、产品与商业模式", f"{_boundary(sections['商业模式与业务线'])}\n\n{_without_boundary(sections['商业模式与业务线'])}"),
        ("财务与估值", f"{_boundary(sections['财务与经营时间序列'])}\n\n{_without_boundary(sections['财务与经营时间序列'])}"),
        ("风险与点评", risk),
    )
    for heading, body in body_map:
        lines.extend((f"## {heading}", "", body, ""))
    output_body = "\n".join(lines)
    production = (
        "## 9. 生产记录\n\n"
        "> 证据边界：本章是确定性运行元数据，不包含新的模型结论。\n\n"
        "| 项目 | 记录 |\n| --- | --- |\n"
        f"| 运行 ID | `v4-official-adapter:{ticker_value}` |\n"
        f"| 适配器 | `{ADAPTER_VERSION}` |\n"
        f"| 输入样本 | `{sample_path}` / `{_sha_bytes(sample_bytes)}` |\n"
        f"| narrative receipt | `{narrative.get('receipt_id')}` / `{narrative.get('receipt_hash')}` |\n"
        f"| financial receipt | `{financial.get('receipt_hash')}` |\n"
        "| 新模型调用 | 0 |\n| 新官方文件 | 0 |\n"
        "| 人工审阅 | pending_human_review |\n| 复跑策略 | 固定官方 receipt 与输入样本 hash，重新适配并比较输出 hash |\n| Tier/action credit | none |\n\n"
    )
    output = output_body + production + "## Sources\n\n" + sections["Sources"].strip() + "\n"
    errors = tuple(validate_v4_dossier(output))
    reader_start = min(output.find(f"## {heading}") for heading, _ in body_map)
    reader_end = output.find("## 9. 生产记录")
    output_hash = _sha_bytes(output.encode("utf-8"))
    record = OfficialV4Output(
        ticker=ticker_value,
        output_path="",
        input_sample_path=str(sample_path),
        input_sample_sha256=_sha_bytes(sample_bytes),
        narrative_receipt_id=str(narrative.get("receipt_id") or ""),
        narrative_receipt_hash=str(narrative.get("receipt_hash") or ""),
        financial_receipt_hash=str(financial.get("receipt_hash") or ""),
        source_urls=source_urls,
        output_sha256=output_hash,
        characters=len(output),
        reader_characters=max(0, reader_end - reader_start),
        validation="passed" if not errors else "failed",
        validation_errors=errors,
    )
    return output, record


def write_official_outputs(rows: Mapping[str, tuple[str, OfficialV4Output]], output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for ticker, (text, record) in rows.items():
        path = output_dir / f"{ticker}.md"
        path.write_text(text, encoding="utf-8")
        updated = OfficialV4Output(**{**asdict(record), "output_path": str(path)})
        records.append(asdict(updated))
    receipt = {
        "schema_version": "park-v4-official-binding-receipt-v1",
        "adapter_version": ADAPTER_VERSION,
        "generation_mode": "official_evidence_adaptation",
        "status": "passed" if all(row["validation"] == "passed" for row in records) else "failed",
        "is_live_research": False,
        "fresh_model_calls": 0,
        "new_official_documents": 0,
        "tier_credit": "none",
        "companies": records,
        "boundary": "Output re-groups existing official-source sample prose; M4 is required for fresh whole-chapter generation and human review.",
    }
    (output_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt
