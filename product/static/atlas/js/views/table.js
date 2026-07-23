// 个股全景表：虚拟滚动 + 多维筛选 + 全列排序。
// 修复爱牛缺陷：表头全部真实可排序；千行滚动不卡顿。

import { api } from "../data.js";
import { h, fmt, chgClass, gradeClass } from "../util.js";

const ROW_H = 34;

const COLS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "market", label: "市场" },
  { key: "chains", label: "链", get: (r) => (r.chains || []).join("/") },
  { key: "layer", label: "层级" },
  { key: "segment", label: "细分" },
  { key: "role", label: "角色" },
  { key: "price", label: "现价", num: true },
  { key: "chg", label: "涨跌%", num: true },
  { key: "pe", label: "PE", num: true },
  { key: "peg", label: "PEG", num: true },
  { key: "mcap", label: "市值", num: true },
  { key: "score", label: "综合", num: true },
  { key: "opp", label: "机会", num: true },
  { key: "grade", label: "分级" },
  { key: "sangao", label: "三高", get: (r) => (r.sangao ? 1 : 0), num: true },
  { key: "_tags", label: "标签", sortable: false },
];

const state = {
  q: "", chain: "", layer: "", market: "", grade: "",
  sangao: false, n: false, t: false, cowos: false, dossier: false,
  sortKey: "mcap", sortDir: -1,
};

export async function renderTable(query) {
  const rows = await api.companies();
  if (query && query.get("chain")) state.chain = query.get("chain");
  if (query && query.get("segment")) state.q = query.get("segment");

  const chainSet = [...new Set(rows.flatMap((r) => r.chains || []))].sort();
  const marketSet = [...new Set(rows.map((r) => r.market).filter(Boolean))];
  const gradeSet = ["S", "A+", "A", "B", "C", "D"];

  const root = h("div", {},
    h("div", { class: "pagehead" },
      h("h1", {}, "个股全景表"),
      h("div", { class: "sub" }, "按产业位置组织的公司全集。点击表头排序，点击名称进入公司工作台。")),
  );

  const countEl = h("span", { class: "count" });
  const filters = h("div", { class: "filters" },
    h("input", {
      type: "search", placeholder: "搜代码/名称/细分…", value: state.q,
      oninput: (e) => { state.q = e.target.value; refresh(); },
    }),
    select("全部链", chainSet, state.chain, (v) => { state.chain = v; refresh(); }),
    select("全部层级", ["上游", "中游", "下游"], state.layer, (v) => { state.layer = v; refresh(); }),
    select("全部市场", marketSet, state.market, (v) => { state.market = v; refresh(); }),
    select("全部分级", gradeSet, state.grade, (v) => { state.grade = v; refresh(); }),
    toggle("三高", "sangao"), toggle("N链", "n"), toggle("T链", "t"),
    toggle("CoWoS", "cowos"), toggle("有档案", "dossier"),
    countEl,
  );

  const thead = h("div", { class: "thead" });
  const vbody = h("div", { class: "vbody" });
  const wrap = h("div", { class: "vwrap" }, thead, vbody);
  root.append(filters, wrap);

  let view = [];
  let rafId = 0;

  function applyFilters() {
    const q = state.q.trim().toLowerCase();
    view = rows.filter((r) => {
      if (q && !(r.code.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)
        || (r.segment || "").toLowerCase().includes(q))) return false;
      if (state.chain && !(r.chains || []).includes(state.chain)) return false;
      if (state.layer && r.layer !== state.layer) return false;
      if (state.market && r.market !== state.market) return false;
      if (state.grade && r.grade !== state.grade) return false;
      for (const flag of ["sangao", "n", "t", "cowos", "dossier"]) {
        if (state[flag] && !r[flag]) return false;
      }
      return true;
    });
    const col = COLS.find((c) => c.key === state.sortKey);
    const get = col && col.get ? col.get : (r) => r[state.sortKey];
    view = [...view].sort((a, b) => {
      const av = get(a), bv = get(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv : String(av).localeCompare(String(bv), "zh-CN");
      return cmp * state.sortDir;
    });
    countEl.textContent = `${view.length} / ${rows.length} 家`;
  }

  function renderHead() {
    thead.innerHTML = "";
    for (const c of COLS) {
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
      vbody.append(rowEl(view[i], i));
    }
  }

  function refresh() { applyFilters(); renderWindow(); }

  wrap.addEventListener("scroll", () => {
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(renderWindow);
  });
  // 挂载后容器才有真实高度；尺寸变化时重算可见窗口
  new ResizeObserver(() => renderWindow()).observe(wrap);
  root._onMount = renderWindow;

  renderHead();
  refresh();
  return root;

  function select(placeholder, options, current, onchange) {
    return h("select", { onchange: (e) => onchange(e.target.value) },
      h("option", { value: "" }, placeholder),
      options.map((o) => h("option", { value: o, selected: o === current || null }, o)));
  }
  function toggle(label, key) {
    return h("label", { class: "tog" },
      h("input", {
        type: "checkbox", checked: state[key] || null,
        onchange: (e) => { state[key] = e.target.checked; refresh(); },
      }), label);
  }
}

function rowEl(r, i) {
  const tags = [];
  if (r.n) tags.push(h("i", { class: "g", title: "英伟达链" }, "N"));
  if (r.t) tags.push(h("i", { title: "特斯拉链" }, "T"));
  if (r.cowos) tags.push(h("i", { title: "CoWoS" }, "CW"));
  if (r.rmap) tags.push(h("i", { title: "有路线图" }, "R"));
  if (r.dossier) tags.push(h("i", { class: "g", title: "有深度档案" }, "档"));

  return h("div", { class: "vrow", style: `top:${i * ROW_H}px` },
    h("div", { class: "co" }, r.code),
    h("div", { class: "name" }, h("a", { href: `#/co/${r.code}` }, r.name)),
    h("div", { class: "dimtxt" }, r.market || "—"),
    h("div", { class: "dimtxt" }, (r.chains || []).join("/") || "—"),
    h("div", { class: "dimtxt" }, r.layer || "—"),
    h("div", { class: "dimtxt", title: r.segment }, r.segment || "—"),
    h("div", { class: "dimtxt" }, r.role || "—"),
    h("div", { class: "num right" }, fmt.num(r.price)),
    h("div", { class: `num right ${chgClass(r.chg)}` }, fmt.pct(r.chg)),
    h("div", { class: "num right" }, fmt.num(r.pe, 1)),
    h("div", { class: "num right" }, fmt.num(r.peg)),
    h("div", { class: "num right" }, fmt.mcap(r.mcap)),
    h("div", { class: "num right" }, r.score ?? "—"),
    h("div", { class: "num right" }, r.opp ?? "—"),
    h("div", { class: `right ${gradeClass(r.grade)}` }, r.grade || "—"),
    h("div", { class: "right" }, r.sangao ? h("span", { class: "grade-S" }, "◆") : ""),
    h("div", { class: "tags" }, tags),
  );
}
