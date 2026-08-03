"""Machine contract for the review-only Ainiu/V4 editorial dossier.

This namespace is intentionally separate from the canonical Round 7 dossier
contract.  It validates source identity and claim closure without changing any
publication, Tier, B6, or decision-policy semantics.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Mapping
from urllib.parse import urlparse


EDITORIAL_V4_SCHEMA = "editorial-v4-dossier-v1"
PACKET_SCHEMA = "editorial-v4-evidence-packet-v1"
SECTIONS = (
    ("one_line_position", "一句话定位", 100),
    ("founder_team", "创始人与团队", 100),
    ("timeline", "发展时间线", 300),
    ("technology_products", "技术与产品", 400),
    ("financial_valuation", "财务与估值", 350),
    ("risks_commentary", "风险与点评", 350),
    ("plain_language", "大白话结论", 150),
)
SECTION_IDS = tuple(item[0] for item in SECTIONS)
SECTION_TITLES = tuple(item[1] for item in SECTIONS)
OFFICIAL_HOSTS = {"static.cninfo.com.cn", "www.cninfo.com.cn"}
TICKER_RE = re.compile(r"^[0-9]{6}\.(?:SZ|SH|BJ)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CLAIM_KINDS = {"fact", "judgment", "issuer_self_report", "gap"}
MARKER_RE = re.compile(r"\[(?:F|J|C|G)-\d{2,4}\]")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[\d,]*(?:\.\d+)?)?(?:%|亿元|万元|千元|百万元|元|万股|亿股)?")
FORBIDDEN_ACTION_RE = re.compile(r"仓位|买入|卖出|加仓|减仓|立即行动|建议买|建议卖|止损价|执行合同")
TARGET_PRICE_RE = re.compile(r"目标价|目标价格")
ABSENCE_WORDS = re.compile(r"未提供|没有|缺失|无法|不提供|不含|禁止|尚无|缺少")
CONDITIONAL_RE = re.compile(r"如果.{0,80}(?:那么|则)|若.{0,80}(?:那么|则)|假如.{0,80}(?:那么|则)")
COMPARISON_WORDS = re.compile(r"同比|环比|较上期|较去年|增长|下滑|下降|增加|减少|持平|提升|回落")
SELF_REPORT_WORDS = re.compile(r"公司披露|年报披露|年报自述|公告披露|公司自述|公司宣称|公司声称|年报宣称|管理层表示|公司称|公司认为|据年报|年报引|年报提及|年报坦承|年报称|年报说明|公司年报")
THIRD_PARTY_CUES = re.compile(
    r"欧睿|Euromonitor|产业在线|奥维|MIR|睿工业|IDC|Gartner|弗若斯特|Frost|SNE|NBD|新华|CPNN|"
    r"东财|东方财富|Wind|彭博|Bloomberg"
)
UNBOUND_GAP_SOURCE_CUES = re.compile(r"公开资料|公开信息|市场资料|业内消息|据了解|有消息称|据传")
UNBOUND_JUDGMENT_FACT_CUES = re.compile(
    r"黄牛价|批价|零售价|市场价|成交价|订单|市值|股价|目标价"
)
AGGRESSIVE_JUDGMENT_CUES = re.compile(
    r"绝对龙头|强定价权|品牌护城河|核心矛盾|存量博弈|时间壁垒|难以复制|超级品牌|硬通货|现金牛|"
    r"最安全|第一品牌|官员型|行政化特征|躺赢|增收不增利|增长曲线|资产角色|护城河|"
    r"全球科技巨头|全球最大|全球领先|家电航母|大国重器|第二曲线|强大规模|规模优势明显|"
    r"精密制造平台|精密制造杂货铺|超级现金流引擎|高风险高回报|高风险高回报期权|"
    r"低毛利的身子|现金流引擎|资产重估|三角布局"
)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _blocked_action_matches(text: str) -> list[str]:
    """Return prohibited execution language while allowing explicit gaps.

    A review-only dossier may truthfully say that a target price is *not
    provided*.  That absence statement must not be confused with publishing a
    target price or recommendation.
    """
    matches = list(FORBIDDEN_ACTION_RE.findall(text))
    for match in TARGET_PRICE_RE.finditer(text):
        # Do not let an absence statement in a previous card/paragraph bless a
        # later positive target-price sentence.  Inspect only the current
        # sentence/line before the term.
        start = max(text.rfind(mark, 0, match.start()) for mark in ("。", "！", "？", "\n")) + 1
        context = text[start:match.start()]
        if not ABSENCE_WORDS.search(context):
            matches.append(match.group(0))
    return matches


def validate_evidence_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    ticker = str(packet.get("ticker") or "").upper()
    if packet.get("schema_version") != PACKET_SCHEMA:
        errors.append(_error("packet_schema", "evidence packet schema mismatch"))
    if packet.get("data_kind") != "real":
        errors.append(_error("packet_data_kind", "evidence packet must be marked real"))
    if not TICKER_RE.fullmatch(ticker):
        errors.append(_error("packet_identity", "invalid ticker"))
    if packet.get("truth_boundary", {}).get("official_pdf_only") is not True:
        errors.append(_error("packet_boundary", "packet is not official-PDF-only"))
    expected_hash = str(packet.get("packet_hash") or "")
    payload = {key: value for key, value in packet.items() if key != "packet_hash"}
    if not SHA_RE.fullmatch(expected_hash) or canonical_hash(payload) != expected_hash:
        errors.append(_error("packet_hash", "packet hash mismatch"))
    sources = packet.get("sources") if isinstance(packet.get("sources"), list) else []
    source_by_id: dict[str, Mapping[str, Any]] = {}
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            errors.append(_error("source_shape", "source must be an object", index=index))
            continue
        source_id = str(source.get("source_id") or "")
        if not source_id or source_id in source_by_id:
            errors.append(_error("source_identity", "source_id missing or duplicated", index=index, source_id=source_id))
        source_by_id[source_id] = source
        parsed = urlparse(str(source.get("source_url") or ""))
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            errors.append(_error("source_host", "source URL is outside official allowlist", source_id=source_id))
        if not SHA_RE.fullmatch(str(source.get("raw_sha256") or "")):
            errors.append(_error("source_hash", "source raw_sha256 is invalid", source_id=source_id))
        if not source.get("document_id") or not source.get("title"):
            errors.append(_error("source_metadata", "source document identity/title missing", source_id=source_id))
        if type(source.get("page_count")) is not int or source.get("page_count") < 1:
            errors.append(_error("source_pages", "source page_count must be positive", source_id=source_id))
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), list) else []
    evidence_by_id: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            errors.append(_error("evidence_shape", "evidence must be an object", index=index))
            continue
        evidence_id = str(item.get("evidence_id") or "")
        if not evidence_id or evidence_id in evidence_by_id:
            errors.append(_error("evidence_identity", "evidence_id missing or duplicated", index=index, evidence_id=evidence_id))
        evidence_by_id[evidence_id] = item
        source_id = str(item.get("source_id") or "")
        source = source_by_id.get(source_id)
        if source is None:
            errors.append(_error("evidence_source", "evidence source_id not in sources", evidence_id=evidence_id, source_id=source_id))
            continue
        for field in ("document_id", "page_number", "quoted_anchor", "source_url", "raw_sha256", "report_period"):
            if item.get(field) in (None, "", []):
                errors.append(_error("evidence_locator", f"evidence field {field} missing", evidence_id=evidence_id))
        if item.get("document_id") != source.get("document_id") or item.get("raw_sha256") != source.get("raw_sha256") or item.get("source_url") != source.get("source_url"):
            errors.append(_error("evidence_binding", "evidence identity does not match source", evidence_id=evidence_id))
        if type(item.get("page_number")) is not int or int(item.get("page_number") or 0) < 1:
            errors.append(_error("evidence_page", "evidence page_number must be positive", evidence_id=evidence_id))
        elif int(item["page_number"]) > int(source.get("page_count") or 0):
            errors.append(_error("evidence_page_range", "evidence page exceeds source page_count", evidence_id=evidence_id))
        source_period = str(source.get("report_period") or "")
        item_period = str(item.get("report_period") or "")
        compatible_periods = {source_period, "unresolved"}
        if source_period.endswith("FY") and source_period[:4].isdigit():
            compatible_periods.add(f"{int(source_period[:4]) - 1}FY")
        if source_period.endswith("Q1") and source_period[:4].isdigit():
            compatible_periods.add(f"{int(source_period[:4]) - 1}Q1")
        if source_period and item_period and item_period not in compatible_periods:
            errors.append(_error("evidence_period", "evidence report_period does not match source", evidence_id=evidence_id))
        if not isinstance(item.get("quoted_anchor"), str) or len(item.get("quoted_anchor", "").strip()) < 8:
            errors.append(_error("evidence_anchor", "evidence quoted_anchor is too short", evidence_id=evidence_id))
    for index, derived in enumerate(packet.get("derived_metrics") or []):
        if not isinstance(derived, Mapping):
            errors.append(_error("derived_shape", "derived metric must be an object", index=index))
            continue
        if derived.get("current_evidence_id") not in evidence_by_id or derived.get("previous_evidence_id") not in evidence_by_id:
            errors.append(_error("derived_binding", "derived metric references missing evidence", index=index))
        if derived.get("direction") not in {"增长", "下滑", "持平"}:
            errors.append(_error("derived_direction", "derived metric direction is invalid", index=index))
    if not evidence_by_id:
        errors.append(_error("packet_empty", "evidence packet has no page-bound evidence"))
    return {"status": "passed" if not errors else "failed", "ticker": ticker, "sources": len(source_by_id), "evidence": len(evidence_by_id), "errors": errors}


def _section_body_map(dossier: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = dossier.get("sections") if isinstance(dossier.get("sections"), list) else []
    return {str(row.get("id")): row for row in rows if isinstance(row, Mapping)}


def _number_token_is_closed(token: str, claim_text: str) -> bool:
    """Allow presentation commas/spacing while requiring the same value/unit."""
    normalized_token = re.sub(r"[\s,]", "", token)
    normalized_claim = re.sub(r"[\s,]", "", claim_text)
    if normalized_token in normalized_claim:
        return True
    # The latest card may use a rounded 亿/万元 display while the claim keeps
    # the exact official-unit amount.  Require the displayed rounded number to
    # be present in a claim rather than treating a comma difference as a gap.
    if token.endswith("亿元"):
        bare = normalized_token[:-2]
        if bare and bare in normalized_claim:
            return True
    # A compact data card may round a page-bound yuan amount to two decimal
    # places in 亿元.  Close that display against an exact 元 claim without
    # asking the model to perform arithmetic.
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized_token):
        try:
            displayed = float(normalized_token)
        except ValueError:
            displayed = None
        if displayed is not None:
            for raw in re.findall(r"([\d,]+(?:\.\d+)?)\s*元", claim_text):
                try:
                    exact_yuan = float(raw.replace(",", ""))
                except ValueError:
                    continue
                if abs(exact_yuan / 100_000_000 - displayed) <= 0.011:
                    return True
    return False


_UNIT_TO_BASE = {
    "元": 1.0,
    "千元": 1_000.0,
    "万元": 10_000.0,
    "百万元": 1_000_000.0,
    "亿元": 100_000_000.0,
}


def _numeric_token_matches_evidence(token: str, refs: list[str], evidence_by_id: Mapping[str, Mapping[str, Any]]) -> bool:
    """Close a displayed amount against the frozen fact value and unit.

    Official table anchors often carry the number but put the unit in a
    separate table header.  Requiring the literal ``千元``/``亿元`` suffix in
    the anchor would therefore reject a correctly bound presentation.  This
    helper performs only deterministic unit conversion against the cited
    packet facts; it does not calculate a new financial fact or accept a
    number from an unrelated row.
    """
    match = re.fullmatch(r"([\d,]+(?:\.\d+)?)(元|千元|万元|百万元|亿元)?", token.strip())
    if not match:
        return False
    raw_value, token_unit = match.groups()
    try:
        displayed = float(raw_value.replace(",", ""))
    except ValueError:
        return False
    if token_unit not in _UNIT_TO_BASE:
        return False
    displayed_base = displayed * _UNIT_TO_BASE[token_unit]
    decimals = len(raw_value.split(".", 1)[1]) if "." in raw_value else 0
    # Match the precision the writer displayed (e.g. 4,237亿元 is rounded to
    # the nearest 1亿元; 4,237.00亿元 is rounded to cents of an 亿元).
    tolerance = 0.5 * (10 ** (-decimals)) * _UNIT_TO_BASE[token_unit]
    for ref in refs:
        item = evidence_by_id.get(ref) or {}
        value = item.get("value")
        unit = str(item.get("unit") or "")
        if not isinstance(value, (int, float)) or unit not in _UNIT_TO_BASE:
            continue
        expected_base = float(value) * _UNIT_TO_BASE[unit]
        if abs(displayed_base - expected_base) <= max(tolerance, abs(expected_base) * 1e-9):
            return True
    return False


def _numeric_tokens(value: str) -> list[str]:
    """Return numeric literals while leaving years available for period checks."""
    return [token for token in NUMBER_RE.findall(value) if any(char.isdigit() for char in token)]


def _is_year_token(token: str) -> bool:
    bare = re.sub(r"[^0-9]", "", token)
    return len(bare) == 4 and bare.startswith(("19", "20"))


def _numeric_token_in_refs(token: str, refs: list[str], evidence_by_id: Mapping[str, Mapping[str, Any]]) -> bool:
    """Check one displayed numeric literal against only its claim's refs.

    This is deliberately claim-local.  A ``20%`` in a different claim must not
    make an unrelated ``20%`` threshold appear evidenced.
    """
    normalized = re.sub(r"[\s,]", "", token)
    for ref in refs:
        item = evidence_by_id.get(ref) or {}
        text = " ".join(
            str(item.get(field) or "")
            for field in ("quoted_anchor", "text", "quoted_label", "column_header_excerpt")
        )
        if normalized and normalized in re.sub(r"[\s,]", "", text):
            return True
        if _numeric_token_matches_evidence(token, [ref], evidence_by_id):
            return True
    return False


def _numeric_token_in_derived(
    token: str,
    derived_ids: list[str],
    derived_by_id: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Allow only deterministic derived values, with displayed precision."""
    raw = re.sub(r"[\s,]", "", token)
    unit = ""
    for suffix in ("亿元", "万元", "千元", "百万元", "万股", "亿股", "%", "元"):
        if raw.endswith(suffix):
            unit = suffix
            raw = raw[: -len(suffix)]
            break
    try:
        displayed = float(raw)
    except ValueError:
        return False
    for derived_id in derived_ids:
        item = derived_by_id.get(derived_id) or {}
        candidates: list[float] = []
        if unit == "%":
            value = item.get("percent_change")
            if isinstance(value, (int, float)):
                candidates.append(float(value))
        else:
            for key in ("absolute_change", "current_value", "previous_value"):
                value = item.get(key)
                if isinstance(value, (int, float)):
                    candidates.append(float(value))
        for expected in candidates:
            # The displayed decimal precision controls the deterministic
            # rounding tolerance (42.3% may represent 42.283446%).
            decimals = len(raw.split(".", 1)[1]) if "." in raw else 0
            tolerance = max(0.5 * (10 ** (-decimals)), abs(expected) * 1e-9)
            if abs(displayed - expected) <= tolerance:
                return True
    return False


