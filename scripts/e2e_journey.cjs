// End-to-end walk through every customer screen and the back office, with screenshots.
// Usage: node scripts/e2e_journey.cjs [baseUrl] [outDir]
// Needs the API on :8000 and the web app (vite dev or built + served) on baseUrl.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:5173";
const OUT = process.argv[3] || path.join(__dirname, "..", "docs", "screenshots");
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  - " + detail : ""}`);
}

async function shot(page, name, full = false) {
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: full });
}

async function say(page, text) {
  const input = page.locator("#advisor-input");
  await input.fill(text);
  const resp = page.waitForResponse((r) => r.url().includes("/messages") && r.request().method() === "POST");
  await input.press("Enter");
  const r = await resp;
  await page.waitForTimeout(150);
  return r.json();
}

async function tapChip(page, label) {
  const resp = page.waitForResponse((r) => r.url().includes("/messages") && r.request().method() === "POST");
  await page.getByRole("button", { name: label, exact: true }).first().click();
  const r = await resp;
  await page.waitForTimeout(150);
  return r.json();
}

async function customerJourney(browser, { specimen, mobile, prefix }) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: "en-IN" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(m.text()));

  // 1 landing
  await page.goto(BASE + "/");
  await page.getByText("Example from the live catalogue").waitFor();
  check(`${prefix} landing shows live catalogue prices`, await page.getByText("Biz Fibre 100").isVisible());
  await shot(page, `${prefix}01-landing`);
  // 2 language (deep-link entry used by WhatsApp / partner QR codes)
  await page.goto(BASE + "/language?src=WhatsApp");
  await shot(page, `${prefix}02-language`);
  await page.getByRole("button", { name: /English/ }).click();
  // 3 onboarding
  await page.waitForURL("**/start");
  await page.getByRole("heading", { name: "Before we begin" }).waitFor();
  check(`${prefix} onboarding lists documents`, await page.getByText("Photo ID of the person who will sign").isVisible());
  await shot(page, `${prefix}03-onboarding`);
  await page.getByRole("button", { name: /Chat with the advisor/ }).click();
  // 4 advisor
  await page.waitForURL("**/advisor");
  await page.locator("#advisor-input").waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
  let r = await say(page, "We run a dental clinic in Kolkata, 5 of us, one clinic");
  check(`${prefix} advisor extracted 4 slots from one sentence`, r.profile.business_type && r.profile.city === "Kolkata" && r.profile.employees === 5 && r.profile.sites === 1, JSON.stringify({ bt: r.profile.business_type, exp: r.expecting }));
  r = await say(page, "Yes, GSTIN is 19EOGXH4115Y1ZL");
  check(`${prefix} GSTIN verified against mock registry`, r.profile.gstin_status === "Active", r.profile.gstin_status);
  if (r.expecting === "needs") {
    await page.getByRole("button", { name: "Billing / POS", exact: true }).click();
    await page.getByRole("button", { name: "Business email", exact: true }).click();
    const resp = page.waitForResponse((x) => x.url().includes("/messages"));
    await page.getByRole("button", { name: "Show my plan" }).click();
    r = await (await resp).json();
  }
  if (r.expecting === "spend") r = await tapChip(page, "Rs 3,000-10,000");
  check(`${prefix} plan recommended`, r.state === "recommended", r.state);
  await page.getByRole("button", { name: "See plan and price" }).waitFor();
  await shot(page, `${prefix}04-advisor`);
  // 5 plan
  await page.getByRole("button", { name: "See plan and price" }).click();
  await page.waitForURL("**/plan");
  await page.getByRole("heading", { name: "Your recommended plan" }).waitFor();
  check(`${prefix} plan shows a reason per product`, (await page.getByRole("button", { name: /Why this/ }).count()) >= 2);
  await shot(page, `${prefix}05-plan`);
  await shot(page, `${prefix}05-plan-full`, true);
  // 6 add-ons
  await page.getByRole("button", { name: "Choose add-ons" }).click();
  await page.waitForURL("**/plan/add-ons");
  const toggles = page.locator('[role="switch"][aria-checked="false"]');
  if ((await toggles.count()) > 0) {
    const resp = page.waitForResponse((x) => x.url().includes("/quotes/preview"));
    await toggles.first().click();
    const pr = await resp;
    check(`${prefix} add-on re-priced by server`, pr.status() === 200 || pr.status() === 422, String(pr.status()));
  }
  await page.waitForTimeout(500);
  {
    // price recalculation: switching a product changes the server price; switching it back restores it
    const price = () => page.locator("[data-testid=price-monthly]").first().innerText();
    const sw = page.locator('[role="switch"]').last();
    const before = await price();
    let resp = page.waitForResponse((x) => x.url().includes("/quotes/preview"));
    await sw.click();
    await resp;
    await page.waitForTimeout(450);
    const changed = await price();
    resp = page.waitForResponse((x) => x.url().includes("/quotes/preview"));
    await sw.click();
    await resp;
    await page.waitForTimeout(450);
    check(`${prefix} add-on switch re-prices and restores`, changed !== before && (await price()) === before, `${before} -> ${changed} -> back`);
  }
  await shot(page, `${prefix}06-addons`);
  // 7 quote
  await page.getByRole("button", { name: "Review quote" }).click();
  await page.waitForURL("**/quote");
  await page.getByText("You pay each month").waitFor();
  await page.getByRole("button", { name: /Save quote/ }).click();
  await page.getByText(/This price is held till/).waitFor();
  check(`${prefix} quote saved with validity`, true);
  await shot(page, `${prefix}07-quote`, true);
  // 8 checkout
  await page.getByRole("button", { name: "Proceed to checkout" }).click();
  await page.waitForURL("**/checkout");
  await page.locator("#mobile").fill(mobile);
  await page.getByRole("button", { name: "Send OTP" }).click();
  await page.getByText(/Demo OTP/).waitFor();
  await page.locator("#otp").fill("123456");
  await page.locator("#cname").fill("Joseph Shah");
  await page.getByRole("button", { name: "Verify" }).click();
  await page.getByText(/Logged in as/).waitFor();
  await page.locator("#a").fill("12 Park Street, Ground floor, Kolkata");
  await page.locator("#pin").fill("700016");
  await page.getByText(/I agree to the plan terms/).click();
  await shot(page, `${prefix}08-checkout`, true);
  // first attempt: simulated payment failure, then retry
  await page.getByText("Demo: simulate a failed payment").click();
  await page.getByRole("button", { name: "Place order" }).click();
  await page.getByText(/The payment did not go through/).waitFor();
  check(`${prefix} payment failure handled with retry`, await page.getByRole("button", { name: "Retry payment" }).isVisible());
  await shot(page, `${prefix}08b-payment-failed`);
  await page.getByRole("button", { name: "Retry payment" }).click();
  // 9 consent
  await page.waitForURL("**/kyc/consent");
  await page.getByText("Verify your business and authorised signatory").waitFor();
  await page.getByRole("button", { name: "Continue to documents" }).click();
  check(`${prefix} consent required before documents`, await page.getByText(/Please agree to KYC verification/).isVisible());
  await page.getByText("I agree to verification as described above").click();
  await shot(page, `${prefix}09-consent`, true);
  await page.getByRole("button", { name: "Continue to documents" }).click();
  // 10 upload
  await page.waitForURL("**/kyc/upload");
  await page.getByRole("button", { name: "Save details" }).click();
  await page.getByText("Demo: load a sample applicant").waitFor();
  await page.locator("#spec").selectOption(specimen);
  const sp = page.waitForResponse((x) => x.url().includes("/specimen"));
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await sp;
  await page.waitForTimeout(1200);
  await shot(page, `${prefix}10-upload`, true);
  // 11 verification
  const ev = page.waitForResponse((x) => x.url().includes("/evaluate"));
  await page.getByRole("button", { name: "Verify documents" }).click();
  const evr = await (await ev).json();
  await page.waitForURL("**/kyc/result");
  await page.getByText("Verification result").waitFor();
  await page.waitForTimeout(500);
  check(`${prefix} KYC decision for ${specimen}`, !!evr.decision, evr.decision);
  if (specimen === "K06") check(`${prefix} low-confidence OCR read is flagged`, (await page.getByText(/% sure, check/).count()) > 0);
  await shot(page, `${prefix}11-verification`, true);
  // 12 confirmation (or straight to tracker if action is needed)
  if (evr.decision !== "action_required") {
    await page.getByRole("button", { name: "Continue" }).click();
    await page.waitForURL("**/confirmed");
    await page.getByText("Order placed").waitFor();
    await shot(page, `${prefix}12-confirmation`, true);
    await page.getByRole("button", { name: "Track my order" }).click();
  } else {
    await page.getByRole("button", { name: "See order status" }).click();
  }
  // 13 tracker
  await page.getByText("Order status").waitFor();
  if (evr.decision === "verified") {
    for (let i = 0; i < 2; i++) {
      const adv = page.waitForResponse((x) => x.url().includes("/advance"));
      await page.getByRole("button", { name: /move to the next milestone/ }).click();
      await adv;
    }
    check(`${prefix} tracker advanced to installation`, await page.getByText(/Installation scheduled/).first().isVisible());
  }
  await shot(page, `${prefix}13-tracker`, true);
  // 14 support
  await page.goto(BASE + "/help");
  await page.getByText("Is the price final?").click();
  await shot(page, `${prefix}14-support`);
  // 15 escalation
  await page.goto(BASE + "/help/callback");
  await page.locator("#cb-mobile").fill(mobile);
  await page.getByText("Evening").click();
  await page.locator("#cb-note").fill("Need help choosing CCTV for the waiting room");
  await page.getByRole("button", { name: "Request call-back" }).click();
  await page.getByText(/A specialist will call you within one working day/).waitFor();
  check(`${prefix} call-back request recorded`, true);
  await shot(page, `${prefix}15-escalation`);
  // my privacy
  await page.goto(BASE + "/privacy");
  await page.getByRole("heading", { name: "Data we hold" }).waitFor();
  await shot(page, `${prefix}16-privacy`, true);
  check(`${prefix} no JS errors`, errors.length === 0, errors.slice(0, 3).join(" | "));
  await ctx.close();
  return evr.decision;
}

