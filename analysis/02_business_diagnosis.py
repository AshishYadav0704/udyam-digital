"""Step 2 - funnel, segment, channel and unit-economics diagnosis.

Usage:  python -I analysis/02_business_diagnosis.py [data_dir]
Writes: analysis/outputs/metrics.json  (single source for every number used in the deck/app)
        analysis/outputs/business_diagnosis.md
        analysis/outputs/charts/*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import (CHARTS, OUT, SEGMENT_SHORT, STAGES, TABLES, cumulative_funnel,  # noqa: E402
                    data_dir, load, parse_bundle, write_json)

dfs = load(data_dir())
L, C, G = dfs["leads"], dfs["catalogue"], dfs["gstin"]
A = L[L.activated == 1].copy()
A["churn"] = (A.churned_within_6_months == "Y").astype(int)
Cx = C.set_index("product_id")
M: dict = {"meta": {"source": "smb_leads.csv (synthetic, Apr-Jun 2026)", "leads": len(L)}}


def nps_index(s: pd.Series) -> float:
    s = s.dropna()
    return float(100 * ((s >= 9).mean() - (s <= 6).mean())) if len(s) else float("nan")


def summarise(g: pd.DataFrame) -> dict:
    a = g[g.activated == 1]
    acq = g.acquisition_cost_inr.sum()
    n_act = int(g.activated.sum())
    return {
        "leads": int(len(g)), "activated": n_act, "activation_rate": n_act / len(g) if len(g) else None,
        "acquisition_spend": float(acq), "cac": float(acq / n_act) if n_act else None,
        "spend_per_lead": float(g.acquisition_cost_inr.mean()),
        "mean_bundle": float(a.monthly_bundle_value_inr.mean()) if n_act else None,
        "median_bundle": float(a.monthly_bundle_value_inr.median()) if n_act else None,
        "mean_setup": float(a.one_time_setup_inr.mean()) if n_act else None,
        "mrr": float(a.monthly_bundle_value_inr.sum()),
        "churn_6m": float((a.churned_within_6_months == "Y").mean()) if n_act else None,
        "nps_mean_score": float(a.nps_score.mean()) if n_act else None,
        "nps_index": nps_index(a.nps_score) if n_act else None,
        "days_to_activate": float(a.days_lead_to_activation.mean()) if n_act else None,
        "status_calls": float(a.customer_follow_up_calls.mean()) if n_act else None,
        "contract_months": float(a.contract_months.mean()) if n_act else None,
        "gstin_share": float((g.has_gstin == "Y").mean()),
        "revenue_payback_months": float(acq / n_act / a.monthly_bundle_value_inr.mean()) if n_act else None,
    }


# ------------------------------------------------------------------ overall + funnel
M["overall"] = summarise(L)
cum = cumulative_funnel(L)
M["funnel"] = {
    "cumulative": cum.to_dict(),
    "stage_conversion": {STAGES[i]: cum.iloc[i] / cum.iloc[i - 1] for i in range(1, len(STAGES))},
    "lost_after_stage": {s: int((L.stage_reached == s).sum()) for s in STAGES[:-1]},
}
# where is the biggest absolute & relative loss among *engaged* stages
conv = M["funnel"]["stage_conversion"]
M["funnel"]["steepest_drop"] = min(conv, key=conv.get)

dur = pd.DataFrame({
    "lead_to_contact": (L.contacted_date - L.created_date).dt.days,
    "contact_to_needs": (L.needs_assessed_date - L.contacted_date).dt.days,
    "needs_to_quote_accepted": (L.quote_accepted_date - L.needs_assessed_date).dt.days,
    "quote_to_kyc": (L.kyc_complete_date - L.quote_accepted_date).dt.days,
    "kyc_to_activation": (L.activated_date - L.kyc_complete_date).dt.days,
})
M["stage_days_mean"] = dur.mean().round(2).to_dict()
M["stage_days_mean_activated"] = dur[L.activated == 1].mean().round(2).to_dict()

# ------------------------------------------------------------------ drop reasons -> product lever
LEVER = {
    "Unreachable after 3 attempts": ("Lead", "Self-serve start: the owner begins the advisor from the ad/link instead of waiting for a call", "digital_entry"),
    "Wrong or invalid number": ("Lead", "OTP-verified mobile at capture", "digital_entry"),
    "Not interested on first call": ("Lead", "Not directly addressable", "none"),
    "Owner had no time for a visit": ("Contacted", "Advisor replaces the needs-discovery visit", "advisor"),
    "Visit not scheduled by sales": ("Contacted", "Advisor replaces the needs-discovery visit", "advisor"),
    "Only wanted a mobile plan": ("Contacted", "Allow single-product checkout (postpaid only)", "advisor"),
    "Locked in with current provider": ("Contacted", "Not directly addressable (save interest, remind at contract end)", "none"),
    "Price too high": ("Needs assessed", "Budget-aware right-sizing against current spend", "quote"),
    "Competitor offered cheaper plan": ("Needs assessed", "Transparent single price, Starter option", "quote"),
    "Quote too complex to understand": ("Needs assessed", "Plain-language quote, no product codes", "quote"),
    "Quote took too long to arrive": ("Needs assessed", "Instant quote in the session", "quote"),
    "Decided to wait": ("Needs assessed", "Saved quote + reminder; partially addressable", "quote"),
    "Missing GST or Udyam document": ("Quote accepted", "Registry pre-fill; non-GST KYC path", "kyc"),
    "Found paperwork too long": ("Quote accepted", "Upload-once Smart KYC, DigiLocker pull (production)", "kyc"),
    "Authorised signatory not available": ("Quote accepted", "Remote e-sign by signatory link (production)", "kyc"),
    "Document details did not match": ("Quote accepted", "Mismatch shown at upload with fix-it guidance", "kyc"),
    "Installation delayed beyond 21 days": ("KYC complete", "Tracker + install SLA alerts to ops", "tracker"),
    "Customer cancelled before install": ("KYC complete", "Tracker visibility; partially addressable", "tracker"),
    "Site not feasible for fibre": ("KYC complete", "Feasibility check before quote; 5G AirFiber fallback (P04)", "quote"),
    "First payment failed": ("KYC complete", "Payment retry / UPI autopay", "tracker"),
}
dr = L[L.activated == 0].groupby("drop_reason").size().rename("leads").reset_index()
dr["after_stage"] = dr.drop_reason.map(lambda r: LEVER[r][0])
dr["lever"] = dr.drop_reason.map(lambda r: LEVER[r][1])
dr["module"] = dr.drop_reason.map(lambda r: LEVER[r][2])
dr = dr.sort_values(["after_stage", "leads"], ascending=[True, False])
dr.to_csv(TABLES / "drop_reasons_with_levers.csv", index=False)
M["drop_reasons"] = dr.to_dict(orient="records")
M["drop_by_module"] = dr.groupby("module").leads.sum().to_dict()
na = dr[dr.after_stage == "Needs assessed"]
M["needs_to_quote_breakdown"] = {
    "lost": int(na.leads.sum()),
    "price": int(na[na.drop_reason.isin(["Price too high", "Competitor offered cheaper plan"])].leads.sum()),
    "quote_experience": int(na[na.drop_reason.isin(["Quote too complex to understand", "Quote took too long to arrive"])].leads.sum()),
    "indecision": int(na[na.drop_reason == "Decided to wait"].leads.sum()),
}
ct = dr[dr.after_stage == "Contacted"]
M["visit_friction"] = int(ct[ct.drop_reason.isin(["Owner had no time for a visit", "Visit not scheduled by sales"])].leads.sum())

# ------------------------------------------------------------------ segments
seg = {}
for s, g in L.groupby("segment"):
    d = summarise(g)
    d["funnel"] = cumulative_funnel(g).to_dict()
    d["lead_share"] = len(g) / len(L)
    d["mrr_share"] = d["mrr"] / M["overall"]["mrr"]
    d["employees_median"] = float(g.employee_count.median())
    d["sites_median"] = float(g.num_sites.median())
    d["telecom_spend_median"] = float(g.monthly_telecom_spend_inr.median())
    seg[SEGMENT_SHORT[s]] = {"name": s, **d}
M["segments"] = seg

# product penetration per segment (share of activated bundles containing product)
rows = []
for _, r in A.iterrows():
    for p, q in parse_bundle(r.bundle_products):
        rows.append({"segment": SEGMENT_SHORT[r.segment], "lead_id": r.lead_id, "product": p, "qty": q,
                     "sites": r.num_sites, "employees": r.employee_count})
I = pd.DataFrame(rows)
pen = (I.groupby(["segment", "product"]).lead_id.nunique().unstack(fill_value=0)
       .div(A.groupby(A.segment.map(SEGMENT_SHORT)).size(), axis=0))
M["product_penetration"] = {s: pen.loc[s][pen.loc[s] > 0].round(3).sort_values(ascending=False).to_dict() for s in pen.index}
pen.round(3).to_csv(TABLES / "product_penetration_by_segment.csv")
qty = I.groupby("product").agg(median_qty=("qty", "median"), qty_per_site=("qty", lambda s: float((s / I.loc[s.index, "sites"]).mean())),
                               qty_per_employee=("qty", lambda s: float((s / I.loc[s.index, "employees"]).mean())))
M["quantity_patterns"] = qty.round(2).to_dict(orient="index")

# ------------------------------------------------------------------ channels
ch = {}
for s, g in L.groupby("lead_source"):
    d = summarise(g)
    d["funnel"] = cumulative_funnel(g).to_dict()
    d["never_contacted_share"] = float((g.stage_reached == "Lead").mean())
    d["segment_mix"] = g.segment.map(SEGMENT_SHORT).value_counts(normalize=True).round(3).to_dict()
    ch[s] = d
M["channels"] = ch

# ------------------------------------------------------------------ registration effect
reg = {}
for flag, g in L.groupby("has_gstin"):
    d = summarise(g)
    f = cumulative_funnel(g)
    d["funnel"] = f.to_dict()
    d["kyc_completion_after_quote"] = f["KYC complete"] / f["Quote accepted"]
    reg["gstin_" + flag] = d
M["gstin_effect"] = reg
m = L.merge(G[["gstin", "status"]], on="gstin", how="left")
M["gstin_status_of_activated"] = m[m.activated == 1].status.fillna("No GSTIN").value_counts().to_dict()

# ------------------------------------------------------------------ retention signals (activated only)
calls = A.groupby("customer_follow_up_calls").agg(n=("churn", "size"), churn=("churn", "mean"), nps=("nps_score", "mean"))
M["status_calls_vs_outcomes"] = {int(k): {"n": int(v.n), "churn": float(v.churn), "nps_mean": float(v.nps)} for k, v in calls.iterrows()}
A["days_band"] = pd.cut(A.days_lead_to_activation, [0, 15, 21, 40], labels=["<=15 days", "16-21 days", ">21 days"])
db = A.groupby("days_band", observed=True).agg(n=("churn", "size"), nps=("nps_score", "mean"), churn=("churn", "mean"))
M["activation_days_vs_outcomes"] = {str(k): {"n": int(v.n), "nps_mean": float(v.nps), "churn": float(v.churn)} for k, v in db.iterrows()}
M["correlations_activated"] = A[["days_lead_to_activation", "customer_follow_up_calls", "nps_score", "churn"]].corr().round(3).to_dict()

# price-to-spend: catalogue floor price of the products the lead asked about vs current telecom spend
L["interest_floor"] = L.products_of_interest.str.split(";").apply(lambda ps: sum(Cx.loc[p, "price_min_inr_per_month"] for p in ps))
L["price_to_spend"] = L.interest_floor / L.monthly_telecom_spend_inr
na_leads = L[L.needs_assessed_date.notna()].copy()
na_leads["price_drop"] = na_leads.drop_reason.isin(["Price too high", "Competitor offered cheaper plan"]).astype(int)
na_leads["q"] = pd.qcut(na_leads.price_to_spend, 5, labels=["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"])
ps = na_leads.groupby("q", observed=True).agg(n=("price_drop", "size"), ratio_median=("price_to_spend", "median"),
                                              price_drop=("price_drop", "mean"), activated=("activated", "mean"))
M["price_to_spend_quintiles"] = {str(k): {kk: float(vv) for kk, vv in v.items()} for k, v in ps.iterrows()}
M["price_to_spend_median_by_segment"] = L.groupby(L.segment.map(SEGMENT_SHORT)).price_to_spend.median().round(2).to_dict()

# speed-to-lead (contacted leads) - reported because it is NOT a signal here
sp = L[L.contacted_date.notna()].assign(t=lambda x: (x.contacted_date - x.created_date).dt.days).groupby("t").activated.mean()
M["speed_to_contact_vs_activation"] = {int(k): float(v) for k, v in sp.items()}
M["existing_accel_customers"] = summarise(L[L.current_provider.isin(["Accel", "Accel (mobile only)"])])
M["non_accel"] = summarise(L[~L.current_provider.isin(["Accel", "Accel (mobile only)"])])

# historic catalogue violations (computed in 01)
dq = OUT / "data_quality.json"
if dq.exists():
    import json
    M["historic_rule_violations"] = json.loads(dq.read_text())["historic_rule_violations"]

# realised price position inside catalogue range -> justifies a midpoint list price
pos, mid_total, actual_total, floor_total = [], 0.0, 0.0, 0.0
for _, r in A.iterrows():
    items = parse_bundle(r.bundle_products)
    lo = sum(q * Cx.loc[p, "price_min_inr_per_month"] for p, q in items)
    hi = sum(q * Cx.loc[p, "price_max_inr_per_month"] for p, q in items)
    pos.append((r.monthly_bundle_value_inr - lo) / (hi - lo))
    mid_total += (lo + hi) / 2
    floor_total += lo
    actual_total += r.monthly_bundle_value_inr
M["price_realisation"] = {"mean_position_in_range": float(np.mean(pos)), "median_position_in_range": float(np.median(pos)),
                          "midpoint_vs_actual_mrr": mid_total / actual_total, "floor_vs_actual_mrr": floor_total / actual_total}

write_json(M, OUT / "metrics.json")

# ------------------------------------------------------------------ charts (report copies; the deck uses native charts)
INK, MUTED, GRID, HI, BASE = "#1f1f1f", "#6b6b6b", "#e6e6e6", "#d0021b", "#9a9a9a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})

fig, ax = plt.subplots(figsize=(8, 3.6))
vals = list(cum.values)[::-1]
labels = list(cum.index)[::-1]
colors = [HI if l == "Quote accepted" else BASE for l in labels]
ax.barh(labels, vals, color=colors, height=0.6)
for i, (l, v) in enumerate(zip(labels, vals)):
    rate = "" if l == "Lead" else f"  {conv[l]:.0%} of previous"
    ax.text(v + 40, i, f"{v:,}{rate}", va="center", color=INK if l != "Quote accepted" else HI, fontsize=9)
ax.set_xlim(0, 6200); ax.set_xticks([]); ax.spines["bottom"].set_visible(False)
ax.set_title("Cumulative SMB funnel, Apr-Jun 2026 (5,000 leads -> 368 activations)", loc="left", fontsize=11, color=INK)
fig.tight_layout(); fig.savefig(CHARTS / "funnel.png", dpi=200); plt.close(fig)

fig, axes = plt.subplots(1, 4, figsize=(11, 2.8))
order = ["micro", "prof", "multi", "mfg"]
names = ["Micro", "Prof. offices", "Multi-site", "Manufacturers"]
for ax, (key, title, fmt) in zip(axes, [("activation_rate", "Activation rate", "{:.1%}"), ("cac", "CAC (Rs)", "{:,.0f}"),
                                        ("mean_bundle", "Avg monthly bundle (Rs)", "{:,.0f}"), ("churn_6m", "6-month churn", "{:.1%}")]):
    v = [seg[s][key] for s in order]
    ax.bar(names, v, color=[HI if s == "prof" else BASE for s in order], width=0.6)
    for i, x in enumerate(v):
        ax.text(i, x, fmt.format(x), ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_title(title, fontsize=10, color=INK, loc="left"); ax.set_yticks([]); ax.tick_params(axis="x", labelsize=8, rotation=20)
fig.tight_layout(); fig.savefig(CHARTS / "segments.png", dpi=200); plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(9, 3))
k = sorted(M["status_calls_vs_outcomes"])
axes[0].plot(k, [M["status_calls_vs_outcomes"][i]["nps_mean"] for i in k], color=INK, marker="o", lw=2)
axes[0].set_title("Mean NPS score by status-chasing calls", loc="left", fontsize=10, color=INK); axes[0].set_xlabel("calls")
axes[1].plot(k, [100 * M["status_calls_vs_outcomes"][i]["churn"] for i in k], color=HI, marker="o", lw=2)
axes[1].set_title("6-month churn % by status-chasing calls", loc="left", fontsize=10, color=INK); axes[1].set_xlabel("calls")
fig.tight_layout(); fig.savefig(CHARTS / "status_calls.png", dpi=200); plt.close(fig)

fig, ax = plt.subplots(figsize=(6, 3))
qs = list(M["price_to_spend_quintiles"])
ax.bar(qs, [100 * M["price_to_spend_quintiles"][q]["price_drop"] for q in qs], color=BASE, width=0.6)
ax.set_title("Price-related drop % by price-to-current-spend quintile", loc="left", fontsize=10, color=INK)
ax.tick_params(axis="x", labelsize=8)
fig.tight_layout(); fig.savefig(CHARTS / "price_to_spend.png", dpi=200); plt.close(fig)

# ------------------------------------------------------------------ markdown
o = M["overall"]
seg_rows = "\n".join(
    f"| {seg[s]['name']} | {seg[s]['leads']:,} ({seg[s]['lead_share']:.0%}) | {seg[s]['activation_rate']:.1%} | "
    f"Rs {seg[s]['cac']:,.0f} | Rs {seg[s]['mean_bundle']:,.0f} | {seg[s]['mrr_share']:.0%} | {seg[s]['churn_6m']:.1%} | "
    f"{seg[s]['revenue_payback_months']:.1f} |" for s in order)
ch_rows = "\n".join(
    f"| {k} | {v['leads']:,} | {v['activation_rate']:.1%} | Rs {v['cac']:,.0f} | Rs {v['spend_per_lead']:,.0f} | "
    f"{v['never_contacted_share']:.0%} | {v['churn_6m']:.1%} |" for k, v in sorted(ch.items(), key=lambda kv: kv[1]['cac']))
g_y, g_n = reg["gstin_Y"], reg["gstin_N"]
md = f"""# Business diagnosis (calculated from smb_leads.csv)

