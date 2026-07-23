#!/usr/bin/env python3
"""Build the N1-1 field-attribution register from a read-only Ainiu archive.

The archive is intentionally an external input: it is a local research artifact,
not a product dependency or a payload to be committed to this repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = ROOT / "docs" / "reverse"
REQUIRED_FIELDS = {
    "field", "surface", "meaning", "archive_layer", "nature", "cadence",
    "candidate_sources", "evidence", "confidence", "auto_update", "fallback",
    "production_method", "source_status",
}
VALID_NATURES = {"原始事实", "派生", "研究判断", "AI推断"}
VALID_CONFIDENCE = {"高", "中", "低", "判断类"}


def _spec(
    meaning: str,
    nature: str,
    cadence: str,
    candidate_sources: list[str],
    confidence: str,
    auto_update: bool,
    fallback: list[str],
    production_method: str,
    source_status: str = "候选来源，待后续复现验证",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "meaning": meaning,
        "nature": nature,
        "cadence": cadence,
        "candidate_sources": candidate_sources,
        "confidence": confidence,
        "auto_update": auto_update,
        "fallback": fallback,
        "production_method": production_method,
        "source_status": source_status,
        "evidence": evidence or {
            "kind": "archive-classification",
            "path": "data/exported/classification-manifest.json",
            "note": "字段存在性与三层归类来自归档分类清单；它不单独确认外部来源。",
        },
    }


RESEARCH_POSITION = _spec(
    "公司在产业链中的研究位置/标签。",
    "研究判断", "重大事件或人工复核", [], "判断类", False, [],
    "多智能体调研、公开资料核对与人工 taxonomy 映射；不是单一市场数据字段。",
    "研究判断，不能宣称已找到单一来源",
)
RESEARCH_NARRATIVE = _spec(
    "研究摘要或解释性文字。",
    "AI推断", "重大事件或人工复核", [], "判断类", False, [],
    "公开资料检索后的 AI/人工编辑性汇总；应保留事实证据与叙事的边界。",
    "AI/人工研究判断，不能作为事实源",
)
MARKET_FACT = _spec(
    "市场快照字段。",
    "原始事实", "日内或收盘后", ["腾讯行情", "东方财富行情", "新浪财经", "Yahoo Finance（海外）"],
    "中", True, ["交易所/官方行情", "次级行情源"],
    "按交易日抓取并附 as_of、交易所、币种与原始响应哈希；#113 负责跨市场来源复现。",
)
FINANCIAL_FACT = _spec(
    "财务或经营指标。",
    "原始事实", "季报/年报披露后", ["公司公告/年报", "交易所披露", "东方财富 F10"],
    "中", True, ["公司 IR", "官方交易所披露", "次级金融数据源"],
    "以期间、单位、币种、修订版本冻结；#112/#113 负责来源验证与采集。",
)
SELL_SIDE_FACT = _spec(
    "卖方研报数量、评级或一致预期字段。",
    "原始事实", "研报发布后/每日", ["东方财富研报中心", "同花顺研报", "券商原始研报"],
    "中", True, ["受控研报目录", "已归档研报 PDF"],
    "目录抓取、报告归档与按报告日聚合；不把单个门户页面当作永恒事实。",
)
DERIVED = _spec(
    "由冻结事实按明确规则计算的指标。",
    "派生", "上游快照或财报更新后", [], "中", True, [],
    "以版本化公式、输入快照和单位检查重算；#114 只验证已披露公式，不猜隐藏模型。",
    "公式/输入待后续复现验证",
)
JUDGMENT = _spec(
    "研究分类、标签或结论。",
    "研究判断", "人工复核或重大事件", [], "判断类", False, [],
    "人工/AI 研究判断；可保存版本与证据，不得伪装成自动确认的外部事实。",
    "研究判断，不能宣称已找到单一来源",
)


def clone(base: dict[str, Any], meaning: str, **overrides: Any) -> dict[str, Any]:
    copied = {key: (value.copy() if isinstance(value, dict) else list(value) if isinstance(value, list) else value)
              for key, value in base.items()}
    copied["meaning"] = meaning
    copied.update(overrides)
    return copied


MAIN_SPECS: dict[str, dict[str, Any]] = {
    "code": clone(FINANCIAL_FACT, "证券代码/公司标识。", cadence="公司行动或证券状态变化", candidate_sources=["交易所证券主数据", "公司公告"], confidence="中", fallback=["官方交易所名录"]),
    "name": clone(FINANCIAL_FACT, "证券简称/公司名称。", cadence="公司行动或证券状态变化", candidate_sources=["交易所证券主数据", "公司公告"], confidence="中", fallback=["官方交易所名录"]),
    "market": clone(FINANCIAL_FACT, "市场/交易所归属。", cadence="公司行动或证券状态变化", candidate_sources=["交易所证券主数据"], confidence="中", fallback=["官方交易所名录"]),
    "price": clone(MARKET_FACT, "快照价格。"),
    "chg": clone(MARKET_FACT, "快照涨跌幅。"),
    "mcap": clone(MARKET_FACT, "快照市值（归档口径）。"),
    "mcap_usd": clone(MARKET_FACT, "快照美元市值（归档口径）。"),
    "pe": clone(MARKET_FACT, "市盈率快照。", candidate_sources=["腾讯行情", "东方财富行情", "Yahoo Finance（海外）", "公司财报"], production_method="行情源估值字段或价格/TTM EPS 计算；需记录亏损和口径。"),
    "pb": clone(MARKET_FACT, "市净率快照。", candidate_sources=["腾讯行情", "东方财富行情", "Yahoo Finance（海外）", "公司财报"], production_method="行情源估值字段或价格/每股净资产计算；需记录口径。"),
    "peg": clone(DERIVED, "PEG 估值指标。", candidate_sources=["PE 快照", "增长率快照"], fallback=["无法稳定定义时留空"], production_method="归档未逐字段给出计算输入与公式；仅作为待复现派生字段。"),
    "gm": clone(FINANCIAL_FACT, "毛利率。", candidate_sources=["公司公告/年报", "交易所披露", "东方财富 F10"], production_method="财报利润表或主营构成口径；必须带期间。"),
    "rev_growth": clone(FINANCIAL_FACT, "营收同比增速。", candidate_sources=["公司公告/年报", "交易所披露", "东方财富 F10"], production_method="同口径收入同比计算；必须带期间与披露版本。"),
    "cashq": clone(DERIVED, "现金质量/现金流质量指标。", candidate_sources=["公司现金流量表", "利润表"], fallback=["缺失时留空"], production_method="归档没有逐字段来源；按定义重建前不得视为原始事实。"),
    "rpt": clone(SELL_SIDE_FACT, "卖方研报总数。"),
    "rpt1y": clone(SELL_SIDE_FACT, "近一年卖方研报数。"),
    "rating": clone(SELL_SIDE_FACT, "聚合后的最新/主导卖方评级。"),
    "s": clone(DERIVED, "五维评分对象（成长、质量、估值、关注、综合）。", candidate_sources=["财务、估值、卖方关注快照"], fallback=["缺失维度显式降级"], production_method="综合分披露为成长28%、质量12%、估值13%、关注8%，对61%可量化部分归一；具体子分与人工覆盖待#114验证。"),
    "opp": clone(DERIVED, "机会分。", candidate_sources=["成长分", "质量分", "估值分"], fallback=["缺失维度显式降级"], production_method="页面披露公式：0.45×成长 + 0.20×质量 + 0.35×估值；#114验证。"),
    "drill": clone(FINANCIAL_FACT, "季度收入、成本、费用、净利钻取。", candidate_sources=["公司季报/年报", "交易所披露", "东方财富 F10"], production_method="按季度披露提取；归档未给每条 drill 逐字段 src。"),
    "stfin": _spec("主营业务分部、收入占比和毛利率。", "原始事实", "季报/年报披露后", ["东方财富 F10 主营构成", "公司年报/季报"], "高", True, ["公司公告/年报", "交易所披露"], "归档有逐路径 src；其中 578 条 src 的值精确为‘东财F10 主营构成’，其他记录可能是公司财报或交叉核验。", "直接溯源", {"kind": "direct-provenance", "path": "data/exported/provenance/provenance-records.json#/records[key=src,value=东财F10 主营构成]", "record_count": 578, "note": "来源标签的全归档计数；不得把未标注行重新猜测为东财。"}),
    "ern": _spec("下一次业绩披露日期、期间和预约状态。", "原始事实", "预约披露更新后", ["东方财富预约披露"], "高", True, ["交易所预约披露", "公司公告"], "归档有逐路径 src；其中 583 条 src 的值精确为‘东财预约披露’。", "直接溯源", {"kind": "direct-provenance", "path": "data/exported/provenance/provenance-records.json#/records[key=src,value=东财预约披露]", "record_count": 583, "note": "来源标签的全归档计数；不得把未标注行重新猜测为东财。"}),
    "rmap": clone(RESEARCH_NARRATIVE, "产品、技术或产能路线图。", cadence="重大事件或人工复核", production_method="公开公告、IR、技术资料与 AI/人工整理；每条需另建证据，不可从归档文本直接复用。"),
    "summary": clone(RESEARCH_NARRATIVE, "公司一句话研究摘要。"),
    "dossier": clone(DERIVED, "是否存在归档公司档案的索引标记。", cadence="归档/档案版本更新", candidate_sources=["归档 dossier 对象"], confidence="高", auto_update=True, fallback=[], production_method="归档内部索引，不是外部研究事实。", source_status="归档内直接可验证"),
    "refQuote": clone(DERIVED, "是否由补池行情记录支撑的归档索引。", cadence="归档快照更新", candidate_sources=["归档 ref_quotes 对象"], confidence="高", auto_update=True, fallback=[], production_method="归档内部关系索引，不是外部研究事实。", source_status="归档内直接可验证"),
    "refSources": clone(DERIVED, "引用来源/参考上下文索引。", cadence="归档快照更新", candidate_sources=["归档 provenance 记录"], confidence="中", auto_update=True, fallback=[], production_method="归档内部引用索引；URL 和文本来源需逐条重新验证。", source_status="归档内索引，外部来源待验证"),
    "refContexts": clone(DERIVED, "引用在归档中出现的上下文索引。", cadence="归档快照更新", candidate_sources=["归档 provenance 记录"], confidence="中", auto_update=True, fallback=[], production_method="归档内部上下文索引；不是独立事实。", source_status="归档内索引，外部来源待验证"),
}

for field, meaning in {
    "chains": "所属产业链标签。", "layer": "产业链上/中/下游层级。", "segment": "细分产业环节。", "role": "产业位置角色（如龙头/挑战者）。", "sc": "上游、下游与客户关系。",
    "cowos": "CoWoS 相关标签。", "cowos_s": "CoWoS 相关补充评分/说明。", "dj": "国家大基金等主题关系。", "t": "特斯拉链标记。", "tcat": "特斯拉链分类。", "n": "英伟达链标记。", "ncat": "英伟达链分类。", "ninv": "英伟达投资/关系标记。", "cc": "题材链标签。", "k": "KOID 主题标记。", "kseg": "KOID 细分标签。", "overseas": "海外/境外属性标签。", "flags": "风险或异常标签。", "sangao": "三高标签。", "audit": "研究口径/位置审计。", "weight": "归档研究权重或排序权重。", "dc": "归档中的数据中心/主题标记。",
}.items():
    MAIN_SPECS[field] = clone(RESEARCH_POSITION if field not in {"flags", "sangao", "audit", "weight", "dc"} else JUDGMENT, meaning)


LEVEL_SPECS: dict[str, dict[str, Any]] = {
    "code": clone(FINANCIAL_FACT, "证券代码/公司标识。", cadence="公司行动或证券状态变化", candidate_sources=["交易所证券主数据"], confidence="中", fallback=["官方交易所名录"]),
    "name": clone(FINANCIAL_FACT, "证券简称/公司名称。", cadence="公司行动或证券状态变化", candidate_sources=["交易所证券主数据"], confidence="中", fallback=["官方交易所名录"]),
    "market": clone(FINANCIAL_FACT, "市场/交易所归属。", cadence="公司行动或证券状态变化", candidate_sources=["交易所证券主数据"], confidence="中", fallback=["官方交易所名录"]),
    "price": clone(MARKET_FACT, "等级页价格快照。"),
    "change_pct": clone(MARKET_FACT, "等级页涨跌幅快照。"),
    "mcap_yi": clone(MARKET_FACT, "等级页人民币亿元市值快照。"),
    "mcap_usd_b": clone(MARKET_FACT, "等级页美元十亿美元市值快照。"),
    "pe": clone(MARKET_FACT, "等级页市盈率快照。"),
    "peg": clone(DERIVED, "等级页 PEG。", candidate_sources=["PE 快照", "增长率快照"], fallback=["无法稳定定义时留空"], production_method="归档未逐字段给出计算输入；待#114验证。"),
    "growth": clone(FINANCIAL_FACT, "营收/经营增长率。", candidate_sources=["公司公告/年报", "交易所披露", "东方财富 F10"], production_method="财报同比或页面口径；必须带期间。"),
    "gross_margin": clone(FINANCIAL_FACT, "毛利率。"),
    "net_margin": clone(FINANCIAL_FACT, "净利率。", candidate_sources=["公司公告/年报", "交易所披露", "东方财富 F10"], production_method="财报口径计算；必须带期间。"),
    "rpt_total": clone(SELL_SIDE_FACT, "卖方研报总数。"),
    "rpt_1y": clone(SELL_SIDE_FACT, "近一年卖方研报数。"),
    "buy_rate": clone(SELL_SIDE_FACT, "买入评级比例。"),
    "rpt_latest_date": clone(SELL_SIDE_FACT, "最近卖方研报日期。"),
    "rpt_latest_org": clone(SELL_SIDE_FACT, "最近卖方研报机构。"),
    "rpt_latest_rating": clone(SELL_SIDE_FACT, "最近卖方研报评级。"),
    "score": clone(DERIVED, "等级页综合分。", candidate_sources=["壁垒、财务、估值、卖方关注"], fallback=["数据不足则显式未评级"], production_method="页面披露由壁垒、毛利、增长、PE、PEG、机构关注构成；具体权重待#114验证。"),
    "pe_grade": clone(DERIVED, "PE 的离散估值标签。", candidate_sources=["PE"], fallback=["无法定义时留空"], production_method="对 PE 阈值分箱，归档未给出完整阈值。"),
    "peg_grade": clone(DERIVED, "PEG 的离散估值标签。", candidate_sources=["PEG"], fallback=["无法定义时留空"], production_method="页面披露阈值：<1 便宜、1-2 合理、2-4 偏贵、>4 极贵。"),
    "gross_margin_str": clone(DERIVED, "毛利率展示字符串。", candidate_sources=["gross_margin"], confidence="高", production_method="展示格式化；不是独立事实。", source_status="归档字段关系可直接验证"),
    "net_margin_str": clone(DERIVED, "净利率展示字符串。", candidate_sources=["net_margin"], confidence="高", production_method="展示格式化；不是独立事实。", source_status="归档字段关系可直接验证"),
    "rev_growth_str": clone(DERIVED, "增长率展示字符串。", candidate_sources=["growth"], confidence="高", production_method="展示格式化；不是独立事实。", source_status="归档字段关系可直接验证"),
}

for field, meaning in {
    "chain": "产业链标签。", "layer": "产业链层级。", "segment": "细分产业环节。", "barrier": "护城河/壁垒等级。", "barrier_str": "壁垒解释文字。", "grade": "S/A+/A/B/C/D 等级。", "rack_verdict": "三高结论。", "rack_reason": "三高结论解释。", "reason": "评级理由。", "note": "补充研究说明。",
}.items():
    LEVEL_SPECS[field] = clone(RESEARCH_POSITION if field in {"chain", "layer", "segment"} else JUDGMENT, meaning)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def records_for(surface: str, fields: dict[str, str], specs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    missing = set(fields) - set(specs)
    extra = set(specs) - set(fields)
    if missing or extra:
        raise ValueError(f"{surface} specification mismatch: missing={sorted(missing)} extra={sorted(extra)}")
    records: list[dict[str, Any]] = []
    for field in sorted(fields):
        record = {"field": field, "surface": surface, "archive_layer": fields[field], **specs[field]}
        if set(record) != REQUIRED_FIELDS:
            raise ValueError(f"{surface}.{field} missing/extra register keys: {sorted(set(record) ^ REQUIRED_FIELDS)}")
        if record["nature"] not in VALID_NATURES or record["confidence"] not in VALID_CONFIDENCE:
            raise ValueError(f"{surface}.{field} has invalid classification")
        records.append(record)
    return records


def provenance_label_count(records: list[dict[str, Any]], label: str) -> int:
    """Count an explicit source label without merging it with field availability."""
    return sum(1 for record in records if record.get("key") == "src" and record.get("value") == label)


def markdown(payload: dict[str, Any]) -> str:
    rows = payload["fields"]
    lines = [
        "# 爱牛归档字段归因总表", "",
        "## 结论", "",
        "这是对归档公开数据的字段级生产归因，不是对爱牛后端或实时接口的声明。",
        "`高` 仅用于归档逐路径自带来源的字段；`中/低` 是候选来源假设；`判断类` 明确表示人工或 AI 研究判断。",
        "所有候选来源仍须在后续 issue 中以自有采集结果复现，未验证前不得进入产品事实输出。", "",
        "## 覆盖与边界", "",
        f"- 主表字段：{payload['summary']['main_field_count']} / 49",
        f"- 分级字段：{payload['summary']['levels_field_count']} / 34",
        f"- 合计：{payload['summary']['field_count']} / 83",
        f"- 归档母版 SHA-256：`{payload['source_archive']['dataset_sha256']}`",
        f"- 分级母版 SHA-256：`{payload['source_archive']['levels_sha256']}`", "",
        "直接溯源共有 1,161 条明确 `src` 标签：578 条为 `东财F10 主营构成`，583 条为 `东财预约披露`。",
        "它们的逐条证据位于 `data/exported/provenance/provenance-records.json`；这不是所有 `stfin`/`ern` 行都来自该来源的断言。", "",
        "## 字段登记", "",
        "| Surface | 字段 | 含义 | 性质 | 更新频率 | 候选来源/生产方法 | 置信度 | 可自动更新 | Fallback |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for record in rows:
        sources = "、".join(record["candidate_sources"]) or "—"
        method = f"{sources}；{record['production_method']}"
        fallback = "、".join(record["fallback"]) or "—"
        display = {
            **record,
            "method": method.replace("|", "\\|"),
            "fallback": fallback.replace("|", "\\|"),
            "auto_update": "是" if record["auto_update"] else "否",
        }
        lines.append(
            "| {surface} | `{field}` | {meaning} | {nature} | {cadence} | {method} | {confidence} | {auto_update} | {fallback} |".format(**display)
        )
    lines.extend([
        "", "## 读取方式", "",
        "机器读取 `field-attribution.json`。它包含每个字段的结构化 evidence、来源状态与生产方法。",
        "使用 `python3 scripts/verify_field_attribution.py --archive-root <归档根目录>` 交叉核验。",
        "", "## Gotchas", "",
        "- `market`、`code`、`name` 看似基础字段，但归档存在 649/661 两套股票宇宙；不能按行号或名称静默合并。",
        "- `price=0` 或缺失估值不能被视为真实零值；后续采集器必须显式保留缺失原因。",
        "- 产业链、角色、三高、上下游、S/A/B 与解释文本均为研究判断或 AI 推断，不得把归档结论直接发布为产品事实。",
    ])
    return "\n".join(lines) + "\n"


def build(archive_root: Path, docs_root: Path) -> dict[str, Any]:
    export_root = archive_root / "data" / "exported"
    manifest_path = export_root / "classification-manifest.json"
    provenance_path = export_root / "provenance" / "provenance-records.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    main_fields = manifest["stock_field_classification"]
    levels_fields = manifest["levels_field_classification"]
    records = records_for("main_stock", main_fields, MAIN_SPECS) + records_for("levels_stock", levels_fields, LEVEL_SPECS)
    direct = {
        "eastmoney_f10_src_labels": provenance_label_count(provenance["records"], "东财F10 主营构成"),
        "eastmoney_earnings_src_labels": provenance_label_count(provenance["records"], "东财预约披露"),
    }
    if direct != {"eastmoney_f10_src_labels": 578, "eastmoney_earnings_src_labels": 583}:
        raise ValueError(f"unexpected direct-provenance counts: {direct}")
    payload = {
        "schema_version": "ainiu-field-attribution-v1",
        "purpose": "公开归档字段的生产归因地图；候选来源不是已确认来源。",
        "source_archive": {
            "archive_root_hint": "research/ainiusq-niu/2026-07-22",
            "classification_manifest": "data/exported/classification-manifest.json",
            "provenance_records": "data/exported/provenance/provenance-records.json",
            "dataset_sha256": manifest["authoritative_masters"]["dataset.json"]["sha256"],
            "levels_sha256": manifest["authoritative_masters"]["levels.json"]["sha256"],
            "classification_manifest_sha256": sha256(manifest_path),
            "provenance_records_sha256": sha256(provenance_path),
        },
        "summary": {
            "main_field_count": len(main_fields),
            "levels_field_count": len(levels_fields),
            "field_count": len(records),
            "direct_provenance": direct,
            "nature_counts": dict(sorted(Counter(record["nature"] for record in records).items())),
            "confidence_counts": dict(sorted(Counter(record["confidence"] for record in records).items())),
        },
        "fields": records,
    }
    docs_root.mkdir(parents=True, exist_ok=True)
    (docs_root / "field-attribution.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (docs_root / "field-attribution.md").write_text(markdown(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True, help="Read-only 2026-07-22 archive root")
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS)
    args = parser.parse_args()
    payload = build(args.archive_root.resolve(), args.docs_root.resolve())
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
