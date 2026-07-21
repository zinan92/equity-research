const state = { data: null, committee: null, history: [], refreshRuns: [], filter: "全部", activeView: "decision", reportOpener: null, reportPushed: false, auth: null };
const colors = ["#17332d", "#245346", "#35685a", "#497a6b", "#5d8c7d", "#739c90", "#8caaa0", "#a7bcb4"];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const formatWeight = (value) => `${Number(value).toFixed(0)}%`;
const formatScore = (value) => Number(value ?? 0).toFixed(1);
const statusLabel = {
  draft: "草稿待审",
  quality_passed: "数据已通过",
  approved: "Park 已批准",
  published: "已发布",
  blocked: "已阻断",
  invalidated: "批准已失效",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

async function fetchJson(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && state.auth?.csrf_token) headers.set("X-CSRF-Token", state.auth.csrf_token);
  const response = await fetch(url, { cache: "no-store", credentials: "same-origin", ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || payload.error || `API ${response.status}`);
    error.code = payload.error || "api_error";
    error.status = response.status;
    throw error;
  }
  return payload;
}

function showAuth(mode = "login") {
  const login = mode === "login";
  $("#auth-gate").hidden = false;
  $("#login-form").hidden = !login;
  $("#signup-form").hidden = login;
  $("#auth-login-tab").classList.toggle("is-active", login);
  $("#auth-signup-tab").classList.toggle("is-active", !login);
  $("#auth-error").textContent = "";
  document.body.style.overflow = "hidden";
}

function applyAuth(payload) {
  state.auth = payload;
  if (payload.auth_required && !payload.member) {
    showAuth();
    return false;
  }
  $("#auth-gate").hidden = true;
  document.body.style.overflow = "";
  const member = payload.member || { display_name: "Park", tier: "local" };
  $("#member-name").textContent = member.display_name;
  $("#member-tier").textContent = ({ owner: "Owner", paid: "付费会员", member: "研究会员", preview: "预览会员", local: "本地模式" })[member.tier] || member.tier;
  $("#member-chip").querySelector(".avatar").textContent = member.display_name.slice(0, 1).toUpperCase();
  $("#logout-button").hidden = !payload.auth_required;
  const entitlements = member.entitlements || ["approve_publication", "manage_members"];
  $("#refresh-button").hidden = !entitlements.includes("manage_members");
  return true;
}

