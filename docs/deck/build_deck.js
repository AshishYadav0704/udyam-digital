// Builds the submission deck on the supplied Airtel SYNC template artwork.
//   node build_deck.js   -> cover + 7 content slides, file Shankhnad_MMMUT_GORAKHPUR.pptx
// Unstop confirmed by email (3 Nov 2026) that a separate cover may precede the 7 content slides. The order follows the
// official asks: approach, a detailed competitive analysis and impact (Unstop round page); architecture, target customer,
// pricing, rollout and risks (case PDF, "What teams submit").
// Every number is taken from analysis/outputs/*.json produced by the analysis scripts.
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

// Optional: writes the theme colours into the package (pptx skill helper). Skipped when not available.
let applyTheme = async () => console.warn("apply_theme.js not found - theme colours left at defaults");
try {
  const skill = process.env.PPTX_SKILL_DIR || fs.readFileSync("/tmp/pptx_skill_dir", "utf8").trim();
  applyTheme = require(path.join(skill, "scripts", "apply_theme.js")).applyTheme;
} catch { /* optional */ }

const ROOT = path.resolve(__dirname, "..", "..");
const TPL = path.join(__dirname, "template");   // artwork unpacked unchanged from Submission_Template_Sync.pptx (ppt/media)
const SCREENS = path.join(__dirname, "screens");
const metrics = JSON.parse(fs.readFileSync(path.join(ROOT, "analysis/outputs/metrics.json"), "utf8"));
const bc = JSON.parse(fs.readFileSync(path.join(ROOT, "analysis/outputs/business_case.json"), "utf8"));
const advEval = JSON.parse(fs.readFileSync(path.join(ROOT, "analysis/outputs/advisor_eval.json"), "utf8"));
const card = JSON.parse(fs.readFileSync(path.join(ROOT, "ml/artifacts/model_card.json"), "utf8"));
const ocr = JSON.parse(fs.readFileSync(path.join(ROOT, "analysis/outputs/ocr_benchmark.json"), "utf8"));
const segBundles = JSON.parse(fs.readFileSync(path.join(ROOT, "analysis/outputs/segment_bundles.json"), "utf8"));

// Optional links to the code repository and the demo video, shown on the last slide (see links.example.json).
const LINKS = (() => {
  const f = path.join(__dirname, "links.json");
  if (!fs.existsSync(f)) return {};
  const l = JSON.parse(fs.readFileSync(f, "utf8"));
  for (const k of ["repo", "video"]) {
    if (l[k] && !/^https:\/\/\S+$/.test(l[k])) throw new Error(`links.json: ${k} must be a full https:// URL, got ${l[k]}`);
  }
  return l;
})();

const OUTNAME = "Shankhnad_MMMUT_GORAKHPUR.pptx";

const C = { navy: "1B2A4A", ink3: "46597F", muted: "5B6475", line: "DDE2EA", mist: "F3F5F8", red: "D40000",
  green: "1F7A4D", amber: "8A5A00", amberSoft: "FFF4D6", white: "FFFFFF", marigold: "E8A317" };
const FONT = "Calibri";
const THEME = { name: "Udyam Digital", headFontFace: FONT, bodyFontFace: FONT,
  colors: { dk1: C.navy, lt1: C.white, dk2: C.ink3, lt2: C.mist, accent1: C.navy, accent2: C.red, accent3: C.green,
    accent4: C.marigold, accent5: C.muted, accent6: C.amber, hlink: C.navy, folHlink: C.ink3 } };

const inr = (x) => "₹" + Math.round(x).toLocaleString("en-IN");
const pct = (x, d = 1) => (x * 100).toFixed(d) + "%";
const sc = bc.scenarios;
const ov = metrics.overall;

// ------------------------------------------------------------------ presentation + layouts
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in, the template's own size
pres.author = "Team Shankhnad, MMMUT Gorakhpur";
pres.company = "Team Shankhnad";
pres.title = "Project Udyam Digital - Airtel SYNC 2026, Track A";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

pres.defineSlideMaster({
  title: "SYNC_COVER",
  background: { path: path.join(TPL, "cover.jpg") },
  objects: [],
});
pres.defineSlideMaster({
  title: "SYNC_CONTENT",
  background: { path: path.join(TPL, "inside.jpg") },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.45, y: 0.64, w: 8.2, h: 0.52, fontFace: FONT, fontSize: 28,
      bold: true, color: C.navy, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.45, y: 1.14, w: 9.1, h: 0.36, fontFace: FONT, fontSize: 14,
      color: C.muted, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 9.25, y: 0.72, w: 0.3, h: 0.3, fontFace: FONT, fontSize: 10, color: C.muted, align: "right" },
});

