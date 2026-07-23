// 总览：世界模型入口 + 数据状态声明。

import { api } from "../data.js";
import { h, fmt, chgClass } from "../util.js";

export async function renderHome() {
  const [meta, companies, chains] = await Promise.all([
    api.meta(), api.companies(), api.chains(),
  ]);

  const sangao = companies.filter((c) => c.sangao).length;
  const dossiers = companies.filter((c) => c.dossier).length;
  const movers = [...companies]
    .filter((c) => c.chg != null)
    .sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg))
    .slice(0, 8);

  return h("div", {},
    notice(meta),
    h("div", { class: "hero" },
      h("h1", {}, "先看", h("em", {}, "产业世界"), "，再看公司"),
      h("p", {},
        "公司不是孤立的代码，而是产业链上的一个坐标。从产业位置出发，",
        "经过当前质量、未来催化、证据与证伪，最终落到你自己的判断。")),
    h("div", { class: "statrow" },
      stat(companies.length, "覆盖公司"),
      stat(Object.keys(chains).length, "产业链结构"),
      stat(sangao, "三高标的"),
      stat(dossiers, "深度档案"),
    ),
    h("div", { class: "grid homegrid" },
      card("#/chains", "产业链全景", "22 套产业结构：AI 算力基建、芯片、机器人、存储、光模块…每个环节标注上下游与代表公司。"),
      card("#/bubble", "三高气泡图", "横轴壁垒、纵轴利润、气泡大小是增速。右上角的大金圈就是「三高俱全」的王炸环节。"),
      card("#/table", "个股全景表", `${companies.length} 家公司按产业位置组织，支持链、层级、市场、三高、角色筛选与全列排序。`),
      card("#/grades", "S/A/B 分级", "661 只股票的壁垒分级：S 卡脖子 → D 亏损泡沫，每一级都写明理由。"),
    ),
    h("div", { class: "card", style: "margin-top:14px" },
      h("h3", {}, "快照异动（非实时）"),
      h("div", { class: "grid", style: "grid-template-columns:repeat(auto-fill,minmax(200px,1fr))" },
        movers.map((c) => h("a", { href: `#/co/${c.code}`, class: "chip link", style: "display:flex;justify-content:space-between;gap:8px;padding:7px 10px" },
          h("span", {}, c.name),
          h("span", { class: `num ${chgClass(c.chg)}` }, fmt.pct(c.chg))))),
      h("p", { class: "src" }, `行情为 ${meta.as_of} 归档快照，不代表当前市场。`)),
  );
}

function notice(meta) {
  return h("div", { class: "notice" },
    h("b", {}, "开发 FIXTURE"),
    h("span", {}, `数据快照 as_of ${meta.as_of}`),
    h("span", {}, `来源 ${meta.origin}`),
    h("span", {}, "仅用于 N5 前端开发验证，禁止当作实时行情或投资建议。"));
}

function stat(v, k) {
  return h("div", { class: "stat" },
    h("div", { class: "v" }, String(v)),
    h("div", { class: "k" }, k));
}

function card(href, title, desc) {
  return h("a", { class: "card", href },
    h("h3", {}, title),
    h("p", {}, desc));
}
