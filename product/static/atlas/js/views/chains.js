// 产业链：22 套结构的索引与层级流程详情。
// 公司 chip 双向跳转：产业节点 → 公司工作台。

import { api, companyIndex } from "../data.js";
import { h, parseStockRef } from "../util.js";

export async function renderChains() {
  const chains = await api.chains();
  const entries = Object.entries(chains);
  const panorama = entries.filter(([k]) => !k.endsWith("_makers"));
  const makers = entries.filter(([k]) => k.endsWith("_makers"));

  return h("div", {},
    h("div", { class: "pagehead" },
      h("h1", {}, "产业链全景"),
      h("div", { class: "sub" }, "每条链按上游 → 中游 → 下游的环节展开，环节里是它的角色、上下游关系和代表公司。")),
    section("产业结构", panorama),
    section("环节厂商图", makers),
  );
}

function section(title, entries) {
  if (!entries.length) return "";
  return h("div", { style: "margin-bottom:22px" },
    h("h3", { style: "font-family:var(--serif);color:var(--gold);letter-spacing:1px;margin-bottom:10px" }, title),
    h("div", { class: "grid chainsgrid" },
      entries.map(([key, c]) => h("a", { class: "card chaincard", href: `#/chain/${encodeURIComponent(key)}` },
        h("h4", {}, c.title || key),
        h("p", {}, c.intro || ""),
        h("div", { class: "meta" }, `${(c.stages || []).length} 个环节`)))));
}

export async function renderChainDetail(key) {
  const [chains, index] = await Promise.all([api.chains(), companyIndex()]);
  const chain = chains[key];
  if (!chain) {
    return h("div", { class: "card" }, h("h3", {}, "未找到该产业链"),
      h("a", { href: "#/chains" }, "← 回到产业链列表"));
  }

  return h("div", {},
    h("p", { style: "margin-bottom:10px" },
      h("a", { class: "backlink", href: "#/chains" }, "← 产业链全景")),
    h("div", { class: "pagehead" },
      h("h1", {}, chain.title || key),
      h("div", { class: "sub" }, chain.intro || "")),
    h("div", { class: "card" },
      (chain.stages || []).map((s) => stageEl(s, index))),
  );
}

function stageEl(s, index) {
  return h("div", { class: "stage" },
    h("div", { class: "shead" },
      h("b", {}, s.name),
      s.layer ? h("span", { class: "chip" }, s.layer) : ""),
    s.role ? h("div", { class: "role" }, s.role) : "",
    (s.upstream || s.downstream)
      ? h("div", { class: "flow" },
        s.upstream ? `上游：${s.upstream}` : "", s.upstream && s.downstream ? " ｜ " : "",
        s.downstream ? `下游：${s.downstream}` : "")
      : "",
    h("div", { class: "stocks" },
      (s.stocks || []).map((raw) => {
        const { name, code } = parseStockRef(raw);
        const known = code && index.has(code);
        return known
          ? h("a", { class: "chip link", href: `#/co/${code}` }, name)
          : h("span", { class: "chip", title: code || "" }, name);
      })),
    s.note ? h("div", { class: "note" }, s.note) : "");
}
