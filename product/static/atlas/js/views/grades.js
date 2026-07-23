// S/A/B 分级表：661 只股票的壁垒分级。
// 修复爱牛缺陷：表头真实可排序；市场筛选覆盖全部标签。

import { api } from "../data.js";
import { h, fmt, gradeClass } from "../util.js";

const GRADES = [
  { g: "S", desc: "卡脖子级：独家或近独家垄断" },
  { g: "A+", desc: "强护城河：寡头/事实垄断" },
  { g: "A", desc: "优质成长：行业龙头" },
  { g: "B", desc: "有一定壁垒" },
  { g: "C", desc: "普通玩家/估值偏高" },
  { g: "D", desc: "亏损/泡沫/被替代" },
];

const state = { grade: "", market: "", q: "", sortKey: "score", sortDir: -1 };

export async function renderGrades() {
  const data = await api.levels();
  const rows = data.records || [];
  const dist = data.grade_dist || {};
  const markets = [...new Set(rows.map((r) => r.market).filter(Boolean))].sort();

  const root = h("div", {},
    h("div", { class: "pagehead" },
      h("h1", {}, "S/A/B 壁垒分级"),
      h("div", { class: "sub" },
        "口径：三高（壁垒+毛利+增长）+ PE + PEG + 机构关注。分级是研究判断，不是买卖信号。")),
  );

  const tabs = h("div", { class: "gradetabs" });
  function drawTabs() {
    tabs.innerHTML = "";
    tabs.append(h("button", {
      class: state.grade === "" ? "on" : "",
      onclick: () => { state.grade = ""; drawTabs(); refresh(); },
    }, "全部 ", h("span", { class: "n" }, `(${rows.length})`)));
    for (const { g, desc } of GRADES) {
      tabs.append(h("button", {
        class: state.grade === g ? "on" : "", title: desc,
        onclick: () => { state.grade = g; drawTabs(); refresh(); },
      }, `${g} `, h("span", { class: "n" }, `(${dist[g] ?? 0})`)));
    }
  }

  const countEl = h("span", { class: "count" });
  const filters = h("div", { class: "filters" },
    h("input", {
      type: "search", placeholder: "搜代码/名称/细分/理由…",
      oninput: (e) => { state.q = e.target.value; refresh(); },
    }),
    h("select", { onchange: (e) => { state.market = e.target.value; refresh(); } },
      h("option", { value: "" }, "全部市场"),
      markets.map((m) => h("option", { value: m }, m))),
    countEl);

  const cols = [
    { key: "code", label: "代码" },
    { key: "name", label: "名称" },
    { key: "market", label: "市场" },
    { key: "segment", label: "细分" },
    { key: "grade", label: "分级" },
    { key: "score", label: "评分", num: true },
    { key: "growth", label: "增速%", num: true },
    { key: "gross_margin", label: "毛利%", num: true },
    { key: "net_margin", label: "净利%", num: true },
    { key: "pe_grade", label: "PE" },
    { key: "peg_grade", label: "PEG" },
    { key: "reason", label: "判断理由", sortable: false },
  ];

  const thead = h("div", { class: "thead gradeshead" });
  const vbody = h("div", { class: "vbody" });
  const wrap = h("div", { class: "vwrap" }, thead, vbody);
  const style = "grid-template-columns:84px 130px 60px minmax(140px,.7fr) 52px 60px 68px 64px 64px 56px 56px minmax(260px,1.3fr);min-width:1180px";
  thead.setAttribute("style", style);

  let view = [];
  let rafId = 0;
  const ROW_H = 34;

  function refresh() {
    const q = state.q.trim().toLowerCase();
    view = rows.filter((r) => {
      if (state.grade && r.grade !== state.grade) return false;
      if (state.market && r.market !== state.market) return false;
      if (q && !((r.code || "").toLowerCase().includes(q)
        || (r.name || "").toLowerCase().includes(q)
        || (r.segment || "").toLowerCase().includes(q)
        || (r.reason || "").toLowerCase().includes(q))) return false;
      return true;
    });
    const col = cols.find((c) => c.key === state.sortKey);
    view.sort((a, b) => {
      const av = a[state.sortKey], bv = b[state.sortKey];
      if (av == null || av === "") return 1;
      if (bv == null || bv === "") return -1;
      const cmp = col && col.num ? av - bv : String(av).localeCompare(String(bv), "zh-CN");
      return cmp * state.sortDir;
    });
    countEl.textContent = `${view.length} / ${rows.length} 只`;
    renderWindow();
  }

  function renderHead() {
    thead.innerHTML = "";
    for (const c of cols) {
      const on = state.sortKey === c.key;
      thead.append(h("div", {
        class: `th ${on ? "on" : ""} ${c.num ? "right" : ""}`,
        onclick: c.sortable === false ? null : () => {
          if (state.sortKey === c.key) state.sortDir *= -1;
          else { state.sortKey = c.key; state.sortDir = c.num ? -1 : 1; }
          renderHead(); refresh();
        },
      }, c.label, on ? h("span", { class: "arr" }, state.sortDir > 0 ? " ▲" : " ▼") : ""));
    }
  }

  function renderWindow() {
    vbody.style.height = `${view.length * ROW_H}px`;
    const top = wrap.scrollTop;
    const first = Math.max(0, Math.floor(top / ROW_H) - 6);
    const last = Math.min(view.length, Math.ceil((top + wrap.clientHeight) / ROW_H) + 6);
    vbody.innerHTML = "";
    for (let i = first; i < last; i++) {
      const r = view[i];
      vbody.append(h("div", { class: "vrow", style: `${style};top:${i * ROW_H}px` },
        h("div", { class: "co" }, r.code),
        h("div", { class: "name" }, h("a", { href: `#/co/${r.code}` }, r.name)),
        h("div", { class: "dimtxt" }, r.market || "—"),
        h("div", { class: "dimtxt", title: r.segment }, r.segment || "—"),
        h("div", { class: gradeClass(r.grade) }, r.grade || "—"),
        h("div", { class: "num right" }, r.score ?? "—"),
        h("div", { class: "num right" }, fmt.num(r.growth, 1)),
        h("div", { class: "num right" }, fmt.num(r.gross_margin, 0)),
        h("div", { class: "num right" }, fmt.num(r.net_margin, 0)),
        h("div", { class: "dimtxt right" }, r.pe_grade || "—"),
        h("div", { class: "dimtxt right" }, r.peg_grade || "—"),
        h("div", { class: "dimtxt", title: r.reason }, r.reason || r.note || "—")));
    }
  }

  wrap.addEventListener("scroll", () => {
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(renderWindow);
  });
  new ResizeObserver(() => renderWindow()).observe(wrap);
  root._onMount = renderWindow;

  drawTabs();
  renderHead();
  refresh();
  root.append(tabs, filters, wrap,
    h("p", { class: "src" },
      `分级生成于 ${data.generated_at || "归档快照"}（爱牛归档）；未评级 ${dist["未评级"] ?? 0} 只表示数据不足，不代表负面。`));
  return root;
}
