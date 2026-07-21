import fs from "node:fs";
import { chromium } from "playwright";


function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const baseUrl = arg("--base-url", "http://127.0.0.1:8877/");
const tickers = arg("--tickers", "300750.SZ,600519.SH").split(",").map((item) => item.trim()).filter(Boolean);
const executablePath = process.env.CHROME_PATH || null;
if (executablePath && !fs.existsSync(executablePath)) throw new Error(`CHROME_PATH does not exist: ${executablePath}`);

const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const results = [];
try {
  for (const ticker of tickers) {
    const viewportResults = [];
    for (const viewport of [{ name: "desktop", width: 1200, height: 900 }, { name: "mobile", width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height }, deviceScaleFactor: 1 });
      const url = new URL(baseUrl);
      url.searchParams.set("report", ticker);
      await page.goto(url.toString(), { waitUntil: "networkidle", timeout: 30000 });
      await page.waitForSelector("#report-content .report-document", { state: "visible", timeout: 30000 });
      const result = await page.evaluate(async (expectedTicker) => {
        const response = await fetch(`/api/reports/${encodeURIComponent(expectedTicker)}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`report API returned ${response.status}`);
        const report = await response.json();
        const expected = report.report_contract.module_manifest.map((module) => module.id);
        const actual = [...document.querySelectorAll("#report-content .report-main > [data-report-module]")].map((node) => node.dataset.reportModule);
        const documentMarkup = document.querySelector("#report-content .report-document").outerHTML;
        const template = document.createElement("template");
        template.innerHTML = documentMarkup;
        template.content.querySelector(".report-main > [data-report-module]:last-of-type")?.remove();
        let negativeRejected = false;
        try {
          orderReportMarkupFromManifest(template.innerHTML, report.report_contract);
        } catch (_) {
          negativeRejected = true;
        }
        return {
          schema_version: report.report_contract.schema_version,
          contract_version: report.report_contract.contract_version,
          research_depth: report.research_depth,
          expected, actual, negativeRejected,
        };
      }, ticker);
      if (result.actual.join("|") !== result.expected.join("|") || !result.negativeRejected) {
        throw new Error(`${ticker} ${viewport.name} DOM contract failed`);
      }
      viewportResults.push({ viewport: viewport.name, width: viewport.width, ...result });
      await page.close();
    }
    results.push({ ticker, viewports: viewportResults });
  }
  console.log(JSON.stringify({ status: "passed", base_url: baseUrl, results }, null, 2));
} finally {
  await browser.close();
}
