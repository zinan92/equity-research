"""Cross-company research contract built around frozen evidence, not model memory.

The module intentionally separates three things that used to be conflated:
company-specific research questions, immutable evidence, and the shared report
format.  Adapters may change the questions.  They cannot change the eight-module
report structure or make an unsupported assertion publishable.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import ipaddress
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from report_contract import MODULE_SPECS, ReportContractError, attach_report_contract, validate_report_contract


PIPELINE_VERSION = "cross-company-research-v1"
EVIDENCE_SCHEMA_VERSION = "cross-company-evidence-v1"
TEMPLATE_VERSION = "institutional-report-v1"
MODEL_BOUNDARY_VERSION = "frozen-evidence-only-v1"
CROSS_COMPANY_PROMPT_VERSION = "cross-company-writer-v4"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CLAIM_TYPES = {"fact", "inference", "risk"}
SECTIONS = {"thesis", "business", "industry", "management", "risk"}
TRUSTED_SOURCE_DOMAINS = {
    "cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn", "stats.gov.cn",
    "csindex.com.cn", "chinabond.com.cn", "pbc.gov.cn", "csrc.gov.cn",
    "news.cn", "people.com.cn", "iea.org", "sneresearch.com",
    "nbd.com.cn", "cpnn.com.cn", "eeo.com.cn",
    "catl.com", "moutaichina.com", "moutai.com.cn", "cmbchina.com",
    "cypc.com.cn", "midea.com.cn", "midea.com",
}


class CrossCompanyResearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompanyAdapter:
    ticker: str
    name: str
    exchange: str
    industry: str
    industry_key: str
    comparables: tuple[str, ...]
    value_chain: tuple[str, ...]
    evidence_questions: tuple[str, ...]
    adapter_version: str = "1.0.0"


@dataclass(frozen=True)
class _VerifiedEvidencePacket:
    """Opaque result of the integrity-checking research evidence store adapter."""

    payload: dict[str, Any]


COMPANY_ADAPTERS: dict[str, CompanyAdapter] = {
    "600519.SH": CompanyAdapter(
        "600519.SH", "贵州茅台", "上海证券交易所", "白酒", "consumer_brands",
        ("五粮液", "泸州老窖", "山西汾酒"),
        ("原粮与基酒", "生产与储存", "渠道与配额", "消费者与礼赠需求"),
        ("量价增长如何拆分", "渠道库存是否健康", "品牌溢价能否转化为现金", "资本回报是否持续"),
    ),
    "600036.SH": CompanyAdapter(
        "600036.SH", "招商银行", "上海证券交易所", "银行", "commercial_bank",
        ("平安银行", "兴业银行", "宁波银行"),
        ("负债与存款", "信贷与非息业务", "资产质量", "资本与分红"),
        ("净息差如何变化", "不良生成与拨备是否匹配", "财富管理收入是否恢复", "资本充足率是否约束增长"),
    ),
    "600900.SH": CompanyAdapter(
        "600900.SH", "长江电力", "上海证券交易所", "水力发电", "regulated_utility",
        ("国投电力", "华能水电", "川投能源"),
        ("来水与库容", "发电与调度", "电价与结算", "现金流与分红"),
        ("来水波动如何影响发电量", "电价机制是否稳定", "资本开支与自由现金流如何匹配", "分红可持续性如何验证"),
    ),
    "000333.SZ": CompanyAdapter(
        "000333.SZ", "美的集团", "深圳证券交易所", "家用电器", "global_manufacturing",
        ("格力电器", "海尔智家", "海信家电"),
        ("零部件与采购", "制造与自动化", "渠道与海外", "售后与更新需求"),
        ("内外销增长如何拆分", "产品结构是否改善毛利", "海外本地化是否提升回报", "并购与资本配置是否增值"),
    ),
    "300750.SZ": CompanyAdapter(
        "300750.SZ", "宁德时代", "深圳证券交易所", "动力电池", "new_energy_manufacturing",
        ("比亚迪", "亿纬锂能", "国轩高科"),
        ("资源与材料", "电芯与制造", "系统集成", "整车与储能应用"),
        ("份额是否由盈利质量支持", "扩产与库存能否被需求消化", "技术迭代是否维持客户黏性", "海外执行是否改善现金回报"),
    ),
}


DEFAULT_CLAIM_CONFIG: dict[str, dict[str, Any]] = {
    "600519.SH": {
        "sources": ("moutai_2025_annual", "moutai_2026_h1_market_meeting", "xinhua_moutai_2025_results"),
        "business": "白酒业务质量应围绕量价结构、渠道库存、品牌溢价、现金转化与资本回报逐项验证。",
        "risk": "若后续正式披露显示渠道、盈利质量或品牌需求恶化，当前研究假设必须重估。",
        "trigger": "后续正式披露改变渠道、需求或盈利质量判断",
        "limitations": (
            "没有渠道库存、动销或相对定价证据，不得断言库存精准、需求强弱或品牌溢价水平。",
            "没有股价、估值倍数、历史区间或同业估值证据，估值章节必须写 Missing evidence。",
            "不得把市场化改革目标写成已实现结果，海外突破、直营提升和消费场景只可写待验证。",
            "销量或收入增长只能按披露原意描述，不得自行评价为较快；产品分类施策是未来动作，不得写成产品结构已经强化。",
            "没有宏观情景、价格稳定、市场份额、替代性或同行比较证据，不得写量稳价平、品牌独占、护城河维持或全链条掌控。",
            "分红只可描述已披露的总额或占比变化；没有同口径每股比较时不得写每股分红进一步增强。",
        ),
    },
    "600036.SH": {
        "stem": "cmb",
        "sources": ("cmb_2025_preliminary", "cmb_2026_q1", "nbd_cmb_2025_results"),
        "thesis": "招商银行的长期研究结论必须同时由公司披露的年度业绩、季度更新与独立交叉核验支持。",
        "business": "银行业务质量应围绕负债成本、净息差、资产质量、财富管理与资本充足性逐项验证。",
        "risk": "若后续正式披露显示资产质量、盈利能力或资本约束恶化，当前研究假设必须重估。",
        "risk_title": "Banking evidence changes",
        "trigger": "后续正式披露改变关键盈利或风险指标",
        "limitations": (
            "没有同业存款成本、零售 AUM、市场份额或客户切换成本证据，不得推断同业优势。",
            "没有股价、估值倍数或可观察阈值证据，估值章节必须写 Missing evidence，不得声称红线尚未触发。",
            "媒体交叉核验只支持其明确披露的信用卡和财富管理变化，不得外推整体客户黏性。",
            "没有监管阈值、资本充足率或分红政策证据，不得写高于监管要求、资本安全垫或分红能力维持。",
            "没有信用成本、减值计提或利润桥证据，不得把利润变化归因于信用成本控制，也不得写拨备反哺利润。",
            "不良率变化不能单独证明风控有效；没有不良生成、迁徙、核销或可观察阈值时不得写风险未恶化或阈值未触发。",
        ),
    },
    "600900.SH": {
        "sources": ("cypc_2025_annual", "cypc_2026_q1", "cpnn_cypc_2025_results"),
        "business": "水电业务质量应围绕来水、发电量、电价机制、资本开支、自由现金流与分红持续性逐项验证。",
        "risk": "若后续正式披露显示来水、电价、资本开支或分红能力恶化，当前研究假设必须重估。",
        "trigger": "后续正式披露改变发电、现金流或分红能力判断",
        "limitations": (
            "没有电价机制、完整电站清单、装机同行比较或流域调度权证据，不得断言独占、不可复制或政府定价稳定。",
            "经营现金流不是自由现金流；没有资本开支高峰、多年分红、授信或再融资证据，不得推断其持续覆盖能力。",
            "没有股价和估值倍数证据，估值章节必须写 Missing evidence。",
            "没有来水或发电量证据，不得把收入利润变化归因于来水稳定或发电量稳定。",
            "没有日常开支、利息支出或资本开支对照，不得声称经营现金流覆盖开支、债务成本或分红。",
            "没有完整借款结构和比较基准，不得评价长期借款占比较高；现金流只可作事实描述，不得评价充沛或造血能力强。",
        ),
    },
    "000333.SZ": {
        "sources": ("midea_2025_annual", "midea_2026_q1", "nbd_midea_2025_results"),
        "business": "制造业务质量应围绕内外销结构、毛利改善、海外本地化、经营现金流与资本配置逐项验证。",
        "risk": "若后续正式披露显示海外执行、盈利质量或资本配置恶化，当前研究假设必须重估。",
        "trigger": "后续正式披露改变海外增长、现金转化或资本回报判断",
        "limitations": (
            "管理层成本领先战略不是已验证的同行成本优势；没有同行效率比较，不得直接下护城河结论。",
            "没有海外仓储物流、售后黏性或自动化工厂输出证据，不得扩写产业链事实。",
            "年度经营现金流变化与季度经营现金流必须分开描述；没有估值数据，估值章节必须写 Missing evidence。",
            "海外增速高于国内只可写增长分化，不得写结构失衡、国内增长放缓、产品结构改善有限或海外已成为主要驱动力。",
            "其他综合收益中的外币报表折算不得写成当期盈利不稳定；没有利润桥时不得写非经常性项目掩盖主营波动。",
            "估值缺失适用于全文和投委会情景，不得写合理估值、重估或安全边际；不得混写年度现金流下降与季度现金流增长。",
        ),
    },
    "300750.SZ": {
        "sources": ("catl_2025_annual", "catl_2026_q1", "sne_2026_ev_jan_apr"),
        "business": "电池业务质量应围绕动力与储能需求、份额质量、技术迭代、扩产消化、库存与现金转化逐项验证。",
        "risk": "若后续正式披露显示份额、产能利用、库存、现金转化或海外执行恶化，当前研究假设必须重估。",
        "trigger": "后续正式披露改变份额、产能或现金质量判断",
        "limitations": (
            "存货增加没有动机证据，不得解释为主动备货；没有续约、留存或切换成本证据，不得断言客户锁定。",
            "材料披露回收业务与回收量，但没有再生材料回用于制造的链路证据，不得写材料闭环；没有同行盈利增速、独立技术对比或估值证据，不得扩写同业领先、壁垒强度或当前估值。",
            "Alfen 文件是合作备忘录，不是合同、确认订单或收入；所有商业化结果必须写待验证。",
            "新业务布局或项目不等于收入贡献；不得写其已经拓展收入来源。",
            "在建产能不等于产能充足或能够支撑未来交付；没有需求、利用率、投产进度和订单匹配时只能描述在建事实。",
            "MOU 是否具有法律约束力需以协议条款判断；只能写不是已确认合同、订单或收入，不得断言无法律约束力。",
            "现金和经营现金流事实不等于资本充足、财务健康或安全垫厚实；没有完整杠杆和到期债务分析时不得作综合评级。",
        ),
    },
}


def default_company_claims(ticker: str, *, available_source_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Return the versioned, company-semantic research questions for a passed evidence set."""

    normalized = ticker.upper()
    company_adapter(normalized)
    config = DEFAULT_CLAIM_CONFIG[normalized]
    sources = list(config["sources"])
    if available_source_ids is not None:
        missing = sorted(set(sources) - set(available_source_ids))
        if missing:
            raise CrossCompanyResearchError(f"required company evidence is unavailable: {missing}")
    stem = config.get("stem") or normalized.replace(".", "_").lower()
    return [
        {
            "id": f"{stem}_thesis", "section": "thesis", "title": "Evidence-bounded thesis",
            "statement": config.get("thesis") or "长期研究结论必须同时由公司正式披露、最新季度更新与独立交叉核验支持。",
            "claim_type": "inference", "source_ids": sources,
        },
        {
            "id": f"{stem}_business", "section": "business", "statement": config["business"],
            "claim_type": "inference", "source_ids": sources[:2],
        },
        {
            "id": f"{stem}_risk", "section": "risk", "title": config.get("risk_title") or "Evidence change risk",
            "statement": config["risk"], "claim_type": "risk", "trigger": config["trigger"],
            "source_ids": [sources[1], sources[2]],
        },
    ]


