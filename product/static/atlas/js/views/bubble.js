// 三高气泡图：横轴=壁垒，纵轴=利润，气泡大小=增速。
// 点击环节 → 右侧显示该环节的周期位置与催化剂，并可跳到个股表。

import { api } from "../data.js";
import { h } from "../util.js";

const W = 760, H = 560, PAD = { l: 46, r: 64, t: 62, b: 40 };
const SETS = [
  { key: "ai", label: "AI 算力" },
  { key: "general", label: "AI 产业链" },
  { key: "materials", label: "半导体材料" },
];

export async function renderBubble(query) {
  const [bubbles, catalysts] = await Promise.all([api.bubble(), api.catalysts()]);
  let cur = query && SETS.some((s) => s.key === query.get("set")) ? query.get("set") : "ai";

  const svgBox = h("div", { class: "card" });
  const panel = h("div", { class: "card bubpanel" },
    h("div", { class: "empty" }, "点击气泡查看该环节的周期位置与催化剂"));
  const tabs = h("div", { class: "bubtabs" });
  const sub = h("div", { class: "sub", style: "margin-bottom:10px;color:var(--dim);font-size:13px" });

  function drawTabs() {
    tabs.innerHTML = "";
    for (const s of SETS) {
      if (!bubbles[s.key]) continue;
      tabs.append(h("button", {
        class: cur === s.key ? "on" : "",
        onclick: () => { cur = s.key; drawTabs(); draw(); },
      }, s.label));
    }
  }

  function draw() {
    const data = bubbles[cur] || {};
    const nodes = data.nodes || [];
    sub.textContent = data.intro || data.title || "";
    svgBox.innerHTML = "";
    svgBox.append(h("h3", {}, data.title || "三高气泡图"));

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "bubsvg");

    const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
    const xmin = Math.min(...xs, 0), xmax = Math.max(...xs, 10);
    const ymin = Math.min(...ys, 0), ymax = Math.max(...ys, 10);
    const X = (v) => PAD.l + ((v - xmin) / (xmax - xmin || 1)) * (W - PAD.l - PAD.r);
    const Y = (v) => H - PAD.b - ((v - ymin) / (ymax - ymin || 1)) * (H - PAD.t - PAD.b);

    for (let i = 1; i <= 4; i++) {
      const gx = PAD.l + (i / 5) * (W - PAD.l - PAD.r);
      const gy = PAD.t + (i / 5) * (H - PAD.t - PAD.b);
      svg.append(line(gx, PAD.t, gx, H - PAD.b, "gridline"));
      svg.append(line(PAD.l, gy, W - PAD.r, gy, "gridline"));
    }
    svg.append(line(PAD.l, H - PAD.b, W - PAD.r, H - PAD.b, "axis"));
    svg.append(line(PAD.l, PAD.t, PAD.l, H - PAD.b, "axis"));
    svg.append(text(W - PAD.r, H - PAD.b + 26, "壁垒 →", "axlabel", "end"));
    svg.append(text(PAD.l - 30, PAD.t + 10, "利润 ↑", "axlabel"));

    const sorted = [...nodes].sort((a, b) => (b.r || 10) - (a.r || 10));
    for (const n of sorted) {
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", `node${n.sangao ? " sangao" : ""}`);
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", X(n.x)); c.setAttribute("cy", Y(n.y));
      c.setAttribute("r", Math.max(8, (n.r || 10) * 1.5));
      const label = text(X(n.x), Y(n.y) - Math.max(8, (n.r || 10) * 1.5) - 5, n.name, "");
      g.append(c, label);
      g.addEventListener("click", () => {
        svg.querySelectorAll(".node.sel").forEach((el) => el.classList.remove("sel"));
        g.classList.add("sel");
        showPanel(n);
      });
      svg.append(g);
    }
    svgBox.append(svg);
    svgBox.append(h("p", { class: "src" },
      "金圈=三高环节（高壁垒·高利润·高增长）。数据为归档快照，位置代表研究判断而非实测值。"));
  }

  function showPanel(n) {
    panel.innerHTML = "";
    const matchKey = Object.keys(catalysts).find((k) =>
      k.includes(n.name) || n.name.includes(k.split("/")[0]));
    const cat = matchKey ? catalysts[matchKey] : null;
    panel.append(h("h4", {}, n.name));
    panel.append(h("p", { class: "cyc" },
      n.sangao ? h("span", { class: "chip gold" }, "三高环节") : h("span", { class: "chip" }, "非三高"),
      " ",
      h("a", { class: "chip link", href: `#/table?segment=${encodeURIComponent(n.name.split("/")[0])}` }, "查看相关公司 →")));
    if (cat) {
      panel.append(h("p", { class: "cyc" },
        h("span", { class: `cattag ${cat.cycle_tag === "上行" ? "up" : cat.cycle_tag === "下行" ? "down" : "mid"}` },
          `周期：${cat.cycle_tag || "—"}`)));
      if (cat.cycle) panel.append(h("p", { class: "cyc" }, h("b", {}, "周期位置："), cat.cycle));
      if (cat.catalyst) panel.append(h("p", { class: "cyc" }, h("b", {}, "下一催化："), cat.catalyst));
      panel.append(h("p", { class: "src" }, `催化剂口径：${matchKey}（归档研究判断）`));
    } else {
      panel.append(h("p", { class: "cyc" }, "该环节在催化剂库中无直接匹配条目。"));
    }
  }

  drawTabs();
  draw();

  return h("div", {},
    h("div", { class: "pagehead" },
      h("h1", {}, "三高气泡图"),
      sub),
    tabs,
    h("div", { class: "bubblewrap" }, svgBox, panel));
}

function line(x1, y1, x2, y2, cls) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "line");
  el.setAttribute("x1", x1); el.setAttribute("y1", y1);
  el.setAttribute("x2", x2); el.setAttribute("y2", y2);
  el.setAttribute("class", cls);
  return el;
}
function text(x, y, str, cls, anchor) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
  el.setAttribute("x", x); el.setAttribute("y", y);
  if (cls) el.setAttribute("class", cls);
  if (anchor) el.setAttribute("text-anchor", anchor);
  el.textContent = str;
  return el;
}
