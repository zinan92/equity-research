const GROUPS = [
  ["钱的价格", ["dxy", "us2y", "us10y", "us2s10s"]],
  ["风险资产", ["sp500", "nasdaq", "us_dividend", "vix", "bitcoin"]],
  ["亚洲与 A 股", ["shanghai", "star50", "china_dividend", "nikkei", "kospi"]],
  ["实物资产", ["wti", "gold", "silver"]],
];
const TIMEFRAME_LABELS = { weekly: "周线", daily: "日线", four_hour: "4小时" };
const api = (path) => fetch(path, { headers: { Accept: "application/json" } }).then((response) => {
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json();
});

const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
const short = (value, length = 68) => {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= length ? text : `${text.slice(0, length - 1).replace(/[，。；、 ]+$/, "")}…`;
};
const chip = (value, tone = "") => `<span class="chip ${tone}">${esc(value)}</span>`;
const assetByKey = (report) => Object.fromEntries(report.assets.map((asset) => [asset.asset_key, asset]));
const formatValue = (value) => value == null ? "—" : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
const formatChange = (slot) => {
  if (slot?.change == null) return "—";
  const sign = slot.change > 0 ? "+" : "";
  if (slot.unit === "basis points") return `${sign}${slot.change.toFixed(1)}bp`;
  if (slot.unit === "percent") return `${sign}${slot.change.toFixed(2)}`;
  if (slot.change_pct != null) return `${sign}${slot.change_pct.toFixed(2)}%`;
  return `${sign}${slot.change.toFixed(2)}`;
};
const positionMeter = (state) => `<span class="position-meter ${esc(state)}" aria-label="${esc(state)}"><i></i><i></i><i></i></span>`;

function drawMiniChart(canvas, points) {
  const rect = canvas.getBoundingClientRect();
  const ratio = Math.max(2, window.devicePixelRatio || 1);
  const width = Math.max(40, rect.width); const height = Math.max(32, rect.height);
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height);
  if (!Array.isArray(points) || points.length < 2) return;
  const values = points.flatMap((p) => [Number(p.low), Number(p.high)]).filter(Number.isFinite);
  if (!values.length) return;
  const min = Math.min(...values); const max = Math.max(...values); const span = max - min || 1;
  const xPad = 5; const yPad = 5; const step = (width - xPad * 2) / points.length;
  const y = (value) => height - yPad - ((value - min) / span) * (height - yPad * 2);
  ctx.strokeStyle = "#eef2f4"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, height / 2); ctx.lineTo(width, height / 2); ctx.stroke();
  const bodyWidth = Math.max(2, step * .58);
  points.forEach((point, index) => {
    const open = Number(point.open); const close = Number(point.close); const high = Number(point.high); const low = Number(point.low);
    if (![open, close, high, low].every(Number.isFinite)) return;
    const x = xPad + step * index + step / 2; const up = close >= open;
    ctx.strokeStyle = up ? "#16875f" : "#d94b4b"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, y(high)); ctx.lineTo(x, y(low)); ctx.stroke();
    const top = y(Math.max(open, close)); const bottom = y(Math.min(open, close)); const bodyHeight = Math.max(1.5, bottom - top);
    if (up) { ctx.fillStyle = "#fff"; ctx.fillRect(x - bodyWidth / 2, top, bodyWidth, bodyHeight); ctx.strokeRect(x - bodyWidth / 2, top, bodyWidth, bodyHeight); }
    else { ctx.fillStyle = "#d94b4b"; ctx.fillRect(x - bodyWidth / 2, top, bodyWidth, bodyHeight); }
  });
  const ema = points.filter((point) => Number.isFinite(Number(point.ema50)));
  if (ema.length > 1) { ctx.strokeStyle = "#6f91cf"; ctx.lineWidth = 1.2; ctx.beginPath(); ema.forEach((point, index) => { const pointIndex = points.indexOf(point); const x = xPad + step * pointIndex + step / 2; const yy = y(Number(point.ema50)); if (index === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy); }); ctx.stroke(); }
}

function paintMiniCharts() {
  document.querySelectorAll("canvas.mini-chart").forEach((canvas) => drawMiniChart(canvas, JSON.parse(canvas.dataset.points || "[]")));
}

function renderSummary(report) {
  document.querySelector("#as-of").textContent = `数据截止 ${report.week_end}`;
  document.querySelector("#coverage").textContent = `分析覆盖 ${report.analysis_validated}/${report.assets.length}`;
  document.querySelector("#source-status").textContent = report.source_status === "complete" ? "完整" : "部分可用";
  document.querySelector("#analysis-count").textContent = `${report.analysis_validated} / ${report.assets.length}`;
  document.querySelector("#stance").textContent = report.source_status === "complete" && report.analysis_validated === report.assets.length ? "待确认" : "等待";
  document.querySelector("#thesis").textContent = report.analysis_validated === report.assets.length
    ? "所有资产分析已通过验证，先比较位置与结构，再进入单资产工作台。"
    : `当前有 ${report.unavailable_assets.length} 个资产缺少完整证据，已验证资产仍可独立阅读，不把缺失数据伪装成方向。`;
  document.querySelector("#footer").innerHTML = `真实 report：<code>${esc(report.report_id)}</code> · source：<code>${esc(report.source_snapshot_id)}</code>`;
  document.querySelector("#footer").hidden = false;
}