function contentSlide(section, title, subtitle, source, notes, last = false) {
  const s = pres.addSlide({ masterName: "SYNC_CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  s.addText(subtitle, { placeholder: "body" });
  if (last && (LINKS.repo || LINKS.video)) {
    // last slide: the source line plus the links judges need to reach the prototype
    const runs = [{ text: source, options: { breakLine: true } }];
    if (LINKS.repo) runs.push({ text: "Code: ", options: { bold: true, color: C.navy } },
      { text: LINKS.repo, options: { color: C.navy, hyperlink: { url: LINKS.repo } } });
    if (LINKS.repo && LINKS.video) runs.push({ text: "      " });
    if (LINKS.video) runs.push({ text: "Demo video: ", options: { bold: true, color: C.navy } },
      { text: LINKS.video, options: { color: C.navy, hyperlink: { url: LINKS.video } } });
    s.addText(runs, { x: 0.45, y: 5.13, w: 7.7, h: 0.4, fontFace: FONT, fontSize: 9, color: C.muted, margin: 0,
      isTextBox: true, valign: "top", objectName: "Source and links" });
  } else if (source) s.addText(source, { x: 0.45, y: 5.22, w: 7.7, h: 0.26, fontFace: FONT, fontSize: 10, color: C.muted, margin: 0,
    isTextBox: true, objectName: "Source" });
  if (notes) s.addNotes(notes);
  return s;
}
const T = (s, text, o) => s.addText(text, { fontFace: FONT, margin: 0, isTextBox: true, color: C.navy, valign: "top", ...o });
const box = (s, o) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { rectRadius: 0.06, line: { color: C.line, width: 1 }, fill: { color: C.white }, ...o });
const ALT = {
  advisor_hi: "Advisor conversation in Hindi ending in a recommended plan with its monthly price",
  plan: "Recommended plan screen with a reason per product and a lower-cost option",
  quote: "Quote rendered as a bill with GST shown separately and a validity stamp",
  kyc_action_needed: "KYC result asking the owner to upload an address proof from the last 90 days",
  tracker: "Order tracker with completed and upcoming milestones and dates",
  kyc_review: "KYC result showing a GSTIN mismatch sent to a human reviewer",
};
const phone = (s, file, x, y, h, name) => {
  const w = h * (1170 / 2532);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.05, y: y - 0.05, w: w + 0.1, h: h + 0.1, rectRadius: 0.1,
    fill: { color: C.white }, line: { color: "C9D0DB", width: 1 },
    shadow: { type: "outer", color: "1B2A4A", opacity: 0.18, blur: 6, offset: 2, angle: 90 }, objectName: name + " frame" });
  s.addImage({ path: path.join(SCREENS, file), x, y, w, h, objectName: name, altText: ALT[name] || name });
  return w;
};

// ------------------------------------------------------------------ cover
pres.addSection({ title: "Cover" });
{
  const s = pres.addSlide({ masterName: "SYNC_COVER", sectionTitle: "Cover" });
  T(s, "Project Udyam Digital", { x: 0.55, y: 2.78, w: 4.3, h: 0.58, fontSize: 32, bold: true, color: C.white, objectName: "Title" });
  T(s, "Enterprise Track A, Digital Track", { x: 0.55, y: 3.36, w: 4.3, h: 0.34, fontSize: 16, color: "F2D6D6" });
  T(s, "From business needs to digital readiness, in one guided journey.", { x: 0.55, y: 3.86, w: 3.9, h: 0.6, fontSize: 16,
    italic: true, color: C.white });
  T(s, [
    { text: "Team Shankhnad", options: { bold: true, breakLine: true } },
    { text: "MMMUT_GORAKHPUR" },
  ], { x: 0.55, y: 4.6, w: 3.5, h: 0.56, fontSize: 14, color: C.white });
  s.addNotes("Team Shankhnad from MMMUT Gorakhpur. Project Udyam Digital, Enterprise Track A. In one sentence: we turn a " +
    "business owner's own words into an eligible, priced plan, a verified KYC and a tracked installation, in one guided " +
    "journey in Hindi or English. Accel Business is the case's fictional operator and all data is the synthetic case data.");
}