def default_company_limitations(ticker: str) -> list[str]:
    normalized = ticker.upper()
    company_adapter(normalized)
    return list(DEFAULT_CLAIM_CONFIG[normalized]["limitations"])


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _instant(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CrossCompanyResearchError("time must be a timezone-aware ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CrossCompanyResearchError("time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _source_known_at(value: Any) -> str:
    """Normalize evidence-store publication dates into auditable instants."""

    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return f"{value.strip()}T23:59:59+08:00"
    _instant(value)
    return str(value)


def _trusted_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            return False
    except ValueError:
        pass
    return any(host == domain or host.endswith(f".{domain}") for domain in TRUSTED_SOURCE_DOMAINS)


def company_adapter(ticker: str) -> CompanyAdapter:
    normalized = ticker.upper()
    try:
        return COMPANY_ADAPTERS[normalized]
    except KeyError as exc:
        raise CrossCompanyResearchError(f"no approved company adapter for {normalized}") from exc


def _packet_payload(packet: dict[str, Any] | _VerifiedEvidencePacket) -> dict[str, Any]:
    return deepcopy(packet.payload if isinstance(packet, _VerifiedEvidencePacket) else packet)


def validate_frozen_evidence(
    packet: dict[str, Any] | _VerifiedEvidencePacket, *, adapter: CompanyAdapter | None = None,
) -> list[str]:
    packet = _packet_payload(packet)
    errors: list[str] = []
    resolved = adapter
    try:
        resolved = resolved or company_adapter(str(packet.get("ticker") or ""))
    except CrossCompanyResearchError as exc:
        errors.append(str(exc))
    if packet.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        errors.append("unsupported evidence schema")
    if packet.get("status") != "passed":
        errors.append("evidence gate is not passed")
    fixture_only = packet.get("fixture_only") is True
    if not fixture_only:
        if packet.get("capture_verified") is not True:
            errors.append("production evidence requires capture_verified=true")
        if not isinstance(packet.get("gate_hash"), str) or not HASH_RE.fullmatch(packet["gate_hash"]):
            errors.append("production evidence requires a gate_hash")
    if resolved and (packet.get("ticker") != resolved.ticker or packet.get("name") != resolved.name):
        errors.append("evidence identity does not match company adapter")
    if not isinstance(packet.get("snapshot_id"), str) or not packet.get("snapshot_id"):
        errors.append("snapshot_id is required")
    try:
        cutoff = _instant(packet.get("knowledge_cutoff"))
    except (ValueError, CrossCompanyResearchError) as exc:
        cutoff = None
        errors.append(str(exc))
    documents = packet.get("documents")
    if not isinstance(documents, list):
        documents = []
        errors.append("documents must be an array")
    document_ids: list[str] = []
    primary_count = 0
    independent_count = 0
    for index, document in enumerate(documents):
        path = f"documents[{index}]"
        if not isinstance(document, dict):
            errors.append(f"{path} must be an object")
            continue
        source_id = document.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(f"{path}.id is required")
        else:
            document_ids.append(source_id)
        for field in ("document_id", "title", "kind", "known_at", "note"):
            if not isinstance(document.get(field), str) or not document[field].strip():
                errors.append(f"{path}.{field} is required")
        if document.get("kind") in {"primary", "company_release"}:
            primary_count += 1
        elif document.get("kind") == "independent":
            independent_count += 1
        else:
            errors.append(f"{path}.kind is unsupported")
        if not _trusted_url(document.get("url")):
            errors.append(f"{path}.url is not an approved public HTTPS source")
        for field in ("raw_sha256", "content_hash"):
            if not isinstance(document.get(field), str) or not HASH_RE.fullmatch(document[field]):
                errors.append(f"{path}.{field} must be a sha256 digest")
        if not fixture_only and (
            not isinstance(document.get("capture_receipt_hash"), str)
            or not HASH_RE.fullmatch(document["capture_receipt_hash"])
        ):
            errors.append(f"{path}.capture_receipt_hash is required for production evidence")
        try:
            known = _instant(document.get("known_at"))
            if cutoff and known > cutoff:
                errors.append(f"{path} is newer than the knowledge cutoff")
        except (ValueError, CrossCompanyResearchError):
            errors.append(f"{path}.known_at must be timezone-aware")
    if len(document_ids) != len(set(document_ids)):
        errors.append("document IDs must be unique")
    if len(documents) < 3 or primary_count < 2 or independent_count < 1:
        errors.append("deep research requires two primary documents and one independent cross-check")
    limitations = packet.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 1:
        errors.append("research limitations must be a non-empty array")
    elif any(not isinstance(item, str) or not item.strip() for item in limitations):
        errors.append("research limitations must contain non-empty strings")
    claims = packet.get("claims")
    if not isinstance(claims, list):
        claims = []
        errors.append("claims must be an array")
    claim_ids: list[str] = []
    for index, claim in enumerate(claims):
        path = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{path} must be an object")
            continue
        if not isinstance(claim.get("id"), str) or not claim["id"]:
            errors.append(f"{path}.id is required")
        else:
            claim_ids.append(claim["id"])
        if claim.get("section") not in SECTIONS:
            errors.append(f"{path}.section is unsupported")
        if claim.get("claim_type") not in CLAIM_TYPES:
            errors.append(f"{path}.claim_type is unsupported")
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            errors.append(f"{path}.statement is required")
        refs = claim.get("source_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{path}.source_ids must be non-empty")
        elif sorted(set(refs) - set(document_ids)):
            errors.append(f"{path} cites unknown source IDs")
        if claim.get("claim_type") == "risk" and not claim.get("trigger"):
            errors.append(f"{path}.trigger is required for risk claims")
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("claim IDs must be unique")
    return sorted(set(errors))


def _manifest_payload(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": packet["schema_version"], "ticker": packet["ticker"],
        "snapshot_id": packet["snapshot_id"], "knowledge_cutoff": packet["knowledge_cutoff"],
        "fixture_only": packet.get("fixture_only") is True,
        "capture_verified": packet.get("capture_verified") is True,
        "gate_hash": packet.get("gate_hash"),
        "documents": packet["documents"], "claims": packet["claims"],
        "limitations": packet["limitations"],
    }


def freeze_evidence(packet: dict[str, Any] | _VerifiedEvidencePacket) -> dict[str, Any]:
    frozen = _packet_payload(packet)
    errors = validate_frozen_evidence(frozen)
    if errors:
        raise CrossCompanyResearchError("frozen evidence rejected: " + "; ".join(errors))
    manifest = _manifest_payload(frozen)
    manifest_hash = _digest(manifest)
    frozen["manifest_hash"] = manifest_hash
    frozen["evidence_set_id"] = f"xcr_{manifest_hash[:20]}"
    return frozen


def baseline_payload_hash(baseline: dict[str, Any]) -> str:
    """Hash the exact deterministic baseline consumed by the deep report.

    Presentation/runtime enrichments are excluded, but every market, financial,
    portfolio and source field that can affect the research output remains bound.
    """
    payload = deepcopy(baseline)
    for key in (
        "report_hash", "report_contract", "ai_narrative", "narrative_provider",
        "update_diff", "publication_approval",
    ):
        payload.pop(key, None)
    return _digest(payload)


def snapshot_binding_for_report(
    baseline: dict[str, Any], *, snapshot_manifest_hash: str | None = None,
) -> dict[str, str]:
    generated = baseline.get("generated_from") or {}
    snapshot_id = str(generated.get("snapshot_id") or "")
    if not snapshot_id:
        raise CrossCompanyResearchError("baseline snapshot identity is missing")
    data_mode = baseline.get("data_mode")
    if data_mode == "REAL":
        if not isinstance(snapshot_manifest_hash, str) or not HASH_RE.fullmatch(snapshot_manifest_hash):
            raise CrossCompanyResearchError("REAL research requires a verified snapshot manifest hash")
        expected_prefix = f"snap_real_{snapshot_manifest_hash[:12]}"
        if snapshot_id != expected_prefix and not snapshot_id.startswith(expected_prefix + "_"):
            raise CrossCompanyResearchError("snapshot ID disagrees with its manifest hash")
    elif data_mode == "ACCEPTANCE_FIXTURE":
        snapshot_manifest_hash = _digest({"fixture_only": True, "snapshot_id": snapshot_id})
    else:
        raise CrossCompanyResearchError("snapshot binding allows only REAL or ACCEPTANCE_FIXTURE data")
    return {
        "snapshot_id": snapshot_id,
        "snapshot_manifest_hash": str(snapshot_manifest_hash),
        "baseline_payload_hash": baseline_payload_hash(baseline),
    }


def production_input_identity(
    packet: dict[str, Any] | _VerifiedEvidencePacket, *, model: str, prompt_version: str,
    snapshot_binding: dict[str, str],
) -> str:
    raw = _packet_payload(packet)
    frozen = freeze_evidence(raw) if "manifest_hash" not in raw else raw
    if frozen.get("manifest_hash") != _digest(_manifest_payload(frozen)):
        raise CrossCompanyResearchError("evidence manifest was modified after freeze")
    adapter = company_adapter(frozen["ticker"])
    required_binding = {"snapshot_id", "snapshot_manifest_hash", "baseline_payload_hash"}
    if set(snapshot_binding) != required_binding or any(
        not isinstance(snapshot_binding.get(key), str) or not snapshot_binding[key]
        for key in required_binding
    ):
        raise CrossCompanyResearchError("snapshot binding is incomplete")
    if snapshot_binding["snapshot_id"] != frozen["snapshot_id"]:
        raise CrossCompanyResearchError("snapshot binding disagrees with frozen evidence")
    if not HASH_RE.fullmatch(snapshot_binding["snapshot_manifest_hash"]) or not HASH_RE.fullmatch(
        snapshot_binding["baseline_payload_hash"]
    ):
        raise CrossCompanyResearchError("snapshot binding hashes are invalid")
    return _digest({
        "pipeline_version": PIPELINE_VERSION, "template_version": TEMPLATE_VERSION,
        "adapter": asdict(adapter), "snapshot_binding": snapshot_binding,
        "evidence_manifest_hash": frozen["manifest_hash"], "model": model,
        "prompt_version": prompt_version, "boundary": MODEL_BOUNDARY_VERSION,
    })


def frozen_model_input(
    packet: dict[str, Any] | _VerifiedEvidencePacket, *, model: str, prompt_version: str,
    snapshot_binding: dict[str, str],
) -> dict[str, Any]:
    raw = _packet_payload(packet)
    frozen = freeze_evidence(raw) if "manifest_hash" not in raw else raw
    identity = production_input_identity(
        frozen, model=model, prompt_version=prompt_version, snapshot_binding=snapshot_binding,
    )
    adapter = company_adapter(frozen["ticker"])
    return {
        "boundary_version": MODEL_BOUNDARY_VERSION,
        "input_identity": identity,
        "model": model,
        "prompt_version": prompt_version,
        "snapshot_binding": deepcopy(snapshot_binding),
        "company_adapter": asdict(adapter),
        "frozen_evidence": frozen,
        "instructions": {
            "module_order": [spec.id for spec in MODULE_SPECS],
            "rule": "Use only frozen_evidence. Cite source_ids. If evidence is absent, write Missing evidence.",
            "network_access": "forbidden",
        },
    }


def _claims(packet: dict[str, Any], section: str) -> list[dict[str, Any]]:
    return [item for item in packet["claims"] if item["section"] == section]


def _source_ids(items: list[dict[str, Any]], fallback: list[str]) -> list[str]:
    ids = []
    for item in items:
        ids.extend(item["source_ids"])
    return list(dict.fromkeys(ids)) or fallback


def build_cross_company_report(
    baseline: dict[str, Any], packet: dict[str, Any] | _VerifiedEvidencePacket, *, model: str = "deepseek-v4-pro",
    prompt_version: str = CROSS_COMPANY_PROMPT_VERSION,
    snapshot_manifest_hash: str | None = None,
) -> dict[str, Any]:
    """Promote a verified snapshot baseline to deep research using one frozen packet."""
    verified_production_packet = isinstance(packet, _VerifiedEvidencePacket)
    raw = _packet_payload(packet)
    frozen = freeze_evidence(raw) if "manifest_hash" not in raw else raw
    if validate_frozen_evidence(frozen):
        raise CrossCompanyResearchError("invalid frozen evidence")
    adapter = company_adapter(str(baseline.get("ticker") or ""))
    generated = baseline.get("generated_from") or {}
    if baseline.get("name") != adapter.name or generated.get("snapshot_id") != frozen["snapshot_id"]:
        raise CrossCompanyResearchError("baseline, adapter and evidence identities disagree")
    if baseline.get("research_status") not in {"baseline", "verified"}:
        raise CrossCompanyResearchError("baseline did not pass its research gate")
    data_mode = baseline.get("data_mode")
    if data_mode not in {"REAL", "ACCEPTANCE_FIXTURE"}:
        raise CrossCompanyResearchError("cross-company reports allow only REAL or ACCEPTANCE_FIXTURE data")
    if data_mode == "REAL" and (
        not verified_production_packet or frozen.get("fixture_only") is True
        or baseline.get("data_status") != "verified"
    ):
        raise CrossCompanyResearchError(
            "REAL research requires a verified snapshot and an evidence-store packet"
        )
    if data_mode == "ACCEPTANCE_FIXTURE" and frozen.get("fixture_only") is not True:
        raise CrossCompanyResearchError("acceptance output requires fixture-only evidence")
    output = deepcopy(baseline)
    for key in ("report_contract", "report_hash", "update_diff", "ai_narrative", "narrative_provider"):
        output.pop(key, None)
    snapshot_binding = snapshot_binding_for_report(
        baseline, snapshot_manifest_hash=snapshot_manifest_hash,
    )
    input_identity = production_input_identity(
        frozen, model=model, prompt_version=prompt_version, snapshot_binding=snapshot_binding,
    )
    output.update({
        "report_version": PIPELINE_VERSION,
        "research_status": "verified",
        "research_depth": "deep",
        "research_profile_hash": _digest(asdict(adapter)),
        "research_logic_hash": _digest({"pipeline": PIPELINE_VERSION, "template": TEMPLATE_VERSION}),
        "title": f"{adapter.name}：标准化深度研究与证据边界",
        "depth_disclosure": "公司语义、行业问题与证据需求已完成适配；每个结论只来自本次冻结证据包。",
        "known_at": frozen["knowledge_cutoff"],
        "research_known_at": frozen["knowledge_cutoff"],
        "generated_from": {
            **generated, "evidence_set_id": frozen["evidence_set_id"],
            "evidence_manifest_hash": frozen["manifest_hash"],
            "production_input_identity": input_identity,
            "snapshot_manifest_hash": snapshot_binding["snapshot_manifest_hash"],
            "baseline_payload_hash": snapshot_binding["baseline_payload_hash"],
            "template_version": TEMPLATE_VERSION, "adapter_version": adapter.adapter_version,
            "narrative_model": model, "prompt_version": prompt_version,
            "model_boundary_version": MODEL_BOUNDARY_VERSION,
        },
    })
    documents = [{
        "id": item["id"], "document_id": item["document_id"], "title": item["title"],
        "kind": item["kind"], "strength": "强" if item["kind"] == "primary" else "中",
        "known_at": item["known_at"], "url": item["url"], "note": item["note"],
        "evidence_manifest_hash": frozen["manifest_hash"],
    } for item in frozen["documents"]]
    existing = []
    for item in output.get("sources") or []:
        source = deepcopy(item)
        if source.get("kind") != "market_snapshot":
            source["evidence_manifest_hash"] = frozen["manifest_hash"]
        existing.append(source)
    output["sources"] = [*existing, *documents]
    fallback_sources = [documents[0]["id"]]
    thesis = _claims(frozen, "thesis")
    business = _claims(frozen, "business")
    industry = _claims(frozen, "industry")
    management = _claims(frozen, "management")
    risks = _claims(frozen, "risk")
    output["thesis"] = [{
        "title": item.get("title") or "证据支持的投资逻辑", "body": item["statement"],
        "claim_type": item["claim_type"], "source_ids": item["source_ids"],
    } for item in thesis] or [{
        "title": "Missing evidence", "body": "Missing evidence：冻结证据尚不足以形成核心投资逻辑。",
        "claim_type": "fact", "source_ids": fallback_sources,
    }]
    output["business_model"] = {
        "description": " ".join(item["statement"] for item in business) if business else "Missing evidence：业务分部与盈利驱动仍待补充。",
        "segments": [],
        "value_chain": [
            {"layer": layer, "items": "待冻结证据逐层验证", "question": adapter.evidence_questions[min(index, len(adapter.evidence_questions) - 1)]}
            for index, layer in enumerate(adapter.value_chain)
        ],
        "source_ids": _source_ids(business, fallback_sources),
    }
    output["industry_position"] = {
        "headline": " ".join(item["statement"] for item in industry) if industry else "Missing evidence：同行份额与竞争排序尚未得到完整交叉验证。",
        "metrics": [{"label": "可比公司", "value": " / ".join(adapter.comparables), "note": "研究范围，不是排名结论"}],
        "source_ids": _source_ids(industry, fallback_sources),
    }
    output["management"] = {
        "score": None,
        "strengths": [item["statement"] for item in management] if management else ["Missing evidence：资本配置与治理优势待补充。"],
        "watchouts": ["所有治理判断须由监管披露和长期资本配置记录共同支持。"],
        "source_ids": _source_ids(management, fallback_sources),
    }
    output["moat"] = [{
        "name": "证据完整度", "score": 0,
        "proof": "Missing evidence：护城河强度必须由相对同行证据与长期财务记录共同验证。",
        "source_ids": fallback_sources,
    }]
    output["valuation"] = {
        "currency": "CNY", "current_price": float((output.get("market") or {}).get("price") or 0),
        "method": "Frozen-evidence scenario framework", "pe_ttm": (output.get("market") or {}).get("pe_ttm"),
        "pb": (output.get("market") or {}).get("pb"),
        "status": "missing_evidence", "reason": "Missing evidence：未冻结盈利预测与合理倍数，因此不形成目标价。",
        "scenarios": [
            {"case": case, "label": label, "target_price": 0, "upside_pct": 0, "eps": 0, "pe": 0, "assumption": "Missing evidence；零值是空状态，不是估值结论。", "currency": "CNY"}
            for case, label in (("bear", "悲观"), ("base", "基准"), ("bull", "乐观"))
        ],
        "earnings_bridge": {"base_period": "Missing evidence", "base_eps": 0, "basis": "No frozen forecast", "cases": [
            {"case": case, "label": label, "eps": 0, "growth_pct": 0}
            for case, label in (("bear", "悲观"), ("base", "基准"), ("bull", "乐观"))
        ]},
        "base_view": "Missing evidence", "reverse_implied": "Missing evidence",
        "warning": "零值表示估值证据缺失，不是目标价或收益率。",
    }
    output["risks"] = [{
        "rank": index + 1, "title": item.get("title") or "证据支持的风险",
        "impact": item.get("impact") or "高", "probability": item.get("probability") or "中",
        "trigger": item["trigger"], "evidence": item["statement"], "source_ids": item["source_ids"],
    } for index, item in enumerate(risks)] or [{
        "rank": 1, "title": "Missing evidence", "impact": "高", "probability": "中",
        "trigger": "关键公司或行业证据仍未进入冻结包", "evidence": "当前证据不足以排除重大反例。",
        "source_ids": fallback_sources,
    }]
    output["catalysts"] = [{
        "date": "下一次正式披露", "title": "证据更新窗口",
        "body": question, "source_ids": fallback_sources,
    } for question in adapter.evidence_questions[:2]]
    output["falsification"] = [f"若后续正式证据否定“{question}”的基准判断，则重建研究结论。" for question in adapter.evidence_questions[:3]]
    output["watchlist"] = [{
        "metric": question, "current": "Missing evidence", "threshold": "取得两类独立证据后更新", "frequency": "每次正式披露",
    } for question in adapter.evidence_questions]
    output["source_contract"] = {
        "execution": [item["id"] for item in output["sources"]],
        "financials": [item["id"] for item in output["sources"]],
        "valuation": [item["id"] for item in output["sources"]],
        "falsification": fallback_sources, "watchlist": fallback_sources,
    }
    document_ids = {item["document_id"] for item in output["sources"]}
    output["evidence_summary"] = {
        "claim_locator_count": len(output["sources"]), "document_count": len(document_ids),
        "independent_document_count": len({item["document_id"] for item in output["sources"] if item.get("kind") == "independent"}),
        "primary_count": sum(item.get("kind") in {"primary", "market_snapshot"} for item in output["sources"]),
        "company_release_count": sum(item.get("kind") == "company_release" for item in output["sources"]),
        "frozen_document_count": len({
            item["document_id"] for item in output["sources"]
            if item.get("kind") != "market_snapshot" and item.get("document_id")
        }),
        "frozen_manifest_hash": frozen["manifest_hash"], "frozen_evidence_set_id": frozen["evidence_set_id"],
        "boundary": "只使用当前 snapshot 与冻结公司证据；缺失项保持 Missing evidence。",
    }
    output.setdefault("disclaimer", "本报告用于研究框架与模型组合讨论，不构成投资建议。")
    fixture = output.get("data_mode") == "ACCEPTANCE_FIXTURE"
    output = attach_report_contract(output, structure_only=fixture)
    errors = validate_report_contract(output["report_contract"], output)
    if errors:
        raise ReportContractError("cross-company report rejected: " + "; ".join(errors))
    output["report_hash"] = report_payload_hash(output)
    return output


def render_standalone_html(report: dict[str, Any]) -> str:
    verify_report_integrity(report)
    errors = validate_report_contract(report.get("report_contract") or {}, report)
    if errors:
        raise ReportContractError("cannot render invalid report: " + "; ".join(errors))
    fixture = report.get("data_mode") == "ACCEPTANCE_FIXTURE"
    banner = "ACCEPTANCE FIXTURE · NOT LIVE RESEARCH" if fixture else "FROZEN EVIDENCE · VERIFIED RESEARCH"
    contracts = report.get("source_contract") or {}

    def record(text: Any, source_ids: Any) -> dict[str, Any]:
        return {
            "text": text,
            "source_ids": list(dict.fromkeys(source_ids)) if isinstance(source_ids, list) else [],
        }

    module_copy = {
        "executive_summary": [
            record(report["executive"].get("summary"), contracts.get("execution")),
            record(report["executive"].get("key_contradiction"), contracts.get("execution")),
        ],
        "investment_thesis": [
            record(item.get("body"), item.get("source_ids")) for item in report.get("thesis") or []
        ],
        "business_and_industry": [
            record(report["business_model"].get("description"), report["business_model"].get("source_ids")),
            record(report["industry_position"].get("headline"), report["industry_position"].get("source_ids")),
        ],
        "financial_quality": [
            record(report["financials"].get("headline"), contracts.get("financials")),
            *(record(item, contracts.get("financials")) for item in report["financials"].get("quality_notes") or []),
        ],
        "framework_assessment": [
            record(report["serenity"].get("meaning"), [
                source_id for factor in report["serenity"].get("factors") or []
                for source_id in factor.get("source_ids") or []
            ]),
            record(report["serenity"].get("method"), contracts.get("financials")),
        ],
        "valuation": [
            record(report["valuation"].get("reason"), contracts.get("valuation")),
            record(report["valuation"].get("method"), contracts.get("valuation")),
        ],
        "catalysts_risks": [
            *(record(item.get("evidence"), item.get("source_ids")) for item in report.get("risks") or []),
            *(record(item, contracts.get("falsification")) for item in report.get("falsification") or []),
        ],
        "evidence_ledger": [],
    }
    narrative = report.get("ai_narrative")
    if isinstance(narrative, dict):
        def block_lines(block: Any) -> list[dict[str, Any]]:
            if not isinstance(block, dict):
                return []
            source_ids = block.get("source_ids") or []
            lines = [
                *([block["title"]] if block.get("title") else []),
                *([block["conclusion"]] if block.get("conclusion") else []),
                *(block.get("paragraphs") or []),
            ]
            return [record(line, source_ids) for line in lines]

        narrative_sections = narrative.get("sections") or {}
        committee = narrative.get("investment_committee") or {}
        module_copy.update({
            "executive_summary": block_lines(narrative.get("executive_summary")),
            "investment_thesis": [
                *(block_lines(narrative.get("executive_summary"))[:1]),
                record(committee.get("bull_case"), committee.get("source_ids")),
                record(committee.get("base_case"), committee.get("source_ids")),
                record(committee.get("bear_case"), committee.get("source_ids")),
            ],
            "business_and_industry": [
                *block_lines(narrative_sections.get("industry_chain")),
                *block_lines(narrative_sections.get("business_quality")),
                *block_lines(narrative_sections.get("competitive_moat")),
            ],
            "financial_quality": block_lines(narrative_sections.get("financial_quality")),
            "valuation": block_lines(narrative_sections.get("valuation_debate")),
            "catalysts_risks": block_lines(narrative_sections.get("risk_falsification")),
        })
    sections = []
    for spec in MODULE_SPECS:
        if spec.id == "evidence_ledger":
            paragraphs = "".join(
                f'<article class="evidence" id="evidence-{escape(str(item["id"]))}">'
                f'<div><code>{escape(str(item["id"]))}</code> · {escape(str(item["title"]))}</div>'
                f'<div class="evidence-meta">{escape(str(item["known_at"]))} · {escape(str(item["kind"]))}</div>'
                + (
                    f'<a href="{escape(str(item["url"]))}" target="_blank" rel="noopener noreferrer">'
                    f'{escape(str(item["url"]))}</a>' if item.get("url") else "<span>Snapshot-bound source; no public URL</span>"
                )
                + "</article>"
                for item in report.get("sources") or []
            )
        else:
            paragraphs = "".join(
                f'<p>{escape(str(item["text"]))}'
                + (
                    '<span class="citations">' + " ".join(
                        f'<a href="#evidence-{escape(str(source_id))}" data-evidence-id="{escape(str(source_id))}">'
                        f'[{escape(str(source_id))}]</a>' for source_id in item["source_ids"]
                    ) + '</span>' if item["source_ids"] else ""
                )
                + "</p>"
                for item in module_copy[spec.id] if item.get("text")
            )
        status = next(item for item in report["report_contract"]["module_manifest"] if item["id"] == spec.id)
        sections.append(
            f'<section id="{spec.anchor}" data-report-module="{spec.id}">'
            f'<div class="section-no">{spec.order:02d}</div><div><div class="kicker">{escape(spec.kicker)}</div>'
            f'<h2>{escape(spec.title)}</h2><div class="status">{escape(status["status"])}</div>{paragraphs}</div></section>'
        )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(report['name'])} · 标准化深度研报</title><style>
@page{{size:A4;margin:16mm}}*{{box-sizing:border-box}}body{{margin:0;background:#eef1f5;color:#162033;font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif}}main{{width:min(1080px,100%);margin:0 auto;background:white;box-shadow:0 20px 70px #21304a22}}header{{padding:66px 72px 52px;border-top:9px solid #173f73;background:linear-gradient(135deg,#fff 0%,#f5f7fa 100%)}}.brand{{font-size:12px;letter-spacing:.22em;color:#6a7586;font-weight:700}}.banner{{margin-top:28px;display:inline-block;padding:7px 10px;background:#edf2f8;color:#173f73;font-size:11px;font-weight:700;letter-spacing:.08em}}h1{{font-family:Georgia,'Songti SC',serif;font-size:48px;line-height:1.18;margin:28px 0 18px;color:#102a4c}}.meta{{color:#667387;font-size:14px}}section{{display:grid;grid-template-columns:68px 1fr;gap:22px;padding:48px 72px;border-top:1px solid #dce2ea;min-height:280px}}.section-no{{font-family:Georgia,serif;color:#9aa7b8;font-size:28px}}.kicker{{color:#8a2533;font-size:11px;font-weight:700;letter-spacing:.16em}}h2{{font-family:Georgia,'Songti SC',serif;font-size:30px;margin:8px 0 8px;color:#173f73}}.status{{display:inline-block;border:1px solid #cfd7e2;padding:4px 8px;color:#6c7788;font-size:11px;margin-bottom:20px}}p{{font-size:16px;line-height:1.85;color:#354157;margin:10px 0}}.citations{{display:block;margin-top:4px;font-size:11px}}.citations a,article.evidence a{{color:#8a2533;text-decoration:none;overflow-wrap:anywhere}}article.evidence{{border-top:1px solid #e2e7ee;padding:12px 0;font-size:13px;line-height:1.55}}.evidence-meta{{color:#7a8493;font-size:11px;margin:4px 0}}footer{{padding:30px 72px 50px;border-top:1px solid #dce2ea;color:#7a8493;font-size:12px}}@media(max-width:700px){{header,section,footer{{padding-left:24px;padding-right:24px}}h1{{font-size:34px}}section{{grid-template-columns:40px 1fr}}}}@media print{{body{{background:#fff}}main{{box-shadow:none;width:100%}}section{{break-inside:avoid}}}}
</style></head><body><main><header><div class="brand">PARK EQUITY RESEARCH · INSTITUTIONAL SERIES</div><div class="banner">{banner}</div><h1>{escape(report['title'])}</h1><div class="meta">{escape(report['ticker'])} · {escape(report['industry'])} · 截止 {escape(str(report['known_at']))}</div></header>{''.join(sections)}<footer>{escape(report['disclaimer'])}<br>Report identity: {escape(report['generated_from']['production_input_identity'][:20])}</footer></main></body></html>"""


def report_payload_hash(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload.pop("report_hash", None)
    return _digest(payload)


def verify_report_integrity(report: dict[str, Any]) -> None:
    expected = report_payload_hash(report)
    if report.get("report_hash") != expected:
        raise CrossCompanyResearchError("report payload changed after its integrity hash was created")


def load_verified_evidence_packet(
    ticker: str,
    snapshot_id: str,
    claims: list[dict[str, Any]],
    db_path: Path,
) -> _VerifiedEvidencePacket:
    """Reverify a passed evidence-store set and bind hash-verified excerpts for synthesis."""
    from research_evidence import _extract_capture_text, load_evidence_set

    evidence_set = load_evidence_set(ticker.upper(), snapshot_id, db_path, passed_only=True)
    if not evidence_set:
        raise CrossCompanyResearchError("no integrity-passed evidence-store set for snapshot")
    adapter = company_adapter(ticker)
    documents = []
    for index, source in enumerate(evidence_set["documents"]):
        raw_path = Path(str(source.get("raw_path") or ""))
        try:
            raw = raw_path.read_bytes()
        except OSError as exc:
            raise CrossCompanyResearchError("captured evidence bytes are unavailable") from exc
        raw_hash = sha256(raw).hexdigest()
        if raw_hash != source.get("raw_sha256"):
            raise CrossCompanyResearchError("captured evidence bytes changed after the evidence gate")
        excerpt = " ".join(_extract_capture_text(raw, None).split())[:6000]
        if not excerpt:
            raise CrossCompanyResearchError("captured document has no extractable frozen excerpt")
        receipt_hash = _digest({
            "evidence_set_id": evidence_set["evidence_set_id"], "gate_hash": evidence_set["gate_hash"],
            "document_id": source["id"], "raw_sha256": raw_hash,
            "content_hash": source["content_hash"], "canonical_url": source["canonical_url"],
            "capture_provenance": source.get("capture_provenance"),
        })
        source_id = str(source.get("source_key") or f"source_{index + 1}")
        documents.append({
            "id": source_id, "document_id": source["id"], "title": source["title"],
            "kind": source["document_kind"], "known_at": _source_known_at(source["published_at"]),
            "url": source["canonical_url"], "raw_sha256": raw_hash,
            "content_hash": source["content_hash"], "capture_receipt_hash": receipt_hash,
            "capture_provenance": deepcopy(source.get("capture_provenance") or {}),
            "identity_matched_by": source.get("identity_matched_by"),
            "identity_excerpt_hash": source.get("identity_excerpt_hash"),
            "identity_extractor_version": source.get("identity_extractor_version"),
            "note": f"Captured by evidence store; role={source['role']}", "excerpt": excerpt,
        })
    packet = {
        "schema_version": EVIDENCE_SCHEMA_VERSION, "status": "passed", "fixture_only": False,
        "capture_verified": True, "gate_hash": evidence_set["gate_hash"],
        "ticker": adapter.ticker, "name": adapter.name, "snapshot_id": snapshot_id,
        "knowledge_cutoff": evidence_set["knowledge_cutoff"], "documents": documents,
        "claims": deepcopy(claims), "limitations": default_company_limitations(ticker),
    }
    errors = validate_frozen_evidence(packet, adapter=adapter)
    if errors:
        raise CrossCompanyResearchError("evidence-store packet rejected: " + "; ".join(errors))
    return _VerifiedEvidencePacket(packet)


def acceptance_baseline(adapter: CompanyAdapter, *, snapshot_id: str, cutoff: str) -> dict[str, Any]:
    """Deterministic, explicitly non-live baseline used only to prove the line."""
    source_id = "market_snapshot"
    report = {
        "ticker": adapter.ticker, "name": adapter.name, "exchange": adapter.exchange,
        "title": f"{adapter.name} acceptance baseline", "industry": adapter.industry,
        "as_of": cutoff, "known_at": cutoff, "market_known_at": cutoff,
        "data_mode": "ACCEPTANCE_FIXTURE", "research_status": "baseline",
        "research_depth": "quantitative_baseline", "report_version": "acceptance-baseline-v1",
        "research_profile_hash": _digest(asdict(adapter)), "research_logic_hash": _digest("acceptance-baseline-v1"),
        "generated_from": {"snapshot_id": snapshot_id, "publication_id": "acceptance_publication", "model_version": "fixture"},
        "market": {"price": None, "change_pct": None, "pe_ttm": None, "pb": None, "market_cap_yi": None, "return_20d": None, "return_60d": None, "return_250d": None, "volatility_60d": None, "max_drawdown_250d": None, "ma20": None, "ma60": None, "ma200": None, "composite_score": None},
        "executive": {"stance": "research_only", "summary": "Acceptance fixture：验证跨公司生产线，不提供实时结论。", "action": "research_only", "score": 0, "current_price": 0, "key_contradiction": "结构已标准化，实时证据仍须由生产数据填充。", "execution_range": "不提供执行区间", "position_plan": [{"stage": "Research", "weight": 0, "condition": "必须先取得 REAL snapshot 与冻结公司证据"}]},
        "thesis": [{"title": "Missing evidence", "body": "Acceptance fixture：不表达实时投资判断。", "claim_type": "fact", "source_ids": [source_id]}],
        "business_model": {"description": "Missing evidence", "segments": [], "value_chain": [{"layer": adapter.value_chain[0], "items": "待验证", "question": adapter.evidence_questions[0]}], "source_ids": [source_id]},
        "industry_position": {"headline": "Missing evidence", "metrics": [], "source_ids": [source_id]},
        "management": {"score": None, "strengths": ["Missing evidence"], "watchouts": ["Missing evidence"], "source_ids": [source_id]},
        "financials": {"headline": "Missing evidence", "annual_quality": {"roe": None, "gross_margin": None, "net_margin": None, "debt_ratio": None}, "series": [{"report_date": "2026-06-30", "report_type": "fixture", "revenue_yi": None, "net_profit_yi": None, "revenue_yoy": None, "net_profit_yoy": None, "gross_margin": None}], "quality_notes": ["Acceptance fixture only"]},
        "serenity": {"raw_score": 0, "penalty": 0, "final_score": 0, "label": "fixture", "meaning": "Missing evidence", "method": "No live scoring in acceptance mode", "factors": [{"label": "Evidence", "score": 0, "contribution": 0, "reason": "Fixture", "source_ids": [source_id]}], "penalties": []},
        "valuation": {"status": "pending_company_research", "reason": "Missing evidence", "current_price": 0, "method": "not available", "pe_ttm": None, "pb": None},
        "quant_signals": [{"name": "Evidence", "score": 0, "proof": "Acceptance fixture", "source_ids": [source_id]}],
        "stress_test": {"method": "not available", "price_basis": 0, "formula": "not available", "scenarios": [{"case": "base", "label": "Missing evidence", "price_basis": 0, "stress_multiple": 0, "stress_price": 0, "change_pct": 0, "assumption": "Acceptance fixture"}], "warning": "Not a target price"},
        "catalysts": [{"date": "下一次正式披露", "title": "Evidence update", "body": "Missing evidence", "source_ids": [source_id]}],
        "risks": [{"rank": 1, "title": "Evidence incomplete", "impact": "高", "probability": "高", "trigger": "REAL evidence is absent", "evidence": "Acceptance fixture", "source_ids": [source_id]}],
        "falsification": ["Any mismatch between frozen evidence and rendered claim invalidates the report."],
        "watchlist": [{"metric": "Evidence", "current": "fixture", "threshold": "REAL passed", "frequency": "each run"}],
        "sources": [{"id": source_id, "document_id": f"fixture_{snapshot_id}", "title": "Acceptance fixture snapshot", "kind": "market_snapshot", "strength": "中", "known_at": cutoff, "url": None, "note": "Not live market evidence", "snapshot_id": snapshot_id, "provider": "acceptance_fixture", "quote_time": cutoff}],
        "evidence_summary": {"claim_locator_count": 1, "document_count": 1, "independent_document_count": 0, "primary_count": 1, "company_release_count": 0, "boundary": "Acceptance fixture only"},
        "source_contract": {"execution": [source_id], "financials": [source_id], "valuation": [source_id], "falsification": [source_id], "watchlist": [source_id]},
        "disclaimer": "验收样例，不是真实、当前或可执行的投资研究。",
    }
    return attach_report_contract(report, structure_only=True)


def acceptance_evidence(adapter: CompanyAdapter, *, snapshot_id: str, cutoff: str) -> dict[str, Any]:
    documents = []
    for index, (kind, domain) in enumerate((("primary", "cninfo.com.cn"), ("primary", "sse.com.cn" if adapter.ticker.endswith(".SH") else "szse.cn"), ("independent", "csindex.com.cn")), 1):
        raw = _digest({"ticker": adapter.ticker, "document": index, "fixture": True})
        documents.append({
            "id": f"fixture_doc_{index}", "document_id": f"{adapter.ticker}_{index}",
            "title": f"Acceptance fixture source {index}", "kind": kind,
            "known_at": cutoff, "url": f"https://www.{domain}/acceptance/{adapter.ticker}/{index}",
            "raw_sha256": raw, "content_hash": _digest({"raw": raw}),
            "note": "Deterministic acceptance fixture; not a captured live document.",
        })
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION, "status": "passed",
        "fixture_only": True,
        "ticker": adapter.ticker, "name": adapter.name, "snapshot_id": snapshot_id,
        "knowledge_cutoff": cutoff, "documents": documents,
        "limitations": [
            "Acceptance fixture contains no live company facts or valuation; every investment conclusion remains Missing evidence."
        ],
        "claims": [
            {"id": "fixture_thesis", "section": "thesis", "title": "Acceptance boundary", "statement": "验收证据只证明五家公司可以走同一结构与证据门，不表达实时基本面判断。", "claim_type": "fact", "source_ids": ["fixture_doc_1"]},
            {"id": "fixture_business", "section": "business", "statement": f"{adapter.industry}适配器定义了公司专属研究问题，但没有改变标准报告模块。", "claim_type": "inference", "source_ids": ["fixture_doc_1", "fixture_doc_2"]},
            {"id": "fixture_risk", "section": "risk", "title": "Fixture mistaken for live research", "statement": "若验收样例被误标为实时研究，产品结论将失真。", "claim_type": "risk", "trigger": "data_mode 不再显示 ACCEPTANCE_FIXTURE", "source_ids": ["fixture_doc_3"]},
        ],
    }
