// UI audit: walks the customer journey once, then captures every route at phone, tablet and desktop widths,
// recording console errors, failed requests, horizontal overflow and undersized touch targets on each screen.
// Usage: node scripts/ui_audit.cjs [baseUrl] [outDir]      (API serving the built app, ideally a fresh database)
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const OUT = process.argv[3] || path.join(__dirname, "..", "docs", "screenshots", "responsive");
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { phone: { width: 390, height: 844 }, tablet: { width: 768, height: 1024 }, desktop: { width: 1280, height: 800 } };
const report = { base: BASE, screens: [], journey: [] };

function watch(page, bucket) {
  page.on("pageerror", (e) => bucket.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && bucket.push(`console: ${m.text()}`));
  page.on("response", (r) => {
    const u = r.url();
    if (r.status() >= 500 || (r.status() >= 400 && u.includes("/api/") && !EXPECTED_4XX.some((x) => u.includes(x)))) bucket.push(`http ${r.status()}: ${u.replace(BASE, "")}`);
  });
}
const EXPECTED_4XX = ["/api/quotes/preview"];   // 422 = an invalid add-on combination, shown to the user as a notice

async function inspect(page) {
  return page.evaluate(() => {
    const overflow = document.documentElement.scrollWidth - window.innerWidth;
    const small = [];
    for (const el of document.querySelectorAll("button, a[href], input:not([type=hidden]):not(.sr-only), select, [role=switch], label[for]")) {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (!r.width || !r.height || style.visibility === "hidden" || el.closest(".sr-only")) continue;
      if (el.tagName === "A" && el.closest("p, li, dd, td") && r.height < 24) continue;      // inline text links are exempt (WCAG 2.5.8)
      const lab = el.tagName === "INPUT" ? el.closest("label") : null;                        // a box inside a big clickable label is fine
      if (lab && lab.getBoundingClientRect().height >= 24) continue;
      if (r.height < 24 || r.width < 24) small.push(`${el.tagName.toLowerCase()} "${(el.innerText || el.getAttribute("aria-label") || "").trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
    return { overflow: Math.max(0, overflow), smallTargets: small.slice(0, 8), notFound: !!document.body.innerText.match(/^404$/m) };
  });
}

async function shoot(page, name, size) {
  await page.waitForTimeout(350);
  const file = `${size}-${name}.jpg`;
  await page.screenshot({ path: path.join(OUT, file), fullPage: true, type: "jpeg", quality: 82 });
  return file;
}

async function say(page, text) {
  const resp = page.waitForResponse((r) => r.url().includes("/messages") && r.request().method() === "POST");
  await page.locator("#advisor-input").fill(text);
  await page.locator("#advisor-input").press("Enter");
  const r = await (await resp).json();
  await page.waitForTimeout(150);
  return r;
}

async function journey(page) {
  const step = (name) => report.journey.push(name);
  await page.goto(BASE + "/");
  await page.getByRole("button", { name: /Start in English/ }).click();
  await page.waitForURL("**/start");
  await page.getByRole("button", { name: /Chat with the advisor/ }).click();
  await page.locator("#advisor-input").waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
  let r = await say(page, "We run a dental clinic in Kolkata, 5 of us, one clinic");
  r = await say(page, "Yes, GSTIN is 19EOGXH4115Y1ZL");
  if (r.expecting === "needs") {
    await page.getByRole("button", { name: "Billing / POS", exact: true }).click();
    const resp = page.waitForResponse((x) => x.url().includes("/messages"));
    await page.getByRole("button", { name: "Show my plan" }).click();
    r = await (await resp).json();
  }
  if (r.expecting === "spend") {
    const resp = page.waitForResponse((x) => x.url().includes("/messages"));
    await page.getByRole("button", { name: "Rs 3,000-10,000", exact: true }).first().click();
    r = await (await resp).json();
  }
  step(`advisor: ${r.state}`);
  await page.getByRole("button", { name: "See plan and price" }).click();
  await page.waitForURL("**/plan");
  await page.getByRole("button", { name: "Choose add-ons" }).click();
  await page.waitForURL("**/plan/add-ons");
  const toggles = page.locator('[role="switch"][aria-checked="false"]');
  if ((await toggles.count()) > 0) {
    const before = await page.locator("[data-testid=price-monthly]").innerText().catch(() => "");
    const resp = page.waitForResponse((x) => x.url().includes("/quotes/preview"));
    await toggles.first().click();
    await resp;
    await page.waitForTimeout(500);
    const after = await page.locator("[data-testid=price-monthly]").innerText().catch(() => "");
    step(`add-on toggled: ${before} -> ${after}`);
  }
  await page.getByRole("button", { name: "Review quote" }).click();
  await page.getByText("You pay each month").waitFor();
  await page.getByRole("button", { name: /Save quote/ }).click();
  await page.getByText(/This price is held till/).waitFor();
  await page.getByRole("button", { name: "Proceed to checkout" }).click();
  await page.waitForURL("**/checkout");
  await page.locator("#mobile").fill("9876543210");
  await page.getByRole("button", { name: "Send OTP" }).click();
  await page.getByText(/Demo OTP/).waitFor();
  await page.locator("#otp").fill("123456");
  await page.locator("#cname").fill("Joseph Shah");
  await page.getByRole("button", { name: "Verify" }).click();
  await page.getByText(/Logged in as/).waitFor();
  await page.locator("#a").fill("12 Park Street, Ground floor, Kolkata");
  await page.locator("#pin").fill("700016");
  await page.getByText(/I agree to the plan terms/).click();
  await page.getByRole("button", { name: "Place order" }).click();
  await page.waitForURL("**/kyc/consent");
  await page.getByText("I agree to verification as described above").click();
  await page.getByRole("button", { name: "Continue to documents" }).click();
  await page.waitForURL("**/kyc/upload");
  await page.getByRole("button", { name: "Save details" }).click();
  await page.locator("#spec").waitFor();
  await page.locator("#spec").selectOption(process.env.UI_SPECIMEN || "K06");
  const sp = page.waitForResponse((x) => x.url().includes("/specimen"));
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await sp;
  await page.waitForTimeout(800);
  const ev = page.waitForResponse((x) => x.url().includes("/evaluate"));
  await page.getByRole("button", { name: "Verify documents" }).click();
  const evr = await (await ev).json();
  step(`kyc: ${evr.decision}`);
  await page.waitForURL("**/kyc/result");
  const orderId = await page.evaluate(() => JSON.parse(sessionStorage.getItem("accel-journey-v1") || "{}").orderId);
  return orderId;
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: SIZES.phone, deviceScaleFactor: 1, locale: "en-IN" });
  const page = await ctx.newPage();
  const errors = [];
  watch(page, errors);
  const orderId = await journey(page);
  report.journey.push(`journey errors: ${errors.length ? errors.join(" | ") : "none"}`);

  const routes = [
    ["landing", "/"], ["language", "/language?src=WhatsApp"], ["onboarding", "/start"], ["advisor", "/advisor"],
    ["advisor-form", "/advisor/form"], ["plan", "/plan"], ["addons", "/plan/add-ons"], ["quote", "/quote"],
    ["checkout", "/checkout"], ["consent", "/kyc/consent"], ["upload", "/kyc/upload"], ["kyc-result", "/kyc/result"],
    ["confirmation", `/orders/${orderId}/confirmed`], ["tracker", `/orders/${orderId}`], ["orders", "/orders"],
    ["help", "/help"], ["callback", "/help/callback"], ["privacy", "/privacy"], ["not-found", "/no-such-page"],
  ];
  for (const [size, vp] of Object.entries(SIZES)) {
    await page.setViewportSize(vp);
    for (const [name, url] of routes) {
      const errs = [];
      const h = (e) => errs.push(e);
      errors.length = 0;
      await page.goto(BASE + url);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      const info = await inspect(page);
      const file = await shoot(page, name, size);
      report.screens.push({ area: "customer", size, name, url: url.replace(orderId, ":id"), file, errors: [...errors], ...info });
    }
  }

  // back office
  const ops = await browser.newContext({ viewport: SIZES.desktop, deviceScaleFactor: 1 });
  const op = await ops.newPage();
  const opErrors = [];
  watch(op, opErrors);
  await op.goto(BASE + "/ops/login");
  await op.locator("#em").fill("admin@accel.demo");
  await op.locator("#pw").fill("demo1234");
  await op.getByRole("button", { name: "Sign in" }).click();
  await op.waitForURL(/\/ops$/);
  const caseId = await (await op.request.get(BASE + "/api/backoffice/kyc-queue", {
    headers: { Authorization: "Bearer " + (await op.evaluate(() => JSON.parse(sessionStorage.getItem("accel-journey-v1") || "{}").staffToken)) },
  })).json().then((d) => d.cases?.[0]?.case_id).catch(() => null);
  const opRoutes = [["ops-overview", "/ops"], ["ops-leads", "/ops/leads"], ["ops-kyc", "/ops/kyc"], ["ops-orders", "/ops/orders"],
    ["ops-partners", "/ops/partners"], ["ops-callbacks", "/ops/callbacks"], ["ops-audit", "/ops/audit"]];
  if (caseId) opRoutes.push(["ops-kyc-case", `/ops/kyc/${caseId}`]);
  for (const [size, vp] of Object.entries(SIZES)) {
    await op.setViewportSize(vp);
    for (const [name, url] of opRoutes) {
      opErrors.length = 0;
      await op.goto(BASE + url);
      await op.waitForLoadState("networkidle").catch(() => undefined);
      const info = await inspect(op);
      const file = await shoot(op, name, size);
      report.screens.push({ area: "ops", size, name, url, file, errors: [...opErrors], ...info });
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "ui_audit.json"), JSON.stringify(report, null, 1));
  const bad = report.screens.filter((s) => s.errors.length || s.overflow > 0 || s.smallTargets.length || (s.notFound && s.name !== "not-found"));
  console.log(report.journey.join("\n"));
  console.log(`${report.screens.length} screens captured; ${bad.length} with findings`);
  for (const s of bad) console.log(` - ${s.size} ${s.name}: ${s.errors.join("; ")}${s.overflow ? ` overflow ${s.overflow}px` : ""}${s.smallTargets.length ? ` small: ${s.smallTargets.join(", ")}` : ""}`);
})();