// ------------------------------------------------------------------ 1. problem and evidence
// pooled 6-month churn of activated customers, by the number of status calls they had to make
function churnByCalls(lo, hi) {
  const g = Object.entries(metrics.status_calls_vs_outcomes).filter(([k]) => +k >= lo && +k <= hi).map(([, v]) => v);
  const n = g.reduce((a, v) => a + v.n, 0);
  return { n, churn: g.reduce((a, v) => a + v.n * v.churn, 0) / n };
}
const fewCalls = churnByCalls(1, 2), manyCalls = churnByCalls(4, 5);
pres.addSection({ title: "Problem" });
{
  const f = metrics.funnel.cumulative;
  const ch = metrics.channels;
  const remote = ["Website form", "WhatsApp campaign", "Referral", "Inbound call"].map((k) => ch[k].cac);
  const s = contentSlide("Problem", "Friction, not demand, loses the customers",
    `${ov.activated} of ${ov.leads.toLocaleString("en-IN")} leads became customers (${pct(ov.activation_rate, 2)}); every step loses more than 30% of those who reach it.`,
    "Observed in smb_leads.csv (synthetic, 5,000 leads, Apr-Jun 2026); analysis/01_data_audit.py and 02_business_diagnosis.py",
    "Five thousand leads, 368 customers. The losses are not about demand: 1,113 owners dropped at the quote, mostly price and " +
    "a quote that was too slow or too complex; 827 never got the visit; 273 said yes and then fell out at paperwork. The data " +
    "shows three more things. 56 of the 368 bundles sold broke the catalogue's own eligibility rules, so a rules engine checks " +
    "every one. Field sales cost twenty-four thousand rupees per customer, against four to six thousand through the website, " +
    "WhatsApp, referrals and inbound calls. And customers who had to chase status four or five times churned about twice as often.");
  T(s, "Leads reaching each stage", { x: 0.45, y: 1.62, w: 4.6, h: 0.3, fontSize: 14, bold: true });
  s.addChart(pres.charts.BAR, [{ name: "Leads", labels: Object.keys(f), values: Object.values(f) }], {
    x: 0.35, y: 1.95, w: 4.75, h: 3.15, barDir: "bar", catAxisOrientation: "maxMin", chartColors: [C.navy],
    barGapWidthPct: 45, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    catAxisLineShow: false, catAxisLabelColor: C.navy, catAxisLabelFontSize: 13, catAxisLabelFontFace: FONT,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13, dataLabelFontFace: FONT, dataLabelColor: C.navy,
    dataLabelFormatCode: "#,##0", showLegend: false, valAxisMaxVal: 6200, objectName: "Funnel chart",
  });
  const n = metrics.needs_to_quote_breakdown;
  const rows = [
    ["1,113", `lost at the quote: price ${n.price}, slow or complex quote ${n.quote_experience}`, C.red],
    ["827", "lost because the needs visit never happened", C.navy],
    ["273", "accepted a quote, then dropped out at paperwork", C.navy],
    ["220", "lost after KYC: slow installs, no fibre, failed payments", C.navy],
  ];
  rows.forEach(([num, txt, col], i) => {
    const y = 1.62 + i * 0.54;
    T(s, num, { x: 5.4, y, w: 1.05, h: 0.46, fontSize: 24, bold: true, color: col, valign: "middle" });
    T(s, txt, { x: 6.5, y: y + 0.01, w: 3.05, h: 0.46, fontSize: 13, valign: "middle" });
  });
  T(s, "What else the data shows", { x: 5.4, y: 3.84, w: 4.1, h: 0.26, fontSize: 12, bold: true, color: C.muted });
  const signals = [
    [`${metrics.historic_rule_violations.bundles} of ${ov.activated}`, "bundles sold broke the catalogue's own eligibility rules"],
    [inr(ch["Field sales"].cac), `CAC via field sales; ${inr(Math.min(...remote))}-${inr(Math.max(...remote)).slice(1)} via web, WhatsApp, referral`],
    [pct(manyCalls.churn), `6-month churn after 4-5 status calls; ${pct(fewCalls.churn)} after 1-2`],
  ];
  signals.forEach(([v, l], i) => {
    const x = 5.4 + i * 1.4;
    box(s, { x, y: 4.13, w: 1.3, h: 1.0, fill: { color: C.mist }, line: { color: C.mist } });
    T(s, v, { x: x + 0.1, y: 4.17, w: 1.15, h: 0.3, fontSize: 15, bold: true, color: i === 0 ? C.red : C.navy });
    T(s, l, { x: x + 0.1, y: 4.47, w: 1.15, h: 0.62, fontSize: 9.5, color: C.ink3, objectName: "Signal " + (i + 1) });
  });
}