All figures are calculated from the synthetic dataset; none describe real Airtel performance.

## Headline
- {o['leads']:,} leads -> {o['activated']} activations = **{o['activation_rate']:.2%}** lead-to-activation.
- Blended CAC = total acquisition spend Rs {o['acquisition_spend']:,.0f} / {o['activated']} activations = **Rs {o['cac']:,.0f}**.
- Activated customers: mean bundle Rs {o['mean_bundle']:,.0f}/month (median Rs {o['median_bundle']:,.0f}), {o['days_to_activate']:.1f} days to activate,
  {o['status_calls']:.1f} status-chasing calls, 6-month churn {o['churn_6m']:.1%}, NPS index {o['nps_index']:.0f}.
- Steepest stage drop: **Needs assessed -> Quote accepted ({conv['Quote accepted']:.0%})**. Of the {M['needs_to_quote_breakdown']['lost']:,} leads lost there,
  {M['needs_to_quote_breakdown']['price']} cite price and {M['needs_to_quote_breakdown']['quote_experience']} cite a slow or confusing quote.
- {M['visit_friction']} leads were lost because no needs-discovery visit happened (owner had no time / visit not scheduled).

## Segments
| Segment | Leads | Activation | CAC | Avg bundle | MRR share | Churn 6m | Revenue payback (months) |
|---|---|---|---|---|---|---|---|
{seg_rows}

