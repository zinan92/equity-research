#!/usr/bin/env python3
"""Build dev fixtures for the Atlas frontend (N5, Epic #120).

Reads the ainiu archive's exported data layers and emits slim per-view JSON
fixtures under product/static/atlas/fixtures/. Fixtures are DEV ONLY:
they derive from the 2026-07-02 archive snapshot, are gitignored, and must
never ship in a production build (origin is stamped in meta.json).

Usage:
    python3 product/static/atlas/build_fixtures.py
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXPORTED = REPO / "research/ainiusq-niu/2026-07-22/data/exported"
OUT = Path(__file__).resolve().parent / "fixtures"

ORIGIN = "ainiu-archive-20260702"
AS_OF = "2026-07-02"


def load(rel: str):
    with open(EXPORTED / rel, encoding="utf-8") as f:
        return json.load(f)


def records(payload):
    if isinstance(payload, dict):
        for key in ("records", "data"):
            if key in payload:
                return payload[key]
    return payload


def infer_market(code: str, levels_market: dict) -> str:
    if code in levels_market and levels_market[code]:
        return levels_market[code]
    if re.fullmatch(r"\d{6}", code):
        return "A股"
    if re.fullmatch(r"\d{4,5}", code):
        return "港股"
    if re.fullmatch(r"\d{4}\.T", code) or code.endswith(".T"):
        return "日股"
    if re.fullmatch(r"[A-Z.\-]+", code):
        return "美股"
    return ""


def build_companies(positions, snapshots, scores, financials, relations,
                    roadmaps, levels_rows):
    levels_market = {r["code"]: r.get("market", "") for r in levels_rows}
    levels_grade = {r["code"]: r.get("grade", "") for r in levels_rows}
    snap = {r["code"]: r for r in snapshots if r.get("universe") == "main"}
    sc = {r["code"]: r for r in scores if r.get("universe") == "main"}
    fin = {r["code"]: r for r in financials if r.get("universe") == "main"}
    rel = {r["code"]: r for r in relations if r.get("universe") == "main"}
    rmap_codes = {r["code"] for r in roadmaps if r.get("universe") == "main"}

    rows = []
    for p in positions:
        if p.get("universe") != "main":
            continue
        code = p["code"]
        s, q, f, r = sc.get(code, {}), snap.get(code, {}), fin.get(code, {}), rel.get(code, {})
        rows.append({
            "code": code,
            "name": p["name"],
            "market": infer_market(code, levels_market),
            "chains": p.get("chains") or [],
            "layer": p.get("layer") or "",
            "segment": p.get("segment") or "",
            "role": p.get("role") or "",
            "flags": p.get("flags") or [],
            "dossier": bool(p.get("dossier")),
            "price": q.get("price"),
            "chg": q.get("chg"),
            "pe": q.get("pe"),
            "pb": q.get("pb"),
            "peg": q.get("peg"),
            "mcap": q.get("mcap"),
            "score": (s.get("s") or {}).get("composite"),
            "opp": s.get("opp"),
            "sangao": bool(s.get("sangao")),
            "grade": levels_grade.get(code, ""),
            "rating": f.get("rating") or "",
            "rpt1y": f.get("rpt1y"),
            "n": bool(r.get("n")),
            "t": bool(r.get("t")),
            "cowos": bool(r.get("cowos")),
            "rmap": code in rmap_codes,
        })
    return rows


def build_company_details(positions, snapshots, scores, financials, relations,
                          roadmaps, three_high, dossiers, earnings):
    by_code = {}

    def slot(code):
        return by_code.setdefault(code, {})

    for p in positions:
        if p.get("universe") != "main":
            continue
        slot(p["code"])["position"] = {
            k: p.get(k) for k in
            ("name", "chains", "layer", "segment", "role", "summary", "flags")
        }
    for group, key in ((snapshots, "quote"), (scores, "scores")):
        for r in group:
            if r.get("universe") == "main":
                cleaned = {k: v for k, v in r.items()
                           if k not in ("universe", "code", "name")}
                slot(r["code"])[key] = cleaned
    for r in financials:
        if r.get("universe") == "main":
            slot(r["code"])["financials"] = {
                k: r.get(k) for k in ("rpt", "rpt1y", "rating", "gm", "cashq", "drill", "stfin")
            }
    for r in relations:
        if r.get("universe") == "main":
            slot(r["code"])["relations"] = {
                k: r.get(k) for k in ("sc", "n", "ncat", "t", "tcat", "cowos", "cc")
            }
    for r in roadmaps:
        if r.get("universe") == "main":
            slot(r["code"])["roadmap"] = r.get("roadmap") or []
    for code, assessment in (three_high.get("company_assessments") or {}).items():
        slot(code)["three_high"] = assessment
    for code, d in (dossiers.get("records_by_code") or {}).items():
        slot(code)["dossier"] = {
            "title": d.get("title", ""), "updated": d.get("updated", ""),
            "md": d.get("md", ""),
        }
    for r in earnings:
        if r.get("universe") == "main" and r.get("date"):
            slot(r["code"])["ern"] = {
                k: r.get(k) for k in ("date", "period", "status", "src")
            }
    return by_code


def main():
    positions = records(load("slow-knowledge/company-sector-positions.json"))
    snapshots = records(load("fast-snapshot/market-snapshot.json"))
    scores = records(load("periodic-research/scores-and-ratings.json"))
    financials = records(load("periodic-research/company-financials.json"))
    relations = records(load("slow-knowledge/company-relations.json"))
    roadmaps = records(load("periodic-research/company-roadmaps.json"))
    three_high = load("periodic-research/three-high-assessments.json")
    dossiers = load("slow-knowledge/company-dossiers.json")
    earnings = records(load("periodic-research/earnings-calendar.json"))
    catalysts = load("periodic-research/catalysts.json")
    levels = load("periodic-research/levels-ratings.json")
    structures = load("slow-knowledge/industry-structures.json")["data"]

    levels_rows = levels.get("records") or []

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "co").mkdir(exist_ok=True)

    companies = build_companies(positions, snapshots, scores, financials,
                                relations, roadmaps, levels_rows)
    details = build_company_details(positions, snapshots, scores, financials,
                                    relations, roadmaps, three_high, dossiers,
                                    earnings)

    write(OUT / "companies.json", companies)
    write(OUT / "chains.json", structures.get("chains") or {})
    write(OUT / "bubble.json", {
        "ai": three_high.get("ai_bubble"),
        "general": three_high.get("general_bubble"),
        "materials": three_high.get("materials_bubble"),
    })
    write(OUT / "catalysts.json", catalysts.get("records_by_segment") or {})
    write(OUT / "levels.json", {
        "grade_dist": levels.get("grade_dist") or {},
        "records": levels_rows,
    })
    for code, payload in details.items():
        safe = code.replace("/", "_")
        write(OUT / "co" / f"{safe}.json", payload)
    write(OUT / "meta.json", {
        "origin": ORIGIN,
        "as_of": AS_OF,
        "generated_from": str(EXPORTED.relative_to(REPO)),
        "companies": len(companies),
        "details": len(details),
        "levels": len(levels_rows),
        "notice": "开发用 fixture：来自爱牛归档 2026-07-02 快照，禁止进入生产构建。",
    })
    print(f"companies={len(companies)} details={len(details)} "
          f"levels={len(levels_rows)} chains={len(structures.get('chains') or {})}")


def write(path: Path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