// ------------------------------------------------------------------ 2. segments: priority, bundle, who sells
pres.addSection({ title: "Segments" });
{
  const seg = metrics.segments;
  const sb = segBundles;
  const s = contentSlide("Segments", "Start with professionals and micro shops",
    "Professionals pay back in 1.6 months, micro shops are half the leads; firms with 73% of revenue stay sales-led.",
    "Observed in smb_leads.csv: bundles are what activated customers bought, medians (analysis/02b_segment_bundles.py)",
    "Which segments first? Professional practices: 11 percent activate, CAC under eleven thousand rupees, paid back in 1.6 " +
    "months, and their bundle is standard: fibre, SIMs and cloud email at about six and a half thousand a month for twelve " +
    "months. Then micro shops: half the leads, and only self-serve reaches them profitably, with fibre and a SIM at about two " +
    "and a half thousand a month. Multi-site businesses and manufacturers bring 73 percent of new revenue; they stay with field " +
    "and key-account sales, who use the same quote, KYC and tracker. Partners serve cities not yet open online and keep the " +
    "sign-ups their QR codes bring. Prices are one catalogue-midpoint price per product, revenue-neutral against history.");
  const mrrTotal = Object.values(seg).reduce((a, v) => a + v.mrr, 0);
  const H = (t, a = "right") => ({ text: t, options: { bold: true, color: C.muted, fontSize: 10.5, align: a, fill: { color: C.mist } } });
  const R = (t) => ({ text: t, options: { align: "right" } });
  const name = (t, how, first) => ({ text: [
    { text: t, options: { bold: true, breakLine: true } },
    { text: how, options: { fontSize: 10, bold: first, color: first ? C.red : C.ink3 } },
  ], options: { align: "left" } });
  const price = (k) => `${inr(sb[k].median_bundle_inr)} a month; ${sb[k].median_contract_months} months`;
  const fits = {
    prof: "Fibre, postpaid SIMs, cloud email; many add security, backup",
    micro: "Fibre and a postpaid SIM; a third add POS, Wi-Fi or CCTV",
    multi: "Fibre and SIMs; about half add 4G/5G failover, POS, CCTV",
    mfg: `SIMs, cloud email, leased line (${pct(sb.mfg.family_share.leased_line, 0)}); security, firewall`,
  };
  const how = { prof: ["1st: digital first, call-back", true], micro: ["2nd: self-serve", true],
    multi: ["Field sales, digital KYC", false], mfg: ["Key-account sales", false] };
  const label = { prof: "Professional practices", micro: "Micro retail & services", multi: "Multi-site businesses", mfg: "Small manufacturers" };
  const rows = [[H("Segment, and who sells", "left"), H("Leads"), H("Activation"), H("CAC"), H("New MRR"),
    H("Bundle that fits: what its customers bought", "left"), H("Median price, term", "left")]];
  ["prof", "micro", "multi", "mfg"].forEach((k) => {
    const v = seg[k];
    rows.push([name(label[k], ...how[k]), R(v.leads.toLocaleString("en-IN")), R(pct(v.activation_rate)), R(inr(v.cac)),
      { text: Math.round((v.mrr / mrrTotal) * 100) + "%", options: { align: "right", bold: true, color: k === "multi" || k === "mfg" ? C.red : C.navy } },
      fits[k], price(k)]);
  });
  s.addTable(rows, { x: 0.45, y: 1.62, w: 9.1, colW: [2.0, 0.6, 0.8, 0.78, 0.72, 2.95, 1.25], fontFace: FONT, fontSize: 11,
    color: C.navy, valign: "middle", border: { type: "solid", color: C.line, pt: 0.75 }, margin: [2, 5, 2, 5],
    rowH: [0.3, 0.5, 0.5, 0.5, 0.5], objectName: "Segment priorities and bundles" });
  box(s, { x: 0.45, y: 4.08, w: 4.45, h: 1.02, fill: { color: C.mist }, line: { color: C.mist } });
  T(s, [
    { text: "Field sales and partners keep a role", options: { bold: true, breakLine: true } },
    { text: "Sales take multi-site and factory deals over ₹25k a month. Partners serve cities not yet online and keep their QR sign-ups. Response: KYC reviewer 4 h, partner 48 h, sales or call-back 24 h." },
  ], { x: 0.58, y: 4.12, w: 4.22, h: 0.94, fontSize: 11, valign: "middle", objectName: "Field force and partners" });
  box(s, { x: 5.1, y: 4.08, w: 4.45, h: 1.02, fill: { color: C.mist }, line: { color: C.mist } });
  T(s, [
    { text: "Pricing", options: { bold: true, breakLine: true } },
    { text: `One catalogue-midpoint price per product: ${(metrics.price_realisation.midpoint_vs_actual_mrr * 100).toFixed(1)}% of historic revenue. A Starter option beside every plan; GST shown apart; the server re-prices at checkout.` },
  ], { x: 5.23, y: 4.12, w: 4.22, h: 0.94, fontSize: 11, valign: "middle", objectName: "Pricing policy" });
}

// ------------------------------------------------------------------ 3. product experience
pres.addSection({ title: "Product" });
{
  const s = contentSlide("Product", "One guided journey, in Hindi or English",
    "Fifteen screens from the first question to activation; a call-back is one tap away on each of them.",
    "Captured from the running prototype with synthetic data (scripts/deck_screens.cjs); Accel Business is the case's fictional operator",
    "Here is the journey. The owner types in Hindi or English, or fills a short form, and the GenAI advisor asks only what " +
    "is missing. The plan explains every product, shows a cheaper option next to it, and add-ons toggle on and off. The quote is one price with GST shown, held for fifteen days. KYC failures come back " +
    "as fix-it steps, not rejections. And the tracker shows every milestone, including the end-user KYC that DoT requires " +
    "for business mobile lines, so nobody has to call to ask.");
  const items = [
    ["advisor_hi.png", "GenAI advisor, Hindi or English"],
    ["plan.png", "Reasons, cheaper option, add-on toggles"],
    ["quote.png", "One price, GST shown, held 15 days"],
    ["kyc_action_needed.png", "Fix-it steps instead of a rejection"],
    ["tracker.png", "Every milestone and date, no status calls"],
  ];
  const h = 2.95, w = h * (1170 / 2532), gap = (9.1 - 5 * w) / 4;
  items.forEach(([f, cap], i) => {
    const x = 0.45 + i * (w + gap);
    phone(s, f, x, 1.66, h, f.replace(".png", ""));
    T(s, cap, { x: x - 0.15, y: 4.72, w: w + 0.3, h: 0.42, fontSize: 12, align: "center", color: C.navy });
  });
}