async function submitAuth(form, route) {
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  $("#auth-error").textContent = "";
  try {
    const payload = Object.fromEntries(new FormData(form).entries());
    const auth = await fetchJson(route, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    applyAuth(auth);
    form.reset();
    await loadDashboard();
    const reportTicker = new URLSearchParams(location.search).get("report");
    if (reportTicker) await openResearchReport(reportTicker, { syncHistory: false });
  } catch (error) {
    $("#auth-error").textContent = error.code === "invalid_credentials" ? "邮箱或密码不正确。" : `无法进入：${error.message}`;
  } finally {
    button.disabled = false;
  }
}

function formatBeijingTime(value) {
  if (!value) return "运行中";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(date).replaceAll("/", "-")} 北京时间`;
}

function refreshErrorLabel(run) {
  const text = String(run.error_summary || "");
  if (/SSL|URL|timeout|timed out|连接/i.test(text)) return "上游数据连接失败，已保留上一版";
  if (/coverage|quality|gate/i.test(text)) return "数据覆盖不足，质量门已阻断";
  if (/already running|in progress/i.test(text)) return "已有更新正在运行";
  return "更新失败，已保留上一版";
}

async function loadDashboard({ announce = false } = {}) {
  try {
    const [data, committee, historyPayload, refreshPayload] = await Promise.all([
      fetchJson("/api/dashboard"),
      fetchJson("/api/committee"),
      fetchJson("/api/publications"),
      fetchJson("/api/refresh/status"),
    ]);
    if (data.validation_errors?.length) throw new Error(data.validation_errors.join("；"));
    if (committee.validation_errors?.length) throw new Error(committee.validation_errors.join("；"));
    if (committee.snapshot.id !== data.snapshot.id) throw new Error("投委会就绪度与组合快照不一致");
    state.data = data;
    state.committee = committee;
    state.history = historyPayload.publications || [];
    state.refreshRuns = refreshPayload.runs || [];
    render(data);
    $("#loading").hidden = true;
    $("#error-state").hidden = true;
    $("#app").hidden = false;
    if (announce) showToast("已重新读取数据库快照");
  } catch (error) {
    $("#loading").hidden = true;
    $("#app").hidden = true;
    $("#error-state").hidden = false;
    $("#error-message").textContent = `无法读取可用快照：${error.message}`;
  }
}

function regimeTitle(regime) {
  if (String(regime).includes("防守")) return `保留火力，<br><em>先让现金替你等待。</em>`;
  if (String(regime).includes("进攻")) return `提高权益，<br><em>但不给任何一只票特权。</em>`;
  return `均衡配置，<br><em>让质量与估值共同决定仓位。</em>`;
}

function render(data) {
  const isReal = data.snapshot.data_mode === "REAL";
  $("#mode-badge").textContent = data.snapshot.data_mode;
  $("#mode-badge").classList.toggle("real", isReal);
  $("#week-label").textContent = `${data.snapshot.as_of} · ${statusLabel[data.publication.status] || data.publication.status}`;
  $("#regime-title").innerHTML = regimeTitle(data.publication.market_regime);
  $("#regime-note").textContent = data.publication.regime_note;
  $("#publication-status").textContent = statusLabel[data.publication.status] || data.publication.status;
  renderCommittee(state.committee);
  renderApproval(data, state.committee);
  $("#equity-weight").textContent = formatWeight(data.allocation.equity);
  $("#cash-weight").textContent = formatWeight(data.allocation.cash);
  $("#data-mode").textContent = data.snapshot.data_mode;
  $("#data-as-of").textContent = data.snapshot.as_of;
  $("#quality-status").textContent = data.snapshot.quality_status === "passed" ? "通过" : data.snapshot.quality_status === "degraded" ? "降级 · 不可发布" : data.snapshot.quality_status;
  $("#model-version").textContent = data.publication.model_version;
  const quotes = data.snapshot.real_quote_coverage;
  const bars = data.snapshot.daily_bar_coverage;
  const financials = data.snapshot.financial_coverage;
  $("#quote-coverage").textContent = `${quotes.accepted}/${quotes.required}`;
  $("#bar-coverage").textContent = `${bars.accepted}/${bars.required_minimum}+`;
  $("#financial-coverage").textContent = `${financials.accepted}/${financials.required_minimum}+`;
  $("#snapshot-id").textContent = data.snapshot.id;
  if (isReal && quotes.accepted === quotes.required && bars.accepted >= bars.required_minimum && financials.accepted >= financials.required_minimum) {
    $("#data-warning").innerHTML = `<strong>核心快照完整：</strong>${quotes.accepted}/${quotes.required} 行情、${bars.accepted} 条前复权日线、${financials.accepted} 条财务记录。这里展示模型观察配置，不是交易指令；只有完成公司级深研并经 Park 批准的仓位才可执行。`;
  } else {
    $("#data-warning").innerHTML = `<strong>${escapeHtml(data.snapshot.data_mode)} 数据未达到正式发布条件。</strong>当前快照仅用于产品结构验证，不得作为真实组合发布。`;
  }
  renderMandate(data.positions, data.allocation.cash);
  renderPortfolio();
  renderChanges(data.positions);
  renderRisks(data.risks);
  renderPerformance(data.performance, data.allocation);
  renderIndustries(data.industry_exposure);
  renderSourceHealth(data.source_status || []);
  renderHistory();
}

function renderCommittee(committee) {
  if (!committee) return;
  const labels = {
    ready_for_park_decision: "可进入 Park 决策",
    narrative_review_pending: "正文终审中",
    deep_research_required: "待公司级深研",
    blocked: "已阻断",
  };
  const statusLabels = { ready_for_park_decision: "可决策", research_incomplete: "研究未覆盖", blocked: "已阻断" };
  $("#committee-state").textContent = statusLabels[committee.decision_status] || committee.decision_status;
  $("#committee-state").className = `committee-state ${escapeHtml(committee.decision_status)}`;
  $("#committee-headline").textContent = committee.headline;
  const metrics = committee.metrics;
  const capitalMetric = metrics.current_executable_equity > 0
    ? ["已批准执行", `${metrics.current_executable_equity.toFixed(0)}%`, `建议复核 ${metrics.decision_review_equity.toFixed(0)}% · 批准哈希有效`]
    : ["当前可复核", `${metrics.decision_review_equity.toFixed(0)}%`, "建议仓位，尚未批准执行"];
  $("#committee-metrics").innerHTML = [
    ["公司级深研", `${metrics.deep_research_count}/${metrics.stock_count}`, "其余不能转成执行仓位"],
    capitalMetric,
    ["模型观察", `${metrics.model_observation_equity.toFixed(0)}%`, "不是已批准仓位"],
    ["研究待完成", `${metrics.research_pending_equity.toFixed(0)}%`, "先研究，再配置"],
  ].map(([label, value, note]) => `<article><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`).join("");
  $("#committee-body").innerHTML = committee.items.map((item) => {
    const reviewWeight = item.decision_review_weight == null ? "—" : `${Number(item.decision_review_weight).toFixed(0)}%`;
    const researchLabel = item.research_depth === "deep" ? "公司级深研" : item.research_status === "blocked" ? "阻断" : "量化基线";
    return `<tr>
      <td data-label="公司"><button class="committee-company" data-ticker="${escapeHtml(item.ticker)}"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.ticker)}</small></button></td>
      <td data-label="研究状态"><span class="readiness-badge ${escapeHtml(item.decision_state)}">${escapeHtml(researchLabel)}</span></td>
      <td data-label="模型观察"><strong>${Number(item.model_observation_weight || 0).toFixed(0)}%</strong></td>
      <td data-label="建议复核仓位"><strong class="${item.decision_review_weight == null ? "muted-value" : "executable-value"}">${reviewWeight}</strong></td>
      <td data-label="下一道门"><span class="next-gate">${escapeHtml(labels[item.decision_state] || item.next_gate)}</span></td>
    </tr>`;
  }).join("");
  $$(".committee-company").forEach((button) => button.addEventListener("click", () => openResearchReport(button.dataset.ticker)));
  $("#research-queue-list").innerHTML = committee.research_queue.slice(0, 4).map((item) => `<li>
    <span>${escapeHtml(item.priority)}</span><button data-ticker="${escapeHtml(item.ticker)}"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.task)}</small></button>
  </li>`).join("");
  $$("#research-queue-list button").forEach((button) => button.addEventListener("click", () => openResearchReport(button.dataset.ticker)));
}

function renderApproval(data, committee) {
  const button = $("#approval-action");
  const seal = document.querySelector(".approval-card .seal");
  const status = data.publication.status;
  if (state.auth?.member && !(state.auth.member.entitlements || []).includes("approve_publication")) {
    seal.textContent = "只读";
    $("#approval-hint").textContent = "当前席位可阅读研究，组合批准仅由 Park 完成。";
    button.hidden = true;
    return;
  }
  if (!committee || committee.decision_status !== "ready_for_park_decision") {
    seal.textContent = committee?.decision_status === "blocked" ? "阻断" : "研究中";
    $("#approval-hint").textContent = "整期研究门未通过；当前只能复核单股，不能批准组合。";
    button.hidden = true;
    delete button.dataset.action;
    return;
  }
  const settings = {
    quality_passed: { seal: "待批", hint: "质量门已通过，等待 Park 作最终判断", label: "批准本期", action: "approve" },
    approved: { seal: "已批", hint: "内容哈希已锁定，可发布给内测用户", label: "发布给内测用户", action: "publish" },
    published: { seal: "已发", hint: "已进入不可回写的模型账本" },
    invalidated: { seal: "失效", hint: "批准后内容发生变化，必须重新生成版本" },
    blocked: { seal: "阻断", hint: "质量门未通过，不允许批准" },
    draft: { seal: "待审", hint: "等待数据质量门" },
  }[status] || { seal: "待审", hint: "状态未知" };
  seal.textContent = settings.seal;
  $("#approval-hint").textContent = settings.hint;
  button.hidden = !settings.action;
  if (settings.action) {
    button.textContent = settings.label;
    button.dataset.action = settings.action;
  } else {
    delete button.dataset.action;
  }
}

async function transitionPublication() {
  const button = $("#approval-action");
  const action = button.dataset.action;
  if (!action || !state.data) return;
  button.disabled = true;
  try {
    await fetchJson(`/api/publications/${encodeURIComponent(state.data.publication.id)}/${action}`, { method: "POST" });
    showToast(action === "approve" ? "本期已由 Park 批准，内容哈希已锁定" : "本期已发布，模型账本开始记录");
    await loadDashboard();
  } catch (error) {
    showToast(`操作未完成：${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function renderMandate(positions, cash) {
  const strip = $("#mandate-strip");
  strip.innerHTML = positions.map((position, index) => `
    <button class="mandate-segment" style="width:${position.target_weight}%;background:${colors[index % colors.length]}" data-ticker="${escapeHtml(position.ticker)}" aria-label="${escapeHtml(position.name)} 模型观察 ${formatWeight(position.target_weight)}">
      <span><strong>${escapeHtml(position.name)}</strong>${formatWeight(position.target_weight)}</span>
    </button>
  `).join("") + `<div class="mandate-segment cash" style="width:${cash}%"><span><strong>现金</strong>${formatWeight(cash)}</span></div>`;
  strip.querySelectorAll("[data-ticker]").forEach((button) => button.addEventListener("click", () => openStock(button.dataset.ticker)));
}

function renderPortfolio() {
  const readiness = new Map((state.committee?.items || []).map((item) => [item.ticker, item]));
  const positions = state.data.positions.filter((item) => {
    const research = readiness.get(item.ticker);
    return state.filter === "全部" || (state.filter === "深研" && research?.research_depth === "deep") || (state.filter === "基线" && research?.research_depth !== "deep");
  });
  $("#portfolio-body").innerHTML = positions.map((item) => {
    const research = readiness.get(item.ticker) || {};
    const delta = Number(item.target_weight) - Number(item.previous_weight);
    const deltaClass = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
    const deltaText = delta > 0 ? `+${delta.toFixed(0)}%` : delta < 0 ? `${delta.toFixed(0)}%` : "—";
    const score = item.composite_score ?? item.confidence;
    return `<tr>
      <td class="company-cell"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.ticker)} · ${escapeHtml(item.industry)}</span></td>
      <td><span class="readiness-badge ${escapeHtml(research.decision_state || "deep_research_required")}">${research.decision_state === "ready_for_park_decision" ? "可复核" : research.decision_state === "blocked" ? "阻断" : "待深研"}</span></td>
      <td><span class="weight">${formatWeight(item.target_weight)}</span><small>模型观察，非执行仓位</small></td>
      <td><span class="delta ${deltaClass}">${deltaText}</span></td>
      <td><div class="confidence"><div class="confidence-track"><i style="width:${Math.max(0, Math.min(100, Number(score)))}%"></i></div><span>${formatScore(score)}</span></div></td>
      <td><button class="row-open" data-ticker="${escapeHtml(item.ticker)}" aria-label="查看 ${escapeHtml(item.name)} 详情">↗</button></td>
    </tr>`;
  }).join("");
  $$(".row-open").forEach((button) => button.addEventListener("click", () => openStock(button.dataset.ticker)));
}

function renderChanges(positions) {
  const changed = positions.filter((item) => Number(item.target_weight) !== Number(item.previous_weight));
  $("#change-list").innerHTML = changed.map((item) => {
    const delta = Number(item.target_weight) - Number(item.previous_weight);
    return `<button class="change-item" data-ticker="${escapeHtml(item.ticker)}" style="width:100%;border-left:0;border-right:0;border-bottom:0;background:transparent;text-align:left;cursor:pointer">
      <span class="change-action">观察变化</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.industry)}</small></span><b>${delta > 0 ? "+" : ""}${delta.toFixed(0)}%</b>
    </button>`;
  }).join("") || `<p class="quiet-empty">本期模型观察权重无变化。</p>`;
  $$(".change-item").forEach((button) => button.addEventListener("click", () => openStock(button.dataset.ticker)));
}

function renderRisks(risks) {
  $("#risk-list").innerHTML = risks.map((risk) => `<li><strong>${escapeHtml(risk.title)}</strong><p>${escapeHtml(risk.detail)}</p></li>`).join("");
}

function renderPerformance(points, allocation) {
  $("#metric-equity").textContent = formatWeight(allocation.equity);
  $("#metric-cash").textContent = formatWeight(allocation.cash);
  if (!points.length) {
    $("#metric-return").textContent = "待发布";
    $("#metric-alpha").textContent = "待发布";
    $("#performance-chart").innerHTML = `<div class="chart-empty"><span><strong>还没有可归因的真实业绩</strong><br>首个版本发布后，才从发布时点开始记录组合与沪深 300。</span></div>`;
    return;
  }
  const first = points[0];
  const last = points.at(-1);
  const portfolioReturn = last.portfolio / first.portfolio * 100 - 100;
  const benchmarkReturn = last.benchmark / first.benchmark * 100 - 100;
  $("#metric-return").textContent = `${portfolioReturn >= 0 ? "+" : ""}${portfolioReturn.toFixed(1)}%`;
  $("#metric-alpha").textContent = `${portfolioReturn - benchmarkReturn >= 0 ? "+" : ""}${(portfolioReturn - benchmarkReturn).toFixed(1)}%`;

  const width = 1000, height = 300, pad = { x: 42, y: 28 };
  const values = points.flatMap((point) => [point.portfolio, point.benchmark]);
  const min = Math.floor(Math.min(...values) - 2), max = Math.ceil(Math.max(...values) + 2);
  const x = (index) => pad.x + index * ((width - pad.x * 2) / Math.max(points.length - 1, 1));
  const y = (value) => height - pad.y - ((value - min) / Math.max(max - min, 1)) * (height - pad.y * 2);
  const line = (key) => points.map((point, index) => `${index ? "L" : "M"}${x(index)},${y(point[key])}`).join(" ");
  const gridValues = [min, Math.round((min + max) / 2), max];
  $("#performance-chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="已发布模型组合净值与基准曲线">
    ${gridValues.map((value) => `<line class="chart-grid" x1="${pad.x}" y1="${y(value)}" x2="${width - pad.x}" y2="${y(value)}"/><text class="chart-label" x="0" y="${y(value) + 3}">${value}</text>`).join("")}
    <path class="benchmark-line" d="${line("benchmark")}"/><path class="portfolio-line" d="${line("portfolio")}"/>
    ${points.map((point, index) => `<text class="chart-label" x="${x(index)}" y="${height - 2}" text-anchor="middle">${escapeHtml(point.date.slice(5))}</text>`).join("")}
  </svg>`;
}

function renderIndustries(exposure) {
  $("#industry-bars").innerHTML = exposure.map((item) => `<div class="industry-row"><span>${escapeHtml(item.industry)}</span><div class="bar-track"><i style="width:${Math.min(item.weight / 30 * 100, 100)}%"></i></div><b>${formatWeight(item.weight)}</b></div>`).join("");
}

function renderSourceHealth(sources) {
  const labels = { tencent_quote: "腾讯实时行情", tencent_qfq_daily: "腾讯前复权日线", eastmoney_f10_main: "东方财富 F10 财务" };
  $("#source-health-list").innerHTML = sources.map((source) => `<article class="source-health-item ${escapeHtml(source.status)}">
    <strong>${escapeHtml(labels[source.source_key] || source.source_key)}</strong>
    <span>${escapeHtml(source.status.toUpperCase())} · ${source.accepted_count}/${source.fetched_count}</span>
    <small>${escapeHtml(formatBeijingTime(source.finished_at))}</small>
  </article>`).join("") || `<p class="quiet-empty">Missing evidence：本快照没有数据源运行凭证。</p>`;
}

function renderHistory() {
  const receipts = state.refreshRuns.slice(0, 4).map((run) => `<article class="refresh-receipt ${escapeHtml(run.status)}"><span>${escapeHtml(run.status.toUpperCase())}</span><div><strong>${escapeHtml(formatBeijingTime(run.finished_at || run.started_at))}</strong><small>${run.status === "failed" ? escapeHtml(refreshErrorLabel(run)) : `${escapeHtml(run.previous_snapshot_id || "无")} → ${escapeHtml(run.result_snapshot_id || "运行中")}`}</small></div></article>`).join("");
  $("#timeline-list").innerHTML = `${receipts ? `<div class="refresh-receipts"><p class="eyebrow">REFRESH RECEIPTS / 数据更新回执</p>${receipts}</div>` : ""}${state.history.map((item, index) => `<article class="timeline-item ${index > 2 ? "muted" : ""}">
    <time>${escapeHtml(item.as_of)}</time>
    <div>
      <span class="timeline-badge">${escapeHtml(item.data_mode)} · ${escapeHtml(statusLabel[item.status] || item.status)}</span>
      <h2>${escapeHtml(item.market_regime)} · 股票 ${formatWeight(item.equity_weight)} / 现金 ${formatWeight(item.cash_weight)}</h2>
      <p>${escapeHtml(item.title)}；模型 ${escapeHtml(item.model_version)}。快照 ${escapeHtml(item.snapshot_id)}，历史记录不回写。</p>
      ${index === 0 ? `<button data-view-jump="decision">查看当前决策</button>` : ""}
    </div>
  </article>`).join("")}`;
  $$("[data-view-jump]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.viewJump)));
}

function financialTable(financials) {
  if (!financials?.length) return `<p>Missing evidence：暂无可用财务记录。</p>`;
  return `<div class="table-wrap"><table class="financial-table"><thead><tr><th>报告期</th><th>ROE</th><th>营收同比</th><th>利润同比</th></tr></thead><tbody>${financials.slice(0, 4).map((row) => `<tr><td>${escapeHtml(row.report_date)}<br><small>${escapeHtml(row.report_type)}</small></td><td>${formatScore(row.roe)}%</td><td>${formatScore(row.revenue_yoy)}%</td><td>${formatScore(row.net_profit_yoy)}%</td></tr>`).join("")}</tbody></table></div>`;
}

function formatMaybe(value, suffix = "", digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function reportRefs(ids = [], sources = []) {
  const index = new Map(sources.map((source, i) => [source.id, i + 1]));
  return ids.map((id) => index.has(id) ? `<a class="source-ref" href="#source-${escapeHtml(id)}" aria-label="跳到证据 ${index.get(id)}">${index.get(id)}</a>` : "").join("");
}

function safeSourceUrl(value) {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.href : null;
  } catch (_) {
    return null;
  }
}

function reportSection(title, eyebrow, id, body, module = null) {
  const meta = module
    ? [String(module.order).padStart(2, "0"), module.kicker]
    : ({ "r-update": ["Δ", "版本变化"] }[id] || ["—", eyebrow || "研究章节"]);
  const statusLabels = { available: "已覆盖", missing_evidence: "Missing evidence", not_applicable: "Not applicable" };
  const status = module ? `<em class="report-module-status ${escapeHtml(module.status)}">${escapeHtml(statusLabels[module.status] || module.status)}</em>` : "";
  const absence = module && module.status !== "available"
    ? `<p class="method-warning report-module-absence"><strong>${escapeHtml(statusLabels[module.status] || module.status)}：</strong>${escapeHtml(module.status_reason)}</p>`
    : "";
  const contractAttribute = module
    ? `data-report-module="${escapeHtml(module.id)}"`
    : `data-report-supporting-block="${escapeHtml(id)}"`;
  return `<section class="report-section" id="${id}" ${contractAttribute}><div class="report-section-head"><span class="report-section-index">${meta[0]}</span><div><p class="report-section-kicker">${escapeHtml(meta[1])}</p><h2>${escapeHtml(title)}</h2></div>${status}</div>${absence}${body}</section>`;
}

function renderAiNarrative(report, sources) {
  const ai = report.ai_narrative;
  const provider = report.narrative_provider;
  if (!ai || !provider) return `<aside class="ai-status-strip" id="r-deepseek" aria-label="研究边界说明"><strong>研究边界</strong><span>本期未纳入外部模型生成内容；所有结论均来自数据库事实、公式结果和确定性仓位条件。</span></aside>`;
  const sectionLabels = {
    industry_chain: "产业链与供需",
    business_quality: "业务质量",
    competitive_moat: "竞争与护城河",
    financial_quality: "财务质量",
    valuation_debate: "估值分歧",
    risk_falsification: "风险与反证",
  };
  const sectionCards = Object.entries(ai.sections || {}).map(([key, block], index) => `<article class="ai-analysis-card">
    <header><span>${escapeHtml(sectionLabels[key] || key)}</span><em class="claim-badge inference">推断</em></header>
    <h3>${escapeHtml(block.title)}</h3><strong>${escapeHtml(block.conclusion)}</strong>
    ${block.paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
    <footer>${reportRefs(block.source_ids, sources)}</footer>
  </article>`).join("");
  const committee = ai.investment_committee;
  return `<aside class="ai-supplement" id="r-deepseek" aria-labelledby="ai-supplement-title"><header><span>补充研判</span><h2 id="ai-supplement-title">定性因果与情景解释</h2></header>
    <div class="ai-executive"><span>模型定性摘要</span><h3>${escapeHtml(ai.executive_summary.conclusion)}</h3>${ai.executive_summary.paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}<footer>${reportRefs(ai.executive_summary.source_ids, sources)}</footer></div>
    <div class="ai-analysis-list">${sectionCards}</div>
    <h3 class="subsection-title">投委会分歧：同一组事实，三种解释</h3>
    <div class="ai-committee"><article class="bull"><span>多方解释</span><p>${escapeHtml(committee.bull_case)}</p></article><article class="base"><span>基准解释</span><p>${escapeHtml(committee.base_case)}</p></article><article class="bear"><span>空方解释</span><p>${escapeHtml(committee.bear_case)}</p></article></div>
    <details class="ai-method"><summary>模型与编辑复核记录</summary><div class="ai-provenance"><div><span>写作模型</span><strong>${escapeHtml(provider.model)}</strong></div><div><span>生成时间</span><strong>${escapeHtml(provider.generated_at)}</strong></div><div><span>复核记录</span><strong>${provider.validation.cited_source_count}/${provider.validation.available_source_count} 来源 · ${escapeHtml(provider.editorial_approval.approved_by)} 编辑批准</strong></div></div></details>
  </aside>`;
}

function renderUpdateDiff(diff) {
  if (!diff) return "";
  const changes = diff.changes || [];
  const changeCards = changes.map((item) => {
    const digits = item.unit === "元" || item.unit === "倍" ? 2 : 1;
    const displayValue = (value) => value === null || value === undefined ? "—" : Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)}${escapeHtml(item.unit)}` : escapeHtml(value);
    const before = displayValue(item.before);
    const after = displayValue(item.after);
    const delta = item.delta === null || item.delta === undefined ? "口径变化" : `${Number(item.delta) > 0 ? "+" : ""}${Number(item.delta).toFixed(1)}${escapeHtml(item.unit)}`;
    return `<article class="update-change ${escapeHtml(item.direction)}"><span>${escapeHtml(item.label)}</span><div><del>${before}</del><b>→</b><strong>${after}</strong></div><small>${delta}</small></article>`;
  }).join("");
  const updateLabel = diff.status === "baseline" ? "首次覆盖" : "深度更新";
  const conclusionLabel = changes.length ? `${changes.length} 项指标变化` : "核心结论未变";
  return reportSection("这次更新改变了什么", "", "r-update", `
    <div class="update-summary ${escapeHtml(diff.status)}"><div><span>${escapeHtml(diff.status === "baseline" ? "建立研究基线" : diff.status === "unchanged" ? "没有实质变化" : "发现新变化")}</span><h3>${escapeHtml(diff.headline)}</h3></div><dl><div><dt>报告类型</dt><dd>${updateLabel}</dd></div><div><dt>结论变化</dt><dd>${conclusionLabel}</dd></div><div><dt>数据核验</dt><dd>已通过</dd></div></dl></div>
    ${changeCards ? `<div class="update-change-grid">${changeCards}</div>` : `<p class="method-warning">${diff.status === "baseline" ? "本次首次建立研究基线，不存在上期可比版本。" : "当前未出现足以改变投资结论的量化变化；本次更新沿用既有评级与仓位框架。"}</p>`}
  `);
}

function renderPendingReport(report) {
  const stock = report.available.stock;
  const pendingLabel = report.research_status === "unverified" ? "DATA GATE BLOCKED" : "RESEARCH PENDING";
  return `<div class="report-pending"><p class="eyebrow">${pendingLabel}</p><h1 id="report-title">${escapeHtml(report.name)}</h1><p>${escapeHtml(report.message)}</p><div class="pending-known"><strong>已经有</strong><span>产品结构</span><span>数据接口</span><span>研究门禁</span></div><div class="pending-missing"><strong>还缺</strong>${report.available.missing_modules.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div><p class="data-warning"><strong>未通过门禁就不展示目标价与仓位。</strong>完成真实快照、完整覆盖和质量校验后，这里才会升级为完整研报。</p><button class="primary-button" data-report-back>返回组合</button><small>当前快照：${escapeHtml(stock.snapshot_id)} · ${escapeHtml(stock.data_mode)} · ${escapeHtml(stock.snapshot_quality || "unknown")}</small></div>`;
}

function orderReportMarkupFromManifest(markup, contract) {
  const template = document.createElement("template");
  template.innerHTML = markup.trim();
  const main = template.content.querySelector(".report-main");
  if (!main) throw new Error("研报正文容器缺失，已拒绝渲染");
  const nodes = [...main.children].filter((node) => node.hasAttribute("data-report-module"));
  const byId = new Map(nodes.map((node) => [node.dataset.reportModule, node]));
  const expected = contract.module_manifest.map((module) => module.id);
  if (nodes.length !== expected.length || byId.size !== expected.length || expected.some((id) => !byId.has(id))) {
    throw new Error("研报正文模块与合同不一致，已拒绝渲染");
  }
  for (const id of expected) main.append(byId.get(id));
  const actual = [...main.children].filter((node) => node.hasAttribute("data-report-module")).map((node) => node.dataset.reportModule);
  if (actual.join("|") !== expected.join("|")) throw new Error("研报正文顺序校验失败，已拒绝渲染");
  return template.innerHTML;
}

function renderDeepReport(report) {
  const s = report.sources;
  const exec = report.executive;
  const m = report.market;
  const valuation = report.valuation;
  const financials = report.financials;
  const serenity = report.serenity;
  const ai = report.ai_narrative;
  const contract = report.report_contract;
  const expectedModules = ["executive_summary", "investment_thesis", "business_and_industry", "financial_quality", "framework_assessment", "valuation", "catalysts_risks", "evidence_ledger"];
  const modules = contract?.module_manifest || [];
  if (contract?.schema_version !== "research-report-v1" || contract?.contract_version !== "1.0.0" || modules.map((item) => item.id).join("|") !== expectedModules.join("|")) {
    throw new Error("研报合同缺失或章节顺序不受支持，已拒绝渲染");
  }
  const moduleById = new Map(modules.map((item) => [item.id, item]));
  const section = (moduleId, _title, eyebrow, anchor, body) => {
    const module = moduleById.get(moduleId);
    if (!module || module.anchor !== anchor) throw new Error(`研报章节合同不匹配：${moduleId}`);
    return reportSection(module.title, eyebrow, anchor, body, module);
  };
  const marketLabels = { CN: "中国股票研究", HK: "香港股票研究", US: "美国股票研究" };
  const currencySymbols = { CNY: "¥", HKD: "HK$", USD: "$" };
  const currencySymbol = currencySymbols[contract.identity.currency] || `${contract.identity.currency} `;
  const formatMoney = (value, digits = 1) => `${currencySymbol}${formatMaybe(value, "", digits)}`;
  const financialUnit = contract.measurement_policy.financial_statement_unit_label;
  const formatFinancialAmount = (value, digits = 1) => value === null || value === undefined ? "—" : `${formatMaybe(value, "", digits)} ${financialUnit}`;
  const isBaseline = report.research_depth === "quantitative_baseline";
  const stressTest = report.stress_test;
  const signalItems = isBaseline ? (report.quant_signals || []) : report.moat;
  const displayScenarios = isBaseline
    ? (stressTest?.scenarios || []).map((item) => ({...item, target_price: item.stress_price, upside_pct: item.change_pct}))
    : valuation.scenarios;
  const priceLabel = isBaseline ? "压力价" : "目标价";
  const earningsLabel = valuation.earnings_label || "2026E EPS";
  const multipleLabel = valuation.multiple_label || "目标 PE";
  const formulaLabel = valuation.formula_label || "目标价 = 2026E EPS × 情景 PE";
  const scenarioClass = (item) => item.case === "bull" ? "bull" : item.case === "bear" ? "bear" : "base";
  const sourceKind = { primary: "一手披露", market_snapshot: "市场快照", company_release: "公司事件", independent: "独立行业源" };
  const claimKind = { fact: "事实", inference: "推断", assumption: "假设" };
  const baseScenario = displayScenarios.find((x) => x.case === "base") || displayScenarios[0] || { target_price: exec.current_price, upside_pct: 0 };
  const reportHeadline = ai?.report_title || report.title;
  const companyName = report.name || report.ticker;
  const thesisHeadline = reportHeadline.startsWith(`${companyName}：`) ? reportHeadline.slice(companyName.length + 1) : reportHeadline;
  const scenarioTargets = displayScenarios.map((item) => Number(item.target_price)).filter(Number.isFinite);
  const targetMin = scenarioTargets.length ? Math.min(...scenarioTargets) : Number(exec.current_price);
  const targetMax = scenarioTargets.length ? Math.max(...scenarioTargets) : Number(exec.current_price);
  const currentMarker = targetMax === targetMin ? 50 : Math.max(0, Math.min(100, ((Number(exec.current_price) - targetMin) / (targetMax - targetMin)) * 100));
  const coverageLabel = isBaseline ? "量化研究基线" : report.update_diff?.status === "baseline" || !report.update_diff?.previous_snapshot_id ? "首次覆盖" : "深度更新";
  let positionLabel = "模型观察权重";
  let positionValue = formatWeight(exec.model_observation_weight);
  let positionNote = "尚未形成执行合同";
  if (!isBaseline && exec.current_executable_weight != null) {
    positionLabel = "已批准执行仓位";
    positionValue = formatWeight(exec.current_executable_weight);
    positionNote = `批准哈希有效 · 条件上限 ${formatWeight(exec.max_target_weight)}`;
  } else if (!isBaseline && exec.decision_review_weight != null) {
    positionLabel = "建议复核仓位";
    positionValue = formatWeight(exec.decision_review_weight);
    positionNote = `尚未批准执行 · 条件上限 ${formatWeight(exec.max_target_weight)}`;
  } else if (!isBaseline) {
    positionLabel = "建议复核仓位";
    positionValue = "—";
    positionNote = "正文终审未通过，不展示建议仓位";
  }
  const nav = modules.map((module) => [module.anchor, module.title, module.order, module.status]);
  const executiveModule = moduleById.get("executive_summary");
  const markup = `<article class="report-document">
    <header class="report-hero" id="r-overview">
      <div class="report-hero-copy"><div class="report-masthead"><strong>PARK RESEARCH</strong><span>${escapeHtml(marketLabels[contract.identity.market] || contract.identity.market)}</span><time>${escapeHtml(report.as_of)}</time></div><p class="report-cover-line">${escapeHtml(report.industry)} · ${coverageLabel}</p><h1 id="report-title">${escapeHtml(companyName)}</h1><h2>${escapeHtml(thesisHeadline)}</h2><p class="report-deck">${escapeHtml(ai?.executive_summary?.conclusion || exec.summary)}</p><div class="report-meta"><span>${escapeHtml(report.ticker)}</span><span>${escapeHtml(report.exchange)}</span><span>${escapeHtml(report.data_mode)} DATA</span><span>${escapeHtml(contract.schema_version)}</span></div></div>
      <aside class="report-rating-panel" aria-label="投资判断摘要"><div class="rating-primary"><span>${isBaseline ? "模型观察结论" : "投资判断"}</span><strong>${escapeHtml(exec.stance)}</strong></div><dl><div><dt>当前价</dt><dd>${formatMoney(exec.current_price, 2)}</dd></div><div><dt>${escapeHtml(priceLabel)}</dt><dd>${formatMoney(baseScenario.target_price, 1)}</dd></div><div><dt>${isBaseline ? "基准偏离" : "隐含空间"}</dt><dd>${Number(baseScenario.upside_pct) >= 0 ? "+" : ""}${formatMaybe(baseScenario.upside_pct, "%", 1)}</dd></div><div><dt>${isBaseline ? "模型观察权重" : "仓位上限"}</dt><dd>${formatWeight(isBaseline ? exec.model_observation_weight : exec.max_target_weight)}</dd></div></dl><div class="rating-range"><div><span>悲观 ${formatMoney(targetMin, 0)}</span><span>乐观 ${formatMoney(targetMax, 0)}</span></div><i><b style="left:${currentMarker}%"></b></i><small>现价在${isBaseline ? "压力" : "估值"}区间的位置</small></div></aside>
    </header>
    <div class="report-layout">
      <aside class="report-toc"><strong>报告目录</strong>${nav.map(([id, label, order, status]) => `<a href="#${id}" class="${escapeHtml(status)}"><span>${String(order).padStart(2, "0")}</span>${escapeHtml(label)}</a>`).join("")}<div><span>合同</span><code>${escapeHtml(contract.schema_version)} · ${escapeHtml(contract.contract_version)}</code></div></aside>
      <main class="report-main">
        <section class="ic-summary" data-report-module="executive_summary" aria-labelledby="ic-summary-title"><header><span>${String(executiveModule.order).padStart(2, "0")}</span><div><p>${escapeHtml(executiveModule.kicker)}</p><h2 id="ic-summary-title">${escapeHtml(executiveModule.title)}</h2></div><em class="report-module-status ${escapeHtml(executiveModule.status)}">${escapeHtml(({ available: "已覆盖", missing_evidence: "Missing evidence", not_applicable: "Not applicable" })[executiveModule.status] || executiveModule.status)}</em></header>${report.depth_disclosure ? `<p class="method-warning"><strong>研究深度说明：</strong>${escapeHtml(report.depth_disclosure)}</p>` : ""}<div class="ic-contradiction"><span>核心分歧</span><strong>${escapeHtml(exec.key_contradiction)}</strong></div><div class="ic-kpis"><article><span>${positionLabel}</span><strong>${positionValue}</strong><small>${positionNote}</small></article><article><span>执行观察区</span><strong>${formatMoney(exec.current_price, 2)}</strong><small>${escapeHtml(exec.execution_range)}</small></article><article><span>${isBaseline ? "基准压力价" : "基准估值"}</span><strong>${formatMoney(baseScenario.target_price, 1)}</strong><small>${Number(baseScenario.upside_pct) >= 0 ? "+" : ""}${formatMaybe(baseScenario.upside_pct, "%", 1)} 相对现价</small></article><article><span>证据覆盖</span><strong>${report.evidence_summary.document_count} 份</strong><small>${report.evidence_summary.claim_locator_count} 处定位 · ${report.evidence_summary.independent_document_count} 份独立行业源</small></article></div><div class="ic-execution"><div><span>${isBaseline ? "研究升级路径" : "分步执行"}</span><h3>${isBaseline ? `${formatWeight(exec.model_observation_weight)} 是模型观察权重，不是已批准仓位` : `${formatWeight(exec.target_weight)} 是条件上限，不是一次买完`}</h3></div><ol>${exec.position_plan.map((item, i) => `<li><span>${i + 1}</span><div><strong>${escapeHtml(item.stage)}${Number(item.weight) > 0 ? ` · ${formatWeight(item.weight)}` : ""}</strong><p>${escapeHtml(item.condition)}</p></div></li>`).join("")}</ol></div>${renderUpdateDiff(report.update_diff)}</section>
        ${section("investment_thesis", "核心投资逻辑", "THESIS / 结论先行", "r-thesis", `<div class="thesis-list">${report.thesis.map((item, i) => `<article><span>0${i + 1}</span><div><h3>${escapeHtml(item.title)} <em class="claim-badge ${escapeHtml(item.claim_type)}">${escapeHtml(claimKind[item.claim_type] || item.claim_type)}</em> ${reportRefs(item.source_ids, s)}</h3><p>${escapeHtml(item.body)}</p></div></article>`).join("")}</div>${renderAiNarrative(report, s)}`)}
        ${section("business_and_industry", isBaseline ? "经营证据边界与量化线索" : "经营链路与收入结构", "BUSINESS MODEL", "r-business", `
          <p class="section-intro">${escapeHtml(report.business_model.description)} ${reportRefs(report.business_model.source_ids, s)}</p>
          ${report.business_model.segments.length ? `<div class="segment-table"><div class="segment-head"><span>业务</span><span>收入（${escapeHtml(financialUnit)}）</span><span>占比</span><span>增速</span><span>毛利率</span></div>${report.business_model.segments.map((item) => `<div><strong>${escapeHtml(item.name)}</strong><span>${formatFinancialAmount(item.revenue_yi, 1)}</span><span>${formatMaybe(item.revenue_share, "%", 1)}</span><span class="${Number(item.growth) < 0 ? "negative" : "positive"}">${formatMaybe(item.growth, "%", 1)}</span><span>${formatMaybe(item.gross_margin, "%", 1)}</span></div>`).join("")}</div>` : ""}
          <div class="value-chain">${report.business_model.value_chain.map((item, i) => `<article><span>0${i + 1}</span><h3>${escapeHtml(item.layer)}</h3><p>${escapeHtml(item.items)}</p><small>研究问题：${escapeHtml(item.question)}</small></article>`).join("")}</div>
          <div class="industry-position"><div><p class="report-block-label">行业位置</p><h3>${escapeHtml(report.industry_position.headline)} ${reportRefs(report.industry_position.source_ids, s)}</h3></div><div class="industry-metrics">${report.industry_position.metrics.map((item) => `<article><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong><small>${escapeHtml(item.note)}</small></article>`).join("")}</div></div>
          <h3 class="subsection-title">${isBaseline ? "四项量化线索（非护城河评分）" : "护城河不是一句话，要有证据"}</h3><div class="moat-grid">${signalItems.map((item) => `<article><header><strong>${escapeHtml(item.name)}</strong><b>${formatScore(item.score)}</b></header><div class="moat-track"><i style="width:${item.score * 10}%"></i></div><p>${escapeHtml(item.proof)} ${reportRefs(item.source_ids, s)}</p></article>`).join("")}</div>
          <div class="management-card"><div><p class="report-block-label">管理层评价</p><h3>${isBaseline ? "治理与资本配置 · 深度证据待补" : `管理层与资本配置 · ${formatScore(report.management.score)}/10`}</h3></div><div><strong>${isBaseline ? "当前边界" : "加分项"}</strong><ul>${report.management.strengths.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div><div><strong>需要盯住</strong><ul>${report.management.watchouts.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>${reportRefs(report.management.source_ids, s)}</div></div>`)}
        ${section("financial_quality", isBaseline ? "财务质量：先确认增长与资产负债表" : "财务质量：利润很好，现金转化要继续验证", "FINANCIAL QUALITY", "r-financial", `
          <p class="section-intro">${escapeHtml(financials.headline)}</p>
          <div class="financial-kpis"><article><span>年度 ROE</span><strong>${formatMaybe(financials.annual_quality.roe, "%", 1)}</strong></article><article><span>年度毛利率</span><strong>${formatMaybe(financials.annual_quality.gross_margin, "%", 1)}</strong></article><article><span>年度净利率</span><strong>${formatMaybe(financials.annual_quality.net_margin, "%", 1)}</strong></article><article><span>资产负债率</span><strong>${formatMaybe(financials.annual_quality.debt_ratio, "%", 1)}</strong></article></div>
          <div class="table-wrap report-table"><table><thead><tr><th>报告期</th><th>累计营收（${escapeHtml(financialUnit)}）</th><th>累计净利润（${escapeHtml(financialUnit)}）</th><th>营收同比</th><th>利润同比</th><th>毛利率</th></tr></thead><tbody>${financials.series.slice(0, 6).map((row) => `<tr><td data-label="报告期">${escapeHtml(row.report_date)}<small>${escapeHtml(row.report_type)}</small></td><td data-label="累计营收">${formatFinancialAmount(row.revenue_yi, 1)}</td><td data-label="累计净利润">${formatFinancialAmount(row.net_profit_yi, 1)}</td><td data-label="营收同比">${formatMaybe(row.revenue_yoy, "%", 1)}</td><td data-label="利润同比">${formatMaybe(row.net_profit_yoy, "%", 1)}</td><td data-label="毛利率">${formatMaybe(row.gross_margin, "%", 1)}</td></tr>`).join("")}</tbody></table></div>
          <div class="quality-notes">${financials.quality_notes.map((note, i) => `<article><span>0${i + 1}</span><p>${escapeHtml(note)}</p></article>`).join("")}</div>`)}
        ${section("framework_assessment", isBaseline ? "量化四维评分：只用于排序，不替代公司研究" : "产业链关键卡位评分：先看结构，再看公司", "", "r-serenity", `
          <div class="serenity-summary"><div><span>原始结构分</span><strong>${formatScore(serenity.raw_score)}</strong></div><b>− ${formatScore(serenity.penalty)} 风险扣分</b><div class="final"><span>最终研究分</span><strong>${formatScore(serenity.final_score)}</strong><small>${escapeHtml(serenity.label)}</small></div></div>
          <p class="method-warning">${escapeHtml(serenity.meaning)}</p>
          <div class="scorecard-table"><div class="scorecard-head"><span>维度</span><span>评分</span><span>权重贡献</span><span>为什么</span></div>${serenity.factors.map((item) => `<div><strong>${escapeHtml(item.label)}</strong><span>${formatScore(item.score)}/5</span><span>${formatScore(item.contribution)}</span><p>${escapeHtml(item.reason)} ${reportRefs(item.source_ids, s)}</p></div>`).join("")}</div>
          <h3 class="subsection-title">风险扣分</h3><div class="penalty-grid">${serenity.penalties.map((item) => `<article><header><strong>${escapeHtml(item.label)}</strong><b>−${formatScore(item.points)}</b></header><p>${escapeHtml(item.reason)}</p></article>`).join("")}</div>`)}
        ${section("valuation", isBaseline ? "三档价格压力测试：不伪造目标价" : "三档估值：公式比目标价更重要", "VALUATION", "r-valuation", `
          <div class="valuation-lead"><div><span>方法</span><strong>${escapeHtml(valuation.method)}</strong></div><div><span>当前</span><strong>PE ${formatMaybe(valuation.pe_ttm, "x", 1)} · PB ${formatMaybe(valuation.pb, "x", 1)}</strong></div></div>
          ${isBaseline ? `
            <p class="method-warning"><strong>估值状态：</strong>${escapeHtml(valuation.reason)}</p>
            <div class="valuation-grid">${(stressTest?.scenarios || []).map((item) => `<article class="${scenarioClass(item)}"><span>${escapeHtml(item.label)}压力情景</span><strong>${formatMoney(item.stress_price, 1)}</strong><b>${Number(item.change_pct) >= 0 ? "+" : ""}${formatMaybe(item.change_pct, "%", 1)}</b><dl><div><dt>当前价基数</dt><dd>${formatMoney(item.price_basis, 1)}</dd></div><div><dt>压力倍数</dt><dd>${formatMaybe(item.stress_multiple, "x", 1)}</dd></div></dl><p>${escapeHtml(item.assumption)}</p></article>`).join("")}</div>
            <div class="valuation-formula"><code>${escapeHtml(stressTest?.formula || "")}</code><p>公司级盈利预测、同行比较与历史估值分位尚未完成。</p><small>${escapeHtml(stressTest?.warning || "")}</small></div>` : `
            <div class="earnings-bridge"><div><span>${escapeHtml(valuation.earnings_bridge.base_period)} ${escapeHtml(earningsLabel)}</span><strong>${formatMoney(valuation.earnings_bridge.base_eps, 2)}</strong><small>${escapeHtml(valuation.earnings_bridge.basis)}</small></div>${valuation.earnings_bridge.cases.map((item) => `<article><span>${escapeHtml(item.label)} ${escapeHtml(earningsLabel)}</span><strong>${formatMoney(item.eps, 1)}</strong><small>${Number(item.growth_pct) >= 0 ? "+" : ""}${formatMaybe(item.growth_pct, "%", 1)} vs 2025A</small></article>`).join("")}</div>
            <div class="valuation-grid">${valuation.scenarios.map((item) => `<article class="${scenarioClass(item)}"><span>${escapeHtml(item.label)}情景</span><strong>${formatMoney(item.target_price, 1)}</strong><b>${Number(item.upside_pct) >= 0 ? "+" : ""}${formatMaybe(item.upside_pct, "%", 1)}</b><dl><div><dt>${escapeHtml(earningsLabel)}</dt><dd>${formatMoney(item.eps, 1)}</dd></div><div><dt>${escapeHtml(multipleLabel)}</dt><dd>${formatMaybe(item.pe, "x", 1)}</dd></div></dl><p>${escapeHtml(item.assumption)}</p></article>`).join("")}</div>
            <div class="valuation-formula"><code>${escapeHtml(formulaLabel)}</code><p>${escapeHtml(valuation.reverse_implied)}</p><small>${escapeHtml(valuation.warning)}</small></div>`}`)}
        ${section("catalysts_risks", "催化剂、风险与反证", "RISK DESK", "r-risks", `
          <h3 class="subsection-title">未来 12 个月最值得跟踪的催化剂</h3><div class="catalyst-list">${report.catalysts.map((item) => `<article><time>${escapeHtml(item.date)}</time><div><h3>${escapeHtml(item.title)} ${reportRefs(item.source_ids, s)}</h3><p>${escapeHtml(item.body)}</p></div></article>`).join("")}</div>
          <h3 class="subsection-title">风险矩阵：写触发器，不写空话</h3><div class="risk-matrix"><div class="risk-head"><span>#</span><span>风险</span><span>影响/概率</span><span>触发信号</span></div>${report.risks.map((item) => `<article><span>0${item.rank}</span><div><strong>${escapeHtml(item.title)} ${reportRefs(item.source_ids, s)}</strong><small>${escapeHtml(item.evidence)}</small></div><b>${escapeHtml(item.impact)} / ${escapeHtml(item.probability)}</b><p>${escapeHtml(item.trigger)}</p></article>`).join("")}</div>
          <div class="falsification"><p class="report-block-label">反证条件 · 什么会证明我们错了</p><ol>${report.falsification.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol></div>
          <h3 class="subsection-title">下次更新只盯这五个数</h3><div class="watchlist-table"><div><span>指标</span><span>当前</span><span>失效/验证阈值</span><span>频率</span></div>${report.watchlist.map((item) => `<div><strong>${escapeHtml(item.metric)}</strong><span>${escapeHtml(item.current)}</span><span>${escapeHtml(item.threshold)}</span><span>${escapeHtml(item.frequency)}</span></div>`).join("")}</div>`)}
        ${section("evidence_ledger", "证据台账", "EVIDENCE LEDGER", "r-evidence", `
          <p class="section-intro">${escapeHtml(report.evidence_summary.boundary)}</p><div class="source-ledger">${s.map((source, i) => { const isMarketSnapshot = source.kind === "market_snapshot"; const publicTitle = isMarketSnapshot ? "最新市场行情与因子数据" : source.title; const publicNote = isMarketSnapshot ? "经数据质量门核验的最新市场行情与因子数据" : source.note; const safeUrl = safeSourceUrl(source.url); return `<article id="source-${escapeHtml(source.id)}"><span>${String(i + 1).padStart(2, "0")}</span><div><header><strong>${escapeHtml(publicTitle)}</strong><em>${escapeHtml(sourceKind[source.kind] || source.kind)} · ${escapeHtml(source.strength)}</em></header><p>${escapeHtml(publicNote)}</p><small>资料时点 ${escapeHtml(source.known_at || "未披露")}</small>${safeUrl ? `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a>` : ""}</div></article>`; }).join("")}</div>
          <p class="report-disclaimer">${escapeHtml(report.disclaimer)}</p>`)}
      </main>
    </div>
    <footer class="report-publication"><strong>Park 投委会研究</strong><span>发布主体：Park 投委会 · 数据与证据门禁复核</span></footer>
  </article>`;
  return orderReportMarkupFromManifest(markup, contract);
}

function setReportVisibility(visible) {
  const report = $("#research-report");
  report.hidden = !visible;
  report.setAttribute("aria-hidden", String(!visible));
  $(".shell").inert = visible;
  $("#stock-drawer").inert = true;
  document.body.style.overflow = visible ? "hidden" : "";
  if (!visible && state.reportOpener?.isConnected) state.reportOpener.focus();
}

async function openResearchReport(ticker, { syncHistory = true } = {}) {
  state.reportOpener = syncHistory ? document.activeElement : state.reportOpener;
  $("#report-content").innerHTML = `<div class="report-pending"><p class="eyebrow">研报载入</p><h1 id="report-title">正在校验研报与数据快照…</h1></div>`;
  $("#report-receipt").textContent = "校验中";
  setReportVisibility(true);
  $("#report-close").focus();
  try {
    const report = await fetchJson(`/api/reports/${encodeURIComponent(ticker)}`);
    closeDrawer();
    const renderable = report.research_status === "verified" || (report.research_status === "baseline" && report.data_status === "verified");
    $("#report-content").innerHTML = renderable ? renderDeepReport(report) : renderPendingReport(report);
    $("#report-receipt").textContent = renderable ? `${report.data_mode} · ${report.as_of} · ${report.report_version}` : "研究待补";
    $("#research-report").scrollTop = 0;
    $$('[data-report-back]').forEach((button) => button.addEventListener("click", closeResearchReport));
    if (syncHistory) {
      const url = new URL(location.href);
      url.searchParams.set("report", ticker);
      history.pushState({ report: ticker }, "", url);
      state.reportPushed = true;
    }
  } catch (error) {
    $("#report-content").innerHTML = `<div class="report-pending"><p class="eyebrow">载入失败</p><h1 id="report-title">研报无法打开</h1><p>${escapeHtml(error.message)}</p><button class="primary-button" data-report-back>返回组合</button></div>`;
    $("[data-report-back]").addEventListener("click", closeResearchReport);
    $("#report-receipt").textContent = "读取失败";
  }
}

function closeResearchReport() {
  if (state.reportPushed && new URLSearchParams(location.search).has("report")) {
    state.reportPushed = false;
    history.back();
    return;
  }
  setReportVisibility(false);
  const url = new URL(location.href);
  url.searchParams.delete("report");
  history.replaceState(null, "", url);
}

async function openStock(ticker) {
  try {
    const stock = await fetchJson(`/api/stocks/${encodeURIComponent(ticker)}`);
    const delta = Number(stock.target_weight) - Number(stock.previous_weight);
    const features = stock.features;
    $("#drawer-content").innerHTML = `
      <div class="drawer-kicker"><span>模型观察</span>${escapeHtml(stock.industry)} · ${escapeHtml(stock.data_mode)}</div>
      <h2 id="drawer-title">${escapeHtml(stock.name)}</h2><p class="drawer-code">${escapeHtml(stock.ticker)} · ${escapeHtml(stock.exchange)}</p>
      <div class="drawer-allocation"><div><span>模型观察权重</span><strong>${formatWeight(stock.target_weight)}</strong></div><div><span>较上期观察</span><strong>${delta > 0 ? "+" : ""}${delta.toFixed(0)}%</strong></div><div><span>行情参考价</span><strong>${stock.market_quote ? `¥${Number(stock.market_quote.price).toFixed(2)}` : "Missing"}</strong></div><div><span>综合评分</span><strong>${features ? formatScore(features.composite_score) : stock.confidence}/100</strong></div></div>
      ${features ? `<div class="score-grid"><div><span>质量</span><strong>${formatScore(features.quality_score)}</strong></div><div><span>价值</span><strong>${formatScore(features.value_score)}</strong></div><div><span>趋势</span><strong>${formatScore(features.trend_score)}</strong></div><div><span>韧性</span><strong>${formatScore(features.resilience_score)}</strong></div></div>` : ""}
      <section class="drawer-section"><h3>为什么在组合里</h3><p>${escapeHtml(stock.thesis)}</p><p><strong>估值：</strong>${escapeHtml(stock.valuation)}</p></section>
      <section class="drawer-section"><h3>三种情景</h3><div class="scenario-grid"><div class="scenario bull"><strong>BULL / 乐观</strong><p>${escapeHtml(stock.bull_case)}</p></div><div class="scenario base"><strong>BASE / 基准</strong><p>${escapeHtml(stock.base_case)}</p></div><div class="scenario bear"><strong>BEAR / 悲观</strong><p>${escapeHtml(stock.bear_case)}</p></div></div></section>
      <section class="drawer-section"><h3>最近四期财务</h3>${financialTable(stock.financials)}</section>
      <section class="drawer-section"><h3>风险触发条件</h3><p>${escapeHtml(stock.primary_risk)}</p></section>
      <section class="drawer-section"><h3>证据与推断</h3>${stock.evidence.map((item) => `<article class="evidence-item"><header><strong>${escapeHtml(item.label)}</strong><em>${escapeHtml(item.evidence_type).toUpperCase()}</em></header><p>${escapeHtml(item.value)}</p><small>${escapeHtml(item.source)} · ${escapeHtml(item.known_at)}</small></article>`).join("")}</section>
      <button class="open-report-button" data-report-ticker="${escapeHtml(stock.ticker)}"><span>完整研究底稿</span><strong>${stock.ticker === "300750.SZ" ? "打开宁德时代深度研报" : "查看研究覆盖状态"} →</strong></button>
      <p class="data-warning"><strong>${escapeHtml(stock.data_mode)} 数据：</strong> ${escapeHtml(stock.source_summary)}</p>`;
    const reportButton = $("[data-report-ticker]");
    reportButton.addEventListener("click", () => openResearchReport(reportButton.dataset.reportTicker));
    $("#drawer-backdrop").hidden = false;
    $("#stock-drawer").inert = false;
    $("#stock-drawer").classList.add("is-open");
    $("#stock-drawer").setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    $("#drawer-close").focus();
  } catch (error) {
    showToast(`个股详情不可用：${error.message}`);
  }
}

function closeDrawer() {
  $("#stock-drawer").classList.remove("is-open");
  $("#stock-drawer").setAttribute("aria-hidden", "true");
  $("#stock-drawer").inert = true;
  $("#drawer-backdrop").hidden = true;
  if ($("#research-report").hidden) document.body.style.overflow = "";
}

function setView(view) {
  state.activeView = view;
  $$(".view").forEach((section) => section.classList.toggle("is-active", section.id === `view-${view}`));
  $$(".nav-item").forEach((button) => button.classList.toggle("is-active", button.dataset.view === view));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function triggerRefresh() {
  const button = $("#refresh-button");
  if (button.disabled) return;
  button.disabled = true;
  button.classList.add("is-refreshing");
  button.setAttribute("aria-busy", "true");
  showToast("正在采集真实数据并执行质量门；旧快照会一直保留");
  try {
    const result = await fetchJson("/api/refresh", { method: "POST" });
    await loadDashboard();
    const reportTicker = new URLSearchParams(location.search).get("report");
    if (reportTicker && !$("#research-report").hidden) await openResearchReport(reportTicker, { syncHistory: false });
    showToast(result.reused ? "数据没有变化：沿用同一不可变快照" : `更新完成：${result.update_diff?.headline || `已生成新快照 ${result.snapshot_id}`}`);
  } catch (error) {
    await loadDashboard();
    const label = error.code === "refresh_in_progress"
      ? "已有更新正在运行"
      : /SSL|URL|timeout|timed out/i.test(error.message)
        ? "上游数据连接失败，仍使用上一版"
        : "数据未通过质量门，仍使用上一版";
    showToast(label);
  } finally {
    button.disabled = false;
    button.classList.remove("is-refreshing");
    button.removeAttribute("aria-busy");
  }
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
}

$$("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
$$(".filter").forEach((button) => button.addEventListener("click", () => {
  state.filter = button.dataset.filter;
  $$(".filter").forEach((item) => item.classList.toggle("is-active", item === button));
  renderPortfolio();
}));
$("#approval-action").addEventListener("click", transitionPublication);
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-backdrop").addEventListener("click", closeDrawer);
$("#report-close").addEventListener("click", closeResearchReport);
$("#refresh-button").addEventListener("click", triggerRefresh);
$("#retry-button").addEventListener("click", () => { $("#error-state").hidden = true; $("#loading").hidden = false; loadDashboard(); });
$("#auth-login-tab").addEventListener("click", () => showAuth("login"));
$("#auth-signup-tab").addEventListener("click", () => showAuth("signup"));
$("#login-form").addEventListener("submit", (event) => { event.preventDefault(); submitAuth(event.currentTarget, "/api/auth/login"); });
$("#signup-form").addEventListener("submit", (event) => { event.preventDefault(); submitAuth(event.currentTarget, "/api/auth/signup"); });
$("#logout-button").addEventListener("click", async () => {
  if (!state.auth?.auth_required || !state.auth.member) return;
  try { await fetchJson("/api/auth/logout", { method: "POST" }); } catch (_) { /* The local session is cleared even if the response is lost. */ }
  state.auth = { auth_required: true, member: null, csrf_token: null };
  state.data = null;
  $("#app").hidden = true;
  showAuth("login");
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!$("#research-report").hidden) closeResearchReport();
  else if ($("#stock-drawer").classList.contains("is-open")) closeDrawer();
});
window.addEventListener("popstate", () => {
  const reportTicker = new URLSearchParams(location.search).get("report");
  state.reportPushed = false;
  if (reportTicker) openResearchReport(reportTicker, { syncHistory: false });
  else setReportVisibility(false);
});
(async function bootstrap() {
  try {
    const auth = await fetchJson("/api/auth/me");
    if (!applyAuth(auth)) {
      $("#loading").hidden = true;
      return;
    }
    await loadDashboard();
    const reportTicker = new URLSearchParams(location.search).get("report");
    if (reportTicker) await openResearchReport(reportTicker, { syncHistory: false });
  } catch (error) {
    $("#loading").hidden = true;
    $("#error-state").hidden = false;
    $("#error-message").textContent = `无法启动内测面板：${error.message}`;
  }
}());
setInterval(async () => {
  if (document.hidden || !state.data) return;
  try {
    const payload = await fetchJson("/api/refresh/status");
    state.refreshRuns = payload.runs || [];
    const latestUsable = state.refreshRuns.find((run) => ["success", "reused"].includes(run.status) && run.result_snapshot_id);
    if (latestUsable && latestUsable.result_snapshot_id !== state.data.snapshot.id) {
      const reportTicker = new URLSearchParams(location.search).get("report");
      const reportWasOpen = reportTicker && !$("#research-report").hidden;
      await loadDashboard();
      if (reportWasOpen) await openResearchReport(reportTicker, { syncHistory: false });
      showToast("后台数据已更新，页面已切换到最新通过质量门的快照");
    } else {
      renderHistory();
    }
  } catch (_) { /* 主面板继续使用最后一次已验证状态。 */ }
}, 60000);
