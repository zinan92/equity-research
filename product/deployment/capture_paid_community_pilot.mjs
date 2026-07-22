import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";


function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function pngSize(file) {
  const value = fs.readFileSync(file);
  if (value.subarray(1, 4).toString() !== "PNG") throw new Error("screenshot is not PNG");
  return { width: value.readUInt32BE(16), height: value.readUInt32BE(20) };
}

async function capture(browser, baseUrl, credentials, viewport, output) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
  await page.locator("#login-form input[name=email]").fill(credentials.acceptance_email);
  await page.locator("#login-form input[name=password]").fill(credentials.acceptance_password);
  await page.locator("#login-form button[type=submit]").click();
  await page.locator("#private-preview-dashboard:not([hidden])").waitFor({ timeout: 30_000 });
  await page.locator("#billing-status-card[data-loaded=true]").waitFor({ timeout: 30_000 });
  await page.locator("#research-pack-download:not([hidden])").waitFor({ timeout: 10_000 });
  const result = await page.evaluate(() => ({
    banner: document.querySelector("#preview-mode-label")?.textContent?.trim(),
    truth: document.querySelector("#preview-mode-copy")?.textContent?.trim(),
    billingStatus: document.querySelector("#billing-status")?.textContent?.trim(),
    billingTruth: document.querySelector("#billing-truth")?.textContent?.trim(),
    packHash: document.querySelector("#billing-pack-hash")?.textContent?.trim(),
    reportCount: document.querySelector("#billing-report-count")?.textContent?.trim(),
    downloadVisible: !document.querySelector("#research-pack-download")?.hidden,
    positionCount: document.querySelectorAll(".canonical-position").length,
    horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    scrollHeight: document.documentElement.scrollHeight,
    mobileReadability: window.innerWidth > 720 ? null : {
      statusFont: parseFloat(getComputedStyle(document.querySelector("#billing-status")).fontSize),
      truthFont: parseFloat(getComputedStyle(document.querySelector("#billing-truth")).fontSize),
      receiptFont: parseFloat(getComputedStyle(document.querySelector("#billing-pack-hash")).fontSize),
      downloadHeight: document.querySelector("#research-pack-download").getBoundingClientRect().height,
    },
  }));
  if (result.banner !== "PRIVATE PREVIEW · MANUAL PAID PILOT") throw new Error("manual paid-pilot banner is missing");
  if (!result.truth?.includes("不提供在线 checkout") || !result.truth?.includes("人工核验")) throw new Error("manual fulfillment truth is missing");
  if (result.billingStatus !== "验收测试权益 · 不计收入") throw new Error("acceptance-test billing status is not explicit");
  if (!result.billingTruth?.includes("排除在真实收入之外")) throw new Error("acceptance event could be mistaken for revenue");
  if (!/^[0-9a-f]{64}$/.test(result.packHash || "")) throw new Error("research-pack identity is missing");
  if (result.reportCount !== "8 份" || !result.downloadVisible || result.positionCount !== 8) throw new Error("paid research-pack product surface is incomplete");
  if (result.horizontalOverflow) throw new Error("paid community page has horizontal overflow");
  if (result.mobileReadability) {
    const r = result.mobileReadability;
    if (r.statusFont < 14 || r.truthFont < 12 || r.receiptFont < 12 || r.downloadHeight < 44) {
      throw new Error("mobile paid-community readability or touch target failed");
    }
  }
  await page.waitForTimeout(500);
  await page.screenshot({ path: output, fullPage: true });
  const size = pngSize(output);
  if (size.width !== viewport.width || size.height !== result.scrollHeight) {
    throw new Error(`full-page screenshot mismatch: ${size.width}x${size.height} vs ${viewport.width}x${result.scrollHeight}`);
  }
  await context.close();
  return { ...result, packHash: `${result.packHash.slice(0, 12)}…`, screenshot: { path: output, sha256: sha256(output), ...size } };
}


const [baseUrl, credentialPath, outputDir] = process.argv.slice(2);
if (!baseUrl || !credentialPath || !outputDir) throw new Error("usage: capture_paid_community_pilot.mjs <url> <credential-json> <output-dir>");
const credentials = JSON.parse(fs.readFileSync(credentialPath, "utf8"));
fs.mkdirSync(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const desktop = await capture(browser, baseUrl, credentials, { width: 1440, height: 1000 }, path.join(outputDir, "paid-community-desktop.png"));
  const mobile = await capture(browser, baseUrl, credentials, { width: 390, height: 844 }, path.join(outputDir, "paid-community-mobile.png"));
  process.stdout.write(JSON.stringify({ status: "passed", base_url: new URL(baseUrl).origin, desktop, mobile }));
} finally {
  await browser.close();
}
