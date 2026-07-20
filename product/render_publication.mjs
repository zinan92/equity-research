import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import crypto from "node:crypto";

const require = createRequire(import.meta.url);
const playwrightPath = process.env.PLAYWRIGHT_PATH || "/Users/wendy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright";
const { chromium } = require(playwrightPath);

function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const baseUrl = arg("--base-url");
const ticker = arg("--ticker");
const outDir = arg("--out-dir");
const cssPath = arg("--css");
const reportHash = arg("--report-hash");
const reportPayloadHash = arg("--report-payload-hash");
const expectedApiPayloadHash = arg("--api-payload-hash");
const companyName = arg("--company-name");
if (!baseUrl || !ticker || !outDir || !cssPath || !reportHash || !reportPayloadHash || !expectedApiPayloadHash || !companyName) {
  throw new Error("--base-url, --ticker, --out-dir, --css, --report-hash, --report-payload-hash, --api-payload-hash and --company-name are required");
}

fs.mkdirSync(outDir, { recursive: true });
const browserCandidates = [
  process.env.CHROME_PATH,
  "/Users/wendy/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);
const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("no compatible Chromium executable is installed");
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 1 });
  const url = new URL(baseUrl);
  url.searchParams.set("report", ticker);
  await page.goto(url.toString(), { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector("#report-content .report-document", { state: "visible", timeout: 30000 });
  const apiResponse = await page.evaluate(async (expectedTicker) => {
    const response = await fetch(`/api/reports/${encodeURIComponent(expectedTicker)}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`report API returned ${response.status}`);
    return { body: await response.text() };
  }, ticker);
  const apiPayloadHash = crypto.createHash("sha256").update(apiResponse.body).digest("hex");
  const apiReport = JSON.parse(apiResponse.body);
  if (apiReport.report_hash !== reportHash || apiReport.ticker !== ticker || apiReport.name !== companyName || apiPayloadHash !== expectedApiPayloadHash) {
    throw new Error("rendered page API report does not match the requested publication identity");
  }
  await page.evaluate(async (expectedReportHash) => {
    if (document.fonts?.ready) await document.fonts.ready;
    document.body.classList.add("report-export");
    const report = document.querySelector("#research-report");
    report?.removeAttribute("hidden");
    const publication = document.querySelector("#report-content .report-publication");
    const hero = document.querySelector("#report-content .report-hero");
    if (!publication || !hero) throw new Error("report publication shell is missing");
    const fingerprint = document.createElement("span");
    fingerprint.className = "report-export-fingerprint";
    fingerprint.textContent = `报告指纹 ${expectedReportHash.slice(0, 12)}`;
    publication.append(fingerprint);
    const bits = [...expectedReportHash.slice(0, 16)].flatMap((digit) => Number.parseInt(digit, 16).toString(2).padStart(4, "0").split(""));
    const code = document.createElement("span");
    code.className = "report-export-code";
    code.setAttribute("aria-label", `报告校验码 ${expectedReportHash.slice(0, 16)}`);
    code.innerHTML = bits.map((bit) => `<i class="bit-${bit}"></i>`).join("");
    hero.append(code);
    window.scrollTo(0, 0);
  }, reportHash);
  await page.waitForTimeout(250);
  const metadata = await page.evaluate(() => ({
    title: document.querySelector("#report-title")?.textContent?.trim() || "",
    width: document.documentElement.scrollWidth,
    height: document.documentElement.scrollHeight,
    bodyText: document.querySelector("#report-content")?.textContent?.trim() || "",
    reportHtml: document.querySelector("#research-report")?.outerHTML || "",
  }));
  if (!metadata.reportHtml || metadata.bodyText.length < 1000) throw new Error("rendered report is incomplete");
  if (!metadata.title.includes(companyName) || !metadata.bodyText.includes(companyName)) throw new Error("rendered report is for the wrong company");
  await page.evaluate((title) => { document.title = title; }, metadata.title);
  const css = fs.readFileSync(cssPath, "utf8");
  const escapeAttr = (value) => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const standalone = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="park-report-hash" content="${escapeAttr(reportHash)}"><meta name="park-report-payload-hash" content="${escapeAttr(reportPayloadHash)}"><meta name="park-report-ticker" content="${escapeAttr(ticker)}"><title>${escapeAttr(metadata.title)}</title><style>${css}</style></head><body class="report-export">${metadata.reportHtml}</body></html>`;
  fs.writeFileSync(path.join(outDir, "report.html"), standalone);
  await page.screenshot({ path: path.join(outDir, "report-long.png"), fullPage: true, type: "png", animations: "disabled" });
  await page.emulateMedia({ media: "print" });
  // 194mm is the printable A4 width after the configured 8mm side margins.
  await page.setViewportSize({ width: 733, height: 1000 });
  const printAudit = await page.evaluate(() => {
    const root = document.querySelector("#report-content .report-document");
    const rootRect = root.getBoundingClientRect();
    const offenders = [...root.querySelectorAll("*")].filter((node) => {
      const style = getComputedStyle(node);
      if (style.display === "none" || style.position === "fixed") return false;
      const rect = node.getBoundingClientRect();
      return node.scrollWidth > node.clientWidth + 2 || rect.right > rootRect.right + 2 || rect.left < rootRect.left - 2;
    }).slice(0, 20).map((node) => ({
      tag: node.tagName, className: node.className,
      parentClassName: node.parentElement?.className || "",
      text: (node.textContent || "").trim().slice(0, 100),
      scrollWidth: node.scrollWidth, clientWidth: node.clientWidth,
    }));
    return { printableWidth: Math.round(rootRect.width), overflowCount: offenders.length, offenders };
  });
  if (printAudit.overflowCount) throw new Error(`print layout overflows: ${JSON.stringify(printAudit.offenders)}`);
  await page.pdf({
    path: path.join(outDir, "report.pdf"), format: "A4", printBackground: true,
    margin: { top: "8mm", right: "8mm", bottom: "10mm", left: "8mm" },
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: '<div style="width:100%;font:8px Arial;color:#6b7280;text-align:center"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  });
  fs.writeFileSync(path.join(outDir, "render-receipt.json"), JSON.stringify({
    renderer: "playwright-chromium-v3", ticker, companyName, reportHash, reportPayloadHash, apiPayloadHash, url: url.toString(),
    title: metadata.title, width: metadata.width, height: metadata.height,
    textLength: metadata.bodyText.length,
    bodyTextHash: crypto.createHash("sha256").update(metadata.bodyText).digest("hex"),
    printAudit,
  }, null, 2));
} finally {
  await browser.close();
}
