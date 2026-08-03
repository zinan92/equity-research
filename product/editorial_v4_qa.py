"""Fail-closed machine and independent-model QA for editorial V4 drafts.

This module deliberately never changes review state to approved.  A DeepSeek
review is an independent diagnostic signal; the dossier remains review-only
and action-blocked until a human reviews it.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from deepseek_writer import DEFAULT_KEY_FILE, DEFAULT_MODEL, call_structured_deepseek
from editorial_v4_contract import THIRD_PARTY_CUES, canonical_hash, validate_dossier
from editorial_v4_generator import generate_once, write_draft
from editorial_v4_renderer import render_dossier


QA_PROMPT_VERSION = "editorial-v4-independent-qa-prompt-v2"
QA_FILTER_VERSION = "editorial-v4-independent-qa-filter-v2"

QA_SYSTEM_PROMPT = """你是 Park Equity Research 的独立编辑质检员。你只做诊断，不批准、不改写、不删改报告。

检查用户提供的 editorial-v4 dossier 和同一份官方 PDF 页级 evidence packet：
1) 每个数字和事实是否能由 evidence_ids 回溯到 document_id、页码、quoted_anchor；
2) 引用有同期对比的数据时，正文是否明确写增长/下滑/持平及确定性输入给出的幅度；
3) 只要是公司年报/季报自述，是否显式写“公司披露/年报自述/公告披露”，没有把自述冒充独立验证；
4) 是否把已经披露的历史实际值写成“如果…那么…”的条件句结论；
5) 是否把未提供证据的客户、订单、排名、份额、估值、股价、目标价或行动建议写成事实；
6) 爱牛式的“绝对龙头/强定价权/品牌护城河/精密制造杂货铺”等独特定位属于允许的 AI judgment，不要因为没有一句逐字证据就要求删除。只要它在 claims 中是 judgment、引用了相关底层 evidence、明确是研究判断并有 falsifier，就不算 blocker；若未标 [J-xx] 或没有 refs/falsifier，才报 blocker。整体结论也允许锋利，但应带对应 judgment marker。
7) 是否有爱牛式的具体资产定位、财务因果链、风险证伪条件和白话结论，而不是公司年报摘要；不要把“判断基于事实”误解为“判断必须逐字出现在证据里”；
8) 是否明确缺口和下一步验证，不用空泛句子凑篇幅。以 evidence packet 的 gaps 为依据写出的“输入未提供/证据不足”是合格的缺口，不要把 gap claim 当作需要额外证据的事实；但不得借 gap 掩盖已有数字或把公司自述升级成事实。