def _numeric_claim_errors(
    claim_id: str,
    value: str,
    refs: list[str],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    field: str = "text",
    derived_ids: list[str] | None = None,
    derived_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    derived_ids = derived_ids or []
    derived_by_id = derived_by_id or {}
    for token in _numeric_tokens(value):
        if _is_year_token(token):
            continue
        if not _numeric_token_in_refs(token, refs, evidence_by_id) and not _numeric_token_in_derived(token, derived_ids, derived_by_id):
            errors.append(
                _error(
                    "judgment_numeric_unbound" if field == "falsifier" else "numeric_claim_unbound",
                    f"{field} contains numeric literal not present in this claim's cited evidence",
                    claim_id=claim_id,
                    number=token,
                )
            )
    return errors


def _specific_judgment_errors(
    claim_id: str,
    value: str,
    refs: list[str],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    field: str,
) -> list[dict[str, Any]]:
    """Reject concrete market/business premises smuggled into a judgment.

    Sharp synthesis ("老洋房", "精密制造杂货铺") is intentionally allowed.
    Concrete market facts in a falsifier (批价、客户、订单、份额、估值等)
    must, however, appear in the claim's own cited pages; otherwise the model
    must express the trigger qualitatively or leave it as a gap.
    """
    cited = " ".join(
        str(evidence_by_id.get(ref, {}).get(field_name) or "")
        for ref in refs
        for field_name in ("quoted_anchor", "text", "quoted_label")
    )
    errors: list[dict[str, Any]] = []
    for cue in UNBOUND_JUDGMENT_FACT_CUES.findall(value):
        if cue not in cited:
            errors.append(
                _error(
                    "judgment_specific_unbound",
                    f"{field} contains a concrete market/business premise not present in this claim's cited evidence",
                    claim_id=claim_id,
                    cue=cue,
                )
            )
    return errors


def validate_dossier(dossier: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    packet_result = validate_evidence_packet(packet)
    if packet_result["status"] != "passed":
        errors.append(_error("packet_invalid", "dossier input packet is invalid", packet_errors=packet_result["errors"]))
    ticker = str(packet.get("ticker") or "").upper()
    if dossier.get("schema_version") != EDITORIAL_V4_SCHEMA:
        errors.append(_error("dossier_schema", "dossier schema mismatch"))
    if str(dossier.get("ticker") or "").upper() != ticker:
        errors.append(_error("dossier_identity", "dossier ticker does not match packet"))
    if not isinstance(dossier.get("sources"), list) or not dossier.get("sources"):
        errors.append(_error("dossier_sources", "dossier must carry the bound source registry"))
    if str(dossier.get("input_packet_hash") or "") != str(packet.get("packet_hash") or ""):
        errors.append(_error("dossier_packet_binding", "dossier input_packet_hash does not match packet"))
    generation = dossier.get("generation_receipt") if isinstance(dossier.get("generation_receipt"), Mapping) else {}
    if not generation.get("request_hash") or not generation.get("response_hash"):
        errors.append(_error("generation_receipt", "generation receipt must bind request and response hashes"))
    production = dossier.get("production_record") if isinstance(dossier.get("production_record"), Mapping) else {}
    for field in ("run_id", "model_provider", "model", "prompt_version", "input_packet_sha256"):
        if not production.get(field):
            errors.append(_error("production_record", f"production_record.{field} is required"))
    if production.get("review_status") != "pending" or production.get("action_state") != "blocked":
        errors.append(_error("review_boundary", "editorial draft must remain pending and action-blocked"))
    boundary = dossier.get("boundary") if isinstance(dossier.get("boundary"), Mapping) else {}
    if boundary.get("review_only") is not True or boundary.get("no_tier_credit") is not True or boundary.get("no_publication_credit") is not True:
        errors.append(_error("editorial_boundary", "editorial dossier boundary is not fail-closed"))
    section_map = _section_body_map(dossier)
    if tuple(section_map) != SECTION_IDS:
        errors.append(_error("section_order", "editorial V4 section order mismatch", expected=list(SECTION_IDS), actual=list(section_map)))
    total_chars = 0
    for section_id, title, minimum in SECTIONS:
        row = section_map.get(section_id)
        body = str(row.get("body") or "") if row else ""
        total_chars += len(body)
        if row is None or str(row.get("title") or "") != title:
            errors.append(_error("section_missing", "required section is missing or title mismatched", section=section_id))
        if len(body) < minimum:
            errors.append(_error("section_short", "section is below minimum length", section=section_id, chars=len(body), minimum=minimum))
    if total_chars < 2200:
        errors.append(_error("dossier_short", "editorial body is materially shorter than the Round 7 V4 reference", chars=total_chars, target=2429))
    if total_chars > 14000:
        errors.append(_error("dossier_long", "editorial body is unbounded", chars=total_chars))
    latest_card = str(dossier.get("latest_card") or "")
    if len(latest_card) < 20:
        errors.append(_error("latest_card_missing", "latest data card is missing"))
    body_text = "\n".join([latest_card] + [str(row.get("body") or "") for row in section_map.values()])
    forbidden = _blocked_action_matches(body_text)
    if forbidden:
        errors.append(_error("action_language", "editorial body contains blocked action/valuation language", matches=sorted(set(forbidden))))
    leaked = [term for term in ("长盈精密", "300115.SZ", "爱牛", "Ainiu", "benchmark") if term.lower() in body_text.lower()]
    if leaked:
        errors.append(_error("benchmark_leak", "editorial body contains benchmark/ticker leakage", matches=sorted(set(leaked))))
    claims = dossier.get("claims") if isinstance(dossier.get("claims"), list) else []
    claims_by_id: dict[str, Mapping[str, Any]] = {}
    packet_evidence_ids = {str(item.get("evidence_id")) for item in packet.get("evidence", []) if isinstance(item, Mapping)}
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in packet.get("evidence", [])
        if isinstance(item, Mapping) and item.get("evidence_id")
    }
    derived_by_id = {str(item.get("derived_id")): item for item in packet.get("derived_metrics", []) if isinstance(item, Mapping)}
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            errors.append(_error("claim_shape", "claim must be an object", index=index))
            continue
        claim_id = str(claim.get("claim_id") or "")
        kind = str(claim.get("kind") or "")
        text = str(claim.get("text") or "")
        refs = [str(value) for value in claim.get("evidence_ids") or []]
        if not claim_id or claim_id in claims_by_id:
            errors.append(_error("claim_identity", "claim_id missing or duplicated", index=index))
        claims_by_id[claim_id] = claim
        if kind not in CLAIM_KINDS:
            errors.append(_error("claim_kind", "claim kind is invalid", claim_id=claim_id, kind=kind))
        if kind != "gap" and not refs:
            errors.append(_error("claim_refs", "non-gap claim has no evidence refs", claim_id=claim_id))
        missing_refs = sorted(set(refs) - packet_evidence_ids)
        if missing_refs:
            errors.append(_error("claim_refs", "claim references evidence outside packet", claim_id=claim_id, missing=missing_refs))
        derived_refs = [str(value) for value in claim.get("derived_ids") or []]
        if kind == "issuer_self_report" and not SELF_REPORT_WORDS.search(text):
            errors.append(_error("self_report_unmarked", "issuer self-report claim lacks explicit label", claim_id=claim_id))
        if kind in {"fact", "issuer_self_report"} and NUMBER_RE.search(text) and not refs:
            errors.append(_error("numeric_claim_unbound", "numeric fact has no page evidence", claim_id=claim_id))
        if kind in {"fact", "issuer_self_report"} and not derived_refs:
            quoted = " ".join(str(evidence_by_id.get(ref, {}).get("quoted_anchor") or "") for ref in refs)
            long_numbers = [
                token for token in NUMBER_RE.findall(text)
                if any(char.isdigit() for char in token)
                and len(re.sub(r"[^0-9]", "", token)) >= 2
                and not (len(re.sub(r"[^0-9]", "", token)) == 4 and re.sub(r"[^0-9]", "", token).startswith(("19", "20")))
            ]
            normalized_quote = re.sub(r"[\s,]", "", quoted)
            for number in long_numbers:
                if re.sub(r"[\s,]", "", number) not in normalized_quote and not _numeric_token_matches_evidence(number, refs, evidence_by_id):
                    errors.append(_error("numeric_quote_mismatch", "numeric claim value is not present in cited page anchor", claim_id=claim_id, number=number))
        # Judgments may be sharp and synthetic, but they cannot smuggle in a
        # made-up threshold, percentage, or other numeric premise.  A future
        # falsifier is subject to the same rule: if its number is not in the
        # cited packet, the writer must state the trigger qualitatively.
        if kind == "judgment":
            errors.extend(_numeric_claim_errors(claim_id, text, refs, evidence_by_id, derived_ids=derived_refs, derived_by_id=derived_by_id))
            errors.extend(_numeric_claim_errors(claim_id, str(claim.get("falsifier") or ""), refs, evidence_by_id, field="falsifier", derived_ids=derived_refs, derived_by_id=derived_by_id))
            errors.extend(_specific_judgment_errors(claim_id, text, refs, evidence_by_id, field="text"))
            errors.extend(_specific_judgment_errors(claim_id, str(claim.get("falsifier") or ""), refs, evidence_by_id, field="falsifier"))
        if kind == "gap" and not refs and UNBOUND_GAP_SOURCE_CUES.search(text):
            errors.append(_error("gap_unbound_source", "gap claim contains an external/public-source fact without evidence refs", claim_id=claim_id))
        missing_derived = sorted(set(derived_refs) - set(derived_by_id))
        if missing_derived:
            errors.append(_error("derived_refs", "claim references unknown deterministic derivation", claim_id=claim_id, missing=missing_derived))
        if derived_refs and not COMPARISON_WORDS.search(text):
            errors.append(_error("comparison_direction_missing", "comparison-backed claim does not state direction", claim_id=claim_id))
        for derived_id in derived_refs:
            derived = derived_by_id.get(derived_id) or {}
            expected_refs = {str(derived.get("current_evidence_id")), str(derived.get("previous_evidence_id"))}
            if not expected_refs.issubset(set(refs)):
                errors.append(_error("derived_binding", "comparison claim must cite both deterministic input facts", claim_id=claim_id, derived_id=derived_id))
        if CONDITIONAL_RE.search(text) and refs:
            periods = [str(evidence_by_id[ref].get("report_period") or "") for ref in refs if ref in evidence_by_id]
            if any(period and not period.startswith(("future", "待")) for period in periods):
                errors.append(_error("historical_condition", "conditional claim is bound to already-disclosed evidence", claim_id=claim_id))
        if kind == "judgment" and not claim.get("falsifier"):
            errors.append(_error("judgment_falsifier", "judgment claim lacks falsifier/trigger", claim_id=claim_id))
    markers = set(MARKER_RE.findall(body_text))
    for marker in sorted(markers):
        if marker[1:-1] not in claims_by_id:
            errors.append(_error("orphan_marker", "body marker has no claim registry row", marker=marker))
    for claim_id, claim in claims_by_id.items():
        marker = f"[{claim_id}]"
        if claim.get("kind") != "gap" and marker not in body_text:
            errors.append(_error("claim_not_rendered", "claim registry row is not visible in body", claim_id=claim_id))
        if claim.get("kind") == "issuer_self_report" and marker in body_text:
            # A paragraph may introduce a run of company disclosures once and
            # then attach several [C-xx] markers to the sourced clauses.  Treat
            # that paragraph-level attribution as explicit rather than forcing
            # the model to repeat boilerplate before every marker.
            contexts = [part for part in body_text.split("\n") if marker in part]
            if not any(SELF_REPORT_WORDS.search(context) for context in contexts):
                errors.append(_error("self_report_body_unmarked", "issuer self-report marker is not accompanied by an explicit attribution in rendered prose", claim_id=claim_id))
    # Strong positioning is allowed and desirable, but it must be visibly
    # separated from facts.  Require a judgment marker on the same sentence;
    # this catches the failure mode where model prose smuggles a thesis in as
    # an unlabelled company fact.
    for sentence in re.split(r"[。！？\n]", body_text):
        if AGGRESSIVE_JUDGMENT_CUES.search(sentence) and not re.search(r"\[J-\d{2,4}\]", sentence):
            errors.append(_error("judgment_marker_missing", "aggressive positioning sentence lacks an explicit [J-xx] judgment marker", excerpt=sentence.strip()[:180]))
    overall = str(dossier.get("overall_conclusion") or "")
    if overall and not MARKER_RE.search(overall):
        errors.append(_error("overall_judgment_marker_missing", "overall_conclusion must carry at least one fact/judgment/gap marker"))
    # Numeric closure is sentence/marker-local.  The old global check allowed
    # an unrelated claim containing ``20%`` to bless a new, unsupported 20%
    # threshold elsewhere in the report.
    ticker_digits = re.sub(r"[^0-9]", "", ticker)
    for segment in re.split(r"[。！？\n]", body_text):
        if not segment.strip():
            continue
        marker_ids = [marker[1:-1] for marker in MARKER_RE.findall(segment)]
        if not marker_ids:
            continue
        refs: list[str] = []
        claim_texts: list[str] = []
        for marker_id in marker_ids:
            claim = claims_by_id.get(marker_id)
            if not claim:
                continue
            refs.extend(str(ref) for ref in claim.get("evidence_ids") or [])
            claim_texts.append(str(claim.get("text") or ""))
            claim_texts.append(str(claim.get("falsifier") or ""))
        for token in _numeric_tokens(MARKER_RE.sub("", segment)):
            if _is_year_token(token):
                continue
            # The ticker in the report header/latest card is an identity
            # label, not a financial premise that needs an evidence ref.
            # Keep every other numeric literal subject to claim-local
            # closure.
            if ticker_digits and re.sub(r"[^0-9]", "", token) == ticker_digits:
                continue
            if not any(_number_token_is_closed(token, text) for text in claim_texts) and not _numeric_token_in_refs(token, refs, evidence_by_id):
                errors.append(_error("body_numeric_unbound", "body numeric literal is not closed by the same sentence's claim/evidence", token=token, claim_ids=marker_ids))
        # Third-party rankings or market statistics inside an issuer filing
        # remain company-reported material.  Attribution must precede the
        # third-party cue so ``根据欧睿数据……年报披露`` cannot read as an
        # independently verified Euromonitor fact.
        if THIRD_PARTY_CUES.search(segment):
            attribution_before_cue = bool(re.search(r"(?:公司披露|年报披露|年报自述|公告披露|年报引|据年报)[^。！？\n]{0,80}(?:" + THIRD_PARTY_CUES.pattern + r")", segment, re.IGNORECASE))
            # A judgment sentence may quote a company-reported third-party
            # statistic as its substrate, provided the issuer attribution is
            # explicit and precedes the provider name.  The claim remains a
            # judgment because its synthesis (for example, “精密制造平台”)
            # is not a filing fact; the attribution rule is about preventing
            # the provider from reading as an independently supplied source.
            if not marker_ids or not attribution_before_cue:
                errors.append(_error("third_party_attribution_missing", "third-party statistic must be attributed to the issuer filing before the provider name", claim_ids=marker_ids))
    # Gap text is rendered too; reject a public-source assertion there as well
    # even when a model hid it behind a gap marker.
    for claim_id, claim in claims_by_id.items():
        if claim.get("kind") == "gap" and not claim.get("evidence_ids") and UNBOUND_GAP_SOURCE_CUES.search(str(claim.get("text") or "")):
            errors.append(_error("gap_unbound_source", "gap text contains an external/public-source assertion without evidence refs", claim_id=claim_id))
    return {"status": "passed" if not errors else "failed", "ticker": ticker, "chars": total_chars, "claims": len(claims_by_id), "errors": errors}


def summarize_claims(dossier: Mapping[str, Any]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for claim in dossier.get("claims") or []:
        if isinstance(claim, Mapping):
            counts[str(claim.get("kind") or "unknown")] += 1
    return dict(sorted(counts.items()))
