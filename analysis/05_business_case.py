"""Business case: what the digital journey could change, in three scenarios, from the competition data.

Method (all inputs printed in the output so every number can be traced):
1. Per segment and funnel step, count the leads lost and why (drop_reason) in smb_leads.csv.
2. Each loss reason that a module of the product addresses gets a recovery rate per scenario (assumption,
   with the reason for the size). Losses with no lever (e.g. 'Locked in with current provider') get 0.
3. Recovery only applies to the share of leads that actually use the digital journey (adoption, assumption).
4. Leads that a lever recovers are weaker than average, so at every later step they convert at a discount
   (assumption). This stops small per-step gains compounding into an unrealistic total.
5. Revenue: activated leads x the segment's mean monthly bundle. Leads recovered from a price objection are
   assumed to take a smaller bundle (the Starter option); leads recovered from 'only wanted a mobile plan'
   are assumed to take 3 postpaid lines.
6. Cost: acquisition spend is held at the historic level (no savings assumed), plus platform run costs.
   Moving part of the field-sales effort to digital-first is shown separately as a sensitivity.

Outputs: analysis/outputs/business_case.json and business_case.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, SEGMENT_SHORT, STAGES, load, write_json  # noqa: E402

CATALOGUE_P07 = None  # filled from the catalogue (Business Postpaid 299 list price, midpoint policy)

# ------------------------------------------------------------------ assumptions (all labelled in the report)
SCENARIOS = ["conservative", "expected", "ambitious"]
ADOPTION = {"conservative": 0.40, "expected": 0.60, "ambitious": 0.80}       # share of leads using the digital journey
DOWNSTREAM_DISCOUNT = {"conservative": 0.60, "expected": 0.75, "ambitious": 0.90}
PRICE_BUNDLE_FACTOR = 0.65        # Starter vs recommended monthly value (observed 0.46-0.78 in test journeys)
MOBILE_ONLY_LINES = 3

# recovery rate of each loss reason, by scenario, and why
RECOVERY = {
    # lost between Lead and Contacted
    "Unreachable after 3 attempts": ((0.05, 0.10, 0.20), "Owner can start from the WhatsApp / SMS link instead of waiting for a call"),
    "Wrong or invalid number": ((0.10, 0.20, 0.30), "Mobile verified by OTP when the owner starts; affects future capture only"),
    "Not interested on first call": ((0.0, 0.0, 0.0), "No lever"),
    # lost between Contacted and Needs assessed
    "Owner had no time for a visit": ((0.15, 0.25, 0.40), "Needs discovery happens in a 3-minute chat; no visit"),
    "Visit not scheduled by sales": ((0.20, 0.35, 0.50), "No visit needed for standard bundles"),
    "Only wanted a mobile plan": ((0.15, 0.30, 0.45), "Mobile-only checkout is allowed (small bundle)"),
    "Locked in with current provider": ((0.0, 0.0, 0.0), "No lever (saved interest only)"),
    # lost between Needs assessed and Quote accepted
    "Quote too complex to understand": ((0.25, 0.40, 0.55), "Plain-language quote with reasons per product"),
    "Quote took too long to arrive": ((0.30, 0.50, 0.65), "Quote is instant and server-priced in the session"),
    "Decided to wait": ((0.10, 0.15, 0.25), "Saved quote held 15 days; reminder"),
    "Price too high": ((0.03, 0.07, 0.12), "Right-sizing against current spend; lowest-cost option shown"),
    "Competitor offered cheaper plan": ((0.0, 0.05, 0.10), "Transparent single price; Starter option"),
    # lost between Quote accepted and KYC complete
    "Missing GST or Udyam document": ((0.25, 0.40, 0.55), "Checklist up front; registry verifies the number; non-GST path"),
    "Found paperwork too long": ((0.25, 0.40, 0.55), "Phone upload, instant feedback; DigiLocker pull in production"),
    "Authorised signatory not available": ((0.10, 0.20, 0.35), "Remote e-sign link (production integration)"),
    "Document details did not match": ((0.20, 0.35, 0.50), "Mismatch explained at upload; human review instead of rejection"),
    # lost between KYC complete and Activated
    "Installation delayed beyond 21 days": ((0.10, 0.20, 0.30), "Dependency-aware schedule; stuck-order alerts"),
    "Customer cancelled before install": ((0.05, 0.10, 0.20), "Tracker visibility"),
    "Site not feasible for fibre": ((0.40, 0.60, 0.75), "5G AirFiber fallback offered automatically"),
    "First payment failed": ((0.40, 0.60, 0.75), "Retry with another method; order kept"),
}

# platform run costs per quarter at the dataset's scale (assumptions: need vendor quotes)
HOSTING_PER_QUARTER = 300_000          # cloud, monitoring, backups (Rs 1 lakh / month)
PER_DIGITAL_SESSION = 2.0              # 2 OTP SMS + registry lookup + LLM tokens (Rs)
PER_KYC_CASE = 60.0                    # e-sign, DigiLocker / GSP API calls, storage (Rs)
REVIEW_SHARE, REVIEW_MINUTES, REVIEWER_RATE_HOUR = 0.35, 10, 400
ONE_TIME_BUILD = 7_500_000             # integrations, security review, hardening, pilot support (Rs 75 lakh)
CONTRIBUTION_MARGIN = 0.35             # share of monthly revenue left after network and service costs
FIELD_SHIFT = {"conservative": 0.15, "expected": 0.30, "ambitious": 0.45}  # sensitivity only


def segment_tables(leads: pd.DataFrame):
    """entered[seg][step], lost[seg][step][reason] for steps 0..4 (Lead->Contacted ... KYC complete->Activated)."""
    out = {}
    for seg_full, short in SEGMENT_SHORT.items():
        df = leads[leads["segment"] == seg_full]
        entered = [int((df["stage_idx"] >= i).sum()) for i in range(5)]
        lost = []
        for i in range(5):
            at = df[(df["stage_idx"] == i) & (df["activated"] == 0)]
            lost.append(at["drop_reason"].fillna("Unknown").value_counts().to_dict())
        act = df[df["activated"] == 1]
        out[short] = {"leads": len(df), "entered": entered, "lost": lost, "activated": int(df["activated"].sum()),
                      "mean_bundle": float(act["monthly_bundle_value_inr"].mean()),
                      "spend": float(df["acquisition_cost_inr"].sum())}
    return out


def simulate(tab: dict, scenario: str, p07_price: float) -> dict:
    k = SCENARIOS.index(scenario)
    adopt, disc = ADOPTION[scenario], DOWNSTREAM_DISCOUNT[scenario]
    res = {}
    for seg, t in tab.items():
        bundle = t["mean_bundle"]
        groups = [[float(t["leads"]), 1.0, False]]            # [count, bundle factor, recovered?]
        recovered_by_step, step_in, step_out = [], [], []
        for i in range(5):
            step_in.append(sum(g[0] for g in groups))
            entered = t["entered"][i]
            passed = t["entered"][i + 1] if i < 4 else t["activated"]
            base_p = passed / entered if entered else 0.0
            add_p, rec_mix = 0.0, []
            for reason, n in t["lost"][i].items():
                rates, _ = RECOVERY.get(reason, ((0, 0, 0), ""))
                r = rates[k] * adopt
                if r and entered:
                    add_p += r * n / entered
                    if reason in ("Price too high", "Competitor offered cheaper plan"):
                        f = PRICE_BUNDLE_FACTOR
                    elif reason == "Only wanted a mobile plan":
                        f = min(1.0, MOBILE_ONLY_LINES * p07_price / bundle)
                    else:
                        f = 1.0
                    rec_mix.append((r * n / entered, f))
            new_groups, rec_here = [], 0.0
            for cnt, f, rec in groups:
                p_orig = base_p * (disc if rec else 1.0)
                new_groups.append([cnt * p_orig, f, rec])
                for share, f2 in rec_mix:           # recovery applies to this group's losers at this step
                    extra = cnt * share * (disc if rec else 1.0)
                    new_groups.append([extra, f * f2 if rec else f2, True])
                    rec_here += extra
            groups = new_groups
            recovered_by_step.append(rec_here)
            step_out.append(sum(g[0] for g in groups))
        acts = sum(g[0] for g in groups)
        mrr = sum(g[0] * g[1] * bundle for g in groups)
        res[seg] = {"activations": acts, "mrr": mrr, "recovered_by_step": recovered_by_step, "step_in": step_in, "step_out": step_out}
    return res


def main():
    data = load()
    leads, cat = data["leads"], data["catalogue"]
    p07 = cat[cat["product_id"] == "P07"].iloc[0]
    p07_price = (float(p07["price_min_inr_per_month"]) + float(p07["price_max_inr_per_month"])) / 2
    tab = segment_tables(leads)
    base_acts = sum(t["activated"] for t in tab.values())
    base_mrr = sum(t["activated"] * t["mean_bundle"] for t in tab.values())
    spend = float(leads["acquisition_cost_inr"].sum())
    base = {"leads": len(leads), "activations": base_acts, "activation_rate": base_acts / len(leads),
            "new_mrr": base_mrr, "spend": spend, "cac": spend / base_acts,
            "days_to_activate": float(leads.loc[leads["activated"] == 1, "days_lead_to_activation"].mean()),
            "churn_6m": float(leads.loc[leads["activated"] == 1, "churned_within_6_months"].astype(str).str.upper()
                              .isin(["Y", "YES", "TRUE", "1"]).mean())}

    # channel spend per lead, for the field-effort sensitivity
    ch = leads.groupby("lead_source").agg(leads=("lead_id", "count"), spend=("acquisition_cost_inr", "sum"))
    ch["spend_per_lead"] = ch["spend"] / ch["leads"]
    field_like = leads[leads["lead_source"].isin(["Field sales", "Channel partner"])
                       & leads["segment"].isin(["Micro retail & services", "Professional offices"])]
    digital_spl = float(ch.loc["Website form", "spend_per_lead"])

    # digital days: same-day advice and quote + KYC within a day + observed KYC->activation time
    kyc_to_act = float((leads["activated_date"] - leads["kyc_complete_date"]).dt.days[leads["activated"] == 1].mean())
    digital_days = 0.5 + 1.0 + kyc_to_act

    out = {"baseline": base, "assumptions": {
        "adoption": ADOPTION, "downstream_discount": DOWNSTREAM_DISCOUNT, "price_bundle_factor": PRICE_BUNDLE_FACTOR,
        "mobile_only_lines": MOBILE_ONLY_LINES, "p07_list_price": p07_price,
        "recovery": {r: {"rates": dict(zip(SCENARIOS, v[0])), "why": v[1]} for r, v in RECOVERY.items()},
        "hosting_per_quarter": HOSTING_PER_QUARTER, "per_digital_session": PER_DIGITAL_SESSION, "per_kyc_case": PER_KYC_CASE,
        "manual_review": {"share": REVIEW_SHARE, "minutes": REVIEW_MINUTES, "rate_per_hour": REVIEWER_RATE_HOUR},
        "one_time_build": ONE_TIME_BUILD, "contribution_margin": CONTRIBUTION_MARGIN, "field_shift_share": FIELD_SHIFT,
        "digital_days_to_activate": digital_days},
        "scenarios": {}}

    for sc in SCENARIOS:
        sim = simulate(tab, sc, p07_price)
        acts = sum(v["activations"] for v in sim.values())
        mrr = sum(v["mrr"] for v in sim.values())
        sessions = len(leads) * ADOPTION[sc]
        kyc_cases = acts / 0.75 * ADOPTION[sc] + 0  # cases opened ~ activations / (KYC->activation pass) for digital share
        review = kyc_cases * REVIEW_SHARE * REVIEW_MINUTES / 60 * REVIEWER_RATE_HOUR
        platform = HOSTING_PER_QUARTER + sessions * PER_DIGITAL_SESSION + kyc_cases * PER_KYC_CASE + review
        cac = (spend + platform) / acts
        shifted = len(field_like) * FIELD_SHIFT[sc]
        saving = float(sum(ch.loc[s, "spend_per_lead"] - digital_spl for s in field_like["lead_source"])) * FIELD_SHIFT[sc]
        cac_shift = (spend + platform - saving) / acts
        d_mrr = mrr - base_mrr
        # revenue: the extra monthly revenue arrives as monthly cohorts (a third of the quarterly gain each month)
        # and decays with the historic churn (15.2% in 6 months -> monthly retention r)
        r = (1 - base["churn_6m"]) ** (1 / 6)
        live = lambda m: sum(d_mrr / 3 * r ** (m - j) for j in range(1, m + 1))  # noqa: E731
        yr1_rev = sum(live(m) for m in range(1, 13))
        yr1_contrib = yr1_rev * CONTRIBUTION_MARGIN
        yr1_cost = ONE_TIME_BUILD + 4 * platform
        payback_months, cum = None, -ONE_TIME_BUILD
        for month in range(1, 61):
            cum += live(month) * CONTRIBUTION_MARGIN - platform / 3
            if cum >= 0:
                payback_months = month
                break
        out["scenarios"][sc] = {
            "activations": acts, "activation_rate": acts / len(leads), "uplift": acts / base_acts,
            "new_mrr": mrr, "delta_mrr": d_mrr, "platform_cost_quarter": platform, "cac": cac,
            "cac_with_field_shift": cac_shift, "field_leads_shifted": shifted, "field_saving_quarter": saving,
            "days_to_activate": ADOPTION[sc] * digital_days + (1 - ADOPTION[sc]) * base["days_to_activate"],
            "year1_incremental_revenue": yr1_rev, "year1_incremental_contribution": yr1_contrib, "year1_cost": yr1_cost,
            "build_payback_months": payback_months,
            "by_segment": {s: {"activations": v["activations"], "mrr": v["mrr"]} for s, v in sim.items()},
            "step_pass_rates": [sum(v["step_out"][i] for v in sim.values()) / sum(v["step_in"][i] for v in sim.values())
                                for i in range(5)],
        }
    base["step_pass_rates"] = [sum(t["entered"][i + 1] if i < 4 else t["activated"] for t in tab.values())
                               / sum(t["entered"][i] for t in tab.values()) for i in range(5)]
    write_json(out, OUT / "business_case.json")

    # ---------------------------------------------------------------- report
    L = lambda x: f"Rs {x/1e5:,.1f} lakh"  # noqa: E731
    lines = ["# Business case (scenario model)", "",
             "Scale: one quarter at the dataset's size (5,000 leads, Apr-Jun 2026, synthetic). Every figure below comes from",
             "`analysis/05_business_case.py`; inputs marked *assumption* need validation in the pilot.", "",
             "| | Baseline (observed) | Conservative | Expected | Ambitious |", "|---|---:|---:|---:|---:|"]
    sc = out["scenarios"]
    row = lambda name, b, f: lines.append(f"| {name} | {b} | " + " | ".join(f(sc[s]) for s in SCENARIOS) + " |")  # noqa: E731
    row("Leads using the digital journey (*assumption*)", "0%", lambda s: "")
    lines[-1] = "| Leads using the digital journey (*assumption*) | 0% | " + " | ".join(f"{ADOPTION[s]:.0%}" for s in SCENARIOS) + " |"
    row("Activations per quarter", f"{base_acts}", lambda s: f"{s['activations']:.0f}")
    row("Lead-to-activation", f"{base['activation_rate']:.2%}", lambda s: f"{s['activation_rate']:.2%}")
    row("Uplift in activations", "1.00x", lambda s: f"{s['uplift']:.2f}x")
    row("New monthly revenue added per quarter", L(base_mrr), lambda s: L(s["new_mrr"]))
    row("Platform run cost per quarter (*assumption*)", "-", lambda s: L(s["platform_cost_quarter"]))
    row("Blended CAC (spend held at history)", f"Rs {base['cac']:,.0f}", lambda s: f"Rs {s['cac']:,.0f}")
    row("CAC if part of field effort moves to digital", "-", lambda s: f"Rs {s['cac_with_field_shift']:,.0f}")
    row("Days lead to activation", f"{base['days_to_activate']:.1f}", lambda s: f"{s['days_to_activate']:.1f}")
    row("Year-1 incremental revenue", "-", lambda s: L(s["year1_incremental_revenue"]))
    row("Quote acceptance (needs assessed to quote accepted)", f"{base['step_pass_rates'][2]:.1%}", lambda s: f"{s['step_pass_rates'][2]:.1%}")
    row("KYC completion after quote", f"{base['step_pass_rates'][3]:.1%}", lambda s: f"{s['step_pass_rates'][3]:.1%}")
    row("Months to pay back build cost (*assumption* Rs 75 lakh)", "-",
        lambda s: f"{s['build_payback_months']}" if s["build_payback_months"] else "> 60")
    lines += ["", "## Assumptions", "",
              f"- Adoption (share of leads using the digital journey): {ADOPTION}.",
              f"- Recovered leads convert at {DOWNSTREAM_DISCOUNT} of the normal rate at every later step.",
              f"- Bundle of a lead recovered from a price objection: {PRICE_BUNDLE_FACTOR:.0%} of the segment average; "
              f"mobile-only recoveries: {MOBILE_ONLY_LINES} x Rs {p07_price:,.0f} postpaid lines.",
              f"- Acquisition spend held at the historic {L(spend)} per quarter; no savings assumed in the headline CAC.",
              f"- Platform: hosting {L(HOSTING_PER_QUARTER)}/quarter; Rs {PER_DIGITAL_SESSION:.0f} per digital session; "
              f"Rs {PER_KYC_CASE:.0f} per KYC case; {REVIEW_SHARE:.0%} of cases reviewed for {REVIEW_MINUTES} min at Rs {REVIEWER_RATE_HOUR}/h.",
              f"- Field-effort sensitivity: {FIELD_SHIFT} of micro and professional leads from field sales and partners start "
              f"digital-first, saving their channel's spend per lead minus the website form's (Rs {digital_spl:,.0f}).",
              f"- Year-1 revenue: the extra monthly revenue arrives in monthly cohorts and decays with the historic {out['baseline']['churn_6m']:.1%} 6-month churn; "
              f"payback uses a {CONTRIBUTION_MARGIN:.0%} contribution margin (*assumption*).",
              f"- Digital days to activate: 0.5 (advice + quote) + 1.0 (KYC) + {kyc_to_act:.1f} (observed KYC to activation).",
              "", "| Loss reason | Conservative | Expected | Ambitious | Why |", "|---|---:|---:|---:|---|"]
    for r, (rates, why) in RECOVERY.items():
        lines.append(f"| {r} | {rates[0]:.0%} | {rates[1]:.0%} | {rates[2]:.0%} | {why} |")
    lines += ["", "Recovery rates apply only to the adopted share. Reasons with no lever stay at 0%.",
              "Not modelled (upside, unproven): lower churn from fewer status calls (historically 1 call: 5.9% churn, "
              "5 calls: 27.9%; correlation, not causation) and cross-sell after activation.", ""]
    (OUT / "business_case.md").write_text("\n".join(lines))
    print("\n".join(lines[:20]))


if __name__ == "__main__":
    main()
