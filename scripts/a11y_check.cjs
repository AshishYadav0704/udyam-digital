// Automated accessibility scan (axe-core, WCAG 2.1 A/AA rules) of the main customer screens and the back office.
// Usage: node scripts/a11y_check.cjs <path-to-axe.min.js> [baseUrl]
// Writes test-results/a11y.json. Automated scans find roughly a third of accessibility issues; manual checks still apply.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const AXE = process.argv[2];
const BASE = process.argv[3] || "http://127.0.0.1:5173";
const OUT = path.join(__dirname, "..", "test-results", "a11y.json");

async function scan(page, name, results) {
  await page.addScriptTag({ path: AXE });
  const r = await page.evaluate(async () => {
    // eslint-disable-next-line no-undef
    const res = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
    return res.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, sample: v.nodes[0]?.target?.join(" ") }));
  });
  results.push({ screen: name, violations: r });
  console.log(name.padEnd(28), r.length ? r.map((v) => `${v.id}(${v.impact},${v.nodes})`).join(" ") : "no violations");
}

(async () => {
  const browser = await chromium.launch();
  const results = [];
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  for (const [name, url] of [["Landing", "/"], ["Language", "/language"], ["Onboarding", "/start"], ["Help", "/help"], ["Call-back", "/help/callback"], ["Form", "/advisor/form"]]) {
    await page.goto(BASE + url);
    await page.waitForTimeout(700);
    await scan(page, name, results);
  }
  // advisor, plan, add-ons, quote, checkout
  await page.goto(BASE + "/advisor");
  await page.locator("#advisor-input").waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[role="log"] p').length > 0);
  await scan(page, "Advisor", results);
  const say = async (t) => {
    const resp = page.waitForResponse((r) => r.url().includes("/messages"));
    await page.locator("#advisor-input").fill(t);
    await page.locator("#advisor-input").press("Enter");
    return (await resp).json();
  };
  let r = await say("CA firm in Delhi, 12 employees, one office, GST registered");
  if (r.state !== "recommended") {
    const resp = page.waitForResponse((x) => x.url().includes("/messages"));
    await page.getByRole("button", { name: "Show my plan" }).click();
    r = await (await resp).json();
  }
  await page.getByRole("button", { name: "See plan and price" }).click();
  await page.getByRole("heading", { name: "Your recommended plan" }).waitFor();
  await scan(page, "Plan", results);
  await page.getByRole("button", { name: "Choose add-ons" }).click();
  await page.waitForTimeout(800);
  await scan(page, "Add-ons", results);
  await page.getByRole("button", { name: "Review quote" }).click();
  await page.getByText("You pay each month").waitFor();
  await scan(page, "Quote", results);
  await page.getByRole("button", { name: "Proceed to checkout" }).click();
  await page.waitForTimeout(600);
  await scan(page, "Checkout", results);
  await ctx.close();
  // back office
  const ops = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const op = await ops.newPage();
  await op.goto(BASE + "/ops/login");
  await scan(op, "Staff sign-in", results);
  await op.locator("#em").fill("admin@accel.demo");
  await op.locator("#pw").fill("demo1234");
  await op.getByRole("button", { name: "Sign in" }).click();
  await op.waitForURL(/\/ops$/);
  await op.getByText("Historic baseline").waitFor();
  await scan(op, "Back-office overview", results);
  await op.getByRole("link", { name: "Leads" }).click();
  await op.waitForURL("**/ops/leads");
  await op.getByText(/leads\. \d+ priority/).waitFor();
  await scan(op, "Back-office leads", results);
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(results, null, 1));
  const total = results.reduce((a, s) => a + s.violations.length, 0);
  console.log(`\n${results.length} screens scanned, ${total} rule violations -> ${OUT}`);
})();