## Channels (sorted by CAC)
| Source | Leads | Activation | CAC | Spend/lead | Never contacted | Churn 6m |
|---|---|---|---|---|---|---|
{ch_rows}

## Registration effect
- With GSTIN: {g_y['activation_rate']:.1%} activation; KYC completion after quote {g_y['kyc_completion_after_quote']:.0%}.
- Without GSTIN: {g_n['activation_rate']:.1%} activation; KYC completion after quote **{g_n['kyc_completion_after_quote']:.0%}** - KYC is where non-GST businesses fail.

## Retention signals (correlational, activated customers only)
- Status calls vs NPS / churn: 1 call -> NPS {M['status_calls_vs_outcomes'][1]['nps_mean']:.1f}, churn {M['status_calls_vs_outcomes'][1]['churn']:.0%}; 5 calls -> NPS {M['status_calls_vs_outcomes'][5]['nps_mean']:.1f}, churn {M['status_calls_vs_outcomes'][5]['churn']:.0%}.
- Activation within 15 days -> mean NPS {M['activation_days_vs_outcomes']['<=15 days']['nps_mean']:.1f}; over 21 days -> {M['activation_days_vs_outcomes']['>21 days']['nps_mean']:.1f}.
- Speed of first contact shows no relationship with activation (0-4 days: {min(M['speed_to_contact_vs_activation'].values()):.1%}-{max(M['speed_to_contact_vs_activation'].values()):.1%}).

## Pricing evidence
- Realised bundle prices sit at {M['price_realisation']['mean_position_in_range']:.0%} of the catalogue min-max range on average; a published midpoint
  price would have produced {M['price_realisation']['midpoint_vs_actual_mrr']:.1%} of the realised MRR (revenue-neutral transparency).
- Price-related drops rise from {M['price_to_spend_quintiles']['Q1 (lowest)']['price_drop']:.0%} to {M['price_to_spend_quintiles']['Q5 (highest)']['price_drop']:.0%} as the asked-for bundle grows relative to current telecom spend.
"""
(OUT / "business_diagnosis.md").write_text(md)
print(md)