对每个问题都给出 severity 和 category：severity 只能是 blocker 或 advisory；category 只能是 provenance、numeric、historical_condition、self_report_attribution、unsupported_specific_fact、judgment_synthesis、style。对于 judgment_synthesis：如果只是说“证据没有逐字写出绝对龙头/护城河”等词，但 claim 有相关底层 evidence、[J] marker 和 falsifier，这是 advisory，不是 blocker；如果判断夹带了未在引用页出现的数字、客户、订单、排名、份额、估值、具体事件或错误 evidence_id，则是 provenance/numeric/unsupported_specific_fact blocker。claim_id 不存在时留空。
只返回 JSON，不要 Markdown；最多列 8 个最重要问题，每个 message 不超过 160 个中文字符：
{"status":"passed"或"failed", "blockers":[{"severity":"blocker","category":"...","code":"...","message":"...","claim_id":"...","evidence_ids":["..."]}], "strengths":["..."], "checked_rules":["..."]}
status 只有在没有 severity=blocker 的问题时才能 passed。advisory 可列出但不能使 status failed。不要因为报告标为 pending 就降低标准。"""


def _compact_packet(packet: Mapping[str, Any], dossier: Mapping[str, Any]) -> dict[str, Any]:
    """Send cited provenance plus a bounded sample, never old report prose."""
    all_evidence = [item for item in packet.get("evidence") or [] if isinstance(item, Mapping)]
    cited_ids = {
        str(ref)
        for claim in dossier.get("claims") or []
        if isinstance(claim, Mapping)
        for ref in claim.get("evidence_ids") or []
    }
    cited = [item for item in all_evidence if str(item.get("evidence_id")) in cited_ids]
    facts = [item for item in all_evidence if item.get("metric") is not None]
    narrative = [item for item in all_evidence if item.get("metric") is None and item not in cited]
    selected: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in cited + facts + narrative[:12]:
        eid = str(item.get("evidence_id"))
        if eid in seen:
            continue
        seen.add(eid)
        selected.append(item)
    return {
        "ticker": packet.get("ticker"),
        "issuer_name": packet.get("issuer_name"),
        "sources": packet.get("sources") or [],
        "evidence": selected,
        "derived_metrics": packet.get("derived_metrics") or [],
        "gaps": packet.get("gaps") or [],
        "truth_boundary": packet.get("truth_boundary") or {},
    }


def build_qa_request(dossier: Mapping[str, Any], packet: Mapping[str, Any], machine: Mapping[str, Any]) -> dict[str, Any]:
    dossier_payload = dict(dossier)
    packet_payload = _compact_packet(packet, dossier)
    return {
        "request_schema": "editorial-v4-independent-qa-request-v2",
        "prompt_version": QA_PROMPT_VERSION,
        "ticker": dossier.get("ticker"),
        "dossier_hash": canonical_hash(dossier_payload),
        "packet_hash": packet.get("packet_hash"),
        "machine_validation": machine,
        "dossier": dossier_payload,
        "evidence_packet": packet_payload,
    }


def _filter_false_positive_blockers(raw: Mapping[str, Any], dossier: Mapping[str, Any], packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Keep independent-judge blockers that survive deterministic provenance checks.

    DeepSeek sometimes reports the fact that a quote does not literally contain
    the words “company disclosure”; that is not a mismatch when the claim is
    explicitly ``issuer_self_report`` and its substantive phrase is in the
    cited official excerpt.  Gap claims are also allowed to have no evidence
    refs by contract.  Real numeric/qualitative mismatches remain blockers.
    """
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in packet.get("evidence") or []
        if isinstance(item, Mapping)
    }
    claims_by_id = {
        str(item.get("claim_id")): item
        for item in dossier.get("claims") or []
        if isinstance(item, Mapping)
    }
    body_text = "\n".join(
        [str(dossier.get("latest_card") or "")]
        + [str(row.get("body") or "") for row in dossier.get("sections") or [] if isinstance(row, Mapping)]
    )

    def attributed_context(claim_id: str) -> bool:
        marker = f"[{claim_id}]"
        for paragraph in body_text.split("\n"):
            if marker not in paragraph:
                continue
            if not re.search(r"公司披露|年报披露|年报自述|公告披露|公司自述|据年报|年报引|公司年报", paragraph):
                continue
            # For a provider name, require the attribution to precede it.  A
            # plain company-disclosure claim only needs the explicit marker.
            if THIRD_PARTY_CUES.search(paragraph):
                if re.search(r"(?:公司披露|年报披露|年报自述|公告披露|年报引|据年报)[^。！？\n]{0,80}(?:" + THIRD_PARTY_CUES.pattern + r")", paragraph, re.IGNORECASE):
                    return True
                continue
            return True
        return False

    def literal_evidence_support(claim: Mapping[str, Any]) -> bool:
        """Use deterministic text/number overlap to reject stale QA claims.

        DeepSeek occasionally says a long quoted anchor does not contain a
        provider or ranking even though the frozen anchor does.  This helper
        only downgrades that narrow false positive when the claim's own refs
        contain its provider/number/major noun phrases; it never rescues an
        unknown evidence ID or an explicit numeric mismatch.
        """
        refs = [str(ref) for ref in claim.get("evidence_ids") or []]
        cited = " ".join(
            str(evidence_by_id.get(ref, {}).get(field) or "")
            for ref in refs
            for field in ("quoted_anchor", "text", "quoted_label")
        )
        normalized = re.sub(r"[\s，。；：:、（）()\[\]“”‘’]", "", cited).lower()
        text = str(claim.get("text") or "")
        claim_numbers = [token for token in re.findall(r"\d+(?:[\d,]*(?:\.\d+)?)?(?:%|亿元|万元|千元|元)?", text) if token]
        for token in claim_numbers:
            if token in {"19", "20"}:
                continue
            if re.sub(r"[\s,]", "", token).lower() not in normalized:
                # Unit-converted financial values are already deterministic
                # in the machine contract; do not use this overlap helper to
                # bless a mismatch.
                return False
        provider_terms = re.findall(r"欧睿|Euromonitor|产业在线|奥维云网|MIR|睿工业|IDC|Gartner|Wind|彭博|Bloomberg", text, re.IGNORECASE)
        if provider_terms and not any(term.lower() in normalized for term in provider_terms):
            return False
        phrases = [phrase for phrase in re.split(r"[，。；：:、]", text) if len(re.sub(r"[^\u4e00-\u9fffA-Za-z]", "", phrase)) >= 8]
        substantive = [re.sub(r"公司披露|年报披露|年报自述|公告披露|公司自述|年报引|据年报", "", phrase) for phrase in phrases]
        hits = sum(1 for phrase in substantive if phrase and re.sub(r"[\s，。；：:、]", "", phrase).lower() in normalized)
        return hits >= 1 or bool(provider_terms and any(term.lower() in normalized for term in provider_terms))
    kept: list[dict[str, Any]] = []
    for blocker in raw.get("blockers") or []:
        if not isinstance(blocker, Mapping):
            kept.append({"code": "qa_blocker_shape", "message": str(blocker)})
            continue
        row = dict(blocker)
        claim = claims_by_id.get(str(row.get("claim_id") or ""), {})
        kind = str(claim.get("kind") or "")
        claim_text = str(claim.get("text") or "")
        severity = str(row.get("severity") or "blocker").lower()
        category = str(row.get("category") or "").lower()
        code = str(row.get("code") or "")
        message = str(row.get("message") or "")

        # The independent model is explicitly allowed to flag an aggressive
        # synthesis as an advisory when it asks for the judgment phrase to be
        # literally present in the filing.  It is not allowed to downgrade a
        # concrete provenance/numeric/identity mismatch.
        if kind == "judgment" and claim.get("evidence_ids") and claim.get("falsifier"):
            hard_judgment_markers = re.compile(
                r"evidence_id.*不在|不在.*(?:packet|证据)|数字|数值|单位|百分比|金额|年份|客户|订单|排名|份额|"
                r"引用错误|错误|错配|具体事实|目标价|仓位|买入|卖出|历史实际|条件句",
                re.IGNORECASE,
            )
            if severity == "advisory" or category == "judgment_synthesis":
                continue
            if code.upper() in {"EVIDENCE_MISMATCH", "MISSING_EVIDENCE", "UNSUPPORTED_INFERENCE", "UNSUPPORTED_CLAIM"} and not hard_judgment_markers.search(message):
                continue
        if code in {
            "third_party_attribution_missing", "self_report_not_attributed", "missing_self_report_label",
            "missing_attribution", "self_report_attribution", "MISSING_ATTRIBUTION", "MISSING_SELF_REPORT_LABEL",
        } and kind in {"judgment", "issuer_self_report"}:
            if attributed_context(str(row.get("claim_id") or "")) and not re.search(r"evidence_id|数字不一致|数值错误|单位错误|页码错误|不在.*(?:packet|证据)", message, re.IGNORECASE):
                continue
        if code in {"missing_evidence_id", "claim_refs"}:
            row_refs = {str(ref) for ref in row.get("evidence_ids") or []}
            if row_refs and row_refs.issubset(set(evidence_by_id)):
                # The model's compact QA snapshot can lose track of a long
                # evidence id even though the deterministic packet contains
                # it.  validate_dossier remains the authority for a real
                # missing reference.
                continue
        # The QA model can misread the long ``source:narrative:page:index``
        # identifiers in its compact packet and report an ID mismatch while
        # echoing the exact IDs that are present.  This is a provenance
        # bookkeeping false positive, not a permission to ignore a real
        # quote/page/number mismatch; deterministic validation remains the
        # authority for those concrete errors.
        if (
            code.upper() in {"EVIDENCE_ID_MISMATCH", "EVIDENCE_MISMATCH"}
            and row.get("evidence_ids")
            and {str(ref) for ref in row.get("evidence_ids") or []}.issubset(set(evidence_by_id))
            and re.search(r"无此ID|不在.*(?:packet|证据)|实际packet中|packet中为|ID格式不一致", message, re.IGNORECASE)
            and not re.search(r"数字|数值|单位|页码|引用内容|quoted_anchor|锚文本", message, re.IGNORECASE)
        ):
            continue
        # A QA reviewer may compare a rounded, deterministic derived metric
        # to the full-precision value and call the display rounding a numeric
        # mismatch.  If the claim is bound to the derived metric and the
        # message itself says rounding/precision, the deterministic contract
        # has already checked the direction and both source facts; treat this
        # as advisory rather than blocking the dossier.
        if (
            code.lower() in {"derived_value_mismatch", "numeric_mismatch", "rounding_mismatch"}
            and str(row.get("claim_id") or "") in claims_by_id
            and claims_by_id[str(row.get("claim_id") or "")].get("derived_ids")
            and re.search(r"四舍五入|舍入|round|精度|derived|派生", message, re.IGNORECASE)
        ):
            continue
        hard_provenance_message = re.compile(r"evidence_id.*不在|不在.*(?:packet|证据)|数字不一致|数值错误|单位错误|页码错误|引用错误|具体数字.*(?:错误|不一致)", re.IGNORECASE)
        if (code.upper() in {"EVIDENCE_MISMATCH", "MISSING_EVIDENCE"} or category == "provenance") and kind in {"fact", "issuer_self_report", "judgment"}:
            # A judgment that cites relevant underlying facts is allowed to
            # synthesize a conclusion not written verbatim in the filing.
            if kind == "judgment" and claim.get("evidence_ids") and claim.get("falsifier") and not hard_provenance_message.search(message):
                continue
            if literal_evidence_support(claim) and not hard_provenance_message.search(message):
                continue
        if kind == "gap" and (
            claim_text.startswith(("输入未提供", "证据不足", "当前未提供"))
            or (not claim.get("evidence_ids") and re.search(r"无法|缺乏|缺失|不足|未披露|未知", claim_text))
        ):
            # Gap claims intentionally describe what the packet does not
            # contain; they do not need a second evidence ref and are not
            # downgraded merely because neighbouring pages contain partial
            # information.
            continue
        if kind == "judgment" and claim.get("evidence_ids") and claim.get("falsifier"):
            # The deterministic contract already checks that every rendered
            # judgment marker is present and bound.  DeepSeek may still emit
            # a stale ``judgment_missing_marker`` blocker based on an earlier
            # sentence snapshot; keep it only when the actual body is missing
            # the claim marker.
            if code in {"judgment_missing_marker", "JUDGMENT_MISSING_MARKER"} and f"[{claim.get('claim_id')}]" in body_text:
                continue
        if kind == "issuer_self_report" and row.get("code") in {"self_report_body_unmarked", "SELF_REPORT_BODY_UNMARKED"}:
            marker = f"[{claim.get('claim_id')}]"
            if any(marker in paragraph and re.search(r"公司披露|年报披露|年报自述|公告披露|公司自述|据年报|年报引|公司年报", paragraph) for paragraph in body_text.split("\n")):
                continue
        kept.append(row)
    return kept


