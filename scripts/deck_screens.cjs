// Captures the product screenshots used in the deck (real app, real API, synthetic data).
// Usage: node scripts/deck_screens.cjs [baseUrl] [outDir]
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:5173";
const OUT = process.argv[3] || path.join(__dirname, "..", "docs", "deck", "screens");
fs.mkdirSync(OUT, { recursive: true });
const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 };

async function say(page, text) {
  const input = page.locator("#advisor-input");
  await input.fill(text);
  const resp = page.waitForResponse((r) => r.url().includes("/messages") && r.request().method() === "POST");
  await input.press("Enter");
  const j = await (await resp).json();
  await page.waitForTimeout(250);
  return j;
}
async function clickAndWait(page, name, urlPart) {
  const resp = page.waitForResponse((r) => r.url().includes(urlPart));
  await page.getByRole("button", { name, exact: true }).first().click();
  const j = await (await resp).json();
  await page.waitForTimeout(250);
  return j;
}
const shot = (page, name, opts = {}) => page.screenshot({ path: path.join(OUT, name + ".png"), ...opts });

async function toPlan(page, { text, gst, needs = [], spend }) {
  await page.goto(BASE + "/advisor");
  await page.locator("#advisor-input").waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
  let r = await say(page, text);
  return { r, page };
}

async function journeyToKyc(browser, specimen, mobile) {
  const ctx = await browser.newContext(PHONE);
  const page = await ctx.newPage();
  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "Start in English" }).click();
  await page.getByRole("button", { name: /Chat with the advisor/ }).click();
  await page.locator("#advisor-input").waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
  let r = await say(page, "We run a dental clinic in Kolkata, 5 of us, one clinic");
  r = await say(page, "Yes, GSTIN is 19EOGXH4115Y1ZL");
  if (r.expecting === "needs") r = await clickAndWait(page, "Show my plan", "/messages");
  if (r.expecting === "spend") r = await clickAndWait(page, "₹3,000-10,000", "/messages");
  await page.getByRole("button", { name: "See plan and price" }).click();
  await page.getByRole("button", { name: "Review quote" }).click();
  await page.getByText("You pay each month").waitFor();
  await page.getByRole("button", { name: "Proceed to checkout" }).click();
  await page.locator("#mobile").fill(mobile);
  await page.getByRole("button", { name: "Send OTP" }).click();
  await page.locator("#otp").fill("123456");
  await page.locator("#cname").fill("Joseph Shah");
  await page.getByRole("button", { name: "Verify" }).click();
  await page.getByText(/Logged in as/).waitFor();
  await page.locator("#a").fill("12 Park Street, Ground floor, Kolkata");
  await page.locator("#pin").fill("700016");
  await page.getByText(/I agree to the plan terms/).click();
  await page.getByRole("button", { name: "Place order" }).click();
  await page.waitForURL("**/kyc/consent");
  await page.getByText("I agree to verification as described above").waitFor();
  return { ctx, page, specimen };
}

async function finishKyc(page, specimen) {
  await page.getByText("I agree to verification as described above").click();
  await page.getByRole("button", { name: "Continue to documents" }).click();
  await page.waitForURL("**/kyc/upload");
  await page.getByRole("button", { name: "Save details" }).click();
  await page.locator("#spec").selectOption(specimen);
  const sp = page.waitForResponse((x) => x.url().includes("/specimen"));
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await sp;
  await page.waitForTimeout(1200);
  const ev = page.waitForResponse((x) => x.url().includes("/evaluate"));
  await page.getByRole("button", { name: "Verify documents" }).click();
  await ev;
  await page.waitForURL("**/kyc/result");
  await page.getByText("Verification result").waitFor();
  await page.waitForTimeout(600);
}