// ------------------------------------------------------------------ 4. competitive analysis
// Facts only from docs/research/research_notes.md (public pages and press, Nov 2026); a dash means we did not find it.
pres.addSection({ title: "Competition" });
{
  const s = contentSlide("Competition", "Rivals list packages; we run the journey",
    "Competitive analysis: how small businesses buy from four telcos today, from their public pages and press.",
    "— = not found on their public pages or in press, Nov 2026; not a claim about internal tools. Sources: docs/research/research_notes.md",
    "We read the public pages and press of the four telcos selling to small businesses. Airtel Office Internet and " +
    "JioBusiness publish packages and prices, then it is an enquiry form or an executive's call. Tata Tele Business is " +
    "consultative and partner-led. Vi offers a self-check tool and sign-up online or in a store. They lead on networks, brands " +
    "and partners, and the case notes that rivals are starting to offer instant online sign-up for single products. What we did not find " +
    "publicly is the whole journey for a bundle: advice in the owner's language, an eligibility-checked quote, KYC that says " +
    "what to fix, and tracking, in one session. That is the gap, and it sits on the operator's own catalogue.");
  const ours = "FCE9E9";
  const head = (t, mine) => ({ text: t, options: { bold: true, fontSize: 11, color: mine ? C.red : C.navy,
    fill: { color: mine ? ours : C.mist }, valign: "middle" } });
  const crit = (t) => ({ text: t, options: { bold: true, fill: { color: C.white } } });
  const cell = (t) => ({ text: t, options: { fill: { color: C.white } } });
  const none = () => ({ text: "—", options: { color: C.muted, align: "center", fill: { color: C.white } } });
  const mine = (t) => ({ text: t, options: { bold: true, fill: { color: ours } } });
  const rows = [
    [head(""), head("Airtel Office Internet"), head("JioBusiness"), head("Tata Tele Business"), head("Vi Business"),
      head("Udyam Digital (ours)", true)],
    [crit("What is sold"), cell("Fibre up to 1 Gbps, calls; one bill"), cell("Fibre, voice and digital tools"),
      cell("SmartOffice, Smartflo cloud calling"), cell("MSME offers; PayU partner tools"),
      mine("A bundle from 25 products, built for this business")],
    [crit("Price before a sales call"), cell("Plans from ₹999"), cell("₹901 to ₹10,001 a month"), none(), none(),
      mine("Exact quote with GST, held 15 days")],
    [crit("How an owner buys"), cell("Plan pages, then an enquiry"), cell("Register interest; an executive calls"),
      cell("Consultative, partner-led, with demos"), cell("Self-check tool; online or in a store"),
      mine("Guided self-serve; a person on request")],
    [crit("Guided advice in Hindi or Hinglish"), none(), none(), none(), none(), mine("Chat or form in English, Hinglish, Hindi")],
    [crit("Need to activation in one session"), none(), none(), none(), none(),
      mine("Quote, KYC with fix-it steps, and a tracker")],
  ];
  s.addTable(rows, { x: 0.45, y: 1.62, w: 9.1, colW: [1.55, 1.42, 1.42, 1.42, 1.42, 1.87], fontFace: FONT, fontSize: 10.5,
    color: C.navy, valign: "middle", border: { type: "solid", color: C.line, pt: 0.75 }, margin: [2, 5, 2, 5],
    rowH: [0.4, 0.42, 0.42, 0.42, 0.42, 0.42], objectName: "Competitor comparison" });
  box(s, { x: 0.45, y: 4.42, w: 4.45, h: 0.68, fill: { color: C.mist }, line: { color: C.mist } });
  T(s, [
    { text: "Where they lead: ", options: { bold: true } },
    { text: "networks, brands and partners (Google Cloud, Cisco, PayU). The case notes rivals are starting to sign up single products online." },
  ], { x: 0.58, y: 4.45, w: 4.22, h: 0.62, fontSize: 11.5, valign: "middle", objectName: "Where they lead" });
  box(s, { x: 5.1, y: 4.42, w: 4.45, h: 0.68, fill: { color: ours }, line: { color: ours } });
  T(s, [
    { text: "Our edge: ", options: { bold: true, color: C.red } },
    { text: "one session from need to an eligible bundle, KYC and tracking, in the owner's language, on the operator's own catalogue." },
  ], { x: 5.23, y: 4.45, w: 4.22, h: 0.62, fontSize: 11.5, valign: "middle", objectName: "Our edge" });
}

