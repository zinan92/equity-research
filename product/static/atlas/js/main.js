// 外壳：hash 路由、顶栏搜索、数据状态标识。

import { api, companyIndex } from "./data.js";
import { h } from "./util.js";
import { renderHome } from "./views/home.js";
import { renderTable } from "./views/table.js";
import { renderChains, renderChainDetail } from "./views/chains.js";
import { renderBubble } from "./views/bubble.js";
import { renderGrades } from "./views/grades.js";
import { renderCompany } from "./views/company.js";

const app = document.getElementById("app");

const routes = [
  { re: /^#?\/?$/, name: "home", view: () => renderHome() },
  { re: /^#\/table$/, name: "table", view: (m, q) => renderTable(q) },
  { re: /^#\/chains$/, name: "chains", view: () => renderChains() },
  { re: /^#\/chain\/([^?]+)$/, name: "chains", view: (m) => renderChainDetail(decodeURIComponent(m[1])) },
  { re: /^#\/bubble$/, name: "bubble", view: (m, q) => renderBubble(q) },
  { re: /^#\/grades$/, name: "grades", view: (m, q) => renderGrades(q) },
  { re: /^#\/co\/([^?]+)$/, name: "table", view: (m) => renderCompany(decodeURIComponent(m[1])) },
];

async function route() {
  const raw = location.hash || "#/";
  const [path, qs] = raw.split("?");
  const query = new URLSearchParams(qs || "");
  const match = routes.find((r) => r.re.test(path));
  markNav(match ? match.name : "");
  app.innerHTML = "";
  app.append(h("div", { class: "loading" }, "载入数据…"));
  try {
    const m = match ? match.re.exec(path) : null;
    const el = match ? await match.view(m, query) : notFound(path);
    app.innerHTML = "";
    app.append(el);
    if (typeof el._onMount === "function") el._onMount(); // 挂载后有真实尺寸，同步重算虚拟窗口
    app.scrollIntoView({ block: "start" });
    window.scrollTo(0, 0);
  } catch (err) {
    console.error(err);
    app.innerHTML = "";
    app.append(h("div", { class: "card" },
      h("h3", {}, "载入失败"),
      h("p", {}, String(err.message || err)),
      h("p", { class: "src" },
        "请确认已生成 fixture：python3 product/static/atlas/build_fixtures.py")));
  }
}

function notFound(path) {
  return h("div", { class: "card" },
    h("h3", {}, "页面不存在"),
    h("p", {}, `未识别的路径：${path}`),
    h("p", {}, h("a", { href: "#/" }, "回到总览")));
}

function markNav(name) {
  for (const a of document.querySelectorAll("[data-route]")) {
    a.classList.toggle("on", a.dataset.route === name);
  }
}

// ── 全局搜索 ──────────────────────────────
function setupSearch() {
  const input = document.getElementById("q");
  const box = document.getElementById("qResults");
  let items = [];
  let sel = -1;

  async function update() {
    const term = input.value.trim().toLowerCase();
    if (!term) { box.hidden = true; return; }
    const rows = await api.companies();
    items = rows.filter((r) =>
      r.code.toLowerCase().includes(term) ||
      r.name.toLowerCase().includes(term) ||
      (r.segment || "").toLowerCase().includes(term) ||
      (r.chains || []).some((c) => c.toLowerCase().includes(term))
    ).slice(0, 12);
    sel = -1;
    box.innerHTML = "";
    if (!items.length) { box.hidden = true; return; }
    for (const r of items) {
      box.append(h("a", { href: `#/co/${r.code}`, onclick: close },
        h("span", { class: "code" }, r.code),
        h("span", {}, r.name),
        h("span", { class: "seg" }, r.segment || (r.chains || [])[0] || "")));
    }
    box.hidden = false;
  }

  function close() { box.hidden = true; input.blur(); }

  input.addEventListener("input", update);
  input.addEventListener("keydown", (e) => {
    const links = [...box.querySelectorAll("a")];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
      links.forEach((a, i) => a.classList.toggle("sel", i === sel));
    } else if (e.key === "Enter" && links.length) {
      location.hash = links[Math.max(sel, 0)].getAttribute("href");
      close();
      input.value = "";
    } else if (e.key === "Escape") close();
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".searchbox")) box.hidden = true;
  });
}

async function boot() {
  setupSearch();
  window.addEventListener("hashchange", route);
  try {
    const meta = await api.meta();
    const chipEl = document.getElementById("datachip");
    chipEl.textContent = `FIXTURE · ${meta.as_of}`;
    chipEl.title = `${meta.notice}（来源：${meta.origin}）`;
    await companyIndex();
  } catch (err) {
    console.error("meta 加载失败", err);
  }
  await route();
}

boot();
