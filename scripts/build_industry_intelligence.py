#!/usr/bin/env python3
"""Build the reviewed industry-intelligence snapshot from the archived browser payload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCHEMA_VERSION = "industry-intelligence-snapshot-v1"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "product" / "data" / "industry-intelligence-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_number(value: object) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def first_number(*values: object) -> float | int | None:
    for value in values:
        normalized = as_number(value)
        if normalized is not None:
            return normalized
    return None


def build(source: Path) -> dict:
    raw = json.loads(source.read_text(encoding="utf-8"))
    dossiers = raw.get("dossiers") or {}
    stocks = raw.get("stocks") or []
    ref_quotes = raw.get("ref_quotes") or []
    if not isinstance(dossiers, dict) or len(dossiers) != 489:
        raise ValueError("source must contain exactly 489 dossiers")
    if not isinstance(stocks, list) or len(stocks) != 649:
        raise ValueError("source must contain exactly 649 primary stocks")

    stock_by_code: dict[str, dict] = {}
    for item in [*stocks, *ref_quotes]:
        if isinstance(item, dict) and item.get("code"):
            stock_by_code.setdefault(str(item["code"]), item)

    three_high = raw.get("th") or {}
    companies = []
    for item in stocks:
        code = str(item.get("code", ""))
        score = item.get("s") if isinstance(item.get("s"), dict) else {}
        dossier = dossiers.get(code) if isinstance(dossiers.get(code), dict) else None
        detail = three_high.get(code) if isinstance(three_high.get(code), dict) else None
        companies.append({
            "code": code,
            "name": str(item.get("name", "")),
            "market": str(item.get("market", "")),
            "chains": [str(value) for value in item.get("chains", []) if value],
            "layer": str(item.get("layer", "")),
            "segment": str(item.get("segment", "")),
            "role": str(item.get("role", "")),
            "rating": str(item.get("rating", "")),
            "sangao": bool(item.get("sangao")),
            "score": first_number(score.get("composite"), item.get("score")),
            "growth": as_number(score.get("growth")),
            "quality": as_number(score.get("quality")),
            "value": as_number(score.get("value")),
            "attention": as_number(score.get("attention")),
            "opportunity": as_number(item.get("opp")),
            "flags": [str(value) for value in item.get("flags", []) if value],
            "summary": str(item.get("summary", "")),
            "dossier": bool(dossier),
            "dossier_updated": str(dossier.get("updated", "")) if dossier else "",
            "three_high": None if not detail else {
                "classification": str(detail.get("v", "")),
                "gross_margin": str(detail.get("gm", "")),
                "net_margin": str(detail.get("nm", "")),
                "revenue_growth": str(detail.get("rg", "")),
                "rationale": str(detail.get("why", "")),
            },
        })

    dossier_payload = {}
    for code, dossier in dossiers.items():
        stock = stock_by_code.get(str(code), {})
        score = stock.get("s") if isinstance(stock.get("s"), dict) else {}
        dossier_payload[str(code)] = {
            "code": str(code),
            "name": str(stock.get("name", "")),
            "title": str(dossier.get("title", "")),
            "updated": str(dossier.get("updated", "")),
            "market": str(stock.get("market", "")),
            "chains": [str(value) for value in stock.get("chains", []) if value],
            "layer": str(stock.get("layer", "")),
            "segment": str(stock.get("segment", "")),
            "role": str(stock.get("role", "")),
            "rating": str(stock.get("rating", "")),
            "sangao": bool(stock.get("sangao")),
            "score": first_number(score.get("composite"), stock.get("score")),
            "opportunity": as_number(stock.get("opp")),
            "flags": [str(value) for value in stock.get("flags", []) if value],
            "summary": str(stock.get("summary", "")),
            "md": str(dossier.get("md", "")),
        }

    map_source = raw.get("sangaobub") or {}
    segment_assessments = raw.get("sangao", {}).get("segments", [])
    assessment_by_name = {
        str(item.get("segment", "")): item
        for item in segment_assessments
        if isinstance(item, dict) and item.get("segment")
    }
    map_nodes = map_source.get("nodes") if isinstance(map_source, dict) else None
    if not isinstance(map_nodes, list) or not map_nodes:
        raise ValueError("source three-high map is missing")
    nodes = []
    for index, node in enumerate(map_nodes):
        if not isinstance(node, dict):
            continue
        assessment = assessment_by_name.get(str(node.get("name", "")), {})
        size = assessment.get("size") if isinstance(assessment.get("size"), dict) else {}
        nodes.append({
            "id": f"node-{index + 1}",
            "name": str(node.get("name", "")),
            "barrier": as_number(node.get("x")),
            "profit": as_number(node.get("y")),
            "growth_radius": as_number(node.get("r")),
            "layer": str(node.get("layer", "")),
            "chain": str(node.get("chain", "")),
            "sangao": bool(node.get("sangao")),
            "assessment": {
                "growth": str(assessment.get("growth", "")),
                "barrier": str(assessment.get("barrier", "")),
                "margin": str(assessment.get("margin", "")),
                "why": str(assessment.get("why", "")),
                "research": str(assessment.get("research", "")),
                "a_leaders": assessment.get("a_leaders", []) if isinstance(assessment.get("a_leaders"), list) else [],
                "global_leaders": assessment.get("us_leaders", []) if isinstance(assessment.get("us_leaders"), list) else [],
                "size": {
                    "value_yi": as_number(size.get("v")),
                    "tier": str(size.get("tier", "")),
                    "substitution": str(size.get("sub", "")),
                    "substitution_timing": str(size.get("subt", "")),
                    "cagr": str(size.get("cagr", "")),
                    "source_segment": str(size.get("src_seg", "")),
                },
            },
        })

    materials_source = raw.get("materials3h") or {}
    material_nodes = []
    for index, node in enumerate(materials_source.get("nodes", [])):
        if not isinstance(node, dict):
            continue
        material_nodes.append({
            "id": f"material-{index + 1}",
            "code": str(node.get("code", "")),
            "name": str(node.get("name", "")),
            "segment": str(node.get("sub", "")),
            "cluster": str(node.get("cluster", "")),
            "barrier": as_number(node.get("x")),
            "profit": as_number(node.get("y")),
            "growth_radius": as_number(node.get("r")),
            "sangao": bool(node.get("sangao")),
            "tier": str(node.get("tier", "")),
            "scores": node.get("scores", {}) if isinstance(node.get("scores"), dict) else {},
            "finance": node.get("finance", {}) if isinstance(node.get("finance"), dict) else {},
            "summary": str(node.get("summary", "")),
            "logic": node.get("logic", []) if isinstance(node.get("logic"), list) else [],
            "risk": str(node.get("risk", "")),
            "business": node.get("business", []) if isinstance(node.get("business"), list) else [],
            "roadmap": node.get("rmap", []) if isinstance(node.get("rmap"), list) else [],
            "variable": node.get("variable", {}) if isinstance(node.get("variable"), dict) else {},
            "has_dossier": bool(node.get("hasDossier")),
        })

    segment_size = raw.get("segsize") if isinstance(raw.get("segsize"), dict) else {}
    catalysts = raw.get("catalyst") if isinstance(raw.get("catalyst"), dict) else {}
    segments = {}
    for name in sorted(set(segment_size) | set(catalysts)):
        catalyst = catalysts.get(name) if isinstance(catalysts.get(name), dict) else {}
        segments[name] = {
            "market_size": as_number(segment_size.get(name)),
            "cycle": str(catalyst.get("cycle", "")),
            "cycle_tag": str(catalyst.get("cycle_tag", "")),
            "catalyst": str(catalyst.get("catalyst", "")),
        }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "url": "http://ainiusq.com/niu/",
            "captured_at": "2026-07-22",
            "archive_as_of": "2026-07-02",
            "title": "产业链中长期投研看板 · AI算力 + 具身智能",
            "source_sha256": sha256(source),
            "truth_boundary": "公开网页下发的归档快照；不是实时行情，也未经过本产品的独立研究证据门。",
        },
        "summary": {
            "primary_company_count": len(companies),
            "dossier_count": len(dossier_payload),
            "three_high_company_count": sum(1 for item in companies if item["sangao"]),
            "map_node_count": len(nodes),
            "materials_node_count": len(material_nodes),
            "segment_count": len(segments),
        },
        "three_high_map": {
            "title": str(map_source.get("title", "AI产业链三高气泡图")),
            "methodology": "横轴为归档壁垒分，纵轴为归档利润厚度，气泡大小代表归档增速强度；颜色只表示上中下游。",
            "nodes": nodes,
        },
        "materials_map": {
            "title": str(materials_source.get("title", "半导体材料公司三高气泡图")),
            "updated": str(materials_source.get("updated", "")),
            "methodology": str(materials_source.get("method", "")),
            "nodes": material_nodes,
        },
        "segments": segments,
        "companies": companies,
        "dossiers": dossier_payload,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.source.expanduser().resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "summary": payload["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
