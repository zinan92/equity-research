(() => {
  "use strict";

  const GROUPS = {
    "group-us": ["sp500", "nasdaq"],
    "group-china": ["shanghai", "star50"],
    "group-commodities": ["wti", "gold", "silver"],
    "group-asia": ["kospi", "nikkei"],
  };

  const GROUP_NAMES = {
    us_equities: "美股",
    a_equities: "A 股",
    asia_ex_china: "亚洲（除中国）",
    energy: "能源",
    precious_metals: "贵金属",
  };

  const STATE_NAMES = {
    leader: "主线明确",
    contested: "领导权争夺",
    none: "暂无主线",
    unknown: "证据不足",
    full: "完整",
    partial: "部分",
    unavailable: "不可用",
    idle: "等待下一轮",
    running: "刷新中",
    failed: "上轮失败",
    interrupted: "上轮中断",
  };

  const TREND_NAMES = {
    strong_up: "强势上行",
    up: "上行",
    flat: "横盘",
    down: "下行",
    strong_down: "强势下行",
  };

  const state = {
    bundle: null,
    health: null,
    range: 66,
    charts: new Map(),
    observer: null,
  };

  const $ = (id) => document.getElementById(id);

  function text(id, value) {
    const node = $(id);
    if (node) node.textContent = value ?? "—";
  }

  function numeric(value, digits = 1) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return number.toLocaleString("zh-CN", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function signed(value, digits = 1, suffix = "") {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return `${number > 0 ? "+" : ""}${numeric(number, digits)}${suffix}`;
  }

  function dateTime(value, options = {}) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      ...options,
    }).format(parsed);
  }

  function sessionDate(value) {
    if (!value) return "—";
    const parts = String(value).split("-");
    return parts.length === 3 ? `${parts[1]}/${parts[2]}` : String(value);
  }

  function tone(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number === 0) return "";
    return number > 0 ? "positive" : "negative";
  }

  function scoreColor(score, type = "risk") {
    const value = Number(score);
    if (!Number.isFinite(value)) return "#6d7585";
    if (type === "style") return value >= 0 ? "#64a8ff" : "#ffb35c";
    return value >= 0 ? "#ff655f" : "#2dd4a8";
  }

  function renderAxis(id, score) {
    const bar = $(id);
    const number = Math.max(-100, Math.min(100, Number(score) || 0));
    if (number >= 0) {
      bar.style.left = "50%";
      bar.style.width = `${number / 2}%`;
    } else {
      bar.style.left = `${50 + number / 2}%`;
      bar.style.width = `${Math.abs(number) / 2}%`;
    }
  }

  function renderDimension(key, dimension) {
    const card = document.querySelector(`[data-dimension="${key}"]`);
    const score = dimension?.score;
    text(`signal-${key}-label`, dimension?.label_zh || "证据不足");
    text(`signal-${key}-score`, Number.isFinite(Number(score)) ? signed(score) : "N/A");
    const color = scoreColor(score, key);
    card?.style.setProperty("--signal-color", color);
    renderAxis(`signal-${key}-axis`, score);
  }

  function renderLeadershipSignal(leadership) {
    const card = document.querySelector('[data-dimension="leadership"]');
    const ranking = leadership?.ranking || [];
    const top = ranking[0];
    const leader = leadership?.leader;
    const label = leader
      ? `${GROUP_NAMES[leader] || leader}领先`
      : STATE_NAMES[leadership?.state] || "证据不足";
    text("signal-leadership-label", label);
    text("signal-leadership-score", top ? signed(top.score) : "N/A");
    card?.style.setProperty("--signal-color", "#a999ff");
    renderAxis("signal-leadership-axis", top?.score);
  }

  function renderHero(bundle) {
    const analysis = bundle.analysis || {};
    const dimensions = analysis.dimensions || {};
    const explanation = analysis.what_is_going_on || {};
    const risk = dimensions.risk || {};
    const riskScore = Number(risk.score);

    text("hero-headline", explanation.headline || "证据不足，暂不下结论");
    text(
      "hero-deck",
      [explanation.confirmation, explanation.rotation].filter(Boolean).join(" ") ||
        "当前没有足够证据形成完整判断。"
    );
    text("verdict-date", `VERDICT AS OF ${dateTime(bundle.verdict_as_of)}`);
    text("risk-score", Number.isFinite(riskScore) ? signed(riskScore) : "N/A");
    text("risk-label", risk.label_zh || "证据不足");
    text("confidence-value", `${numeric((analysis.confidence?.score || 0) * 100, 0)}% · ${String(analysis.confidence?.level || "—").toUpperCase()}`);
    text("analysis-status", STATE_NAMES[bundle.analysis_status] || bundle.analysis_status || "—");
    text("close-skew", Number.isFinite(Number(analysis.cross_market_close_skew_hours)) ? `${numeric(analysis.cross_market_close_skew_hours)}H` : "—");
    $("risk-marker").style.left = `${50 + Math.max(-100, Math.min(100, riskScore || 0)) / 2}%`;

    text("data-kind-tag", `${String(bundle.data_kind || "unknown").toUpperCase()} SNAPSHOT`);
    text("review-tag", "MODEL · UNREVIEWED");
    text("advice-tag", bundle.truth_boundary?.not_investment_advice ? "NOT INVESTMENT ADVICE" : "BOUNDARY UNKNOWN");
    text("top-quality", `${String(bundle.data_quality || "unknown").toUpperCase()} · ${bundle.charts?.length || 0}/9 CHARTS`);

    renderDimension("risk", dimensions.risk);
    renderDimension("posture", dimensions.posture);
    renderDimension("style", dimensions.style);
    renderLeadershipSignal(dimensions.leadership);

    text("scenario-code", String(analysis.scenario?.code || "unknown").replaceAll("_", " ").toUpperCase());
    text("story-confirmation", explanation.confirmation);
    text("story-rotation", explanation.rotation);
    text("story-divergence", explanation.divergence);
    text("story-invalidation", explanation.invalidation);
  }

  function renderLeadership(leadership) {
    const host = $("leadership-bars");
    const ranking = leadership?.ranking || [];
    host.replaceChildren();
    text("leadership-state", STATE_NAMES[leadership?.state] || leadership?.state || "证据不足");
    if (!ranking.length) {
      const empty = document.createElement("p");
      empty.className = "empty-copy";
      empty.textContent = "领导力证据不足。";
      host.append(empty);
      return;
    }
    ranking.forEach((row, index) => {
      const score = Math.max(-100, Math.min(100, Number(row.score) || 0));
      const item = document.createElement("div");
      item.className = "leadership-row";

      const name = document.createElement("span");
      name.className = "leadership-name";
      name.textContent = `${String(index + 1).padStart(2, "0")} ${GROUP_NAMES[row.group] || row.group}`;

      const track = document.createElement("div");
      track.className = "leadership-track";
      const fill = document.createElement("span");
      fill.className = "leadership-fill";
      fill.style.setProperty("--bar-color", index === 0 ? "#ffb35c" : score >= 0 ? "#64a8ff" : "#2dd4a8");
      if (score >= 0) {
        fill.style.left = "50%";
        fill.style.width = `${score / 2}%`;
      } else {
        fill.style.left = `${50 + score / 2}%`;
        fill.style.width = `${Math.abs(score) / 2}%`;
      }
      track.append(fill);

      const value = document.createElement("span");
      value.className = "leadership-score";
      value.textContent = signed(score);
      item.append(name, track, value);
      host.append(item);
    });
  }

  function featureMap(bundle) {
    return new Map((bundle.analysis?.asset_features || []).map((item) => [item.key, item]));
  }

  function renderProbes(bundle) {
    const features = featureMap(bundle);
    const host = $("probe-cards");
    host.replaceChildren();
    (bundle.probes || []).forEach((probe) => {
      const key = probe.instrument?.key;
      const feature = features.get(key);
      const card = document.createElement("article");
      card.className = "probe-card";
      const name = document.createElement("span");
      name.textContent = probe.instrument?.display_name || key || "未知探针";
      const price = document.createElement("strong");
      price.textContent = feature ? numeric(feature.close, 2) : "N/A";
      const move = document.createElement("small");
      const return20 = feature?.returns?.["20d"];
      move.className = tone(return20);
      move.textContent = feature
        ? `20D ${signed(return20, 1, "%")} · TREND ${signed(feature.trend_score)}`
        : `${String(probe.quality || "unavailable").toUpperCase()} · 暂不参与判断`;
      card.append(name, price, move);
      host.append(card);
    });
  }

  function movingAverage(bars, windowSize) {
    let sum = 0;
    return bars.map((bar, index) => {
      sum += Number(bar.close);
      if (index >= windowSize) sum -= Number(bars[index - windowSize].close);
      return index >= windowSize - 1 ? sum / windowSize : null;
    });
  }

  function chartPrice(value, key) {
    const digits = ["sp500", "nasdaq", "shanghai", "star50", "kospi", "nikkei"].includes(key) ? 1 : 2;
    return numeric(value, digits);
  }

  function createChartCard(chart, feature) {
    const key = chart.instrument?.key || "unknown";
    const card = document.createElement("article");
    card.className = `chart-card ${chart.quality === "unavailable" ? "unavailable" : ""}`;
    card.dataset.key = key;

    const header = document.createElement("header");
    header.className = "chart-header";
    const title = document.createElement("div");
    title.className = "chart-title";
    const heading = document.createElement("h4");
    heading.textContent = chart.instrument?.display_name || key;
    const symbol = document.createElement("span");
    symbol.className = "chart-symbol";
    symbol.textContent = chart.instrument?.canonical_symbol || chart.instrument?.provider_symbol || "—";
    title.append(heading, symbol);

    const price = document.createElement("strong");
    price.className = "chart-price";
    price.textContent = feature ? chartPrice(feature.close, key) : "N/A";

    const metrics = document.createElement("div");
    metrics.className = "chart-metrics";
    const oneDay = feature?.returns?.["1d"];
    const twentyDay = feature?.returns?.["20d"];
    metrics.innerHTML = [
      `<span class="${tone(oneDay)}">1D ${signed(oneDay, 1, "%")}</span>`,
      `<span class="${tone(twentyDay)}">20D ${signed(twentyDay, 1, "%")}</span>`,
      `<span>TREND ${feature ? signed(feature.trend_score) : "—"}</span>`,
      `<span class="quality-pill ${chart.quality || "unavailable"}">${chart.refresh_failure ? "REFRESH FAILED" : chart.quality || "unavailable"}</span>`,
    ].join("");
    header.append(title, price, metrics);

    const body = document.createElement("div");
    const bars = Array.isArray(chart.bars) ? chart.bars : [];
    if (bars.length) {
      body.className = "chart-canvas-wrap";
      const canvas = document.createElement("canvas");
      canvas.tabIndex = 0;
      canvas.setAttribute(
        "aria-label",
        `${chart.instrument?.display_name || key} 日 K 线，最后完成交易日 ${chart.last_completed_session || "未知"}`
      );
      body.append(canvas);
      state.charts.set(key, {
        key,
        canvas,
        bars,
        ma20: movingAverage(bars, 20),
        ma60: movingAverage(bars, 60),
        hoverIndex: null,
      });
      bindChartPointer(state.charts.get(key));
      state.observer?.observe(canvas);
    } else {
      body.className = "chart-empty";
      body.textContent = chart.refresh_failure?.reason || "当前没有可验证的完整日线，不以旧图伪装最新行情。";
    }

    const footer = document.createElement("footer");
    footer.className = "chart-footer";
    const legend = document.createElement("span");
    legend.className = "chart-legend";
    legend.innerHTML = '<span class="legend-item legend-ma20">MA20</span><span class="legend-item legend-ma60">MA60</span>';
    const session = document.createElement("span");
    session.textContent = `SESSION ${chart.last_completed_session || "—"}`;
    footer.append(legend, session);
    card.append(header, body, footer);
    return card;
  }

  function renderCharts(bundle) {
    state.charts.forEach((chart) => state.observer?.unobserve(chart.canvas));
    state.charts.clear();
    const charts = new Map((bundle.charts || []).map((item) => [item.instrument?.key, item]));
    const features = featureMap(bundle);
    Object.entries(GROUPS).forEach(([hostId, keys]) => {
      const host = $(hostId);
      host.replaceChildren();
      keys.forEach((key) => {
        const chart = charts.get(key) || {
          instrument: {key, display_name: key},
          quality: "unavailable",
          bars: [],
          refresh_failure: {reason: "API bundle 缺少这个市场，页面已降级。"},
        };
        host.append(createChartCard(chart, features.get(key)));
      });
    });
    requestAnimationFrame(redrawAll);
  }

  function drawChart(chart) {
    const canvas = chart.canvas;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(280, rect.width);
    const height = Math.max(220, rect.height);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const count = Math.min(state.range, chart.bars.length);
    const start = chart.bars.length - count;
    const bars = chart.bars.slice(start);
    const ma20 = chart.ma20.slice(start);
    const ma60 = chart.ma60.slice(start);
    const pad = {top: 15, right: 54, bottom: 28, left: 12};
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const values = [];
    bars.forEach((bar, index) => {
      values.push(Number(bar.high), Number(bar.low));
      if (ma20[index] != null) values.push(ma20[index]);
      if (ma60[index] != null) values.push(ma60[index]);
    });
    let low = Math.min(...values);
    let high = Math.max(...values);
    const padding = Math.max((high - low) * 0.08, Math.abs(high) * 0.004, 0.01);
    low -= padding;
    high += padding;
    const y = (value) => pad.top + ((high - value) / (high - low || 1)) * plotHeight;

    ctx.font = '9px "SFMono-Regular", Consolas, monospace';
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (let index = 0; index <= 4; index += 1) {
      const py = pad.top + (plotHeight / 4) * index;
      ctx.strokeStyle = "rgba(214,223,240,0.08)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad.left, Math.round(py) + 0.5);
      ctx.lineTo(width - pad.right, Math.round(py) + 0.5);
      ctx.stroke();
      const value = high - ((high - low) / 4) * index;
      ctx.fillStyle = "#6d7585";
      ctx.fillText(chartPrice(value, chart.key), width - pad.right + 8, py);
    }

    const step = plotWidth / Math.max(bars.length, 1);
    const candleWidth = Math.max(1.5, Math.min(8, step * 0.58));
    bars.forEach((bar, index) => {
      const x = pad.left + step * (index + 0.5);
      const open = Number(bar.open);
      const close = Number(bar.close);
      const isUp = close >= open;
      ctx.strokeStyle = isUp ? "#ff655f" : "#2dd4a8";
      ctx.fillStyle = isUp ? "rgba(255,101,95,0.84)" : "rgba(45,212,168,0.82)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + 0.5, y(Number(bar.high)));
      ctx.lineTo(Math.round(x) + 0.5, y(Number(bar.low)));
      ctx.stroke();
      const bodyTop = Math.min(y(open), y(close));
      const bodyHeight = Math.max(1, Math.abs(y(open) - y(close)));
      ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    });

    const line = (series, color) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      let started = false;
      series.forEach((value, index) => {
        if (value == null) return;
        const x = pad.left + step * (index + 0.5);
        if (!started) {
          ctx.moveTo(x, y(value));
          started = true;
        } else {
          ctx.lineTo(x, y(value));
        }
      });
      if (started) ctx.stroke();
    };
    line(ma20, "rgba(255,179,92,0.9)");
    line(ma60, "rgba(169,153,255,0.82)");

    const dateIndexes = [0, Math.floor((bars.length - 1) / 2), bars.length - 1];
    ctx.fillStyle = "#6d7585";
    ctx.textBaseline = "bottom";
    dateIndexes.forEach((index, labelIndex) => {
      if (!bars[index]) return;
      const x = pad.left + step * (index + 0.5);
      ctx.textAlign = labelIndex === 0 ? "left" : labelIndex === 2 ? "right" : "center";
      ctx.fillText(sessionDate(bars[index].date), x, height - 4);
    });

    if (chart.hoverIndex != null && bars[chart.hoverIndex]) {
      const x = pad.left + step * (chart.hoverIndex + 0.5);
      ctx.strokeStyle = "rgba(241,243,247,0.36)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, pad.top + plotHeight);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    chart.rendered = {bars, start, pad, step, width, height};
  }

  function bindChartPointer(chart) {
    const canvas = chart.canvas;
    const tooltip = $("chart-tooltip");
    canvas.addEventListener("pointermove", (event) => {
      if (!chart.rendered) return;
      const rect = canvas.getBoundingClientRect();
      const localX = event.clientX - rect.left;
      const {bars, pad, step} = chart.rendered;
      const index = Math.max(0, Math.min(bars.length - 1, Math.floor((localX - pad.left) / step)));
      chart.hoverIndex = index;
      const bar = bars[index];
      tooltip.innerHTML = [
        `<strong>${bar.date}</strong>`,
        `O ${chartPrice(bar.open, chart.key)} · H ${chartPrice(bar.high, chart.key)}`,
        `L ${chartPrice(bar.low, chart.key)} · C ${chartPrice(bar.close, chart.key)}`,
      ].join("<br>");
      tooltip.hidden = false;
      const left = Math.min(window.innerWidth - 200, event.clientX + 14);
      const top = Math.max(8, Math.min(window.innerHeight - 90, event.clientY - 24));
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
      drawChart(chart);
    });
    canvas.addEventListener("pointerleave", () => {
      chart.hoverIndex = null;
      tooltip.hidden = true;
      drawChart(chart);
    });
    canvas.addEventListener("blur", () => {
      chart.hoverIndex = null;
      tooltip.hidden = true;
      drawChart(chart);
    });
  }

  function redrawAll() {
    state.charts.forEach(drawChart);
  }

  function renderHealth(health, bundle) {
    const scheduler = health?.scheduler || {};
    const next = scheduler.next_due_at;
    text("top-schedule", `${scheduler.interval_hours || 4}H CYCLE`);
    text("next-due", next ? `${dateTime(next)}（北京时间）` : "尚未记录下一次运行");
    text("runtime-interval", `${scheduler.interval_hours || "—"} 小时`);
    text("runtime-success", dateTime(scheduler.last_success_at));
    text("runtime-state", STATE_NAMES[scheduler.state] || scheduler.state || "不可用");
    text("runtime-quality", String(bundle.data_quality || "unknown").toUpperCase());
  }

  function renderBoundary(bundle) {
    const boundary = bundle.license?.boundary;
    const judgment = bundle.truth_boundary?.judgment_state;
    text(
      "license-boundary",
      `${boundary || "行情授权状态未知"} ${judgment === "model_generated_unreviewed" ? "模型判断未经过人工复核，不构成投资建议。" : "判断边界未知。"}`
    );
    const id = bundle.bundle_id || "NO VERIFIED BUNDLE";
    text("snapshot-id", id);
    $("snapshot-id").title = id;
  }

  function render(bundle, health) {
    state.bundle = bundle;
    state.health = health;
    renderHero(bundle);
    renderLeadership(bundle.analysis?.dimensions?.leadership);
    renderProbes(bundle);
    renderCharts(bundle);
    renderHealth(health, bundle);
    renderBoundary(bundle);
    $("hero").classList.remove("loading-shell");
    $("hero").setAttribute("aria-busy", "false");
    $("error-banner").hidden = true;
    document.body.dataset.ready = "true";
    window.__MARKET_REGIME_STATE__ = {bundle, health};
    window.__MARKET_REGIME_READY__ = true;
  }

  function showError(error) {
    const message = error instanceof Error ? error.message : String(error);
    text("error-message", message || "请确认本地数据服务已启动。");
    $("error-banner").hidden = false;
    $("hero").classList.remove("loading-shell");
    $("hero").setAttribute("aria-busy", "false");
    text("hero-headline", "快照暂不可用");
    text("hero-deck", "页面没有拿到通过校验的本地行情包，因此不会用演示数据伪装实时市场。请检查本机服务后重试。");
    document.body.dataset.ready = "error";
    window.__MARKET_REGIME_READY__ = false;
  }

  async function fetchJson(url) {
    const response = await fetch(url, {headers: {Accept: "application/json"}, cache: "no-store"});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `${url} 返回 ${response.status}`);
    }
    return payload;
  }

  async function load() {
    const button = $("reload-button");
    button.classList.add("loading");
    button.disabled = true;
    try {
      const [bundle, healthResult] = await Promise.all([
        fetchJson("/api/market-regime"),
        fetchJson("/api/market-regime/health").catch((error) => ({
          scheduler: {state: "unavailable", interval_hours: 4},
          latest: {status: "unavailable", detail: error.message},
        })),
      ]);
      render(bundle, healthResult);
    } catch (error) {
      showError(error);
    } finally {
      button.classList.remove("loading");
      button.disabled = false;
    }
  }

  document.querySelectorAll("[data-range]").forEach((button) => {
    button.addEventListener("click", () => {
      state.range = Number(button.dataset.range) || 66;
      document.querySelectorAll("[data-range]").forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle("active", active);
        candidate.setAttribute("aria-pressed", active ? "true" : "false");
      });
      redrawAll();
    });
  });

  state.observer = new ResizeObserver((entries) => {
    entries.forEach((entry) => {
      const chart = [...state.charts.values()].find((item) => item.canvas === entry.target);
      if (chart) drawChart(chart);
    });
  });

  $("reload-button").addEventListener("click", load);
  $("error-retry").addEventListener("click", load);
  window.addEventListener("resize", redrawAll, {passive: true});
  load();
})();