// ------------------------------------------------------------------ 5. architecture and intelligence
pres.addSection({ title: "Architecture" });
{
  const off = advEval.offline;
  const lr = card.leaderboard["Logistic regression"];
  const s = contentSlide("Architecture", "Rules decide, models assist",
    "One FastAPI service with separate modules; the rules engine and the KYC checks make every decision.",
    "Held-out results: analysis/outputs/advisor_eval.md, ml_report.md (trained Apr-May, tested on June), ocr_benchmark.md",
    "The architecture is a modular monolith: one service, clear modules. The two dark boxes decide: the rules engine prices " +
    "and checks eligibility, Smart KYC checks documents. Everything else assists. The advisor reads English, Hinglish and " +
    "Hindi: GenAI, when a key is set, reads the owner's words and explains the computed plan; with GenAI off, the offline " +
    "extractor still gets 94 percent of fields right on a held-out set. The lead score lifts the top fifth to 2.3 times the average rate " +
    "on a month it never saw. And no language model ever sets a price or makes a decision; with no key, it runs offline. " +
    "Along the bottom are the integration points: the operator's CRM, catalogue and billing, and order and provisioning " +
    "systems, plus GSP, Udyam, DigiLocker, eSign, SMS and UPI. GSP, Udyam, SMS and payments are mocks today, behind the " +
    "interface the real service will use; DigiLocker, eSign and the operator's own systems are designed, not built.");
  const node = (x, y, w, h, title, sub, style = {}) => {
    const dark = style.dark, dash = style.dash;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.05,
      fill: { color: dark ? C.navy : style.fill || C.white },
      line: { color: dark ? C.navy : style.stroke || C.navy, width: 1, dashType: dash ? "dash" : "solid" }, objectName: title });
    s.addText([
      { text: title, options: { bold: true, fontSize: 12, color: dark ? C.white : C.navy, breakLine: !!sub } },
      ...(sub ? [{ text: sub, options: { fontSize: 10, color: dark ? "D6DCEA" : C.ink3 } }] : []),
    ], { x, y, w, h, fontFace: FONT, align: "center", valign: "middle", margin: 2, isTextBox: true });
  };
  const arrow = (x1, y1, x2, y2, dash) => s.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color: C.ink3, width: 1.25, endArrowType: "triangle", dashType: dash ? "dash" : "solid" } });
  node(0.45, 1.62, 2.8, 0.44, "Business owner", "phone, Hindi or English");
  node(3.45, 1.62, 2.8, 0.44, "Staff", "sales, partner, KYC reviewer, admin");
  arrow(1.85, 2.06, 1.85, 2.22); arrow(4.85, 2.06, 4.85, 2.22);
  node(0.45, 2.24, 5.8, 0.4, "Web app", "15 customer screens + back office (React, TypeScript)");
  arrow(3.35, 2.64, 3.35, 2.78);
  node(0.45, 2.8, 5.8, 0.4, "Security layer", "OTP + JWT, five roles, rate limits, masked logs, audit trail", { fill: C.mist, stroke: C.mist });
  const mods = [["Advisor", "EN, Hinglish, HI", false], ["Rules engine", "price, eligibility", true], ["Smart KYC", "OCR, cross-checks", true],
    ["Orders, privacy", "consent, tracker", false], ["Routing", "score, who helps", false]];
  const mw = (5.8 - 4 * 0.1) / 5;
  mods.forEach(([t, sub, dark], i) => {
    const x = 0.45 + i * (mw + 0.1);
    arrow(x + mw / 2, 3.2, x + mw / 2, 3.34);
    node(x, 3.36, mw, 0.74, t, sub, { dark });
  });
  const colX = (i) => 0.45 + i * (mw + 0.1);
  arrow(colX(0) + mw / 2, 4.1, colX(0) + mw / 2, 4.3, true);
  arrow(colX(1) + mw / 2, 4.1, colX(1) + mw / 2, 4.3);
  [2, 3, 4].forEach((i) => arrow(colX(i) + mw / 2, 4.1, colX(i) + mw / 2, 4.3, true));
  node(colX(0), 4.32, mw, 0.78, "GenAI", "optional; reads and explains masked text", { dash: true, stroke: C.ink3 });
  node(colX(1), 4.32, mw, 0.78, "Storage", "encrypted files, audited views", { fill: C.mist, stroke: C.mist });
  node(colX(2), 4.32, 3 * mw + 0.2, 0.78, "Integration points, not live yet",
    "Operator CRM, catalogue and billing, orders and provisioning; GSP, Udyam, DigiLocker, eSign, SMS, UPI",
    { fill: C.amberSoft, stroke: C.amber, dash: true });
  const kpis = [
    [pct(off.field_accuracy, 0), `of fields right on ${off.cases} held-out messages in English, Hinglish, Hindi; GenAI off`],
    [lr.lift_at_20pct.toFixed(2) + "x", "activation rate in the top-scored 20% of June leads, against the average"],
    [pct(ocr.summary.pipeline.field_accuracy, 1), `of ${ocr.summary.pipeline.fields_scored} labelled document fields read correctly`],
    ["0", "prices, eligibility rules or KYC decisions set by a language model"],
  ];
  kpis.forEach(([v, l], i) => {
    const y = 1.62 + i * 0.88;
    T(s, v, { x: 6.6, y, w: 1.2, h: 0.5, fontSize: 26, bold: true, color: i === 3 ? C.red : C.navy, valign: "middle" });
    T(s, l, { x: 7.85, y: y + 0.02, w: 1.7, h: 0.8, fontSize: 12, color: C.navy, valign: "top" });
  });
}