async function hindiJourney(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: "hi-IN" });
  const page = await ctx.newPage();
  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "हिंदी में शुरू करें" }).click();
  await page.waitForURL("**/start");
  await shot(page, "hi03-onboarding");
  await page.getByRole("button", { name: /सलाहकार से चैट करें/ }).click();
  await page.locator("#advisor-input").waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
  let r = await say(page, "मेरी किराना की दुकान है लखनऊ में, हम दो लोग हैं, एक ही दुकान");
  check("hi advisor understood Devanagari", r.profile.city === "Lucknow" && r.profile.employees === 2, JSON.stringify({ bt: r.profile.business_type, city: r.profile.city, emp: r.profile.employees, exp: r.expecting }));
  if (r.expecting === "sites") r = await say(page, "एक");
  if (r.expecting === "gstin") r = await say(page, "GST नहीं है");
  if (r.expecting === "needs") {
    const resp = page.waitForResponse((x) => x.url().includes("/messages"));
    await page.getByRole("button", { name: "मेरा प्लान दिखाइए" }).click();
    r = await (await resp).json();
  }
  if (r.expecting === "spend") r = await say(page, "महीने का 800 रुपये");
  check("hi plan recommended in Hindi", r.state === "recommended", r.state);
  await page.waitForTimeout(300);
  await shot(page, "hi04-advisor");
  await page.getByRole("button", { name: "प्लान और कीमत देखें" }).click();
  await page.waitForURL("**/plan");
  await shot(page, "hi05-plan", true);
  await page.getByRole("button", { name: "कोटेशन देखें" }).click();
  await page.getByText("हर महीने आप देंगे").waitFor();
  await shot(page, "hi07-quote", true);
  await ctx.close();
}

