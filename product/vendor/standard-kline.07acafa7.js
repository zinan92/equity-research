/*!
 * standard-kline
 *
 * Provider-agnostic OHLCV candlestick chart wrapper around TradingView
 * Lightweight Charts. Adapts any OHLCV-shaped payload into chart data,
 * flags synthetic/placeholder data, and drives zoom/pan/fit through a
 * clamped logical-range path that stays correct even when the caller
 * (or a user) requests an out-of-bounds range.
 *
 * Browser global: window.StandardKline
 * Node export: require("standard-kline")
 *
 * Peer dependency: lightweight-charts (loaded as window.LightweightCharts
 * in the browser, e.g. via the vendored standalone build).
 */
(function(root, factory){
  const api = factory(root || {});
  if(typeof module === "object" && module.exports) module.exports = api;
  if(root) root.StandardKline = api;
})(typeof window !== "undefined" ? window : globalThis, function(root){
  "use strict";

  const COLORS = {
    up:"#2dd4bf",
    down:"#ff6b6b",
    text:"#a4acb8",
    faint:"#788391",
    grid:"rgba(255,255,255,.07)",
    line:"rgba(255,255,255,.14)",
    gold:"#d8aa3f",
    red:"#ff6b6b",
    amber:"#f5b84b",
    panel:"rgba(8,9,11,.82)",
  };
  const DEFAULT_EMA_COLORS = ["#7aa2ff", "#f5b84b", "#c084fc", "#2dd4bf", "#ff6b6b"];
  const DEFAULT_RSI_COLOR = "#b7f566";
  const LINE_SERIES_KINDS = new Set(["rate_level", "spread"]);
  const PRESET_CONFIGS = {
    large:{preset:"large", height:640, minHeight:520, compact:false, showToolbar:true, showOhlcHeader:true, showScaleControls:true, showVolume:true, barSpacing:8, rightOffset:10, minVisibleBars:12},
    medium:{preset:"medium", height:440, minHeight:340, compact:false, showToolbar:true, showOhlcHeader:true, showScaleControls:true, showVolume:true, barSpacing:7, rightOffset:8, minVisibleBars:8},
    small:{preset:"small", height:300, minHeight:240, compact:true, showToolbar:true, showOhlcHeader:true, showScaleControls:true, showVolume:true, barSpacing:5, rightOffset:6, minVisibleBars:6},
    inset:{preset:"inset", height:180, minHeight:150, compact:true, showToolbar:false, showOhlcHeader:false, showScaleControls:false, showVolume:false, barSpacing:4, rightOffset:4, minVisibleBars:5},
    responsive:{preset:"responsive", height:380, minHeight:320, compact:false, showToolbar:true, showOhlcHeader:true, showScaleControls:true, showVolume:true, barSpacing:7, rightOffset:8, minVisibleBars:6},
  };
  const CANDLE_THEMES = {
    "green-up-red-down":{
      candleDirection:"green-up-red-down",
      up:"#2dd4bf",
      down:"#ff6b6b",
      upFill:"rgba(45,212,191,.74)",
      downFill:"rgba(255,107,107,.72)",
      upVolume:"rgba(45,212,191,.42)",
      downVolume:"rgba(255,107,107,.38)",
    },
    "red-up-green-down":{
      candleDirection:"red-up-green-down",
      up:"#ef5f7c",
      down:"#23c19f",
      upFill:"rgba(239,95,124,.72)",
      downFill:"rgba(35,193,159,.72)",
      upVolume:"rgba(239,95,124,.45)",
      downVolume:"rgba(35,193,159,.40)",
    },
  };

  function clonePlain(value){
    if(Array.isArray(value)) return value.map(clonePlain);
    if(value && typeof value === "object"){
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, clonePlain(item)]));
    }
    return value;
  }

  function getPresetConfig(preset){
    const key = String(preset || "responsive").toLowerCase();
    return clonePlain(PRESET_CONFIGS[key] || PRESET_CONFIGS.responsive);
  }

  function normalizeCandleTheme(options){
    const source = options || {};
    const theme = source.theme && typeof source.theme === "object" ? source.theme : {};
    const requested = source.candleDirection || source.candleTheme || theme.candleDirection || source.theme;
    const key = typeof requested === "string" ? requested : "green-up-red-down";
    const base = clonePlain(CANDLE_THEMES[key] || CANDLE_THEMES["green-up-red-down"]);
    const hollowUp = source.hollowUp ?? theme.hollowUp ?? true;
    const filledDown = source.filledDown ?? theme.filledDown ?? true;
    const up = source.upColor || theme.upColor || base.up;
    const down = source.downColor || theme.downColor || base.down;
    return {
      ...base,
      up,
      down,
      hollowUp:Boolean(hollowUp),
      filledDown:Boolean(filledDown),
      upColor:Boolean(hollowUp) ? "transparent" : (source.upFill || theme.upFill || base.upFill),
      downColor:Boolean(filledDown) ? (source.downFill || theme.downFill || base.downFill) : "transparent",
      borderUpColor:source.borderUpColor || theme.borderUpColor || up,
      borderDownColor:source.borderDownColor || theme.borderDownColor || down,
      wickUpColor:source.wickUpColor || theme.wickUpColor || up,
      wickDownColor:source.wickDownColor || theme.wickDownColor || down,
      volumeUpColor:source.volumeUpColor || theme.volumeUpColor || base.upVolume,
      volumeDownColor:source.volumeDownColor || theme.volumeDownColor || base.downVolume,
    };
  }

  function createStandardKlineOptions(options){
    const requested = options || {};
    const preset = getPresetConfig(requested.preset);
    const merged = {...preset, ...requested};
    merged.preset = preset.preset;
    merged.candleTheme = normalizeCandleTheme(merged);
    if(!merged.indicators) merged.indicators = {};
    return merged;
  }

  function defaultAgentDeploymentOptions(){
    return createStandardKlineOptions({
      preset:"responsive",
      candleDirection:"green-up-red-down",
      hollowUp:true,
      filledDown:true,
      indicators:{},
    });
  }

  function normalizeQualityFlags(value){
    if(Array.isArray(value)) return value.map(item => String(item || "").trim()).filter(Boolean);
    if(value == null || value === "") return [];
    return String(value).split(/[,\s|]+/).map(item => item.trim()).filter(Boolean);
  }

  function normalizeRenderMode(value){
    const requested = String(value || "").trim().toLowerCase();
    return requested === "line" || LINE_SERIES_KINDS.has(requested) ? "line" : "candles";
  }

  function toEpochSeconds(value){
    if(value == null || value === "") return null;
    if(typeof value === "number" && Number.isFinite(value)){
      return Math.floor(value > 1e12 ? value / 1000 : value);
    }
    const text = String(value).trim();
    if(/^\d{13}$/.test(text)) return Math.floor(Number(text) / 1000);
    if(/^\d{10}$/.test(text)) return Number(text);
    const parsed = Date.parse(text);
    if(Number.isFinite(parsed)) return Math.floor(parsed / 1000);
    return null;
  }

  function numberOrNull(value){
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function booleanOrNull(value){
    if(value === true || value === false) return value;
    if(value == null || value === "") return null;
    const text = String(value).trim().toLowerCase();
    if(text === "true") return true;
    if(text === "false") return false;
    return null;
  }

  function uniqueNormalized(values){
    return Array.from(new Set(normalizeQualityFlags(values)));
  }

  function normalizeAccessIssues(value){
    if(Array.isArray(value)) return value.map(item => {
      if(typeof item === "string") return item;
      if(item?.message) return String(item.message);
      if(item?.reason) return String(item.reason);
      if(item?.code) return String(item.code);
      return JSON.stringify(item);
    }).filter(Boolean);
    if(value == null || value === "") return [];
    return [String(value)];
  }

  function clampNumber(value, min, max){
    return Math.min(max, Math.max(min, value));
  }

  function clampLogicalRange(range, barCount, options){
    if(!range || !Number.isFinite(Number(barCount)) || Number(barCount) <= 0) return null;
    let from = Number(range.from);
    let to = Number(range.to);
    if(!Number.isFinite(from) || !Number.isFinite(to)) return null;
    if(to < from) [from, to] = [to, from];

    const count = Math.max(1, Math.floor(Number(barCount)));
    const configuredBuffer = numberOrNull(options?.bufferBars);
    const buffer = Math.max(0, Math.floor(configuredBuffer ?? Math.max(8, Math.ceil(count * .12))));
    const rightOffset = Math.max(0, numberOrNull(options?.rightOffset) ?? 0);
    const minFrom = -buffer;
    const maxTo = Math.max(minFrom + 1, count - 1 + Math.max(buffer, rightOffset));
    const maxWidth = Math.max(1, maxTo - minFrom);
    const minVisibleBars = clampNumber(numberOrNull(options?.minVisibleBars) ?? 6, 1, maxWidth);

    let width = to - from;
    if(!Number.isFinite(width) || width <= 0) width = minVisibleBars;
    width = clampNumber(width, minVisibleBars, maxWidth);

    let center = (from + to) / 2;
    const minCenter = minFrom + width / 2;
    const maxCenter = maxTo - width / 2;
    if(minCenter <= maxCenter) center = clampNumber(center, minCenter, maxCenter);
    else center = (minFrom + maxTo) / 2;

    return {from:center - width / 2, to:center + width / 2};
  }

  function isSyntheticMeta(meta, syntheticFlags){
    if(!meta) return true;
    const flags = normalizeQualityFlags(meta.quality_flags).map(flag => flag.toLowerCase());
    const provider = String(meta.provider || "").toLowerCase();
    const sourceMode = String(meta.source_mode || "").toLowerCase();
    const extra = new Set(normalizeQualityFlags(syntheticFlags).map(flag => flag.toLowerCase()));
    return meta.is_synthetic === true
      || provider.includes("synthetic")
      || sourceMode.includes("synthetic")
      || flags.some(flag => extra.has(flag));
  }

  function adaptBarPayload(payload, options){
    const rows = Array.isArray(payload?.bars) ? payload.bars : [];
    const syntheticFlags = options?.syntheticFlags;
    const payloadMeta = metaFromPayload(payload);
    const byTime = new Map();
    let rejectedRows = 0;

    rows.forEach((row, index) => {
      const item = adaptOneBar(row, payloadMeta, index, options);
      if(!item){
        rejectedRows += 1;
        return;
      }
      byTime.set(item.time, item);
    });

    const sorted = Array.from(byTime.values()).sort((a,b) => a.time - b.time);
    const barMeta = sorted.map(item => item.meta);
    const mergedFlags = uniqueNormalized(payloadMeta.quality_flags.concat(barMeta.flatMap(item => item.quality_flags)));
    const meta = {
      ...payloadMeta,
      symbol:payloadMeta.symbol || barMeta.at(-1)?.symbol || "",
      ticker:payloadMeta.ticker || barMeta.at(-1)?.ticker || payloadMeta.symbol || "",
      asset_class:payloadMeta.asset_class || barMeta.at(-1)?.asset_class || "",
      timeframe:payloadMeta.timeframe || barMeta.at(-1)?.timeframe || "",
      provider:payloadMeta.provider || barMeta.at(-1)?.provider || "",
      source_mode:payloadMeta.source_mode || barMeta.at(-1)?.source_mode || "",
      quality_flags:mergedFlags,
      bar_count:sorted.length,
      latest_timestamp:payloadMeta.latest_timestamp || barMeta.at(-1)?.timestamp || "",
      rejected_rows:rejectedRows,
    };
    meta.is_synthetic = isSyntheticMeta(meta, syntheticFlags);
    const trustState = evaluateTrustPolicy(meta, options?.trustPolicy);
    return {
      candles:sorted.map(item => item.candle),
      line:payloadMeta.render_mode === "line" ? sorted.map(item => item.line).filter(Boolean) : [],
      volumes:sorted.map(item => item.volume),
      barMeta,
      meta,
      trustState,
    };
  }

  function adaptDatafeedResponse(response, options){
    const provenance = response?.provenance || {};
    const candles = Array.isArray(response?.candles)
      ? response.candles
      : (Array.isArray(response?.bars) ? response.bars : []);
    const payload = {
      schema_version:response?.schema_version || provenance.schema_version || "kline-candles-v1",
      status:response?.status || "ready",
      source_mode:response?.source_mode ?? provenance.source_mode ?? "",
      symbol:response?.symbol ?? response?.ticker ?? provenance.symbol ?? provenance.ticker ?? "",
      ticker:response?.ticker ?? provenance.ticker ?? response?.symbol ?? "",
      asset_class:response?.asset_class ?? provenance.asset_class ?? "",
      series_kind:response?.series_kind ?? provenance.series_kind ?? "price",
      unit:response?.unit ?? provenance.unit ?? "",
      price_basis:response?.price_basis ?? provenance.price_basis ?? "",
      semantic_role:response?.semantic_role ?? provenance.semantic_role ?? "",
      render_mode:response?.render_mode ?? provenance.render_mode ?? response?.series_kind ?? provenance.series_kind ?? "candles",
      timeframe:response?.timeframe ?? provenance.timeframe ?? "",
      provider:response?.provider ?? provenance.provider ?? provenance.name ?? "",
      quality_flags:uniqueNormalized([...(normalizeQualityFlags(response?.quality_flags)), ...(normalizeQualityFlags(provenance.quality_flags))]),
      is_synthetic:response?.is_synthetic === true || provenance.is_synthetic === true,
      served_from:response?.served_from ?? provenance.served_from ?? "",
      fresh:response?.fresh ?? provenance.fresh,
      latest_timestamp:response?.latest_timestamp ?? provenance.latest_timestamp ?? "",
      age_seconds:response?.age_seconds ?? provenance.age_seconds,
      max_age_seconds:response?.max_age_seconds ?? provenance.max_age_seconds,
      requested:response?.requested || {},
      access_issues:response?.access_issues ?? response?.accessIssues ?? [],
      reject_reason:response?.reject_reason || response?.rejectReason || response?.error || response?.detail || "",
      provenance,
      bars:candles.map(candle => ({
        timestamp:candle.timestamp ?? candle.time,
        open:candle.open,
        high:candle.high,
        low:candle.low,
        close:candle.close,
        value:candle.value ?? candle.close,
        volume:candle.volume ?? 0,
        provider:candle.provider ?? response?.provider ?? provenance.provider ?? provenance.name ?? "",
        quality_flags:candle.quality_flags ?? candle.qualityFlags ?? [],
        symbol:candle.symbol ?? response?.symbol ?? response?.ticker ?? "",
        ticker:candle.ticker ?? response?.ticker ?? response?.symbol ?? "",
        asset_class:candle.asset_class ?? response?.asset_class ?? "",
        timeframe:candle.timeframe ?? response?.timeframe ?? "",
        is_synthetic:candle.is_synthetic === true,
      })),
    };
    return adaptBarPayload(payload, options);
  }

  function mergeBarIntoAdaptedData(adapted, bar, options){
    const current = adapted || adaptBarPayload(null, options);
    const meta = {...(current.meta || {}), ...(options?.meta || {})};
    const item = adaptOneBar(bar, meta, current.candles?.length || 0, options);
    if(!item) return {adapted:current, action:"invalid"};
    const candles = (current.candles || []).slice();
    const line = (current.line || []).slice();
    const volumes = (current.volumes || []).slice();
    const barMeta = (current.barMeta || []).slice();
    const existingIndex = candles.findIndex(candle => Number(candle.time) === item.time);
    let action = "append";
    if(existingIndex >= 0){
      candles[existingIndex] = item.candle;
      volumes[existingIndex] = item.volume;
      barMeta[existingIndex] = item.meta;
      action = existingIndex === candles.length - 1 ? "replace-last" : "replace-historical";
    }else{
      candles.push(item.candle);
      volumes.push(item.volume);
      barMeta.push(item.meta);
      const zipped = candles.map((candle, index) => ({candle, volume:volumes[index], meta:barMeta[index]})).sort((a,b) => Number(a.candle.time) - Number(b.candle.time));
      candles.splice(0, candles.length, ...zipped.map(row => row.candle));
      volumes.splice(0, volumes.length, ...zipped.map(row => row.volume));
      barMeta.splice(0, barMeta.length, ...zipped.map(row => row.meta));
      if(candles.at(-1)?.time !== item.time) action = "insert-historical";
    }
    if(meta.render_mode === "line"){
      const linePoint = item.line || {time:item.time, value:item.candle.close};
      const lineIndex = line.findIndex(point => Number(point.time) === item.time);
      if(lineIndex >= 0) line[lineIndex] = linePoint;
      else line.push(linePoint);
      line.sort((a, b) => Number(a.time) - Number(b.time));
    }
    const nextMeta = {
      ...meta,
      bar_count:candles.length,
      latest_timestamp:barMeta.at(-1)?.timestamp || candles.at(-1)?.time || "",
      quality_flags:uniqueNormalized((meta.quality_flags || []).concat(barMeta.flatMap(item => item.quality_flags || []))),
    };
    nextMeta.is_synthetic = isSyntheticMeta(nextMeta, options?.syntheticFlags);
    const next = {
      candles,
      line,
      volumes,
      barMeta,
      meta:nextMeta,
      trustState:evaluateTrustPolicy(nextMeta, options?.trustPolicy),
    };
    return {adapted:next, action, item};
  }

  function nearestTime(candles, timestamp){
    const target = toEpochSeconds(timestamp);
    if(target == null || !candles?.length) return null;
    let best = candles[0].time;
    let bestDistance = Infinity;
    candles.forEach(candle => {
      const distance = Math.abs(Number(candle.time) - target);
      if(distance < bestDistance){
        best = candle.time;
        bestDistance = distance;
      }
    });
    return best;
  }

  function formatPrice(value, digits){
    return Number(value || 0).toLocaleString("en-US", {minimumFractionDigits:digits, maximumFractionDigits:digits});
  }

  function formatSigned(value, digits){
    const parsed = numberOrNull(value) ?? 0;
    const sign = parsed > 0 ? "+" : "";
    return `${sign}${formatPrice(parsed, digits)}`;
  }

  function calculateMovement(candles, bar){
    const rows = candles || [];
    const targetTime = Number(bar?.time);
    const index = rows.findIndex(item => Number(item.time) === targetTime);
    const previous = index > 0 ? rows[index - 1] : null;
    const base = previous?.close ?? bar?.open;
    const change = numberOrNull(bar?.close) != null && numberOrNull(base) != null ? Number(bar.close) - Number(base) : 0;
    const pct = base ? change / Number(base) * 100 : 0;
    return {change, pct, direction:change >= 0 ? "up" : "down"};
  }

  function calculateRiskReward(riskReward){
    const entry = numberOrNull(riskReward?.entry);
    const stop = numberOrNull(riskReward?.stop);
    const target = numberOrNull(riskReward?.target);
    if(entry == null || stop == null || target == null) return null;
    const risk = Math.abs(entry - stop);
    const reward = Math.abs(target - entry);
    if(risk <= 0 || reward < 0) return null;
    return {
      entry,
      stop,
      target,
      side:riskReward?.side === "short" ? "short" : "long",
      risk,
      reward,
      ratio:reward / risk,
    };
  }

  function lineStyleValue(style){
    const lwc = root.LightweightCharts || {};
    if(style === "solid") return lwc.LineStyle?.Solid ?? 0;
    if(style === "dotted") return lwc.LineStyle?.Dotted ?? 1;
    return lwc.LineStyle?.Dashed ?? 2;
  }

  function makeVolumePoint(bar, options){
    const colors = options?.volumeColors || normalizeCandleTheme(options?.candleTheme || {});
    const volume = Math.max(0, numberOrNull(bar.volume) ?? 0);
    return {
      time:bar.time,
      value:volume,
      color:bar.close >= bar.open ? colors.volumeUpColor : colors.volumeDownColor,
    };
  }

  function metaFromPayload(payload){
    const provenance = payload?.provenance || {};
    return {
      schema_version:payload?.schema_version || provenance.schema_version || "",
      status:payload?.status || "",
      symbol:payload?.symbol ?? payload?.ticker ?? provenance.symbol ?? provenance.ticker ?? "",
      ticker:payload?.ticker ?? provenance.ticker ?? payload?.symbol ?? "",
      asset_class:payload?.asset_class ?? provenance.asset_class ?? "",
      series_kind:payload?.series_kind ?? provenance.series_kind ?? "price",
      unit:payload?.unit ?? provenance.unit ?? "",
      price_basis:payload?.price_basis ?? provenance.price_basis ?? "",
      semantic_role:payload?.semantic_role ?? provenance.semantic_role ?? "",
      render_mode:normalizeRenderMode(payload?.render_mode ?? provenance.render_mode ?? payload?.series_kind ?? provenance.series_kind),
      timeframe:payload?.timeframe ?? provenance.timeframe ?? "",
      provider:payload?.provider ?? provenance.provider ?? provenance.name ?? "",
      source_mode:payload?.source_mode ?? provenance.source_mode ?? "",
      quality_flags:uniqueNormalized([...(normalizeQualityFlags(payload?.quality_flags)), ...(normalizeQualityFlags(provenance.quality_flags))]),
      is_synthetic:payload?.is_synthetic === true || provenance.is_synthetic === true,
      served_from:payload?.served_from ?? provenance.served_from ?? "",
      fresh:booleanOrNull(payload?.fresh ?? provenance.fresh),
      requested:payload?.requested || {},
      latest_timestamp:payload?.latest_timestamp ?? provenance.latest_timestamp ?? "",
      age_seconds:numberOrNull(payload?.age_seconds ?? provenance.age_seconds),
      max_age_seconds:numberOrNull(payload?.max_age_seconds ?? provenance.max_age_seconds),
      access_issues:normalizeAccessIssues(payload?.access_issues ?? payload?.accessIssues),
      reject_reason:payload?.reject_reason || payload?.rejectReason || payload?.error || payload?.detail || "",
      provenance,
    };
  }

  function adaptOneBar(row, payloadMeta, index, options){
    const time = toEpochSeconds(row?.timestamp ?? row?.time);
    const open = numberOrNull(row?.open);
    const high = numberOrNull(row?.high);
    const low = numberOrNull(row?.low);
    const close = numberOrNull(row?.close);
    if(time == null || open == null || high == null || low == null || close == null) return null;
    const normalized = {time, open, high, low, close, volume:Math.max(0, numberOrNull(row?.volume) ?? 0)};
    const qualityFlags = uniqueNormalized([...(normalizeQualityFlags(row?.quality_flags)), ...(normalizeQualityFlags(row?.qualityFlags))]);
    const lineValue = numberOrNull(row?.value ?? close);
    return {
      time,
      sourceIndex:index,
      candle:{time, open, high, low, close},
      line:lineValue == null ? null : {time, value:lineValue},
      volume:makeVolumePoint(normalized, options),
      meta:{
        symbol:row?.symbol ?? payloadMeta.symbol ?? "",
        ticker:row?.ticker ?? payloadMeta.ticker ?? payloadMeta.symbol ?? "",
        asset_class:row?.asset_class ?? payloadMeta.asset_class ?? "",
        timeframe:row?.timeframe ?? payloadMeta.timeframe ?? "",
        timestamp:row?.timestamp ?? row?.time ?? "",
        provider:row?.provider ?? payloadMeta.provider ?? "",
        source_mode:row?.source_mode ?? payloadMeta.source_mode ?? "",
        quality_flags:qualityFlags,
        is_synthetic:row?.is_synthetic === true || payloadMeta.is_synthetic === true,
      },
    };
  }

  function evaluateTrustPolicy(meta, trustPolicy){
    const policy = trustPolicy || {};
    const reasons = [];
    const flags = normalizeQualityFlags(meta?.quality_flags).map(flag => flag.toLowerCase());
    const mode = String(meta?.source_mode || "").trim();
    const servedFrom = String(meta?.served_from || "").trim().toLowerCase();
    const synthetic = meta?.is_synthetic === true;

    if(policy.requireFresh === true && booleanOrNull(meta?.fresh) !== true){
      reasons.push({code:"fresh_required", message:"payload fresh=true is required"});
    }
    if(policy.allowSynthetic === false && synthetic){
      reasons.push({code:"synthetic_forbidden", message:"synthetic payload is not allowed"});
    }
    if(policy.allowCache === false && (servedFrom === "cache" || servedFrom === "cached")){
      reasons.push({code:"cache_forbidden", message:"cached payload is not allowed"});
    }
    const forbidden = normalizeQualityFlags(policy.forbiddenQualityFlags).map(flag => flag.toLowerCase());
    forbidden.forEach(flag => {
      if(flags.includes(flag)) reasons.push({code:"quality_flag_forbidden", flag, message:`quality flag forbidden: ${flag}`});
    });
    const allowedModes = normalizeQualityFlags(policy.allowedSourceModes);
    if(allowedModes.length){
      const allowed = new Set(allowedModes.map(item => item.toLowerCase()));
      if(!mode || !allowed.has(mode.toLowerCase())){
        reasons.push({code:"source_mode_not_allowed", source_mode:mode, message:`source_mode not allowed: ${mode || "missing"}`});
      }
    }

    return {
      trusted:reasons.length === 0,
      blocked:reasons.length > 0,
      reasons,
      policy:{...policy},
      meta:{...meta, quality_flags:normalizeQualityFlags(meta?.quality_flags)},
    };
  }

  function formatTrustReasons(reasons){
    return (reasons || []).map(reason => reason.message || reason.code || String(reason)).join("; ");
  }

  function describeEmptyMeta(meta){
    const issues = normalizeAccessIssues(meta?.access_issues);
    const reject = meta?.reject_reason ? [String(meta.reject_reason)] : [];
    const details = issues.concat(reject);
    return details.length ? details.join("; ") : "No valid OHLCV bars were provided to the standard adapter.";
  }

  function calculateEmaData(candles, period){
    const parsedPeriod = Math.max(1, Math.floor(numberOrNull(period) ?? 0));
    if(!candles?.length || !parsedPeriod) return [];
    const multiplier = 2 / (parsedPeriod + 1);
    let ema = null;
    let sum = 0;
    const out = [];
    candles.forEach((bar, index) => {
      const close = numberOrNull(bar.close);
      if(close == null) return;
      if(index < parsedPeriod - 1){
        sum += close;
        return;
      }
      if(index === parsedPeriod - 1){
        sum += close;
        ema = sum / parsedPeriod;
      }else{
        ema = (close - ema) * multiplier + ema;
      }
      out.push({time:bar.time, value:Number(ema.toFixed(6))});
    });
    return out;
  }

  function calculateMacdData(candles, options){
    const fast = Math.max(1, Math.floor(numberOrNull(options?.fastPeriod) ?? 12));
    const slow = Math.max(fast + 1, Math.floor(numberOrNull(options?.slowPeriod) ?? 26));
    const signalPeriod = Math.max(1, Math.floor(numberOrNull(options?.signalPeriod) ?? 9));
    const fastData = calculateEmaData(candles, fast);
    const slowData = calculateEmaData(candles, slow);
    const fastByTime = new Map(fastData.map(point => [point.time, point.value]));
    const macdRaw = slowData.map(point => {
      const fastValue = fastByTime.get(point.time);
      if(fastValue == null) return null;
      return {time:point.time, close:fastValue - point.value};
    }).filter(Boolean);
    const signalInput = macdRaw.map(item => ({time:item.time, close:item.close}));
    const signal = calculateEmaData(signalInput, signalPeriod);
    const signalByTime = new Map(signal.map(point => [point.time, point.value]));
    const macd = macdRaw.map(item => ({time:item.time, value:Number(item.close.toFixed(6))}));
    const histogram = macdRaw.map(item => {
      const signalValue = signalByTime.get(item.time);
      if(signalValue == null) return null;
      const value = item.close - signalValue;
      return {time:item.time, value:Number(value.toFixed(6)), color:value >= 0 ? "rgba(45,212,191,.45)" : "rgba(255,107,107,.42)"};
    }).filter(Boolean);
    return {macd, signal, histogram};
  }

  function calculateRsiData(candles, period){
    const parsedPeriod = Math.max(1, Math.floor(numberOrNull(period) ?? 14));
    const closes = (candles || []).map(bar => numberOrNull(bar.close));
    const out = [];
    if(closes.length <= parsedPeriod || closes.some(value => value == null)) return out;

    let gain = 0;
    let loss = 0;
    for(let index = 1; index <= parsedPeriod; index += 1){
      const change = closes[index] - closes[index - 1];
      if(change >= 0) gain += change;
      else loss -= change;
    }
    let averageGain = gain / parsedPeriod;
    let averageLoss = loss / parsedPeriod;
    const firstValue = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
    out.push({time:candles[parsedPeriod].time, value:Number(firstValue.toFixed(6))});

    for(let index = parsedPeriod + 1; index < closes.length; index += 1){
      const change = closes[index] - closes[index - 1];
      const currentGain = Math.max(0, change);
      const currentLoss = Math.max(0, -change);
      averageGain = ((averageGain * (parsedPeriod - 1)) + currentGain) / parsedPeriod;
      averageLoss = ((averageLoss * (parsedPeriod - 1)) + currentLoss) / parsedPeriod;
      const value = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
      out.push({time:candles[index].time, value:Number(value.toFixed(6))});
    }
    return out;
  }

  function recolorVolumes(candles, volumes, candleTheme){
    const colors = candleTheme || normalizeCandleTheme({});
    const byTime = new Map((candles || []).map(candle => [Number(candle.time), candle]));
    return (volumes || []).map(volume => {
      const candle = byTime.get(Number(volume.time));
      if(!candle) return volume;
      return {
        ...volume,
        color:candle.close >= candle.open ? colors.volumeUpColor : colors.volumeDownColor,
      };
    });
  }

  function injectStyles(){
    if(!root.document || root.document.getElementById("standard-kline-styles")) return;
    const style = root.document.createElement("style");
    style.id = "standard-kline-styles";
    style.textContent = `
.standard-kline-root{position:relative;width:100%;height:100%;min-height:320px;display:grid;grid-template-rows:auto minmax(0,1fr);background:transparent;overflow:hidden}
.standard-kline-root.compact{min-height:220px}
.standard-kline-toolbar{display:flex;align-items:center;gap:6px;min-height:30px;padding:6px 8px;border-bottom:1px solid rgba(255,255,255,.08);font:11px/1.2 var(--mono,"SFMono-Regular",ui-monospace,monospace);color:${COLORS.faint};background:rgba(255,255,255,.018)}
.standard-kline-toolbar button{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:${COLORS.text};border-radius:5px;padding:3px 8px;cursor:pointer;font:inherit}
.standard-kline-toolbar button:hover{border-color:rgba(216,170,63,.45);color:${COLORS.gold}}
.standard-kline-source{margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:58%;color:${COLORS.faint}}
.standard-kline-canvas{position:relative;min-width:0;min-height:0}
.standard-kline-canvas.is-dragging-price-line{cursor:ns-resize}
.standard-kline-ohlc{position:absolute;top:8px;left:10px;z-index:3;display:flex;align-items:center;gap:7px;max-width:calc(100% - 190px);padding:3px 6px;border:1px solid rgba(255,255,255,.10);background:rgba(8,9,11,.72);backdrop-filter:blur(8px);color:${COLORS.text};font:11px/1.2 var(--mono,"SFMono-Regular",ui-monospace,monospace);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none}
.standard-kline-canvas.has-trade-controls .standard-kline-ohlc{left:118px;max-width:calc(100% - 300px)}
.standard-kline-ohlc .is-up{color:${COLORS.up}}
.standard-kline-ohlc .is-down{color:${COLORS.down}}
.standard-kline-actionbar{position:absolute;top:8px;left:10px;z-index:3;display:flex;gap:6px}
.standard-kline-actionbar button,.standard-kline-scale-controls button{border:1px solid rgba(255,255,255,.16);background:rgba(8,9,11,.82);color:${COLORS.text};border-radius:5px;min-width:28px;height:24px;padding:0 8px;font:700 11px/1 var(--mono,"SFMono-Regular",ui-monospace,monospace);cursor:pointer}
.standard-kline-actionbar button[data-side="long"]{border-color:rgba(45,212,191,.42);color:${COLORS.up}}
.standard-kline-actionbar button[data-side="short"]{border-color:rgba(255,107,107,.42);color:${COLORS.down}}
.standard-kline-actionbar button:hover,.standard-kline-scale-controls button:hover,.standard-kline-scale-controls button.is-active{border-color:rgba(216,170,63,.62);color:${COLORS.gold}}
.standard-kline-scale-controls{position:absolute;right:10px;bottom:10px;z-index:3;display:flex;gap:5px}
.standard-kline-risk-reward{position:absolute;z-index:2;display:none;pointer-events:none;font:11px/1.15 var(--mono,"SFMono-Regular",ui-monospace,monospace)}
.standard-kline-risk-reward.is-visible{display:block}
.standard-kline-risk-zone{position:absolute;left:0;right:0;border:1px solid rgba(255,255,255,.20)}
.standard-kline-risk-zone.reward{background:rgba(45,212,191,.12);border-color:rgba(45,212,191,.34)}
.standard-kline-risk-zone.risk{background:rgba(255,107,107,.16);border-color:rgba(255,107,107,.36)}
.standard-kline-risk-label{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);padding:5px 7px;border-radius:5px;background:rgba(8,9,11,.76);color:${COLORS.text};text-align:center;white-space:nowrap;box-shadow:0 8px 24px rgba(0,0,0,.25)}
.standard-kline-overlay{position:absolute;inset:32px 14px 14px 14px;display:none;place-items:center;text-align:center;pointer-events:none;z-index:4}
.standard-kline-overlay.is-visible{display:grid}
.standard-kline-overlay[data-state="blocked"]{pointer-events:auto}
.standard-kline-message{max-width:min(520px,94%);border:1px solid rgba(255,255,255,.15);background:${COLORS.panel};box-shadow:0 16px 48px rgba(0,0,0,.34);padding:14px 18px;color:${COLORS.text};font:12px/1.45 var(--mono,"SFMono-Regular",ui-monospace,monospace)}
.standard-kline-message b{display:block;font-size:18px;color:${COLORS.red};margin-bottom:4px;letter-spacing:0}
.standard-kline-message span{color:#ffb3b3}
.standard-kline-empty .standard-kline-message b{color:${COLORS.amber}}
.standard-kline-blocked .standard-kline-message{border-color:rgba(255,107,107,.44);background:rgba(34,8,10,.92)}
.standard-kline-root.light{background:#fffefa;color:#17201b}
.standard-kline-root.light .standard-kline-toolbar{border-color:#dedfd8;color:#68736b;background:#f7f9f5}
.standard-kline-root.light .standard-kline-toolbar button,.standard-kline-root.light .standard-kline-actionbar button,.standard-kline-root.light .standard-kline-scale-controls button{border-color:#cfd7d0;background:#fff;color:#526779}
.standard-kline-root.light .standard-kline-toolbar button:hover,.standard-kline-root.light .standard-kline-actionbar button:hover,.standard-kline-root.light .standard-kline-scale-controls button:hover,.standard-kline-root.light .standard-kline-scale-controls button.is-active{border-color:#187b51;color:#187b51}
.standard-kline-root.light .standard-kline-source{color:#87918b}
.standard-kline-root.light .standard-kline-ohlc{border-color:#dedfd8;background:rgba(255,255,255,.92);color:#526779}
.standard-kline-root.light .standard-kline-ohlc .is-up{color:#187b51}
.standard-kline-root.light .standard-kline-ohlc .is-down{color:#c94640}
.standard-kline-root.light .standard-kline-message{border-color:#dedfd8;background:#fff;color:#526779;box-shadow:0 16px 48px rgba(23,32,27,.12)}
.standard-kline-root.light .standard-kline-message span{color:#8a4b47}
.standard-kline-root.light .standard-kline-empty .standard-kline-message b{color:#a36c14}
.standard-kline-root.light .standard-kline-blocked .standard-kline-message{border-color:#e6b5b1;background:#fff5f3}
`;
    root.document.head.appendChild(style);
  }

  class StandardKlineChart {
    constructor(container, options){
      if(!root.document) throw new Error("StandardKlineChart requires a browser document");
      this.container = typeof container === "string" ? root.document.querySelector(container) : container;
      if(!this.container) throw new Error("StandardKlineChart container not found");
      this.options = createStandardKlineOptions(options);
      this.candleTheme = this.options.candleTheme;
      this.renderMode = normalizeRenderMode(this.options.renderMode || this.options.series_kind || this.options.seriesKind);
      this.chart = null;
      this.libraryAvailable = false;
      this.candleSeries = null;
      this.lineSeries = null;
      this.volumeSeries = null;
      this.markerApi = null;
      this.priceLines = [];
      this.priceLineItems = [];
      this.indicatorSeries = {ema:new Map(), macd:null, rsi:null};
      this.indicatorOptions = null;
      this.lastOverlays = {};
      this.trustPolicy = this.options.trustPolicy || null;
      this.current = adaptBarPayload(null, {syntheticFlags:this.options.syntheticFlags, trustPolicy:this.trustPolicy, candleTheme:this.candleTheme, volumeColors:this.candleTheme});
      this.trustState = this.current.trustState;
      this.resizeObserver = null;
      this.loading = false;
      this.destroyed = false;
      this.dragState = null;
      this.logScale = this.options.logScale === true;
      this.autoFit = this.options.autoFit === true;
      this.currentRiskReward = null;
      this._timeScale = null;
      this._nativeSetVisibleLogicalRange = null;
      this._nativeGetVisibleLogicalRange = null;
      this._boundMouseDown = event => this._onMouseDown(event);
      this._boundMouseMove = event => this._onMouseMove(event);
      this._boundMouseUp = event => this._onMouseUp(event);
      this._boundVisibleRangeChange = () => this._updateRiskRewardOverlay();
      this._boundCrosshairMove = param => this._onCrosshairMove(param);
      injectStyles();
      this._buildDom();
      this._initChart();
    }

    _buildDom(){
      this.container.innerHTML = "";
      this.rootEl = root.document.createElement("div");
      const appearance = String(this.options.appearance || this.options.surface || "dark").toLowerCase();
      this.rootEl.className = `standard-kline-root${this.options.compact ? " compact" : ""}${appearance === "light" ? " light" : ""}`;
      this.rootEl.dataset.standardKline = "true";
      this.rootEl.dataset.preset = this.options.preset || "responsive";
      if(this.options.minHeight) this.rootEl.style.minHeight = `${this.options.minHeight}px`;
      this.toolbarEl = root.document.createElement("div");
      this.toolbarEl.className = "standard-kline-toolbar";
      this.toolbarEl.innerHTML = `<button type="button" data-action="zoom-in" title="Zoom in">+</button><button type="button" data-action="zoom-out" title="Zoom out">-</button><button type="button" data-action="pan-left" title="Pan left">&lt;</button><button type="button" data-action="pan-right" title="Pan right">&gt;</button><button type="button" data-action="fit" title="Fit">fit</button><span class="standard-kline-source" data-source></span>`;
      this.chartEl = root.document.createElement("div");
      this.chartEl.className = "standard-kline-canvas";
      this.ohlcEl = root.document.createElement("div");
      this.ohlcEl.className = "standard-kline-ohlc";
      this.ohlcEl.dataset.standardKlineOhlc = "true";
      this.ohlcEl.textContent = "O -- H -- L -- C --";
      this.actionbarEl = root.document.createElement("div");
      this.actionbarEl.className = "standard-kline-actionbar";
      this.actionbarEl.innerHTML = `<button type="button" data-side="long" title="Long">Long</button><button type="button" data-side="short" title="Short">Short</button>`;
      this.scaleControlsEl = root.document.createElement("div");
      this.scaleControlsEl.className = "standard-kline-scale-controls";
      this.scaleControlsEl.innerHTML = `<button type="button" data-scale-action="auto" title="Auto fit">A</button><button type="button" data-scale-action="log" title="Log scale">L</button>`;
      this.riskRewardEl = root.document.createElement("div");
      this.riskRewardEl.className = "standard-kline-risk-reward";
      this.riskRewardEl.dataset.standardKlineRiskReward = "true";
      this.riskRewardEl.innerHTML = `<div class="standard-kline-risk-zone reward"></div><div class="standard-kline-risk-zone risk"></div><div class="standard-kline-risk-label"></div>`;
      this.overlayEl = root.document.createElement("div");
      this.overlayEl.className = "standard-kline-overlay";
      this.overlayEl.dataset.standardKlineOverlay = "true";
      this.overlayEl.innerHTML = `<div class="standard-kline-message"><b></b><span></span></div>`;
      if(this.options.showToolbar !== false) this.rootEl.appendChild(this.toolbarEl);
      this.rootEl.appendChild(this.chartEl);
      this.rootEl.appendChild(this.overlayEl);
      this.container.appendChild(this.rootEl);
      const hasTradeControls = this.options.showTradeControls === true || this.options.tradeControls === true;
      if(hasTradeControls) this.chartEl.classList.add("has-trade-controls");
      if(this.options.showOhlcHeader !== false) this.chartEl.appendChild(this.ohlcEl);
      if(hasTradeControls) this.chartEl.appendChild(this.actionbarEl);
      if(this.options.showScaleControls !== false) this.chartEl.appendChild(this.scaleControlsEl);
      this.chartEl.appendChild(this.riskRewardEl);
      this.toolbarEl.addEventListener("click", event => {
        const action = event.target?.closest?.("button[data-action]")?.dataset?.action;
        if(!action) return;
        if(action === "zoom-in") this.zoom(0.72);
        if(action === "zoom-out") this.zoom(1.38);
        if(action === "pan-left") this.pan(-12);
        if(action === "pan-right") this.pan(12);
        if(action === "fit") this.fit();
      });
      this.chartEl.addEventListener("mousedown", this._boundMouseDown);
      this.actionbarEl.addEventListener("click", event => {
        const side = event.target?.closest?.("button[data-side]")?.dataset?.side;
        if(side) this._emitTradeAction(side);
      });
      this.scaleControlsEl.addEventListener("click", event => {
        const action = event.target?.closest?.("button[data-scale-action]")?.dataset?.scaleAction;
        if(action === "auto") this.setAutoFit(!this.autoFit);
        if(action === "log") this.setLogScale(!this.logScale);
      });
      root.document.addEventListener("mousemove", this._boundMouseMove);
      root.document.addEventListener("mouseup", this._boundMouseUp);
    }

    _priceScaleMode(){
      const lwc = root.LightweightCharts || {};
      return this.logScale ? (lwc.PriceScaleMode?.Logarithmic ?? 1) : (lwc.PriceScaleMode?.Normal ?? 0);
    }

    _initChart(){
      const lwc = root.LightweightCharts;
      if(!lwc?.createChart){
        this.libraryAvailable = false;
        this._setOverlay("empty", "CHART LIBRARY MISSING", "window.LightweightCharts is not loaded (peer dependency).");
        return;
      }
      const size = this._size();
      const light = String(this.options.appearance || this.options.surface || "dark").toLowerCase() === "light";
      this.chart = lwc.createChart(this.chartEl, {
        width:size.width,
        height:size.height,
        layout:{background:{type:"solid", color:"transparent"}, textColor:this.options.textColor || (light ? "#68736b" : COLORS.text), fontSize:11, attributionLogo:false},
        grid:{vertLines:{color:this.options.gridColor || (light ? "rgba(23,32,27,.08)" : "rgba(255,255,255,.045)")}, horzLines:{color:this.options.gridColor || (light ? "rgba(23,32,27,.10)" : COLORS.grid)}},
        crosshair:{mode:lwc.CrosshairMode?.Normal ?? 1},
        rightPriceScale:{borderVisible:true, borderColor:light ? "rgba(23,32,27,.18)" : "rgba(255,255,255,.18)", minimumWidth:46, mode:this._priceScaleMode(), scaleMargins:{top:.08,bottom:this.options.showVolume === false ? .10 : .28}},
        timeScale:{visible:true, borderVisible:true, borderColor:light ? "rgba(23,32,27,.20)" : "rgba(255,255,255,.20)", timeVisible:true, secondsVisible:false, rightOffset:this.options.rightOffset ?? 8, barSpacing:this.options.barSpacing || (this.options.compact ? 5 : 7), minBarSpacing:.5, rightBarStaysOnScroll:true, ticksVisible:true},
        handleScroll:{mouseWheel:true, pressedMouseMove:true, horzTouchDrag:true, vertTouchDrag:true},
        handleScale:{axisPressedMouseMove:true, mouseWheel:true, pinch:true},
        localization:{priceFormatter:price => formatPrice(price,2)},
      });
      this.libraryAvailable = true;
      this._patchTimeScale();
      this._createPrimarySeries();
      this.chart.subscribeCrosshairMove?.(this._boundCrosshairMove);
      this._timeScale?.subscribeVisibleLogicalRangeChange?.(this._boundVisibleRangeChange);
      this._refreshScaleControlState();
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(this.container);
      this.resize();
    }

    _createPrimarySeries(){
      const lwc = root.LightweightCharts || {};
      if(this.renderMode === "line"){
        this.lineSeries = this.chart.addSeries(lwc.LineSeries, {
          color:this.options.lineColor || "#526779",
          lineWidth:Math.max(1, numberOrNull(this.options.lineWidth) ?? 2),
          priceLineVisible:false,
          lastValueVisible:true,
          title:this.options.lineTitle || "",
          priceFormat:{type:"price", precision:2, minMove:.01},
        });
        this.lineSeries.priceScale().applyOptions({scaleMargins:{top:.08,bottom:.10}});
        this.volumeSeries = null;
        this.markerApi = lwc.createSeriesMarkers ? lwc.createSeriesMarkers(this.lineSeries, []) : null;
        return;
      }
      this.candleSeries = this.chart.addSeries(lwc.CandlestickSeries, {
        upColor:this.candleTheme.upColor,
        downColor:this.candleTheme.downColor,
        borderUpColor:this.candleTheme.borderUpColor,
        borderDownColor:this.candleTheme.borderDownColor,
        wickUpColor:this.candleTheme.wickUpColor,
        wickDownColor:this.candleTheme.wickDownColor,
        priceLineVisible:false,
        lastValueVisible:true,
        priceFormat:{type:"price", precision:2, minMove:.01},
      });
      this.candleSeries.priceScale().applyOptions({scaleMargins:{top:.08,bottom:this.options.showVolume === false ? .10 : .28}});
      if(this.options.showVolume !== false){
        this.volumeSeries = this.chart.addSeries(lwc.HistogramSeries, {
          priceFormat:{type:"volume"},
          priceScaleId:"",
          priceLineVisible:false,
          lastValueVisible:false,
        });
        this.volumeSeries.priceScale().applyOptions({scaleMargins:{top:.78,bottom:.02}});
      }
      if(lwc.createSeriesMarkers) this.markerApi = lwc.createSeriesMarkers(this.candleSeries, []);
    }

    _ensureRenderMode(mode){
      const nextMode = normalizeRenderMode(mode);
      if(nextMode === this.renderMode || !this.chart) return;
      if(this.candleSeries) this.chart.removeSeries?.(this.candleSeries);
      if(this.lineSeries) this.chart.removeSeries?.(this.lineSeries);
      if(this.volumeSeries) this.chart.removeSeries?.(this.volumeSeries);
      this.candleSeries = null;
      this.lineSeries = null;
      this.volumeSeries = null;
      this.markerApi = null;
      this.renderMode = nextMode;
      this._createPrimarySeries();
    }

    _patchTimeScale(){
      if(!this.chart?.timeScale) return;
      const nativeTimeScale = this.chart.timeScale.bind(this.chart);
      const timeScale = nativeTimeScale();
      if(!timeScale) return;
      this._timeScale = timeScale;
      this._nativeSetVisibleLogicalRange = timeScale.setVisibleLogicalRange?.bind(timeScale) || null;
      this._nativeGetVisibleLogicalRange = timeScale.getVisibleLogicalRange?.bind(timeScale) || null;
      const owner = this;
      if(this._nativeSetVisibleLogicalRange){
        timeScale.setVisibleLogicalRange = function(range){
          return owner._setVisibleLogicalRange(range);
        };
      }
      if(timeScale.fitContent){
        timeScale.fitContent = function(){
          return owner.fit();
        };
      }
    }

    _size(){
      const containerRect = this.container.getBoundingClientRect();
      const chartRect = this.chartEl?.getBoundingClientRect?.() || {};
      const toolbarHeight = this.toolbarEl?.getBoundingClientRect?.().height || 0;
      const width = Math.max(260, Math.floor(containerRect.width || chartRect.width || this.options.width || 640));
      const availableHeight = chartRect.height || (containerRect.height ? containerRect.height - toolbarHeight : 0) || this.options.height || 380;
      const minHeight = numberOrNull(this.options.minHeight) ?? (this.options.compact ? 220 : 320);
      const height = Math.max(minHeight, Math.floor(availableHeight));
      return {width, height};
    }

    resize(){
      if(!this.chart || this.destroyed) return;
      const size = this._size();
      this.chart.applyOptions({width:size.width, height:size.height});
      this._updateRiskRewardOverlay();
    }

    setLoading(loading, message){
      this.loading = Boolean(loading);
      if(this.loading) this._setOverlay("loading", "LOADING KLINE", message || "Waiting for OHLCV bars.");
      else this._refreshOverlay();
    }

    /**
     * Adapt a raw OHLCV payload and render it in one call.
     * `overlays.priceLines` / `overlays.markers` are generic arrays this
     * chart draws as-is — build them from your own domain model (trade
     * plans, fills, alerts, ...) before calling this.
     */
    setPayload(payload, overlays){
      const adapted = adaptBarPayload(payload, {syntheticFlags:this.options.syntheticFlags, trustPolicy:this.trustPolicy, candleTheme:this.candleTheme, volumeColors:this.candleTheme});
      return this.setAdaptedData(adapted, overlays);
    }

    /** Load a normalized datafeed CandleResponse through the canonical adapter. */
    setDatafeedResponse(response, overlays){
      const adapted = adaptDatafeedResponse(response, {syntheticFlags:this.options.syntheticFlags, trustPolicy:this.trustPolicy, candleTheme:this.candleTheme, volumeColors:this.candleTheme});
      return this.setAdaptedData(adapted, overlays);
    }

    setAdaptedData(adapted, overlays){
      this.lastOverlays = overlays || {};
      this.current = adapted || adaptBarPayload(null, {syntheticFlags:this.options.syntheticFlags, trustPolicy:this.trustPolicy});
      if(!this.current.trustState) this.current.trustState = evaluateTrustPolicy(this.current.meta, this.trustPolicy);
      this.trustState = this.current.trustState;
      this._ensureRenderMode(this.current.meta?.render_mode);
      const candles = this.current.candles || [];
      if(this.renderMode === "line"){
        const line = this.current.line?.length ? this.current.line : candles.map(item => ({time:item.time, value:item.close}));
        this.lineSeries?.setData(line);
      }else{
        if(this.candleSeries) this.candleSeries.setData(candles);
        if(this.volumeSeries) this.volumeSeries.setData(recolorVolumes(candles, this.current.volumes || [], this.candleTheme));
      }
      this._setPriceLines(this.lastOverlays?.priceLines || []);
      this._setMarkers(this.lastOverlays?.markers || []);
      this._setRiskReward(this.lastOverlays?.riskReward || this.lastOverlays?.risk_reward || null);
      this._applyIndicators(this.lastOverlays?.indicators);
      this._updateOhlcHeader(this.renderMode === "line" ? this.current.line?.at(-1) : candles.at(-1));
      this._setSourceText(this.current.meta);
      this._refreshOverlay();
      if(this._barCount() && this.lastOverlays?.fit !== false) this.fit();
      return this.current;
    }

    replaceBars(payload, overlays){
      return this.setPayload(payload, overlays === undefined ? this.lastOverlays : overlays);
    }

    updateBar(bar){
      const merged = mergeBarIntoAdaptedData(this.current, bar, {
        syntheticFlags:this.options.syntheticFlags,
        trustPolicy:this.trustPolicy,
        candleTheme:this.candleTheme,
        volumeColors:this.candleTheme,
      });
      if(merged.action === "invalid") return null;
      this.current = merged.adapted;
      this.trustState = this.current.trustState;
      if(this.renderMode === "line" && this.lineSeries){
        const linePoint = merged.item.line || {time:merged.item.time, value:merged.item.candle?.close};
        if(merged.action === "append" || merged.action === "replace-last"){
          this.lineSeries.update(linePoint);
        }else{
          this.lineSeries.setData(this.current.line || []);
        }
      }else if(this.candleSeries){
        if(merged.action === "append" || merged.action === "replace-last"){
          this.candleSeries.update(merged.item.candle);
        }else{
          this.candleSeries.setData(this.current.candles);
        }
      }
      if(this.volumeSeries){
        if(merged.action === "append" || merged.action === "replace-last"){
          this.volumeSeries.update(merged.item.volume);
        }else{
          this.volumeSeries.setData(this.current.volumes || []);
        }
      }
      this._applyIndicators(this.lastOverlays?.indicators);
      this._setRiskReward(this.lastOverlays?.riskReward || this.lastOverlays?.risk_reward || null);
      this._updateOhlcHeader(this.renderMode === "line" ? this.current.line?.at(-1) : this.current.candles.at(-1));
      this._setSourceText(this.current.meta);
      this._refreshOverlay();
      if(this.autoFit) this.fit();
      return this.current;
    }

    appendBars(bars){
      const rows = Array.isArray(bars) ? bars : [];
      let latest = this.current;
      rows.forEach(row => {
        const next = this.updateBar(row);
        if(next) latest = next;
      });
      return latest;
    }

    getTrustState(){
      return this.trustState || evaluateTrustPolicy(this.current?.meta, this.trustPolicy);
    }

    setTrustPolicy(trustPolicy){
      this.trustPolicy = trustPolicy || null;
      this.current.trustState = evaluateTrustPolicy(this.current.meta, this.trustPolicy);
      this.trustState = this.current.trustState;
      this._refreshOverlay();
      return this.trustState;
    }

    setAutoFit(enabled){
      this.autoFit = Boolean(enabled);
      if(this.autoFit) this.fit();
      (this.candleSeries || this.lineSeries)?.priceScale?.()?.applyOptions?.({autoScale:true});
      this._refreshScaleControlState();
      this._updateRiskRewardOverlay();
      return this.autoFit;
    }

    setLogScale(enabled){
      this.logScale = Boolean(enabled);
      (this.candleSeries || this.lineSeries)?.priceScale?.()?.applyOptions?.({mode:this._priceScaleMode()});
      this.chart?.applyOptions?.({rightPriceScale:{mode:this._priceScaleMode()}});
      this._refreshScaleControlState();
      this._updateRiskRewardOverlay();
      return this.logScale;
    }

    _setMarkers(markers){
      const sorted = (markers || []).slice().sort((a,b) => Number(a.time) - Number(b.time));
      if(this.markerApi?.setMarkers) this.markerApi.setMarkers(sorted);
      else if(this.candleSeries?.setMarkers) this.candleSeries.setMarkers(sorted);
      else if(this.lineSeries?.setMarkers) this.lineSeries.setMarkers(sorted);
    }

    _setPriceLines(lines){
      const primarySeries = this.candleSeries || this.lineSeries;
      if(primarySeries?.removePriceLine){
        this.priceLineItems.forEach(line => primarySeries.removePriceLine(line.api));
      }
      this.priceLines = [];
      this.priceLineItems = [];
      (lines || []).forEach(line => {
        const price = numberOrNull(line.price);
        if(price == null || !primarySeries?.createPriceLine) return;
        const id = String(line.id || line.title || `price-line-${this.priceLineItems.length + 1}`);
        const api = primarySeries.createPriceLine({
          price,
          color:line.color || COLORS.gold,
          lineWidth:line.lineWidth || 1,
          lineStyle:lineStyleValue(line.lineStyle),
          axisLabelVisible:line.axisLabelVisible !== false,
          title:line.title || "",
        });
        const item = {
          id,
          api,
          price,
          draggable:line.draggable === true,
          onChange:typeof line.onChange === "function" ? line.onChange : null,
        };
        this.priceLineItems.push(item);
        this.priceLines.push(api);
      });
    }

    _normalizeIndicatorOptions(indicators){
      const config = indicators || this.options.indicators || {};
      const emaRaw = config.ema ?? config.emas ?? config.emaPeriods ?? [];
      const emaList = Array.isArray(emaRaw) ? emaRaw : (emaRaw === true ? [20] : []);
      const ema = emaList.map((item, index) => {
        const period = Math.max(1, Math.floor(numberOrNull(typeof item === "number" ? item : item?.period) ?? 0));
        if(!period) return null;
        return {
          period,
          color:typeof item === "object" && item?.color ? item.color : DEFAULT_EMA_COLORS[index % DEFAULT_EMA_COLORS.length],
          lineWidth:typeof item === "object" ? Math.max(1, Math.floor(numberOrNull(item.lineWidth) ?? 1)) : 1,
          title:typeof item === "object" && item?.title ? item.title : `EMA ${period}`,
        };
      }).filter(Boolean);
      const macdRaw = config.macd;
      const macd = macdRaw === true ? {} : (macdRaw && typeof macdRaw === "object" ? macdRaw : null);
      const rsiRaw = config.rsi;
      let rsi = null;
      if(rsiRaw === true) rsi = {};
      else if(typeof rsiRaw === "number") rsi = {period:rsiRaw};
      else if(rsiRaw && typeof rsiRaw === "object") rsi = rsiRaw;
      if(rsi){
        rsi = {
          period:Math.max(1, Math.floor(numberOrNull(rsi.period) ?? 14)),
          color:rsi.color || DEFAULT_RSI_COLOR,
          lineWidth:Math.max(1, Math.floor(numberOrNull(rsi.lineWidth) ?? 1)),
          height:Math.max(80, numberOrNull(rsi.height) ?? 110),
          overbought:numberOrNull(rsi.overbought) ?? 70,
          oversold:numberOrNull(rsi.oversold) ?? 30,
        };
      }
      return {ema, macd, rsi};
    }

    _indicatorCandles(){
      const candles = this.current?.candles || [];
      if(candles.length) return candles;
      return (this.current?.line || []).map(point => ({time:point.time, close:point.value}));
    }

    _applyIndicators(indicators){
      if(!this.chart || (!this.candleSeries && !this.lineSeries)) return;
      const lwc = root.LightweightCharts || {};
      const options = this._normalizeIndicatorOptions(indicators);
      const candles = this._indicatorCandles();
      const wantedEmaKeys = new Set(options.ema.map(item => String(item.period)));

      this.indicatorSeries.ema.forEach((entry, key) => {
        if(!wantedEmaKeys.has(key)){
          this.chart.removeSeries(entry.series);
          this.indicatorSeries.ema.delete(key);
        }
      });
      options.ema.forEach(item => {
        const key = String(item.period);
        let entry = this.indicatorSeries.ema.get(key);
        if(!entry){
          entry = {
            series:this.chart.addSeries(lwc.LineSeries, {
              color:item.color,
              lineWidth:item.lineWidth,
              priceLineVisible:false,
              lastValueVisible:false,
              title:item.title,
            }),
            options:item,
          };
          this.indicatorSeries.ema.set(key, entry);
        }else{
          entry.series.applyOptions?.({color:item.color, lineWidth:item.lineWidth, title:item.title});
        }
        entry.series.setData(calculateEmaData(candles, item.period));
      });

      if(options.macd){
        if(!this.indicatorSeries.macd){
          this.indicatorSeries.macd = {
            histogram:this.chart.addSeries(lwc.HistogramSeries, {
              color:"rgba(122,162,255,.38)",
              priceScaleId:"macd",
              priceLineVisible:false,
              lastValueVisible:false,
              title:"",
            }, 1),
            macd:this.chart.addSeries(lwc.LineSeries, {
              color:options.macd.macdColor || "#7aa2ff",
              lineWidth:1,
              priceScaleId:"macd",
              priceLineVisible:false,
              lastValueVisible:false,
              title:"",
            }, 1),
            signal:this.chart.addSeries(lwc.LineSeries, {
              color:options.macd.signalColor || "#f5b84b",
              lineWidth:1,
              priceScaleId:"macd",
              priceLineVisible:false,
              lastValueVisible:false,
              title:"",
            }, 1),
          };
          this.chart.panes?.()?.[1]?.setHeight?.(Math.max(90, numberOrNull(options.macd.height) ?? 118));
        }
        const macdData = calculateMacdData(candles, options.macd);
        this.indicatorSeries.macd.histogram.setData(macdData.histogram);
        this.indicatorSeries.macd.macd.setData(macdData.macd);
        this.indicatorSeries.macd.signal.setData(macdData.signal);
      }else if(this.indicatorSeries.macd){
        this.chart.removeSeries(this.indicatorSeries.macd.histogram);
        this.chart.removeSeries(this.indicatorSeries.macd.macd);
        this.chart.removeSeries(this.indicatorSeries.macd.signal);
        this.indicatorSeries.macd = null;
        if(this.chart.panes?.()?.[1]) this.chart.removePane?.(1);
      }

      if(options.rsi){
        const paneIndex = options.macd ? 2 : 1;
        if(this.indicatorSeries.rsi?.paneIndex !== paneIndex){
          if(this.indicatorSeries.rsi){
            this.chart.removeSeries(this.indicatorSeries.rsi.line);
          }
          this.indicatorSeries.rsi = {
            paneIndex,
            line:this.chart.addSeries(lwc.LineSeries, {
              color:options.rsi.color,
              lineWidth:options.rsi.lineWidth,
              priceScaleId:"rsi",
              priceLineVisible:false,
              lastValueVisible:false,
              title:"",
            }, paneIndex),
          };
          this.chart.panes?.()?.[paneIndex]?.setHeight?.(options.rsi.height);
          this.indicatorSeries.rsi.overboughtLine = this.indicatorSeries.rsi.line.createPriceLine?.({
            price:options.rsi.overbought,
            color:"rgba(245,184,75,.52)",
            lineWidth:1,
            lineStyle:lineStyleValue("dotted"),
            axisLabelVisible:false,
            title:"",
          });
          this.indicatorSeries.rsi.oversoldLine = this.indicatorSeries.rsi.line.createPriceLine?.({
            price:options.rsi.oversold,
            color:"rgba(122,162,255,.52)",
            lineWidth:1,
            lineStyle:lineStyleValue("dotted"),
            axisLabelVisible:false,
            title:"",
          });
        }else{
          this.indicatorSeries.rsi.line.applyOptions?.({
            color:options.rsi.color,
            lineWidth:options.rsi.lineWidth,
            title:"",
          });
        }
        this.indicatorSeries.rsi.line.setData(calculateRsiData(candles, options.rsi.period));
      }else if(this.indicatorSeries.rsi){
        this.chart.removeSeries(this.indicatorSeries.rsi.line);
        this.indicatorSeries.rsi = null;
      }
      this.indicatorOptions = options;
    }

    _hitTestPriceLine(clientY){
      const primarySeries = this.candleSeries || this.lineSeries;
      if(!primarySeries?.priceToCoordinate) return null;
      const rect = this.chartEl.getBoundingClientRect();
      const y = clientY - rect.top;
      let best = null;
      let bestDistance = Infinity;
      this.priceLineItems.forEach(item => {
        if(!item.draggable) return;
        const coordinate = primarySeries.priceToCoordinate(item.price);
        if(coordinate == null) return;
        const distance = Math.abs(Number(coordinate) - y);
        if(distance <= 10 && distance < bestDistance){
          best = item;
          bestDistance = distance;
        }
      });
      return best;
    }

    _onMouseDown(event){
      if(this.destroyed || event.button !== 0 || this.getTrustState().blocked) return;
      const item = this._hitTestPriceLine(event.clientY);
      if(!item) return;
      event.preventDefault();
      this.dragState = {id:item.id, startPrice:item.price};
      this.chartEl.classList.add("is-dragging-price-line");
    }

    _onMouseMove(event){
      const primarySeries = this.candleSeries || this.lineSeries;
      if(!this.dragState || !primarySeries?.coordinateToPrice) return;
      const rect = this.chartEl.getBoundingClientRect();
      const y = clampNumber(event.clientY - rect.top, 0, rect.height);
      const price = numberOrNull(primarySeries.coordinateToPrice(y));
      if(price == null) return;
      const item = this.priceLineItems.find(line => line.id === this.dragState.id);
      if(!item) return;
      item.price = price;
      item.api.applyOptions?.({price});
      this._syncOverlayPriceLine(item.id, price);
      this._emitPriceLineChange(item, price);
    }

    _onMouseUp(){
      if(!this.dragState) return;
      this.dragState = null;
      this.chartEl.classList.remove("is-dragging-price-line");
    }

    _syncOverlayPriceLine(id, price){
      const lines = this.lastOverlays?.priceLines;
      if(!Array.isArray(lines)) return;
      const target = lines.find(line => String(line.id || line.title || "") === id);
      if(target) target.price = price;
    }

    _emitPriceLineChange(item, price){
      const payload = {id:item.id, price};
      item.onChange?.(payload);
      if(typeof this.options.onPriceLineChange === "function") this.options.onPriceLineChange(payload);
    }

    _setRiskReward(riskReward){
      this.currentRiskReward = riskReward || null;
      this._updateRiskRewardOverlay();
    }

    _riskRewardXRange(riskReward){
      const candles = this.current?.candles || [];
      const scale = this.chart?.timeScale?.();
      const width = Math.max(1, this.chartEl.getBoundingClientRect().width || 1);
      const startTime = toEpochSeconds(riskReward?.startTime ?? riskReward?.fromTime);
      const endTime = toEpochSeconds(riskReward?.endTime ?? riskReward?.toTime);
      let left = startTime != null ? scale?.timeToCoordinate?.(startTime) : null;
      let right = endTime != null ? scale?.timeToCoordinate?.(endTime) : null;
      if(left == null || right == null){
        const widthBars = Math.max(6, Math.floor(numberOrNull(riskReward?.widthBars) ?? 36));
        const endIndex = candles.length - 1;
        const startIndex = Math.max(0, endIndex - widthBars);
        left = scale?.timeToCoordinate?.(candles[startIndex]?.time) ?? width * .52;
        right = scale?.timeToCoordinate?.(candles[endIndex]?.time) ?? width * .88;
      }
      if(right < left) [left, right] = [right, left];
      return {
        left:clampNumber(left, 0, width - 12),
        right:clampNumber(Math.max(right, left + 32), 12, width),
      };
    }

    _updateRiskRewardOverlay(){
      const primarySeries = this.candleSeries || this.lineSeries;
      if(!this.riskRewardEl || !primarySeries) return;
      const rr = calculateRiskReward(this.currentRiskReward);
      if(!rr){
        this.riskRewardEl.classList.remove("is-visible");
        this.riskRewardEl.dataset.r = "";
        return;
      }
      const yEntry = primarySeries.priceToCoordinate?.(rr.entry);
      const yStop = primarySeries.priceToCoordinate?.(rr.stop);
      const yTarget = primarySeries.priceToCoordinate?.(rr.target);
      if(yEntry == null || yStop == null || yTarget == null){
        this.riskRewardEl.classList.remove("is-visible");
        return;
      }
      const x = this._riskRewardXRange(this.currentRiskReward);
      const top = Math.min(yEntry, yStop, yTarget);
      const bottom = Math.max(yEntry, yStop, yTarget);
      const rewardTop = Math.min(yEntry, yTarget) - top;
      const rewardHeight = Math.max(1, Math.abs(yTarget - yEntry));
      const riskTop = Math.min(yEntry, yStop) - top;
      const riskHeight = Math.max(1, Math.abs(yStop - yEntry));
      this.riskRewardEl.style.left = `${x.left}px`;
      this.riskRewardEl.style.top = `${top}px`;
      this.riskRewardEl.style.width = `${Math.max(32, x.right - x.left)}px`;
      this.riskRewardEl.style.height = `${Math.max(1, bottom - top)}px`;
      this.riskRewardEl.querySelector(".reward").style.top = `${rewardTop}px`;
      this.riskRewardEl.querySelector(".reward").style.height = `${rewardHeight}px`;
      this.riskRewardEl.querySelector(".risk").style.top = `${riskTop}px`;
      this.riskRewardEl.querySelector(".risk").style.height = `${riskHeight}px`;
      const amount = numberOrNull(this.currentRiskReward?.amount);
      const qty = numberOrNull(this.currentRiskReward?.quantity ?? this.currentRiskReward?.qty);
      const detail = [
        `R ${rr.ratio.toFixed(2)}`,
        amount != null ? `Amount ${formatPrice(amount, 0)}` : "",
        qty != null ? `Qty ${formatPrice(qty, 3)}` : "",
      ].filter(Boolean).join(" · ");
      this.riskRewardEl.querySelector(".standard-kline-risk-label").textContent = detail;
      this.riskRewardEl.dataset.r = rr.ratio.toFixed(2);
      this.riskRewardEl.classList.add("is-visible");
    }

    _updateOhlcHeader(bar){
      if(!this.ohlcEl || this.options.showOhlcHeader === false) return;
      if(this.renderMode === "line"){
        const point = bar || this.current?.line?.at(-1);
        if(!point){
          this.ohlcEl.textContent = "值 --";
          return;
        }
        const points = this.current?.line || [];
        const index = points.findIndex(item => Number(item.time) === Number(point.time));
        const previous = index > 0 ? points[index - 1]?.value : point.value;
        const change = numberOrNull(point.value) != null && numberOrNull(previous) != null ? Number(point.value) - Number(previous) : 0;
        const pct = previous ? change / Number(previous) * 100 : 0;
        const cls = change >= 0 ? "is-up" : "is-down";
        this.ohlcEl.innerHTML = `<span>值 ${formatPrice(point.value, 3)}</span><span class="${cls}">${formatSigned(change, 3)} (${formatSigned(pct, 2)}%)</span>`;
        return;
      }
      if(!bar){
        this.ohlcEl.textContent = "O -- H -- L -- C --";
        return;
      }
      const movement = calculateMovement(this.current?.candles || [], bar);
      const cls = movement.direction === "up" ? "is-up" : "is-down";
      this.ohlcEl.innerHTML = [
        `<span>O ${formatPrice(bar.open, 2)}</span>`,
        `<span>H ${formatPrice(bar.high, 2)}</span>`,
        `<span>L ${formatPrice(bar.low, 2)}</span>`,
        `<span>C ${formatPrice(bar.close, 2)}</span>`,
        `<span class="${cls}">${formatSigned(movement.change, 2)} (${formatSigned(movement.pct, 2)}%)</span>`,
      ].join("");
    }

    _onCrosshairMove(param){
      if(!param?.time){
        this._updateOhlcHeader(this.renderMode === "line" ? this.current?.line?.at(-1) : this.current?.candles?.at(-1));
        return;
      }
      const time = toEpochSeconds(param.time);
      if(this.renderMode === "line"){
        const point = (this.current?.line || []).find(item => Number(item.time) === Number(time));
        this._updateOhlcHeader(point || this.current?.line?.at(-1));
        return;
      }
      const bar = (this.current?.candles || []).find(item => Number(item.time) === Number(time));
      this._updateOhlcHeader(bar || this.current?.candles?.at(-1));
    }

    _emitTradeAction(side){
      const bar = this.renderMode === "line" ? this.current?.line?.at(-1) : this.current?.candles?.at(-1) || null;
      const payload = {
        side,
        price:this.renderMode === "line" ? (bar?.value ?? null) : (bar?.close ?? null),
        bar,
        meta:this.current?.meta || {},
        trustState:this.getTrustState(),
      };
      if(typeof this.options.onTradeAction === "function") this.options.onTradeAction(payload);
    }

    _refreshScaleControlState(){
      this.scaleControlsEl?.querySelector?.("[data-scale-action='auto']")?.classList.toggle("is-active", this.autoFit);
      this.scaleControlsEl?.querySelector?.("[data-scale-action='log']")?.classList.toggle("is-active", this.logScale);
    }

    _setSourceText(meta){
      const source = this.toolbarEl.querySelector("[data-source]");
      if(!source) return;
      const mode = meta?.source_mode || "unknown";
      const provider = meta?.provider || "unknown";
      const count = meta?.bar_count || this._barCount() || 0;
      const flags = normalizeQualityFlags(meta?.quality_flags);
      source.textContent = `${meta?.symbol || "--"} ${meta?.timeframe || ""} · ${mode} · ${provider} · ${count} bars${flags.length ? " · " + flags.join(",") : ""}`;
    }

    _refreshOverlay(){
      if(this.loading) return;
      if(!this.chart || this.libraryAvailable === false){
        this._setOverlay("empty", "CHART LIBRARY MISSING", "window.LightweightCharts is not loaded (peer dependency).");
        return;
      }
      const points = this.renderMode === "line" ? (this.current.line || []) : (this.current.candles || []);
      if(!points.length){
        this._setOverlay("empty", "NO KLINE DATA", describeEmptyMeta(this.current.meta));
        return;
      }
      const trustState = this.getTrustState();
      if(trustState.blocked){
        this._setOverlay("blocked", "TRUST POLICY BLOCKED", formatTrustReasons(trustState.reasons));
        return;
      }
      if(this.current.meta?.is_synthetic){
        this._setOverlay("synthetic", "SIMULATED DATA / NOT REAL PRICE", "Display-only seed or synthetic bars. Do not use for trading signal or manual order decisions.");
        return;
      }
      this._hideOverlay();
    }

    _setOverlay(kind, title, detail){
      this.overlayEl.classList.remove("standard-kline-loading", "standard-kline-empty", "standard-kline-synthetic", "standard-kline-blocked");
      this.overlayEl.classList.add("is-visible", `standard-kline-${kind}`);
      this.overlayEl.dataset.state = kind;
      this.overlayEl.querySelector("b").textContent = title;
      this.overlayEl.querySelector("span").textContent = detail;
    }

    _hideOverlay(){
      this.overlayEl.classList.remove("is-visible", "standard-kline-loading", "standard-kline-empty", "standard-kline-synthetic", "standard-kline-blocked");
      this.overlayEl.dataset.state = "ready";
    }

    _barCount(){
      return this.renderMode === "line" ? (this.current?.line?.length || 0) : (this.current?.candles?.length || 0);
    }

    _rightOffset(){
      const offset = numberOrNull(this._timeScale?.options?.()?.rightOffset);
      return offset == null ? 8 : offset;
    }

    _clampLogicalRange(range){
      return clampLogicalRange(range, this._barCount(), {
        bufferBars:this.options.logicalRangeBufferBars,
        minVisibleBars:this.options.minVisibleBars,
        rightOffset:this._rightOffset(),
      });
    }

    _readLogicalRange(){
      return this._nativeGetVisibleLogicalRange?.() || this._timeScale?.getVisibleLogicalRange?.() || null;
    }

    _setVisibleLogicalRange(range){
      const target = this._clampLogicalRange(range);
      if(!target || !this._timeScale) return null;
      const width = Math.max(.001, target.to - target.from);
      const scaleWidth = Math.max(1, Number(this._timeScale.width?.() || this._size().width || 1));
      const scaleOptions = this._timeScale.options?.() || {};
      const minSpacing = Math.max(.1, numberOrNull(scaleOptions.minBarSpacing) ?? .5);
      const configuredMax = numberOrNull(scaleOptions.maxBarSpacing);
      const maxSpacing = configuredMax && configuredMax > 0 ? configuredMax : Math.max(40, numberOrNull(this.options.maxBarSpacing) ?? 80);
      const barSpacing = clampNumber(scaleWidth / width, minSpacing, maxSpacing);
      this._timeScale.applyOptions?.({barSpacing});
      this._timeScale.scrollToPosition?.(target.to - (this._barCount() - 1), false);
      return target;
    }

    fit(){
      if(!this.chart) return null;
      const count = this._barCount();
      if(!count) return null;
      return this._setVisibleLogicalRange({from:-1, to:count - 1 + this._rightOffset()});
    }

    zoom(factor){
      const scale = this.chart?.timeScale?.();
      const range = scale?.getVisibleLogicalRange?.();
      const parsedFactor = numberOrNull(factor);
      if(parsedFactor == null || parsedFactor <= 0) return null;
      if(!range) return;
      const safeFactor = clampNumber(parsedFactor, .2, 5);
      const center = (range.from + range.to) / 2;
      const half = Math.max(3, (range.to - range.from) * safeFactor / 2);
      return scale.setVisibleLogicalRange({from:center - half, to:center + half});
    }

    pan(bars){
      const scale = this.chart?.timeScale?.();
      const range = scale?.getVisibleLogicalRange?.();
      const step = numberOrNull(bars);
      if(step == null) return null;
      if(!range) return;
      return scale.setVisibleLogicalRange({from:range.from + step, to:range.to + step});
    }

    destroy(){
      this.destroyed = true;
      this.resizeObserver?.disconnect?.();
      this.chartEl?.removeEventListener?.("mousedown", this._boundMouseDown);
      root.document?.removeEventListener?.("mousemove", this._boundMouseMove);
      root.document?.removeEventListener?.("mouseup", this._boundMouseUp);
      this.chart?.unsubscribeCrosshairMove?.(this._boundCrosshairMove);
      this._timeScale?.unsubscribeVisibleLogicalRangeChange?.(this._boundVisibleRangeChange);
      this.chart?.remove?.();
      this.container.innerHTML = "";
    }
  }

  return {
    StandardKlineChart,
    CANDLE_THEMES:clonePlain(CANDLE_THEMES),
    PRESET_CONFIGS:clonePlain(PRESET_CONFIGS),
    adaptDatafeedResponse,
    adaptBarPayload,
    calculateEmaData,
    calculateMacdData,
    calculateRiskReward,
    calculateRsiData,
    clampLogicalRange,
    createStandardKlineOptions,
    defaultAgentDeploymentOptions,
    evaluateTrustPolicy,
    getPresetConfig,
    isSyntheticMeta,
    mergeBarIntoAdaptedData,
    normalizeCandleTheme,
    normalizeRenderMode,
    nearestTime,
    normalizeQualityFlags,
    toEpochSeconds,
  };
});
