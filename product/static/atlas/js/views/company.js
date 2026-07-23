// 公司工作台：产业位置 → 当前质量 → 催化/路线图 → 证据（档案）。
// 每个区块标注数据口径与来源；行情为归档快照，显式声明非实时。

import { api, companyIndex } from "../data.js";
import { h, fmt, chgClass, gradeClass, renderMarkdown } from "../util.js";

export async function renderCompany(code) {
  const [detail, index, meta] = await Promise.all([
    api.company(code).catch(() => null), companyIndex(), api.meta(),
  ]);
  const row = index.get(code);
  if (!detail || !detail.position) {
    return h("div", { class: "card" },
      h("h3", {}, "未找到该公司"),
      h("p", {}, `代码 ${code} 不在当前 fixture 宇宙中。`),
      h("p", {}, h("a", { href: "#/table" }, "← 回到个股表")));
  }

  const p = detail.position;
  const q = detail.quote || {};
  const s = (detail.scores || {}).s || {};
  const fin = detail.financials || {};
  const rel = detail.relations || {};

  const cards = [];

  // 产业位置
  cards.push(h("div", { class: "card w8" },
    h("h3", {}, "产业位置"),
    h("p", { style: "font-size:13.5px;color:#c3ccdb;line-height:1.7" }, p.summary || "—"),
    rel.sc ? h("dl", { class: "kv", style: "margin-top:10px" },
      h("dt", {}, "上游"), h("dd", {}, rel.sc.up || "—"),
      h("dt", {}, "下游"), h("dd", {}, rel.sc.down || "—"),
      h("dt", {}, "大客户"), h("dd", {}, rel.sc.cust || "—")) : "",
    h("p", { class: "src" }, "产业位置与上下游为研究判断（归档口径），非交易所披露字段。")));

  // 评分
  cards.push(h("div", { class: "card w4 scorebars" },
    h("h3", {}, "五维评分"),
    bar("成长", s.growth), bar("质量", s.quality), bar("估值", s.value),
    bar("关注", s.attention), bar("综合", s.composite),
    h("div", { class: "row opp" },
      h("span", {}, "机会分"),
      h("div", { class: "bar" }, h("i", { style: `width:${detail.scores?.opp ?? 0}%` })),
      h("span", { class: "num" }, detail.scores?.opp ?? "—")),
    h("p", { class: "src" },
      "综合分=成长28%+质量12%+估值13%+关注8%（对可量化61%归一）；机会分=0.45成长+0.20质量+0.35估值。")));

  // 三高
  if (detail.three_high) {
    const t = detail.three_high;
    cards.push(h("div", { class: "card w4" },
      h("h3", {}, "三高判定"),
      h("p", {}, h("span", { class: "chip gold" }, t.v || "—")),
      h("dl", { class: "kv", style: "margin-top:8px" },
        h("dt", {}, "毛利率"), h("dd", {}, t.gm || "—"),
        h("dt", {}, "净利率"), h("dd", {}, t.nm || "—"),
        h("dt", {}, "增速"), h("dd", {}, t.rg || "—")),
      t.why ? h("p", { style: "color:var(--dim);font-size:12.5px;margin-top:8px" }, t.why) : "",
      h("p", { class: "src" }, "三高=高壁垒·高利润·高增长，判定为研究口径。")));
  }

  // 财务钻取
  if (fin.drill && fin.drill.length) {
    const quarters = fin.drill.slice(0, 6);
    cards.push(h("div", { class: "card w8" },
      h("h3", {}, "季度财务钻取"),
      h("div", { style: "overflow-x:auto" },
        h("table", { class: "mini" },
          h("thead", {}, h("tr", {},
            h("th", {}, "期间"), h("th", {}, "营收(亿)"), h("th", {}, "营收yoy"),
            h("th", {}, "归母净利(亿)"), h("th", {}, "净利yoy"), h("th", {}, "研发(亿)"))),
          h("tbody", {}, quarters.map((d) => {
            const rev = d["营业收入"], revY = d["营业收入_yoy"];
            const np = d["归属于母公司所有者的净利润"], npY = d["归属于母公司所有者的净利润_yoy"];
            return h("tr", {},
              h("td", {}, d.label),
              h("td", {}, fmt.num(rev, 1)),
              h("td", { class: chgClass(revY) }, fmt.pct(revY)),
              h("td", {}, fmt.num(np, 1)),
              h("td", { class: chgClass(npY) }, fmt.pct(npY)),
              h("td", {}, fmt.num(d["研发费用"], 1)));
          })))),
      h("p", { class: "src" },
        `毛利率 ${fin.gm != null ? fin.gm + "%" : "—"} ｜ 现金含量 ${fin.cashq ?? "—"} ｜ 机构评级 ${fin.rating || "—"}（研报 ${fin.rpt ?? "—"} 份 / 一年 ${fin.rpt1y ?? "—"} 份）`)));
  }

  // 主营构成
  if (fin.stfin && fin.stfin.segments) {
    const st = fin.stfin;
    cards.push(h("div", { class: "card w4" },
      h("h3", {}, `主营构成 · ${st.period || ""}`),
      st.segments.slice(0, 6).map((seg) => h("div", { class: "segbar" },
        h("div", { class: "lbl" },
          h("b", {}, seg.name),
          h("span", { class: "num" }, `${fmt.num(seg.pct, 1)}%${seg.gm != null ? ` · 毛利${fmt.num(seg.gm, 1)}%` : ""}`)),
        h("div", { class: "track" }, h("i", { style: `width:${Math.min(seg.pct || 0, 100)}%` })))),
      h("p", { class: "src" }, st.src ? `来源：${st.src}` : "")));
  }

  // 路线图
  if (detail.roadmap && detail.roadmap.length) {
    cards.push(h("div", { class: "card w6", style: "grid-column:span 6" },
      h("h3", {}, "在研路线图（未来期权）"),
      detail.roadmap.map((r) => h("div", { class: "rmitem" },
        h("div", { class: "t" }, r.t),
        h("div", { class: "metas" },
          r.stage ? h("span", { class: "chip" }, r.stage) : "",
          r.eta ? h("span", { class: "chip" }, r.eta) : "",
          r.impact ? h("span", { class: `chip ${r.impact === "高" ? "gold" : ""}` }, `影响:${r.impact}`) : "",
          r.gc ? h("span", { class: "chip gold" }, "真料") : h("span", { class: "chip" }, "待验")),
        r.note ? h("div", { class: "note" }, r.note) : "")),
      h("p", { class: "src" }, "路线图=尚未完全兑现的技术期权，与当前财务分开看。")));
  }

  // 财报与关系
  const misc = [];
  if (detail.ern) {
    misc.push(h("p", { style: "font-size:13px" },
      h("b", {}, "下次财报："), `${detail.ern.date}（${detail.ern.period} · ${detail.ern.status}）`,
      h("span", { class: "src", style: "display:inline;margin-left:8px" }, detail.ern.src || "")));
  }
  const relChips = [];
  if (rel.n) relChips.push(h("span", { class: "chip gold" }, `英伟达链${(rel.ncat || []).length ? "：" + rel.ncat.join("、") : ""}`));
  if (rel.t) relChips.push(h("span", { class: "chip" }, `特斯拉链${(rel.tcat || []).length ? "：" + rel.tcat.join("、") : ""}`));
  if (rel.cowos) relChips.push(h("span", { class: "chip" }, `CoWoS：${rel.cowos}`));
  for (const c of rel.cc || []) relChips.push(h("span", { class: "chip" }, c));
  if (misc.length || relChips.length) {
    cards.push(h("div", { class: "card w6", style: "grid-column:span 6" },
      h("h3", {}, "事件与关系网络"),
      misc,
      relChips.length ? h("div", { class: "cochips", style: "margin:6px 0 0" }, relChips) : ""));
  }

  // 深度档案
  if (detail.dossier && detail.dossier.md) {
    cards.push(h("div", { class: "card w12" },
      h("h3", {}, `深度档案 · ${detail.dossier.title || p.name}`),
      h("div", { class: "dossier", html: renderMarkdown(detail.dossier.md) }),
      h("p", { class: "src" },
        `档案更新于 ${detail.dossier.updated || "—"}（爱牛归档研究正文，仅作开发样例，产品版将由自有管线生产）。`)));
  }

  const chainChips = (p.chains || []).map((c) =>
    h("a", { class: "chip link", href: `#/table?chain=${encodeURIComponent(c)}` }, c));

  return h("div", {},
    h("p", { style: "margin-bottom:10px" },
      h("a", { class: "backlink", href: "#/table" }, "← 个股表"),
      "　",
      h("a", { class: "backlink", href: "#/bubble" }, "◉ 气泡图定位")),
    h("div", { class: "cohead" },
      h("h1", {}, p.name),
      h("span", { class: "code" }, code),
      row && row.grade ? h("span", { class: `chip ${gradeClass(row.grade)}` }, `分级 ${row.grade}`) : "",
      detail.scores?.sangao ? h("span", { class: "chip gold" }, "◆ 三高") : ""),
    h("div", { class: "cochips" },
      chainChips,
      p.layer ? h("span", { class: "chip" }, p.layer) : "",
      p.segment ? h("span", { class: "chip" }, p.segment) : "",
      p.role ? h("span", { class: "chip" }, p.role) : "",
      (p.flags || []).map((f) => h("span", { class: "chip risk" }, f))),
    h("div", { class: "quotebar" },
      quoteCell(fmt.num(q.price), "现价"),
      quoteCell(fmt.pct(q.chg), "涨跌", chgClass(q.chg)),
      quoteCell(fmt.mcap(q.mcap), "市值"),
      quoteCell(fmt.num(q.pe, 1), "PE"),
      quoteCell(fmt.num(q.pb, 1), "PB"),
      quoteCell(fmt.num(q.peg), "PEG")),
    h("p", { class: "src", style: "margin:-8px 0 14px" },
      `行情/估值为 ${meta.as_of} 归档快照，非实时数据。`),
    h("div", { class: "grid cogrid" }, cards));
}

function bar(label, v) {
  return h("div", { class: "row" },
    h("span", {}, label),
    h("div", { class: "bar" }, h("i", { style: `width:${v ?? 0}%` })),
    h("span", { class: "num" }, v ?? "—"));
}

function quoteCell(v, k, cls = "") {
  return h("div", { class: "q" },
    h("div", { class: `v ${cls}` }, v),
    h("div", { class: "k" }, k));
}