async function formJourney(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(BASE + "/advisor/form");
  await page.getByRole("button", { name: "Show my plan" }).click();
  check("form validation shows required errors", (await page.getByText("required").count()) >= 3);
  await shot(page, "form-validation", true);
  await page.locator("#bt").selectOption("Restaurant / cafe");
  await page.locator("#city").fill("Darbhanga");
  await page.locator("#emp").fill("12");
  await page.getByText("No GSTIN").click();
  await page.getByRole("button", { name: "Show my plan" }).click();
  await page.getByText(/online yet/).first().waitFor();
  check("unserviceable city routes to partner call-back", await page.getByRole("button", { name: "Add call-back details" }).isVisible());
  await shot(page, "form-not-serviceable", true);
  await ctx.close();
}

async function backOffice(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const login = async (email) => {
    await page.goto(BASE + "/ops/login");
    await page.locator("#em").fill(email);
    await page.locator("#pw").fill("demo1234");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL(/\/ops$/);
  };
  await login("admin@accel.demo");
  await page.getByText("Historic baseline").waitFor();
  await page.waitForTimeout(800);
  check("ops overview shows baseline 7.36%", await page.getByText("7.36%").isVisible());
  await shot(page, "ops01-overview", true);
  await page.getByRole("link", { name: "Leads" }).click();
  await page.waitForURL("**/ops/leads");
  await page.getByText(/leads\. \d+ priority/).waitFor();
  await page.locator("tbody tr").first().click();
  await page.getByText("What moves the score").waitFor();
  check("lead panel explains score and route", await page.getByText(/^Recommended next step:/).isVisible());
  const ref = (await page.locator("aside[aria-label='Lead detail'] p.num").first().innerText()).trim();
  await page.locator("#lead-status").selectOption("contacted");
  await page.locator("#lead-note").fill("Called; owner wants the quote on WhatsApp");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByText("Follow-up saved.").waitFor();
  check("lead follow-up saved with history", (await page.getByText("Called; owner wants the quote on WhatsApp").count()) > 0);
  await shot(page, "ops02-leads");
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByLabel("Search leads").fill(ref);
  await page.waitForTimeout(400);
  await page.getByText(/^1 leads\./).waitFor();
  check("lead search finds the lead by reference", (await page.locator("tbody tr").count()) === 1, ref);
  await shot(page, "ops02b-leads-search");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await page.getByRole("link", { name: "KYC queue" }).click();
  await page.waitForURL("**/ops/kyc");
  await page.waitForTimeout(1200);
  const caseLink = page.locator("tbody a").first();
  if ((await caseLink.count()) > 0) {
    await shot(page, "ops03-kyc-queue");
    await caseLink.click();
    await page.getByText("Findings").waitFor();
    const img = page.waitForResponse((x) => x.url().includes("/image"));
    await page.getByRole("button", { name: /Open document/ }).first().click();
    await img;
    await page.waitForTimeout(600);
    await shot(page, "ops04-kyc-case", true);
  } else {
    await shot(page, "ops03-kyc-queue");
  }
  await page.getByRole("link", { name: "Call-backs" }).click();
  await page.waitForURL("**/ops/callbacks");
  await page.getByRole("columnheader", { name: "Requested" }).waitFor();
  const show = page.getByRole("button", { name: /Show/ }).first();
  if ((await show.count()) > 0) {
    await show.click();
    await page.locator('a[href^="tel:"]').first().waitFor();
    check("call-back number revealed on demand", true);
  }
  await shot(page, "ops05-callbacks");
  await page.getByRole("link", { name: "Orders" }).click();
  await page.waitForURL("**/ops/orders");
  await page.getByRole("columnheader", { name: "Last update" }).waitFor();
  await shot(page, "ops06-orders");
  await page.getByRole("link", { name: "Audit log" }).click();
  await page.waitForURL("**/ops/audit");
  await page.getByRole("columnheader", { name: "Action" }).waitFor();
  check("audit log records reveal", (await page.getByText("escalation.contact_revealed").count()) > 0);
  await shot(page, "ops07-audit");
  // role scoping: KYC reviewer sees no sales pipeline
  await page.evaluate(() => sessionStorage.clear());
  await login("kyc@accel.demo");
  check("KYC reviewer nav has no Leads", (await page.getByRole("link", { name: "Leads" }).count()) === 0);
  await page.evaluate(() => sessionStorage.clear());
  await login("partner@accel.demo");
  await page.getByRole("link", { name: "Leads" }).click();
  await page.waitForURL("**/ops/leads");
  await page.waitForTimeout(1200);
  await shot(page, "ops08-partner-leads");
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  const only = (process.env.E2E_ONLY || "main,k06,hindi,form,ops").split(",");
  try {
    if (only.includes("main")) await customerJourney(browser, { specimen: "K02", mobile: "9876543210", prefix: "" });
    if (only.includes("k06")) await customerJourney(browser, { specimen: "K06", mobile: "9812345678", prefix: "k06-" });
    if (only.includes("hindi")) await hindiJourney(browser);
    if (only.includes("form")) await formJourney(browser);
    if (only.includes("ops")) await backOffice(browser);
  } catch (e) {
    check("journey completed without exceptions", false, e.message.split("\n")[0]);
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => !r.ok);
  fs.writeFileSync(path.join(OUT, "e2e_results.json"), JSON.stringify({ base: BASE, passed: results.length - failed.length, failed: failed.length, results }, null, 2));
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})();
