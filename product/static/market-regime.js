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
    busy: "等待发布锁",
    running: "刷新中",
    failed: "上轮失败",
    interrupted: "上轮中断",
    stopped: "已停止",
    closed: "休市",
  };

  const TREND_NAMES = {
    strong_up: "强势上行",
    up: "上行",
    flat: "横盘",
    down: "下行",
    strong_down: "强势下行",
  };

  const SESSION_NAMES = {
    pre: "盘前",
    open: "交易中",
    lunch_break: "午休",
    post: "盘后",
    maintenance: "维护时段",
    closed: "休市",
    unknown: "时段未知",
  };

  const ASSET_LABELS = {
    sp500_cash: {name: "S&P 500 Cash", tag: "CASH · ^GSPC"},
    nasdaq_cash: {name: "Nasdaq Composite Cash", tag: "CASH · ^IXIC"},
    sp500_futures_proxy: {name: "S&P 500 Futures Proxy", tag: "PROXY · ES=F"},
    nasdaq100_futures_proxy: {name: "Nasdaq-100 Futures Proxy", tag: "PROXY · NQ=F"},
    wti: {name: "WTI Continuous", tag: "FUTURE · CL=F"},
    gold: {name: "Gold Continuous", tag: "FUTURE · GC=F"},
    silver: {name: "Silver Continuous", tag: "FUTURE · SI=F"},
    kospi: {name: "KOSPI Cash", tag: "CASH · ^KS11"},
    nikkei: {name: "Nikkei 225 Cash", tag: "CASH · ^N225"},
    vix: {name: "VIX Cash", tag: "CASH · ^VIX"},
    us_dividend: {name: "US Dividend ETF", tag: "ETF · SCHD"},
    shanghai: {name: "上证指数 Cash", tag: "CASH · 000001.SH"},
    star50: {name: "科创 50 Cash", tag: "CASH · 000688.SH"},
    china_dividend: {name: "上证红利 Cash", tag: "CASH · 000015.SH"},
  };

  const A_SHARE_INTRADAY_KEYS = new Set(["shanghai", "star50", "china_dividend"]);

  const RELATION_VIEWS = {
    confirms: {
      label: "确认日线结构",
      copy: "A股可用盘中证据与冻结的日线结构同向；这是一致性判断，不是涨跌预测。",
    },
    diverges: {
      label: "背离日线结构",
      copy: "A股可用盘中证据与冻结的日线结构反向；先观察背离是否持续，不据此自动行动。",
    },
    insufficient: {
      label: "证据不足",
      copy: "缺少可用时段、关键A股身份或连续确认，因此不判定确认或背离。",
    },
    closed: {
      label: "A股已休市",
      copy: "A股依赖均处于已知非交易时段；休市不是转弱，也不会被标记为当前行情。",
    },
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

  function shortId(value, size = 12) {
    if (!value) return "—";
    const textValue = String(value);
    const digest = textValue.includes(":") ? textValue.split(":").at(-1) : textValue;
    return digest.length > size ? `${digest.slice(0, size)}…` : digest;
  }

  function ageLabel(value) {
    if (!value) return "AGE —";
    const timestamp = new Date(value).getTime();
    if (!Number.isFinite(timestamp)) return "AGE UNKNOWN";
    const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (seconds < 60) return `AGE ${seconds}S`;
    if (seconds < 3600) return `AGE ${Math.floor(seconds / 60)}M`;
    if (seconds < 86400) return `AGE ${Math.floor(seconds / 3600)}H`;
    return `AGE ${Math.floor(seconds / 86400)}D`;
  }

  function compactValue(value) {
    if (value == null || value === "") return "—";
    if (Array.isArray(value)) return value.length ? value.join(", ") : "无";
    if (typeof value === "object") {
      return Object.entries(value)
        .map(([key, item]) => `${key}:${item}`)
        .join(" · ");
    }
    return String(value);
  }

  function freshnessView(asset) {
    const session = String(asset.session_state || "unknown");
    const freshness = String(asset.freshness || "unavailable");
    const providerTime = new Date(asset.provider_timestamp || 0).getTime();
    const ageSeconds = Number.isFinite(providerTime)
      ? Math.max(0, Math.floor((Date.now() - providerTime) / 1000))
      : Number.POSITIVE_INFINITY;
    if (asset.refresh_status === "rejected" || freshness === "unavailable") {
      return {
        state: freshness === "unavailable" ? "unavailable" : "delayed",
        label: asset.refresh_status === "rejected" ? "刷新失败 · 保留旧证据" : "证据不可用",
      };
    }
    if (session !== "open") {
      return {state: session === "unknown" ? "unknown" : "closed", label: SESSION_NAMES[session] || session};
    }
    if (freshness === "live_candidate" && ageSeconds <= 15 * 60) {
      return {state: "current", label: "CURRENT ≤15M"};
    }
    if (freshness === "stale") return {state: "delayed", label: "STALE"};
    return {state: "delayed", label: "DELAYED"};
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

  function renderOverlay(bundle) {
    const overlay = bundle.overlay || {};
    const intraday = bundle.intraday || {};
    const relation = String(overlay.relation || "insufficient");
    const view = RELATION_VIEWS[relation] || RELATION_VIEWS.insufficient;
    const aShare = overlay.a_share_tape || {};
    const assets = Array.isArray(intraday.assets) ? intraday.assets : [];
    const providerTimes = assets
      .map((asset) => asset.provider_timestamp)
      .filter(Boolean)
      .map((value) => new Date(value))
      .filter((value) => !Number.isNaN(value.getTime()));
    const newestProvider = providerTimes.length
      ? new Date(Math.max(...providerTimes.map((value) => value.getTime()))).toISOString()
      : null;
    const sessions = [...new Set(Object.values(aShare.session_states || {}))];
    const sessionText = sessions.length
      ? sessions.map((session) => SESSION_NAMES[session] || session).join(" / ")
      : "时段未知";

    const aShareAssets = assets.filter((asset) => A_SHARE_INTRADAY_KEYS.has(asset.instrument?.key));
    const aShareStates = aShareAssets.map(freshnessView);
    const aShareIsCurrent = aShareAssets.length === A_SHARE_INTRADAY_KEYS.size &&
      aShareStates.every((item) => item.state === "current");
    const recordedRelationIsHistoric = ["confirms", "diverges"].includes(relation) && !aShareIsCurrent;
    const displayedLabel = recordedRelationIsHistoric ? `上次${view.label}` : view.label;
    const displayedCopy = recordedRelationIsHistoric
      ? `这是 ${dateTime(overlay.generated_at)} 已验证 overlay 的历史关系；A股盘中证据已超过 15 分钟，不代表当前盘面。`
      : view.copy;
    const displayedSession = relation === "closed"
      ? "A股 · 休市"
      : sessions.includes("open")
        ? `A股 · 交易中 · ${aShareIsCurrent ? "CURRENT ≤15M" : "数据延迟"}`
        : `A股 · ${sessionText}`;

    $("overlay-card").dataset.relation = relation;
    $("overlay-card").dataset.current = aShareIsCurrent ? "true" : "false";
    text("overlay-relation", displayedLabel);
    text("overlay-copy", displayedCopy);
    text("overlay-session", displayedSession);
    text("overlay-a-score", signed(aShare.impulse_score));
    text("overlay-cross-score", signed(overlay.cross_asset?.score));
    text("overlay-provider-time", dateTime(newestProvider));
    text("overlay-generated", `OVERLAY ${dateTime(overlay.generated_at)} · ${ageLabel(overlay.generated_at)}`);
    text(
      "overlay-quality",
      `${String(intraday.quality || "unknown").toUpperCase()} · ${intraday.accepted_count ?? 0}/14 ACCEPTED`
    );
    text(
      "top-quality",
      `${String(intraday.quality || "unknown").toUpperCase()} ${intraday.accepted_count ?? 0}/14 · ${displayedLabel}`
    );
    const dot = $("top-state-dot");
    if (dot) {
      dot.dataset.state = relation === "closed"
        ? "closed"
        : relation === "insufficient" || intraday.quality !== "complete"
          ? "degraded"
          : aShareIsCurrent
            ? "current"
            : "degraded";
    }
  }

  function renderChange(bundle) {
    const overlay = bundle.overlay || {};
    const receipt = bundle.material_change_receipt || {};
    const change = receipt.change || overlay.material_change || {};
    const relation = String(overlay.relation || "insufficient");
    const previous = receipt.previous_overlay_id || overlay.baseline_overlay_id;
    const material = change.is_material === true;
    let title = "没有可比较的上一份盘中层";
    let copy = "这是第一份已验证 overlay；不会把首次出现误写成市场发生了变化。";
    if (previous) {
      if (relation === "closed") {
        title = "A股进入已知非交易时段";
        copy = "本轮相对上一份成功 overlay 只确认休市状态；休市不代表风险偏好转弱。";
      } else if (relation === "insufficient") {
        title = "关键盘中证据暂不足";
        copy = "当前无法复验确认或背离；页面保留上一份基线身份，但不延用它的结论。";
      } else if (relation === "diverges") {
        title = material ? "A股背离达到实质变化门槛" : "A股出现背离，尚未达到实质变化门槛";
        copy = "背离来自可验证市场信号与冻结日线结构的方向比较，不是新闻原因或交易指令。";
      } else {
        title = material ? "A股确认达到实质变化门槛" : "A股仍在确认结构，未达到实质变化门槛";
        copy = "确认仅表示盘中证据与日线结构同向；阈值、连续性和冷却状态仍然有效。";
      }
    }
    $("change-card").dataset.material = material ? "true" : "false";
    text("change-state", material ? "MATERIAL CHANGE" : "NO MATERIAL CHANGE");
    text("change-title", title);
    text("change-copy", copy);
    text("change-a-delta", `A股 Δ ${signed(change.a_share_score_delta)}`);
    text("change-cross-delta", `跨资产 Δ ${signed(change.cross_asset_score_delta)}`);
    text("change-baseline", `BASELINE ${shortId(previous, 18)}`);
  }

  function renderDrivers(bundle) {
    const host = $("top-contributions");
    const rows = (bundle.overlay?.top_drivers || []).slice(0, 3);
    host.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "empty-copy";
      empty.textContent = "当前没有达到可展示条件的市场信号；不会补写新闻原因。";
      host.append(empty);
      return;
    }
    rows.forEach((row) => {
      const identity = ASSET_LABELS[row.instrument] || {name: row.instrument, tag: "SIGNAL"};
      const item = document.createElement("div");
      item.className = "driver-row";
      item.title = `${row.evidence_id || ""} · ${row.normalized_artifact_sha256 || ""}`;
      const main = document.createElement("div");
      main.className = "driver-main";
      const name = document.createElement("strong");
      name.textContent = identity.name;
      const value = document.createElement("span");
      value.textContent = signed(row.contribution, 2);
      main.append(name, value);
      const meta = document.createElement("small");
      meta.textContent = `${identity.tag} · ${dateTime(row.provider_timestamp)} · EVIDENCE ${shortId(row.evidence_id, 10)}`;
      item.append(main, meta);
      host.append(item);
    });
  }

  function renderWatchConditions(bundle) {
    const host = $("watch-conditions");
    const rows = (bundle.overlay?.watch_conditions || []).slice(0, 2);
    const evidence = shortId(bundle.intraday_snapshot_id, 10);
    host.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "empty-copy";
      empty.textContent = "当前 overlay 没有可验证的观察条件。";
      host.append(empty);
      return;
    }
    rows.forEach((row, index) => {
      const item = document.createElement("div");
      item.className = "watch-row";
      const main = document.createElement("div");
      main.className = "watch-main";
      const name = document.createElement("strong");
      name.textContent = `${String(index + 1).padStart(2, "0")} ${String(row.code || "condition").replaceAll("_", " ").toUpperCase()}`;
      const threshold = document.createElement("small");
      threshold.textContent = `阈值 ${compactValue(row.threshold)}`;
      main.append(name, threshold);
      const condition = document.createElement("p");
      condition.textContent = row.condition || "条件说明不可用";
      const meta = document.createElement("small");
      meta.textContent = `当前 ${compactValue(row.current)} · SNAPSHOT ${evidence}`;
      item.append(main, condition, meta);
      host.append(item);
    });
  }

  function renderFreshness(bundle, health) {
    const host = $("intraday-assets");
    const assets = Array.isArray(bundle.intraday?.assets) ? bundle.intraday.assets : [];
    host.replaceChildren();
    const stateCounts = {};
    assets.forEach((asset) => {
      const key = asset.instrument?.key || "unknown";
      const identity = ASSET_LABELS[key] || {
        name: asset.instrument?.display_name || key,
        tag: asset.instrument?.canonical_symbol || "UNKNOWN",
      };
      const freshness = freshnessView(asset);
      stateCounts[freshness.state] = (stateCounts[freshness.state] || 0) + 1;
      const card = document.createElement("article");
      card.className = "freshness-card";
      card.dataset.asset = key;
      card.dataset.state = freshness.state;
      card.title = `${asset.evidence?.sha256 || "NO EVIDENCE HASH"}`;
      const header = document.createElement("header");
      const name = document.createElement("h3");
      name.textContent = identity.name;
      const tag = document.createElement("span");
      tag.className = "identity-tag";
      tag.textContent = identity.tag;
      header.append(name, tag);
      const status = document.createElement("div");
      status.className = "freshness-state";
      status.textContent = `${freshness.label} · ${SESSION_NAMES[asset.session_state] || asset.session_state || "未知"}`;
      const footer = document.createElement("footer");
      const provider = document.createElement("span");
      provider.textContent = `PROVIDER ${dateTime(asset.provider_timestamp)}`;
      const age = document.createElement("span");
      age.textContent = ageLabel(asset.provider_timestamp);
      footer.append(provider, age);
      card.append(header, status, footer);
      host.append(card);
    });
    const layer = health?.latest?.layers?.intraday || {};
    const sessions = Object.entries(layer.session_counts || {})
      .map(([key, count]) => `${SESSION_NAMES[key] || key} ${count}`)
      .join(" · ");
    const errors = Array.isArray(layer.errors) ? layer.errors.length : 0;
    const freshnessCounts = [
      stateCounts.current ? `CURRENT ${stateCounts.current}` : null,
      stateCounts.delayed ? `DELAYED ${stateCounts.delayed}` : null,
      stateCounts.closed ? `CLOSED ${stateCounts.closed}` : null,
      stateCounts.unavailable ? `UNAVAILABLE ${stateCounts.unavailable}` : null,
      stateCounts.unknown ? `UNKNOWN ${stateCounts.unknown}` : null,
    ].filter(Boolean).join(" · ");
    text(
      "freshness-summary",
      `${assets.length}/14 IDENTITIES · ${sessions || "SESSION UNKNOWN"}${freshnessCounts ? ` · ${freshnessCounts}` : ""}${errors ? ` · ${errors} ERROR` : ""}`
    );
  }

  function renderLiveLayer(bundle, health) {
    renderOverlay(bundle);
    renderChange(bundle);
    renderDrivers(bundle);
    renderWatchConditions(bundle);
    renderFreshness(bundle, health);
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
    const intradayScheduler = health?.intraday_scheduler || {};
    const next = intradayScheduler.next_due_at;
    const intradayState = STATE_NAMES[intradayScheduler.state] || intradayScheduler.state || "不可用";
    text("top-schedule", `${intradayScheduler.interval_minutes || 15}M TARGET · ${intradayState}`);
    text(
      "next-due",
      next
        ? `盘中下一目标 ${dateTime(next)}（北京时间）`
        : `盘中尚未记录下一目标；日线下一轮 ${dateTime(scheduler.next_due_at)}`
    );
    text("runtime-interval", `${intradayScheduler.interval_minutes || 15} 分钟目标`);
    text("runtime-success", dateTime(intradayScheduler.last_success_at));
    text("runtime-state", intradayState);
    text("runtime-quality", String(bundle.intraday?.quality || "unknown").toUpperCase());
    text("structural-runtime-interval", `${scheduler.interval_hours || "—"} 小时`);
    text("structural-runtime-success", dateTime(scheduler.last_success_at));
    const dot = $("top-state-dot");
    if (dot && ["failed", "interrupted", "stopped"].includes(intradayScheduler.state)) {
      dot.dataset.state = intradayScheduler.state;
    }
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
    renderLiveLayer(bundle, health);
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
    text("hero-deck", "页面没有拿到通过校验的本地行情包，因此不会用演示数据伪装当前市场。请检查本机服务后重试。");
    $("top-state-dot").dataset.state = "failed";
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

  async function load({silent = false} = {}) {
    const button = $("reload-button");
    if (!silent) {
      button.classList.add("loading");
      button.disabled = true;
    }
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
      if (silent && state.bundle) {
        $("top-state-dot").dataset.state = "failed";
        text("top-quality", "本地读取失败 · 保留上次已验证成果");
      } else {
        showError(error);
      }
    } finally {
      if (!silent) {
        button.classList.remove("loading");
        button.disabled = false;
      }
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
  window.setInterval(() => load({silent: true}), 60_000);
})();
