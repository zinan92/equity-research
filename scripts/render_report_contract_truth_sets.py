from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "product" / "tests" / "fixtures" / "report_contract"


def render(contract: dict) -> str:
    identity = contract["identity"]
    modules = contract["module_manifest"]
    module_html = "".join(
        f'''<section><b>{item["order"]:02d}</b><div><small>{html.escape(item["kicker"])}</small><h2>{html.escape(item["title"])}</h2><code>{html.escape(item["id"])} · #{html.escape(item["anchor"])}</code><p>{html.escape(" · ".join(item["content_paths"]))}</p></div><em>{html.escape(item["status"].replace("_", " "))}</em></section>'''
        for item in modules
    )
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(identity["name"])} · research-report-v1 structure truth set</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#edf2f7;color:#13233a;font:14px/1.6 Arial,"PingFang SC",sans-serif}}main{{width:min(980px,calc(100% - 32px));margin:32px auto;background:white;border-top:7px solid #075aa5;box-shadow:0 16px 50px #17324d1f}}header{{padding:42px 48px 32px;border-bottom:1px solid #cbd5e1}}header strong{{color:#075aa5;letter-spacing:.13em}}h1{{margin:16px 0 4px;font-size:40px;line-height:1.1}}header p{{margin:3px 0;color:#526277}}.warning{{padding:18px 48px;background:#fff6e8;border-bottom:1px solid #efce9d;color:#7a4510;font-weight:700}}article{{padding:0 48px 36px}}section{{display:grid;grid-template-columns:42px minmax(0,1fr) auto;gap:18px;padding:26px 0;border-bottom:1px solid #dbe3ec}}section>b{{color:#075aa5;font-size:18px}}section small{{color:#075aa5;font-weight:700;letter-spacing:.08em}}h2{{margin:3px 0;font-size:22px}}code{{color:#526277}}section p{{margin:8px 0 0;color:#526277}}section em{{align-self:start;padding:5px 8px;background:#fff6e8;color:#8b4a12;font:700 10px Arial}}footer{{padding:22px 48px;background:#13233a;color:#dce6f0}}@media(max-width:600px){{header,.warning,article,footer{{padding-left:20px;padding-right:20px}}h1{{font-size:30px}}section{{grid-template-columns:28px 1fr}}section em{{grid-column:2}}}}
    </style></head><body><main><header><strong>PARK RESEARCH · STRUCTURE TRUTH SET</strong><h1>{html.escape(identity["name"])}</h1><p>{html.escape(identity["ticker"])} · {html.escape(identity["exchange"])} · {html.escape(identity["market"])} / {html.escape(identity["currency"])} / {html.escape(identity["reporting_standard"])}</p><p>{html.escape(contract["schema_version"])} · contract {html.escape(contract["contract_version"])}</p></header><div class="warning">结构与格式样张，不是真实研报；不包含当前数据、评级、估值或仓位建议。</div><article>{module_html}</article><footer>同一 8 模块结构 · 市场差异显式表达 · Missing evidence 不被隐藏</footer></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Render structure-only CATL and Tesla report contract evidence")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for slug in ("catl", "tesla"):
        contract = json.loads((FIXTURES / f"{slug}.structure.json").read_text(encoding="utf-8"))
        if contract.get("truth_set") != {
            "scope": "structure_only",
            "is_live_research": False,
            "note": "Contract and format fixture only; not current data, valuation, rating, or position advice.",
        }:
            raise RuntimeError(f"{slug} fixture is not a structure-only truth set")
        (args.out / f"m1-{slug}-report-contract.html").write_text(render(contract), encoding="utf-8")


if __name__ == "__main__":
    main()
