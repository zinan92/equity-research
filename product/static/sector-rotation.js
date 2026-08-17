(() => {
  "use strict";

  const DEMO_NOTE = "示例数据，仅用于验证信息架构；不是当前市场判断。";

  const SECTORS = [
    {id: "chips", label: "芯片", posture: "attack", group: "芯片簇", provider: "半导体", symbol: "BK1036", identity: "accepted_alias", quality: "conditional_complete", role: "improving", stage: "筑底确认", pattern: "双底候选", flow: "改善", relative: "改善", values: [38, 34, 31, 32, 29, 33, 35, 34, 38, 41, 43, 47], flows: [-2, -1, 0, 1, 2, 3, 2, 4, 5, 4], note: "逻辑板块“芯片”暂接受行业板块“半导体”作为条件别名；真实接入仍需保留 alias 记录。"},
    {id: "semiconductor-equipment", label: "半导体设备", posture: "attack", group: "芯片簇", provider: "半导体设备", symbol: "BK1326", identity: "provider_candidate", quality: "fixture", role: "improving", stage: "启动候选", pattern: "平台突破候选", flow: "确认", relative: "改善", values: [34, 35, 34, 33, 35, 36, 37, 39, 41, 42, 45, 48], flows: [-1, 0, 1, 2, 3, 2, 3, 4, 4, 5], note: "provider identity 已有候选，目录类型仍需在真实采集窗口复核。"},
    {id: "memory", label: "存储", posture: "mixed", group: "芯片簇", provider: "存储芯片", symbol: "BK1137", identity: "concept", quality: "fixture", role: "leader", stage: "趋势延续", pattern: "高位平台", flow: "确认", relative: "领先", values: [40, 43, 45, 44, 48, 51, 50, 53, 55, 57, 59, 61], flows: [1, 2, 3, 3, 4, 4, 5, 4, 5, 6], note: "概念板块成分可能调样；展示时必须显式显示 provider 与 as-of。"},
    {id: "pcb", label: "PCB", posture: "attack", group: "芯片簇", provider: "PCB", symbol: "BK0877", identity: "concept", quality: "fixture", role: "leader", stage: "加速", pattern: "突破后延续", flow: "确认", relative: "领先", values: [35, 36, 38, 37, 41, 45, 44, 48, 53, 55, 58, 63], flows: [0, 1, 2, 4, 4, 5, 6, 6, 7, 6], note: "示例中作为领先板块；真实状态必须由完整 K 线与资金快照共同生成。"},
    {id: "ai-applications", label: "AI应用", posture: "attack", group: "AI 软件", provider: "AI应用", symbol: "BK1629", identity: "concept", quality: "partial", role: "watch", stage: "unknown", pattern: "K 线未验证", flow: "当前快照可读", relative: "unknown", values: [50, 49, 48, 47, 49, 48, 50, 49, 51, 50, 52, 53], flows: [1, 2, 1, 2, 3, 2, 1, 2, 3, 2], note: "资金流当前快照已读，但主路由历史 K 线尚未通过实证；下游必须保持 unknown。"},
    {id: "robotics", label: "机器人", posture: "attack", group: "AI 硬件/制造", provider: "机器人概念", symbol: "BK1090", identity: "concept", quality: "fixture", role: "leader", stage: "启动", pattern: "弧形底候选", flow: "确认", relative: "领先", values: [30, 31, 31, 32, 33, 35, 36, 38, 40, 42, 45, 47], flows: [-1, 0, 1, 1, 2, 3, 3, 4, 4, 5], note: "V1 保留 broad 机器人，不与人形机器人同时占槽。"},
    {id: "innovative-drugs", label: "创新药", posture: "mixed", group: "成长防守", provider: "创新药", symbol: "BK1106", identity: "concept", quality: "fixture", role: "improving", stage: "底部候选", pattern: "弧形底", flow: "边际改善", relative: "改善", values: [46, 43, 41, 40, 40, 41, 42, 43, 45, 46, 48, 49], flows: [-3, -2, -1, 0, 0, 1, 1, 2, 2, 3], note: "底部形态仍需突破和持续性确认，不直接转成买入。"},
    {id: "new-energy", label: "新能源", posture: "attack", group: "能源转型", provider: "新能源", symbol: "BK0493", identity: "concept", quality: "fixture", role: "improving", stage: "平台修复", pattern: "平台收敛", flow: "边际改善", relative: "中性", values: [55, 53, 50, 49, 50, 49, 51, 52, 53, 52, 54, 55], flows: [-2, -1, -1, 0, 1, 1, 2, 1, 2, 2, 3, 3], note: "新能源保持 broad 槽位；光伏、风电、储能默认作为下钻或替换项。"},
    {id: "power-generation", label: "发电", posture: "mixed", group: "能源转型", provider: "电力", symbol: "BK0428", identity: "accepted_alias_pending", quality: "partial", role: "watch", stage: "unknown", pattern: "K 线未验证", flow: "当前快照可读", relative: "unknown", values: [50, 50, 49, 50, 49, 51, 50, 50, 51, 50, 51, 52], flows: [0, 1, 0, 1, 2, 1, 2, 2, 3, 2], note: "“发电”没有精确同名板；BK0428“电力”是候选别名，需 taxonomy 签收与主路由 K 线重试。"},
    {id: "defense", label: "军工", posture: "attack", group: "独立进攻", provider: "国防军工", symbol: "BK1204", identity: "industry", quality: "fixture", role: "improving", stage: "趋势延续", pattern: "上升通道", flow: "确认", relative: "改善", values: [39, 40, 42, 41, 44, 45, 47, 48, 47, 50, 52, 53], flows: [0, 1, 2, 2, 3, 3, 4, 3, 4, 4], note: "军工与商业航天保留两个观察槽，但不得自动解释为同一轮动。"},
    {id: "commercial-space", label: "商业航天", posture: "attack", group: "独立进攻", provider: "商业航天", symbol: "BK0963", identity: "concept", quality: "fixture", role: "leader", stage: "加速", pattern: "突破后延续", flow: "确认", relative: "领先", values: [35, 37, 36, 40, 43, 42, 46, 49, 52, 54, 57, 60], flows: [1, 2, 2, 3, 4, 4, 5, 6, 5, 6], note: "窄主题波动较大，需显示成分漂移和相关性，不扩展成父级产业链。"},
    {id: "controlled-fusion", label: "可控核聚变", posture: "attack", group: "独立进攻", provider: "可控核聚变", symbol: "BK1163", identity: "concept", quality: "fixture", role: "improving", stage: "底部候选", pattern: "双底候选", flow: "边际改善", relative: "中性", values: [45, 42, 39, 38, 39, 38, 40, 42, 41, 43, 44, 46], flows: [-2, -1, -1, 0, 1, 0, 1, 2, 2, 3], note: "历史组件很窄，先作为观察槽，不把形态识别当成交易信号。"},
    {id: "rare-metals", label: "稀有金属", posture: "mixed", group: "资源", provider: "小金属", symbol: "BK1027", identity: "accepted_alias", quality: "fixture", role: "watch", stage: "趋势衰减", pattern: "冲高回落", flow: "流出", relative: "转弱", values: [52, 55, 57, 59, 61, 60, 59, 57, 56, 54, 53, 51], flows: [5, 5, 4, 3, 2, 1, 0, -1, -2, -3], note: "稀有金属与贵金属分开；BK1027 是小金属代理，不能静默视为完全同名。"},
    {id: "precious-metals", label: "贵金属", posture: "defense", group: "防守资源", provider: "贵金属", symbol: "BK0732", identity: "industry", quality: "fixture", role: "leader", stage: "趋势延续", pattern: "高位趋势", flow: "确认", relative: "领先", values: [42, 44, 45, 47, 49, 48, 51, 53, 55, 56, 58, 60], flows: [2, 3, 3, 4, 4, 5, 5, 6, 5, 6], note: "防守标签是长期先验，不代表任何单日都处于防守状态。"},
    {id: "media-gaming", label: "传媒", posture: "mixed", group: "AI 软件", provider: "传媒", symbol: "BK0486", identity: "accepted_alias", quality: "fixture", role: "improving", stage: "底部候选", pattern: "平台收敛", flow: "边际改善", relative: "改善", values: [47, 45, 44, 43, 44, 45, 46, 45, 47, 48, 49, 50], flows: [-2, -1, 0, 1, 1, 2, 1, 2, 3, 3], note: "传媒/游戏与 AI 应用可能重叠；V1 保留显示身份，breadth 去重留到后续。"},
    {id: "baijiu", label: "白酒", posture: "defense", group: "消费防守", provider: "白酒", symbol: "BK0896", identity: "industry", quality: "fixture", role: "watch", stage: "下行", pattern: "下降通道", flow: "流出", relative: "转弱", values: [58, 57, 55, 54, 53, 52, 51, 50, 49, 47, 46, 45], flows: [2, 1, 0, -1, -2, -2, -3, -3, -4, -4], note: "白酒是防守观察槽，不因为标签而自动得到正面状态。"},
    {id: "banks", label: "银行", posture: "defense", group: "金融防守", provider: "银行Ⅱ", symbol: "BK0475", identity: "industry", quality: "fixture", role: "watch", stage: "横盘", pattern: "平台", flow: "稳定", relative: "中性", values: [50, 50, 51, 50, 50, 51, 50, 50, 51, 50, 50, 51], flows: [0, 0, 1, 0, 1, 0, 0, 1, 0, 1], note: "旧金融篮子被拆为银行、保险、证券，避免把不同攻防行为合并。"},
    {id: "insurance", label: "保险", posture: "defense", group: "金融防守", provider: "保险Ⅱ", symbol: "BK0474", identity: "industry", quality: "fixture", role: "watch", stage: "平台修复", pattern: "弧形底候选", flow: "稳定", relative: "中性", values: [45, 44, 43, 44, 43, 44, 45, 46, 45, 46, 47, 48], flows: [-1, 0, 0, 1, 0, 1, 1, 0, 1, 1], note: "保险与银行的利率敏感度不同，必须独立显示。"},
    {id: "securities", label: "证券", posture: "attack", group: "金融高 beta", provider: "证券Ⅱ", symbol: "BK0473", identity: "industry", quality: "fixture", role: "improving", stage: "启动候选", pattern: "平台突破候选", flow: "改善", relative: "改善", values: [40, 39, 40, 41, 40, 42, 43, 44, 43, 45, 47, 48], flows: [-1, 0, 1, 1, 2, 2, 3, 2, 3, 4], note: "证券承担风险偏好/成交活跃度观察功能，不与银行、保险合并。"},
    {id: "tourism", label: "旅游", posture: "mixed", group: "消费周期", provider: "旅游及景区", symbol: "BK1272", identity: "industry", quality: "fixture", role: "watch", stage: "平台", pattern: "横向整理", flow: "流出", relative: "转弱", values: [52, 53, 52, 51, 50, 51, 49, 50, 48, 47, 48, 47], flows: [1, 0, 0, -1, -1, -2, -1, -2, -2, -3], note: "旅游为可选消费观察槽；不把旧自定义四股篮子直接当作行业序列。"},
  ];

  const LABELS = {
    attack: "进攻",
    defense: "防守",
    mixed: "混合",
    leader: "领先",
    improving: "改善",
    watch: "需确认",
    conditional_complete: "条件完整",
    partial: "partial",
    unknown: "unknown",
    fixture: "fixture",
  };

  const state = {filter: "all"};
  const $ = (id) => document.getElementById(id);

  function toneFor(sector) {
    return sector.role === "leader" ? "leader" : sector.role === "improving" ? "improving" : sector.quality === "partial" || sector.quality === "unknown" ? "unknown" : "weakening";
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));
  }

  function sparkline(values, tone = "improving", large = false) {
    const width = large ? 620 : 190;
    const height = large ? 170 : 48;
    const pad = large ? 16 : 5;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const points = values.map((value, index) => {
      const x = pad + index * ((width - pad * 2) / Math.max(1, values.length - 1));
      const y = height - pad - ((value - min) / span) * (height - pad * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    const color = tone === "leader" ? "#ff655f" : tone === "improving" ? "#ffb35c" : tone === "unknown" ? "#8e99aa" : "#a999ff";
    const grid = large ? [0.25, 0.5, 0.75].map((ratio) => `<line x1="${pad}" y1="${(height * ratio).toFixed(1)}" x2="${width - pad}" y2="${(height * ratio).toFixed(1)}" stroke="rgba(214,223,240,.10)"/>`).join("") : "";
    const dots = large ? points.map((point, index) => {
      const [x, y] = point.split(",");
      return `<circle cx="${x}" cy="${y}" r="2.4" fill="${color}"/>`;
    }).join("") : "";
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${large ? "示例 K 线形状" : "示例趋势"}">${grid}<polyline fill="none" stroke="${color}" stroke-width="${large ? 2.5 : 1.8}" points="${points.join(" ")}"/>${dots}</svg>`;
  }

  function candlestickChart(sector) {
    const width = 620;
    const height = 190;
    const pad = 18;
    const values = sector.values;
    const min = Math.min(...values) - 4;
    const max = Math.max(...values) + 4;
    const scaleY = (value) => height - pad - ((value - min) / (max - min || 1)) * (height - pad * 2);
    const step = (width - pad * 2) / values.length;
    const grid = [0.25, 0.5, 0.75].map((ratio) => `<line x1="${pad}" y1="${(height * ratio).toFixed(1)}" x2="${width - pad}" y2="${(height * ratio).toFixed(1)}" stroke="rgba(214,223,240,.10)"/>`).join("");
    const candles = values.map((close, index) => {
      const previous = index ? values[index - 1] : close - 1;
      const open = previous + (close - previous) * .35;
      const high = Math.max(open, close) + 1.4 + (index % 3) * .35;
      const low = Math.min(open, close) - 1.1 - (index % 2) * .25;
      const x = pad + index * step + step * .5;
      const yOpen = scaleY(open);
      const yClose = scaleY(close);
      const bodyY = Math.min(yOpen, yClose);
      const bodyH = Math.max(3, Math.abs(yOpen - yClose));
      const color = close >= open ? "#ff655f" : "#2dd4a8";
      return `<line x1="${x.toFixed(1)}" y1="${scaleY(high).toFixed(1)}" x2="${x.toFixed(1)}" y2="${scaleY(low).toFixed(1)}" stroke="${color}" stroke-width="1"/><rect x="${(x - step * .25).toFixed(1)}" y="${bodyY.toFixed(1)}" width="${(step * .5).toFixed(1)}" height="${bodyH.toFixed(1)}" fill="${color}" opacity=".85"/>`;
    }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(sector.label)} 示例 K 线图">${grid}${candles}</svg>`;
  }

  function flowBars(values) {
    const max = Math.max(...values.map((value) => Math.abs(value)), 1);
    return values.map((value) => {
      const height = Math.max(7, Math.round(Math.abs(value) / max * 67));
      return `<span class="flow-bar ${value < 0 ? "negative" : ""}" style="height:${height}px" title="${value > 0 ? "inflow" : value < 0 ? "outflow" : "flat"}"></span>`;
    }).join("");
  }

  function cardHtml(sector, index) {
    const tone = toneFor(sector);
    const quality = LABELS[sector.quality] || sector.quality;
    return `<button class="sector-card" type="button" data-sector-id="${sector.id}" data-posture="${sector.posture}" data-quality="${sector.quality}" aria-label="打开 ${escapeHtml(sector.label)} 证据">
      <span class="card-head"><span class="card-index">${String(index + 1).padStart(2, "0")}</span><span class="quality-pill" data-quality="${sector.quality}">${quality}</span></span>
      <span class="card-title">${escapeHtml(sector.label)}</span>
      <span class="card-meta">${escapeHtml(sector.group)} · ${escapeHtml(sector.posture === "attack" ? "进攻" : sector.posture === "defense" ? "防守" : "混合")}</span>
      <span class="card-sparkline">${sparkline(sector.values, tone)}</span>
      <span class="card-facts"><span class="card-fact"><span>K 线结构</span><strong>${escapeHtml(sector.pattern)}</strong></span><span class="card-fact"><span>资金状态</span><strong>${escapeHtml(sector.flow)}</strong></span></span>
      <span class="card-footer"><span>${escapeHtml(sector.stage)}</span><strong>${escapeHtml(sector.relative)}</strong></span>
    </button>`;
  }

  function renderCounts() {
    const counts = {attack: 0, defense: 0, mixed: 0, unknown: 0};
    SECTORS.forEach((sector) => {
      counts[sector.posture] += 1;
      if (sector.quality === "partial" || sector.quality === "unknown") counts.unknown += 1;
    });
    document.querySelectorAll("[data-filter]").forEach((button) => {
      const filter = button.dataset.filter;
      const value = filter === "all" ? SECTORS.length : filter === "unknown" ? counts.unknown : counts[filter];
      const span = button.querySelector("span");
      if (span) span.textContent = String(value);
    });
    $("leader-count").textContent = String(SECTORS.filter((sector) => sector.role === "leader").length);
    $("improving-count").textContent = String(SECTORS.filter((sector) => sector.role === "improving").length);
    $("unknown-count").textContent = String(counts.unknown);
    $("edge-count").textContent = "多对多";
  }

  function renderGrid() {
    const visible = SECTORS.filter((sector) => {
      if (state.filter === "all") return true;
      if (state.filter === "unknown") return sector.quality === "partial" || sector.quality === "unknown";
      return sector.posture === state.filter;
    });
    $("sector-grid").innerHTML = visible.map((sector) => cardHtml(sector, SECTORS.indexOf(sector))).join("");
    $("empty-state").hidden = visible.length > 0;
    document.querySelectorAll(".sector-card").forEach((card) => card.addEventListener("click", () => openEvidence(card.dataset.sectorId)));
  }

  function chipHtml(sector) {
    return `<button class="rotation-chip" type="button" data-sector-id="${sector.id}">${escapeHtml(sector.label)} <small>${escapeHtml(sector.quality === "partial" ? "unknown" : sector.relative)}</small></button>`;
  }

  function renderRotation() {
    const lists = {leader: $("leaders"), improving: $("improving"), watch: $("watching")};
    Object.values(lists).forEach((node) => { node.innerHTML = ""; });
    SECTORS.filter((sector) => sector.role === "leader").forEach((sector) => { lists.leader.insertAdjacentHTML("beforeend", chipHtml(sector)); });
    SECTORS.filter((sector) => sector.role === "improving").forEach((sector) => { lists.improving.insertAdjacentHTML("beforeend", chipHtml(sector)); });
    SECTORS.filter((sector) => sector.role === "watch").forEach((sector) => { lists.watch.insertAdjacentHTML("beforeend", chipHtml(sector)); });
    document.querySelectorAll(".rotation-chip").forEach((chip) => chip.addEventListener("click", () => openEvidence(chip.dataset.sectorId)));
  }

  function renderFilters() {
    document.querySelectorAll("[data-filter]").forEach((button) => {
      button.classList.toggle("active", button.dataset.filter === state.filter);
      button.addEventListener("click", () => {
        state.filter = button.dataset.filter;
        renderFilters();
        renderGrid();
      });
    });
  }

  function renderSummary(sector) {
    const entries = [
      ["阶段", sector.stage],
      ["形态证据", sector.pattern],
      ["资金状态", sector.flow],
      ["相对状态", sector.relative],
    ];
    $("evidence-summary").innerHTML = entries.map(([label, value]) => `<div class="summary-cell"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  }

  function renderLedger(sector) {
    const rows = [
      ["logical sector_id", sector.id],
      ["provider identity", `eastmoney:90.${sector.symbol}:${sector.identity}`],
      ["K 线状态", sector.quality === "partial" ? "unknown · 主路由待验证" : "fixture · not live"],
      ["资金流状态", sector.quality === "partial" ? "current snapshot only" : "fixture · not live"],
      ["as_of_trade_date", "FIXTURE / 未接实时"],
      ["quality", LABELS[sector.quality] || sector.quality],
    ];
    $("evidence-ledger").innerHTML = rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  }

  function openEvidence(id) {
    const sector = SECTORS.find((item) => item.id === id);
    if (!sector) return;
    $("evidence-title").textContent = sector.label;
    $("evidence-subtitle").textContent = `${sector.group} · ${sector.provider} · ${sector.symbol}`;
    $("evidence-kicker").textContent = `SECTOR EVIDENCE · ${LABELS[sector.quality] || sector.quality}`;
    $("chart-window").textContent = "形态示例 / 不代表真实行情";
    $("flow-window").textContent = "资金示例 / 不代表真实流量";
    $("evidence-chart").innerHTML = candlestickChart(sector);
    $("flow-bars").innerHTML = flowBars(sector.flows);
    renderSummary(sector);
    renderLedger(sector);
    $("evidence-note").textContent = `${sector.note} ${DEMO_NOTE}`;
    const dialog = $("evidence-dialog");
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeEvidence() {
    const dialog = $("evidence-dialog");
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function init() {
    renderCounts();
    renderRotation();
    renderFilters();
    renderGrid();
    $("close-dialog").addEventListener("click", closeEvidence);
    $("evidence-dialog").addEventListener("click", (event) => {
      if (event.target === $("evidence-dialog")) closeEvidence();
    });
    $("reset-button").addEventListener("click", () => {
      state.filter = "all";
      renderFilters();
      renderGrid();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