// ------------------------------------------------------------------ 6. Smart KYC, consent and data protection
pres.addSection({ title: "KYC and privacy" });
{
  const s = contentSlide("KYC and privacy", "Verify in minutes, ask a person when unsure",
    "Consent first, only the data KYC needs, and a reviewer instead of an automatic rejection.",
    "Specimen decisions are our own evaluation (analysis/03), not an answer key; GSTIN and Udyam registries are local mocks.",
    "KYC starts only after itemised consent. Each upload is checked, cleaned and read three ways, then looked up in the GSTIN " +
    "and Udyam registries, which are mocks today, and cross-checked against the declaration. On the twelve specimen " +
    "applicants: six verified automatically, two were told exactly what to fix, four went to a reviewer - for example K06, " +
    "whose certificate GSTIN fails its checksum. The DPDP Act's three tests from the case are built in: consent per purpose, " +
    "data used only for KYC, and only the data needed - lookups send just the GSTIN or Udyam number, and GenAI sees masked " +
    "text, never documents. Documents are encrypted, every view is audited, and withdrawing consent deletes them.");
  const steps = [
    "Consent per purpose, before any upload",
    "File checks; metadata stripped",
    "Deskew, blur check, watermark removal",
    "Three OCR passes; GSTIN checksum, formats",
    "Mock GSTIN and Udyam lookup; cross-checks",
    "Verified, fix-it request, or a reviewer",
  ];
  steps.forEach((t, i) => {
    const y = 1.64 + i * 0.44;
    s.addShape(pres.shapes.OVAL, { x: 0.45, y: y + 0.03, w: 0.3, h: 0.3, fill: { color: i === 5 ? C.red : C.navy }, line: { color: i === 5 ? C.red : C.navy } });
    T(s, String(i + 1), { x: 0.45, y: y + 0.03, w: 0.3, h: 0.3, fontSize: 12, bold: true, color: C.white, align: "center", valign: "middle" });
    T(s, t, { x: 0.88, y, w: 3.85, h: 0.36, fontSize: 13, valign: "middle" });
  });
  box(s, { x: 0.45, y: 4.34, w: 4.2, h: 0.8, fill: { color: C.mist }, line: { color: C.mist } });
  T(s, [
    { text: "12 specimen applicants: ", options: { bold: true } },
    { text: "6 verified, 2 asked to fix, 4 to a reviewer", options: { breakLine: true } },
    { text: "K06 GSTIN fails its checksum; K11 bill is 257 days old", options: { color: C.ink3 } },
  ], { x: 0.58, y: 4.4, w: 4.0, h: 0.7, fontSize: 13, valign: "middle" });
  phone(s, "kyc_review.png", 4.88, 1.66, 3.45, "kyc_review");
  T(s, "DPDP Act 2023, by design", { x: 6.62, y: 1.62, w: 2.93, h: 0.3, fontSize: 14, bold: true });
  const dp = (head, body, last) => [{ text: head + " ", options: { bold: true } }, { text: body, options: { breakLine: !last } }];
  T(s, [
    ...dp("Consent:", "per purpose, before any upload; optional ones start off; withdraw any time."),
    ...dp("Purpose limitation:", "KYC data is used only for KYC; partners see only their own leads."),
    ...dp("Data minimisation:", "lookups send only the GSTIN or Udyam number; GenAI sees masked text, never documents."),
    ...dp("Retention:", "documents deleted on schedule, and at once on withdrawal; encrypted, every view audited.", true),
  ], { x: 6.62, y: 1.96, w: 2.93, h: 2.14, fontSize: 11, paraSpaceAfter: 5, valign: "top", objectName: "DPDP by design" });
  box(s, { x: 6.62, y: 4.18, w: 2.93, h: 0.96, fill: { color: C.amberSoft }, line: { color: C.amberSoft } });
  T(s, "DPDP Rules 2025: notice, security and retention duties apply from 13-14 May 2027. Built in now; legal review before launch.",
    { x: 6.72, y: 4.23, w: 2.75, h: 0.88, fontSize: 11, color: C.navy, valign: "middle" });
}

