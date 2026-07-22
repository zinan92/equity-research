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

async function loginAndVerify(browser, baseUrl, credentials, viewport, output) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
  await page.locator("#login-form input[name=email]").fill(credentials.acceptance_email);
  await page.locator("#login-form input[name=password]").fill(credentials.acceptance_password);
  await page.locator("#login-form button[type=submit]").click();
  await page.locator("#private-preview-dashboard:not([hidden])").waitFor({ timeout: 30_000 });
  await page.locator(".canonical-position").nth(7).waitFor({ timeout: 10_000 });
  const result = await page.evaluate(() => ({
    title: document.title,
    banner: document.querySelector(".preview-banner span")?.textContent?.trim(),
    positionCount: document.querySelectorAll(".canonical-position").length,
    portfolioId: document.querySelector("#canonical-identity")?.textContent?.trim(),
    truthText: document.querySelector(".preview-banner p")?.textContent?.trim(),
    reportButtonsLocked: [...document.querySelectorAll(".research-link")].every((item) => item.disabled),
    horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    scrollHeight: document.documentElement.scrollHeight,
    mobileReadability: window.innerWidth > 720 ? null : {
      thesisFont: parseFloat(getComputedStyle(document.querySelector(".position-thesis p")).fontSize),
      riskFont: parseFloat(getComputedStyle(document.querySelector(".canonical-risk-panel p")).fontSize),
      receiptFont: parseFloat(getComputedStyle(document.querySelector(".canonical-receipt-panel dd")).fontSize),
      formLabelFont: parseFloat(getComputedStyle(document.querySelector("#feedback-form label")).fontSize),
      reportButtonHeight: document.querySelector(".research-link").getBoundingClientRect().height,
      feedbackButtonHeight: document.querySelector("#feedback-form button").getBoundingClientRect().height,
    },
  }));
  if (result.banner !== "PRIVATE PREVIEW") throw new Error("private preview banner is missing");
  if (result.positionCount !== 8) throw new Error("canonical position count differs from eight");
  if (!result.portfolioId?.startsWith("canonical_portfolio_")) throw new Error("canonical portfolio identity is missing");
  if (!result.truthText?.includes("付款") || !result.truthText?.includes("券商")) throw new Error("preview truth boundary is missing");
  if (!result.reportButtonsLocked) throw new Error("preview member report buttons are not visibly locked");
  if (result.horizontalOverflow) throw new Error("private preview has horizontal overflow");
  if (result.mobileReadability) {
    const r = result.mobileReadability;
    if (r.thesisFont < 14 || r.riskFont < 14 || r.receiptFont < 12 || r.formLabelFont < 12) {
      throw new Error("mobile private preview text is below the readability contract");
    }
    if (r.reportButtonHeight < 44 || r.feedbackButtonHeight < 44) {
      throw new Error("mobile private preview touch target is below 44px");
    }
  }
  await page.waitForTimeout(800);
  await page.screenshot({ path: output, fullPage: true });
  const size = pngSize(output);
  if (size.width !== viewport.width || size.height !== result.scrollHeight) {
    throw new Error(`full-page screenshot mismatch: ${size.width}x${size.height} vs ${viewport.width}x${result.scrollHeight}`);
  }
  await context.close();
  return { ...result, screenshot: { path: output, sha256: sha256(output), ...size } };
}

const [baseUrl, credentialPath, outputDir] = process.argv.slice(2);
if (!baseUrl || !credentialPath || !outputDir) throw new Error("usage: capture_private_preview.mjs <url> <credential-json> <output-dir>");
const credentials = JSON.parse(fs.readFileSync(credentialPath, "utf8"));
fs.mkdirSync(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const desktop = await loginAndVerify(browser, baseUrl, credentials, { width: 1440, height: 1000 }, path.join(outputDir, "private-preview-desktop.png"));
  const mobile = await loginAndVerify(browser, baseUrl, credentials, { width: 390, height: 844 }, path.join(outputDir, "private-preview-mobile.png"));
  process.stdout.write(JSON.stringify({ status: "passed", base_url: new URL(baseUrl).origin, desktop, mobile }));
} finally {
  await browser.close();
}
