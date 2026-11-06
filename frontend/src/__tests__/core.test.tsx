import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { inr } from "../lib/api";
import { selectedLines, selectionFromRecommendation, JourneyProvider } from "../lib/store";
import { translate } from "../i18n/strings";
import * as strings from "../i18n/strings";
import { Bill } from "../pages/Plan";
import type { Quote, Recommendation } from "../lib/types";

describe("formatting", () => {
  it("uses Indian digit grouping", () => {
    expect(inr(4544990)).toBe("₹45,44,990");
    expect(inr(709.74)).toBe("₹709.74");
    expect(inr(null)).toBe("-");
  });
});

describe("i18n", () => {
  it("interpolates variables and falls back to English", () => {
    expect(translate("en", "quote.saved", { date: "17 Nov 2026" })).toBe("Saved. This price is held till 17 Nov 2026.");
    expect(translate("hi", "brand")).toBe("Accel Business");
    expect(translate("hi", "no.such.key")).toBe("no.such.key");
  });
  it("has Hindi strings for the main customer-facing screens", () => {
    expect(typeof strings.translate).toBe("function");
    const keys = ["landing.title", "advisor.placeholder", "quote.monthly_total", "checkout.terms", "consent.agree", "kyc.verify", "track.title", "help.callback", "privacy.withdraw"];
    for (const k of keys) expect(translate("hi", k)).not.toBe(translate("en", k));
  });
});

const rec = {
  status: "ok",
  missing: [],
  profile: { business_type: "Kirana store", city: "Lucknow", employees: 2, sites: 1 },
  notes: [],
  items: [
    { product_id: "P01", qty: 1 },
    { product_id: "P07", qty: 2 },
    { product_id: "P19", qty: 1 },
  ],
  add_ons: [{ product_id: "P23", qty: 2 }],
  starter_ids: ["P01", "P07"],
} as unknown as Recommendation;

describe("selection", () => {
  it("recommended keeps all core items and leaves add-ons off", () => {
    const s = selectionFromRecommendation(rec);
    expect(selectedLines(s)).toEqual([
      { product_id: "P01", qty: 1 },
      { product_id: "P07", qty: 2 },
      { product_id: "P19", qty: 1 },
    ]);
  });
  it("lowest-cost option drops non-starter items", () => {
    const s = selectionFromRecommendation(rec, "starter");
    expect(selectedLines(s).map((l) => l.product_id)).toEqual(["P01", "P07"]);
  });
});

const quote: Quote = {
  lines: [
    { product_id: "P01", name: "Biz Fibre 100", category: "Connectivity", unit: "per site", qty: 1, unit_price: 1099, monthly: 1099, setup_unit: 1000, setup: 1000, min_contract_months: 12, install_days: 5, install_start_day: 0, install_done_day: 5 },
    { product_id: "P07", name: "Business Postpaid 299", category: "Connectivity", unit: "per line", qty: 2, unit_price: 349, monthly: 698, setup_unit: 0, setup: 0, min_contract_months: 1, install_days: 1, install_start_day: 0, install_done_day: 1 },
  ],
  monthly_subtotal: 1797,
  monthly_gst: 323.46,
  monthly_total: 2120.46,
  setup_subtotal: 1000,
  setup_gst: 180,
  setup_total: 1180,
  contract_months: 12,
  contract_driver: "P01",
  total_contract_value: 22564,
  expected_activation_days: 5,
  price_policy: "midpoint",
  gst_rate: 0.18,
  valid_until: "2026-11-17",
  warnings: [],
  fingerprint: "x",
};

describe("bill", () => {
  it("shows every line, GST separately and the contract driver", () => {
    render(
      <MemoryRouter>
        <JourneyProvider initial={{ lang: "en" }}>
          <Bill q={quote} title="Kirana store, Lucknow" />
        </JourneyProvider>
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Biz Fibre 100").length).toBe(2); // bill line + installation plan
    expect(screen.getByText("₹2,120.46")).toBeInTheDocument();
    expect(screen.getByText("₹323.46")).toBeInTheDocument();
    expect(screen.getByText(/longest minimum term among your products \(Biz Fibre 100\)/)).toBeInTheDocument();
  });
});