// ------------------------------------------------------------------ 7. targets, rollout and risks (last slide carries the links)
const ex = sc.expected;
pres.addSection({ title: "Targets and rollout" });
{
  const s = contentSlide("Targets and rollout", "Five targets, proved in a two-city pilot",
    `At 60% of leads digital: ₹${(ex.year1_incremental_revenue / 1e7).toFixed(1)} crore extra revenue in year 1, and the build pays back in ${ex.build_payback_months} months.`,
    "Targets: expected case in analysis/05_business_case.py; the status-call target is an assumption. Privacy note: docs/privacy_security_note.pdf",
    "Five numbers decide whether this works, each read weekly or monthly: lead to activation from 7.4 to 10 percent, CAC " +
    "from fifteen thousand to under twelve, days to activate from 17.6 to under 11, quote acceptance from 44 to 49 percent, " +
    "and status calls halved. In the expected case that is about three crore rupees of extra revenue in year one, and the " +
    "build pays back in eleven months. We would not launch nationally on day one: eight weeks of foundations, then a " +
    "two-city pilot against today's process, gated on 1.1 times the activations and zero KYC false accepts, then ten cities " +
    "with two more languages, then national. On the right are the risks and how each is contained. The code, the demo " +
    "video and the privacy note are linked below. From business needs to digital readiness, in one guided journey.", true);
  const kpis = [
    ["Lead to activation", pct(ex.activation_rate), "from " + pct(bc.baseline.activation_rate, 2)],
    ["Blended CAC", inr(ex.cac), "from " + inr(bc.baseline.cac)],
    ["Days to activate", ex.days_to_activate.toFixed(1), "from " + bc.baseline.days_to_activate.toFixed(1)],
    ["Quote acceptance", pct(ex.step_pass_rates[2]), "from " + pct(bc.baseline.step_pass_rates[2])],
    ["Calls to chase status", "1.5 or fewer", "from " + ov.status_calls.toFixed(1)],
  ];
  const kw = (9.1 - 4 * 0.12) / 5;
  kpis.forEach(([l, v, sub], i) => {
    const x = 0.45 + i * (kw + 0.12);
    box(s, { x, y: 1.62, w: kw, h: 0.92, fill: { color: C.mist }, line: { color: C.mist } });
    T(s, l, { x: x + 0.12, y: 1.66, w: kw - 0.2, h: 0.24, fontSize: 10.5, color: C.muted });
    T(s, v, { x: x + 0.12, y: 1.9, w: kw - 0.2, h: 0.36, fontSize: 20, bold: true, color: i === 0 ? C.red : C.navy });
    T(s, sub, { x: x + 0.12, y: 2.26, w: kw - 0.2, h: 0.24, fontSize: 10.5, color: C.ink3 });
  });
  T(s, "Rollout, with a gate before each step", { x: 0.45, y: 2.68, w: 3.9, h: 0.28, fontSize: 13, bold: true });
  const phases = [
    ["Foundations", "weeks 0-8", "GSP, SMS, payments; security review, legal sign-off"],
    ["Pilot in 2 cities", "months 3-5", "A/B; gate: 1.1x activations, 0 KYC false accepts"],
    ["Scale to 10 cities", "months 6-9", "Partner QR codes, DigiLocker, two more languages"],
    ["National", "months 10-15", "Model retrained on real outcomes; eSign; DPDP live"],
  ];
  phases.forEach(([name, when, what], i) => {
    const y = 3.02 + i * 0.5;
    if (i < phases.length - 1) s.addShape(pres.shapes.LINE, { x: 0.58, y: y + 0.27, w: 0, h: 0.23, line: { color: C.line, width: 1.5 } });
    s.addShape(pres.shapes.OVAL, { x: 0.45, y, w: 0.26, h: 0.26, fill: { color: i === 1 ? C.red : C.navy }, line: { color: i === 1 ? C.red : C.navy } });
    T(s, String(i + 1), { x: 0.45, y, w: 0.26, h: 0.26, fontSize: 11, bold: true, color: C.white, align: "center", valign: "middle" });
    T(s, [{ text: name, options: { bold: true } }, { text: "   " + when, options: { color: C.muted } }],
      { x: 0.82, y: y - 0.01, w: 3.5, h: 0.24, fontSize: 12, valign: "middle" });
    T(s, what, { x: 0.82, y: y + 0.22, w: 3.55, h: 0.22, fontSize: 10, color: C.ink3, valign: "middle" });
  });
  T(s, "Risks, and how we contain them", { x: 4.55, y: 2.68, w: 5.0, h: 0.28, fontSize: 13, bold: true });
  const rh = { bold: true, color: C.muted, fontSize: 10 };
  const risk = (t) => ({ text: t, options: { bold: true } });
  const rows = [
    [{ text: "Risk", options: rh }, { text: "How we contain it", options: rh }],
    [risk("AI gives a wrong price or approval"), "GenAI never prices, decides eligibility or sees documents; offline fallback"],
    [risk("Forged or reused documents"), "Checksum, registry and duplicate checks; a person decides every unclear case"],
    [risk("Sales and partners feel bypassed"), "Routing rules, partner QR attribution; sales keep big and complex deals"],
    [risk("Owners not comfortable online"), "Hindi or English, chat or form, call-back on every screen, partner help"],
    [risk("Lead score learnt on synthetic data"), "It only orders the queue; retrained on pilot outcomes before scaling"],
  ];
  s.addTable(rows, { x: 4.55, y: 2.98, w: 5.0, colW: [1.62, 3.38], fontFace: FONT, fontSize: 10, color: C.navy,
    valign: "middle", border: { type: "solid", color: C.line, pt: 0.75 }, margin: [1, 4, 1, 4],
    rowH: [0.24, 0.35, 0.35, 0.35, 0.35, 0.35], objectName: "Risk table" });
}

// ------------------------------------------------------------------ write
(async () => {
  const out = path.join(__dirname, OUTNAME);
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("wrote", out);
})();
