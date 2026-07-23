// 通用工具：DOM 构造、数字格式化、迷你 Markdown 渲染。

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]
  ));
}

export const fmt = {
  num(v, digits = 2) {
    if (v == null || Number.isNaN(v)) return "—";
    return Number(v).toLocaleString("zh-CN", {
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
  },
  int(v) {
    if (v == null || Number.isNaN(v)) return "—";
    return Math.round(v).toLocaleString("zh-CN");
  },
  pct(v) {
    if (v == null || Number.isNaN(v)) return "—";
    const s = v > 0 ? "+" : "";
    return `${s}${Number(v).toFixed(2)}%`;
  },
  mcap(v) {
    if (v == null || Number.isNaN(v)) return "—";
    if (v >= 10000) return `${(v / 10000).toFixed(2)}万亿`;
    return `${fmt.int(v)}亿`;
  },
};

export function chgClass(v) {
  if (v == null) return "";
  return v > 0 ? "pos" : v < 0 ? "neg" : "";
}

export function gradeClass(g) {
  if (!g) return "";
  return `grade-${g.replace("+", "plus")}`;
}

// 从 "华大九天(301269)" 解析 { name, code }
export function parseStockRef(s) {
  const m = /^(.*?)[（(]([A-Za-z0-9.\-]+)[)）]\s*$/.exec(s.trim());
  if (m) return { name: m[1].trim(), code: m[2].trim() };
  return { name: s.trim(), code: null };
}

// ── 迷你 Markdown（档案正文渲染，无外部依赖） ──────────────

function inline(md) {
  let s = esc(md);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return s;
}

export function renderMarkdown(md) {
  const lines = String(md || "").split(/\r?\n/);
  const out = [];
  let list = null; // { tag, items }
  let table = null; // { header, rows }
  let para = [];

  const flushPara = () => {
    if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; }
  };
  const flushList = () => {
    if (list) {
      out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`);
      list = null;
    }
  };
  const flushTable = () => {
    if (table) {
      const head = `<tr>${table.header.map((c) => `<th>${inline(c)}</th>`).join("")}</tr>`;
      const body = table.rows.map((r) =>
        `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("");
      out.push(`<div class="tablebox"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`);
      table = null;
    }
  };
  const flushAll = () => { flushPara(); flushList(); flushTable(); };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const t = line.trim();

    if (!t) { flushAll(); continue; }

    if (/^\|.*\|$/.test(t)) {
      flushPara(); flushList();
      const cells = t.slice(1, -1).split("|").map((c) => c.trim());
      if (cells.every((c) => /^:?-{2,}:?$/.test(c))) continue; // 分隔行
      if (!table) table = { header: cells, rows: [] };
      else table.rows.push(cells);
      continue;
    }
    flushTable();

    const hm = /^(#{1,4})\s+(.*)$/.exec(t);
    if (hm) {
      flushAll();
      // 档案正文以 ## 为主章节：# 和 ## 都归入 h2（金色节标题），### 起递进
      const lvl = Math.min(Math.max(hm[1].length, 2), 4);
      out.push(`<h${lvl}>${inline(hm[2])}</h${lvl}>`);
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(t)) { flushAll(); out.push("<hr>"); continue; }
    if (/^>\s?/.test(t)) {
      flushAll();
      out.push(`<blockquote>${inline(t.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }
    const ul = /^[-•*]\s+(.*)$/.exec(t);
    const ol = /^\d+[.、]\s+(.*)$/.exec(t);
    if (ul || ol) {
      flushPara();
      const tag = ul ? "ul" : "ol";
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push((ul || ol)[1]);
      continue;
    }
    flushList();
    para.push(t);
  }
  flushAll();
  return out.join("\n");
}