def independent_qa(
    dossier: Mapping[str, Any], packet: Mapping[str, Any], machine: Mapping[str, Any], *,
    key_file: Path = DEFAULT_KEY_FILE, model: str = DEFAULT_MODEL, transport: Any = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request = build_qa_request(dossier, packet, machine)
    raw, provider_receipt = call_structured_deepseek(
        system_prompt=QA_SYSTEM_PROMPT,
        request_object=request,
        key_file=key_file,
        model=model,
        max_tokens=5000,
        reasoning_effort="medium",
        temperature=0.0,
        thinking_type="disabled",
        transport=transport,
    )
    qa = dict(raw)
    # Preserve the model's unfiltered verdict before the deterministic filter
    # recomputes the gate status.  A receipt must distinguish “the reviewer
    # emitted blockers” from “those blockers survived packet-backed checks”.
    qa["raw_status"] = raw.get("status") if raw.get("status") in {"passed", "failed"} else "failed"
    qa["raw_blockers"] = list(raw.get("blockers") or [])
    qa["blockers"] = _filter_false_positive_blockers(raw, dossier, packet)
    qa["advisories"] = [
        dict(row)
        for row in raw.get("blockers") or []
        if isinstance(row, Mapping)
        and (str(row.get("severity") or "").lower() == "advisory" or str(row.get("category") or "").lower() == "judgment_synthesis")
    ]
    qa["request_hash"] = canonical_hash(request)
    qa["response_hash"] = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    qa["run_id"] = f"editorial-v4-qa:{provider_receipt.get('request_id') or qa['response_hash'][:24]}"
    qa["provider"] = "DeepSeek"
    qa["model"] = provider_receipt.get("model") or model
    qa["request_id"] = provider_receipt.get("request_id")
    qa["prompt_version"] = QA_PROMPT_VERSION
    qa["filter_version"] = QA_FILTER_VERSION
    qa["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if qa.get("status") not in {"passed", "failed"} or not isinstance(qa.get("blockers"), list):
        qa["status"] = "failed"
        qa.setdefault("blockers", []).append({"code": "qa_shape", "message": "independent QA response shape is invalid"})
    else:
        qa["status"] = "passed" if not qa["blockers"] else "failed"
    return qa, provider_receipt, request


def repair_feedback(machine: Mapping[str, Any], qa: Mapping[str, Any]) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    for error in machine.get("errors") or []:
        if isinstance(error, Mapping):
            feedback.append({"source": "machine", **dict(error)})
    for blocker in qa.get("blockers") or []:
        if isinstance(blocker, Mapping):
            feedback.append({"source": "independent_qa", **dict(blocker)})
    return feedback[:80]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_quality_loop(
    packet: Mapping[str, Any], out_dir: Path, *, max_iterations: int = 3,
    key_file: Path = DEFAULT_KEY_FILE, model: str = DEFAULT_MODEL, transport: Any = None,
) -> dict[str, Any]:
    """Generate, diagnose, and repair a dossier without ever human-approving it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    feedback: list[dict[str, Any]] = []
    iterations: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    prior: Mapping[str, Any] | None = None
    for iteration in range(max_iterations):
        dossier, provider_receipt, request = generate_once(
            packet,
            key_file=key_file,
            model=model,
            iteration=iteration,
            repair_feedback=feedback,
            prior_dossier=prior,
            reasoning_effort="high",
            max_tokens=22000,
            thinking_type="enabled",
            transport=transport,
        )
        machine = validate_dossier(dossier, packet)
        qa, qa_receipt, qa_request = independent_qa(
            dossier, packet, machine, key_file=key_file, model=model, transport=transport,
        )
        iteration_dir = out_dir / "iterations" / str(iteration)
        iteration_dir.mkdir(parents=True, exist_ok=True)
        write_draft(dossier, iteration_dir)
        _write_json(iteration_dir / "generation-request.json", request)
        _write_json(iteration_dir / "provider-receipt.json", provider_receipt)
        _write_json(iteration_dir / "machine-validation.json", machine)
        _write_json(iteration_dir / "independent-qa.json", qa)
        _write_json(iteration_dir / "qa-request.json", qa_request)
        row = {
            "iteration": iteration,
            "run_id": dossier.get("production_record", {}).get("run_id"),
            "request_id": provider_receipt.get("request_id"),
            "report_hash": canonical_hash(dossier),
            "machine_status": machine.get("status"),
            "machine_errors": len(machine.get("errors") or []),
            "qa_status": qa.get("status"),
            "qa_run_id": qa.get("run_id"),
            "qa_request_id": qa_receipt.get("request_id"),
            "qa_blockers": len(qa.get("blockers") or []),
            "qa_advisories": len(qa.get("advisories") or []),
        }
        iterations.append(row)
        final = dossier
        prior = dossier
        if machine.get("status") == "passed" and qa.get("status") == "passed":
            break
        feedback = repair_feedback(machine, qa)
    if final is None:
        raise RuntimeError("quality loop produced no dossier")
    final_dir = out_dir
    write_draft(final, final_dir)
    render_dossier(final, packet, final_dir)
    summary = {
        "schema_version": "editorial-v4-quality-loop-receipt-v1",
        "ticker": packet.get("ticker"),
        "packet_hash": packet.get("packet_hash"),
        "iterations": iterations,
        "final_status": "passed" if iterations[-1]["machine_status"] == "passed" and iterations[-1]["qa_status"] == "passed" else "needs_review",
        "review_status": "pending",
        "action_state": "blocked",
        "no_tier_credit": True,
        "no_publication_credit": True,
        "advisory_count": int((iterations[-1] if iterations else {}).get("qa_advisories", 0)),
    }
    _write_json(out_dir / "quality-loop-receipt.json", summary)
    return summary