(async () => {
  const browser = await chromium.launch();
  try {
    // ---- English advisor mid-conversation, then plan and quote
    {
      const ctx = await browser.newContext(PHONE);
      const page = await ctx.newPage();
      await page.goto(BASE + "/");
      await page.getByRole("button", { name: "Start in English" }).click();
      await page.getByRole("button", { name: /Chat with the advisor/ }).click();
      await page.locator("#advisor-input").waitFor();
      await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
      await say(page, "We run a dental clinic in Kolkata, 5 of us, one clinic");
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, "advisor_en");
      let r = await say(page, "Yes, GSTIN is 19EOGXH4115Y1ZL");
      if (r.expecting === "needs") {
        await page.getByRole("button", { name: "Billing / POS", exact: true }).click();
        await page.getByRole("button", { name: "Business email", exact: true }).click();
        await page.evaluate(() => window.scrollTo(0, 0));
        await shot(page, "advisor_needs");
        r = await clickAndWait(page, "Show my plan", "/messages");
      }
      if (r.expecting === "spend") r = await clickAndWait(page, "₹3,000-10,000", "/messages");
      await page.getByRole("button", { name: "See plan and price" }).click();
      await page.getByRole("heading", { name: "Your recommended plan" }).waitFor();
      await page.waitForTimeout(400);
      await shot(page, "plan");
      await page.getByRole("button", { name: "Choose add-ons" }).click();
      await page.waitForTimeout(800);
      await shot(page, "addons");
      await page.getByRole("button", { name: "Review quote" }).click();
      await page.getByText("You pay each month").waitFor();
      await page.waitForTimeout(400);
      await page.evaluate(() => window.scrollTo(0, 150));
      await page.waitForTimeout(200);
      await shot(page, "quote");
      await ctx.close();
    }
    // ---- Hindi advisor with a recommendation
    {
      const ctx = await browser.newContext({ ...PHONE, locale: "hi-IN" });
      const page = await ctx.newPage();
      await page.goto(BASE + "/");
      await page.getByRole("button", { name: "हिंदी में शुरू करें" }).click();
      await page.getByRole("button", { name: /सलाहकार से चैट करें/ }).click();
      await page.locator("#advisor-input").waitFor();
      await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
      let r = await say(page, "मेरी किराना की दुकान है लखनऊ में, हम दो लोग हैं, एक ही दुकान");
      if (r.expecting === "gstin") r = await say(page, "GST नहीं है");
      if (r.expecting === "needs") r = await clickAndWait(page, "मेरा प्लान दिखाइए", "/messages");
      if (r.expecting === "spend") r = await say(page, "महीने का 800 रुपये");
      await page.waitForTimeout(400);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.locator('[role="log"]').evaluate((el) => (el.scrollTop = el.scrollHeight));
      await page.waitForTimeout(300);
      await shot(page, "advisor_hi");
      await ctx.close();
    }
    // ---- KYC: consent, action-needed (K11) and verified (K02) results, tracker
    {
      const { ctx, page } = await journeyToKyc(browser, "K11", "9822233344");
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, "consent");
      await finishKyc(page, "K11");
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, "kyc_action_needed");
      await ctx.close();
    }
    {
      const { ctx, page } = await journeyToKyc(browser, "K06", "9833344455");
      await finishKyc(page, "K06");
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, "kyc_review");
      await ctx.close();
    }
    {
      const { ctx, page } = await journeyToKyc(browser, "K02", "9844455566");
      await finishKyc(page, "K02");
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, "kyc_verified");
      await page.getByRole("button", { name: "Continue" }).click();
      await page.getByRole("button", { name: "Track my order" }).click();
      await page.getByText("Order status").waitFor();
      for (let i = 0; i < 2; i++) {
        const adv = page.waitForResponse((x) => x.url().includes("/advance"));
        await page.getByRole("button", { name: /move to the next milestone/ }).click();
        await adv;
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(300);
      await shot(page, "tracker");
      await ctx.close();
    }
    // ---- back office (desktop)
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
      const page = await ctx.newPage();
      await page.goto(BASE + "/ops/login");
      await page.locator("#em").fill("admin@accel.demo");
      await page.locator("#pw").fill("demo1234");
      await page.getByRole("button", { name: "Sign in" }).click();
      await page.waitForURL(/\/ops$/);
      await page.getByText("Historic baseline").waitFor();
      await page.waitForTimeout(800);
      await shot(page, "ops_overview");
      await page.getByRole("link", { name: "Leads" }).click();
      await page.waitForURL("**/ops/leads");
      await page.getByText(/leads\. \d+ priority/).waitFor();
      await page.locator("tbody tr").first().click();
      await page.getByText("What moves the score").waitFor();
      await page.waitForTimeout(400);
      await shot(page, "ops_leads");
      await page.getByRole("button", { name: "Close" }).click();
      await page.getByRole("link", { name: "KYC queue" }).click();
      await page.waitForURL("**/ops/kyc");
      await page.waitForTimeout(800);
      const link = page.locator("tbody a").first();
      if (await link.count()) {
        await link.click();
        await page.getByText("Findings").waitFor();
        await page.waitForTimeout(500);
        await shot(page, "ops_kyc_case");
      }
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
  console.log("screens written to", OUT, fs.readdirSync(OUT));
})();