function renderNav() {
  document.querySelector("#group-nav").innerHTML = GROUPS.map(([label]) => `<a href="#group-${esc(label)}">${esc(label)}</a>`).join("");
}

function renderGroups(report) {
  const byKey = assetByKey(report);
  document.querySelector("#groups").innerHTML = GROUPS.map(([label, keys]) => {
    const rows = keys.map((key) => {
      const asset = byKey[key];
      const weekly = asset.slots.weekly;
      const tone = asset.analysis_status === "validated" ? "" : "warn";
      const mini = asset.mini_chart || {};
      return `<button class="asset-row" type="button" data-asset="${esc(key)}" aria-label="打开${esc(asset.display_name)}单资产工作台">
        <div class="asset-name"><strong>${esc(asset.display_name)}</strong><small>${esc(key)}</small></div>
        <div class="mini-cell"><canvas class="mini-chart" data-points="${esc(JSON.stringify(mini.mini_points || []))}" aria-label="${esc(asset.display_name)}最近20根周线"></canvas><small class="last-candle ${esc((mini.last_candle || {}).tone || "")}">${esc((mini.last_candle || {}).label || "—")}</small></div>
        <div class="latest-value"><b>${esc(formatValue(mini.latest_value))}</b><small>${esc(weekly.unit || "")}</small></div>
        <div class="change ${mini.change > 0 ? "up" : mini.change < 0 ? "down" : "flat"}">${esc(formatChange(weekly))}</div>
        <div class="position-cell">${positionMeter(asset.position_state)}${chip(asset.position, "neutral")}</div>
        <div class="trend ${esc((asset.trend || {}).tone || "flat")}"><b>${esc((asset.trend || {}).marker || "→")}</b><span>${esc((asset.trend || {}).label || "分歧")}</span></div>
        <div class="row-status ${tone}">${esc(asset.status_label)}</div>
      </button>`;
    }).join("");
    return `<section class="group" id="group-${esc(label)}"><header><h2>${esc(label)}</h2><span>${keys.length} 个资产</span></header><div class="table-head"><span>资产</span><span>K 线（周线）</span><span>最新价</span><span>周涨跌</span><span>位置</span><span>趋势</span><span>状态</span></div>${rows}</section>`;
  }).join("");
  document.querySelectorAll("[data-asset]").forEach((button) => button.addEventListener("click", () => showDetail(report, button.dataset.asset)));
  requestAnimationFrame(() => requestAnimationFrame(paintMiniCharts));
}

function renderPeriod(asset, timeframe) {
  const slot = asset.slots[timeframe];
  if (!slot) return "";
  return `<article class="period"><header><div><b>${TIMEFRAME_LABELS[timeframe]}</b><small>${esc(short(slot.text || "当前该周期分析不可用。", 34))}</small></div><span>EMA50 · MACD</span></header><div class="period-chart"><img src="${esc(slot.image_url)}" alt="${esc(asset.display_name)} ${TIMEFRAME_LABELS[timeframe]}" loading="lazy"></div><p>${esc(slot.text || "当前该周期分析不可用。")}</p></article>`;
}

function showDetail(report, key) {
  const asset = assetByKey(report)[key];
  if (!asset) return;
  const detail = document.querySelector("#detail");
  detail.hidden = false;
  detail.innerHTML = `<header class="detail-header"><div><small>宏观 K 线周报 · 单资产工作台</small><h2>${esc(asset.display_name)} <em>(${esc(key.toUpperCase())})</em></h2><p>截至 ${esc(report.week_end)}（周五收盘） · ${esc(asset.status_label)}</p></div><button class="back-button" type="button" id="back-to-overview">返回市场全景</button></header><section class="metric-strip"><div><small>位置</small><strong>${esc(asset.position)}</strong></div><div><small>结构</small><strong>${esc(asset.structure)}</strong></div><div><small>赔率</small><strong>${esc(asset.odds)}</strong></div><div><small>来源状态</small><strong>${esc(asset.status_label)}</strong></div></section><section class="period-grid">${["weekly", "daily", "four_hour"].map((timeframe) => renderPeriod(asset, timeframe)).join("")}</section><section class="interpretation"><article><small>多周期结论</small><h3>先把三个周期放在一起看</h3><p>${esc(asset.synthesis || "当前多周期分析不可用。")}</p><strong>工作判断：先看关键位，再决定是否扩大方向。</strong></article><article><small>这意味着什么 · 机制解释</small><h3>把 K 线翻译成市场语言</h3><p>${esc(asset.theoretical_implication || "当前机制解释不可用。")}</p><span class="evidence-note">证据绑定：${esc(report.source_snapshot_id)} · 截止 ${esc(report.week_end)}</span></article></section><div class="detail-footer">数据来自最新不可变 Weekly report；缺失状态不会被旧数据或隐式 fallback 替代。</div>`;
  document.querySelector("#back-to-overview").addEventListener("click", () => { detail.hidden = true; document.querySelector("#overview").scrollIntoView({ behavior: "smooth" }); });
  detail.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function boot() {
  try {
    const report = await api("/api/weekly-report");
    renderSummary(report); renderNav(); renderGroups(report);
    document.querySelector("#loading").hidden = true;
    document.querySelector("#app").hidden = false;
  } catch (error) {
    document.querySelector("#loading").hidden = true;
    const panel = document.querySelector("#error");
    panel.textContent = `无法读取最新 Weekly report：${error.message}`;
    panel.hidden = false;
  }
}
boot();
