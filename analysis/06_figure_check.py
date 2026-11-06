"""Independent check of the headline figures quoted on the deck and in the README.

Everything is recomputed here from data/raw with plain pandas; no project module is imported. The only project
file read as an input is business_case.json, and only for its *declared assumptions* (adoption, recovery rates,
cost inputs), so that the scenario arithmetic can be redone from scratch. Each figure is then looked up in the
text and chart data of the built deck (docs/deck/Shankhnad_MMMUT_GORAKHPUR.pptx) and in README.md.

    python -I analysis/06_figure_check.py [deck.pptx]   # exit code 1 if any figure disagrees

Writes analysis/outputs/figure_check.md and figure_check.json.
"""
from __future__ import annotations

import html
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "analysis" / "outputs"
DECK = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "docs" / "deck" / "Shankhnad_MMMUT_GORAKHPUR.pptx"
STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]


def inr(x: float) -> str:
    return f"₹{x:,.0f}"


def deck_text(path: Path) -> tuple[str, set[float]]:
    """All slide text (a:t runs) and every number cached in the deck's native charts."""
    text, numbers = [], set()
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            xml = z.read(name).decode("utf-8", "ignore")
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                text.append(" ".join(html.unescape(t) for t in re.findall(r"<a:t>([^<]*)</a:t>", xml)))
            elif re.fullmatch(r"ppt/charts/chart\d+\.xml", name):
                numbers |= {round(float(v), 2) for v in re.findall(r"<c:v>(-?[\d.]+)</c:v>", xml)}
    return "\n".join(text), numbers


def gstin_check_char(first14: str) -> str:
    """GSTIN check character (mod 36, alternating weights 1 and 2), written from the published algorithm."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for i, ch in enumerate(first14):
        p = alphabet.index(ch) * (2 if i % 2 else 1)
        total += p // 36 + p % 36
    return alphabet[(36 - total % 36) % 36]


def main() -> int:
    leads = pd.read_csv(RAW / "smb_leads.csv")
    cat = pd.read_csv(RAW / "product_catalogue.csv").set_index("product_id")
    leads["idx"] = leads["stage_reached"].map({s: i for i, s in enumerate(STAGES)})
    assert leads["idx"].notna().all(), "unknown stage_reached value"
    act = leads[leads["outcome"] == "Activated"]
    assert (act["idx"] == 5).all() and len(act) == (leads["idx"] == 5).sum()

    n, a = len(leads), len(act)
    reached = [int((leads["idx"] >= i).sum()) for i in range(6)]
    spend = float(leads["acquisition_cost_inr"].sum())
    lost_needs = leads[(leads["idx"] == 2)]["drop_reason"].value_counts()
    lost_contacted = leads[(leads["idx"] == 1)]["drop_reason"].value_counts()
    nps = act["nps_score"].dropna()
    churned = act["churned_within_6_months"].eq("Y")
    calls = act["customer_follow_up_calls"]
    churn_few, churn_many = churned[calls <= 2].mean(), churned[calls >= 4].mean()
    nps_index = 100 * ((nps >= 9).mean() - (nps <= 6).mean())

    seg = {}
    for name, g in leads.groupby("segment"):
        ga = g[g["outcome"] == "Activated"]
        seg[name] = {"leads": len(g), "rate": len(ga) / len(g), "cac": g["acquisition_cost_inr"].sum() / len(ga),
                     "mrr": ga["monthly_bundle_value_inr"].sum(),
                     "payback": (g["acquisition_cost_inr"].sum() / len(ga)) / ga["monthly_bundle_value_inr"].mean()}
    total_mrr = act["monthly_bundle_value_inr"].sum()

    # bundle that fits each segment: median value and contract of what activated customers bought
    seg_med = {name: (g["monthly_bundle_value_inr"].median(), g["contract_months"].median()) for name, g in act.groupby("segment")}
    def has_any(g, ids):
        return g["bundle_products"].map(lambda b: bool({x.split("x")[0] for x in b.split(";")} & ids)).mean()
    mfg_leased = has_any(act[act["segment"] == "Small manufacturers"], {"P05", "P06"})

    # acquisition cost by lead source (spend of all leads from the source / its activations)
    src_cac = {k: g["acquisition_cost_inr"].sum() / (g["outcome"] == "Activated").sum() for k, g in leads.groupby("lead_source")}
    remote = [src_cac[k] for k in ("Website form", "WhatsApp campaign", "Referral", "Inbound call")]

    # activated bundles that break at least one catalogue eligibility rule (written here from the catalogue columns)
    reg = pd.read_csv(RAW / "mock_gstin_registry.csv").set_index("gstin")["status"]
    def breaks_rules(r) -> bool:
        ids = [x.split("x")[0] for x in r["bundle_products"].split(";")]
        status = reg.get(r["gstin"], "NONE") if isinstance(r["gstin"], str) else "NONE"
        for pid in ids:
            c = cat.loc[pid]
            deps = str(c["requires_one_of"]) if isinstance(c["requires_one_of"], str) else ""
            if (str(r["city_tier"]) not in str(c["available_city_tiers"]).split(";")
                    or r["employee_count"] < c["min_employees"] or r["num_sites"] < c["min_sites"]
                    or (c["requires_gstin"] == "Y" and (r["has_gstin"] != "Y" or status != "Active"))
                    or (deps and not any(d in ids for d in deps.split("|")))):
                return True
        return False
    rule_breaking = int(act.apply(breaks_rules, axis=1).sum())

    # price policy: catalogue midpoint for every activated bundle line vs the revenue actually booked
    mid = (cat["price_min_inr_per_month"] + cat["price_max_inr_per_month"]) / 2
    def bundle_mid(s: str) -> float:
        return sum(mid[pid] * int(q) for pid, q in (x.split("x") for x in s.split(";")))
    midpoint_ratio = act["bundle_products"].map(bundle_mid).sum() / total_mrr

    # KYC facts quoted on the deck, from the hand-labelled ground truth
    gt = json.loads((ROOT / "analysis" / "kyc_ground_truth.json").read_text())
    k11_age = (date(2026, 7, 15) - date.fromisoformat(gt["K11"]["address_proof"]["bill_date"])).days
    k06 = gt["K06"]["gst_certificate"]["gstin"]
    k06_checksum_fails = gstin_check_char(k06[:14]) != k06[14]
    certs = {k: g["gst_certificate"]["gstin"] for k, g in gt.items()
             if k.startswith("K") and isinstance(g.get("gst_certificate"), dict) and g["gst_certificate"].get("gstin")}
    gstins = list(certs.values())
    checksum_failures = [k for k, v in certs.items() if gstin_check_char(v[:14]) != v[14]]

    # business-case scenarios: redo the arithmetic from the declared assumptions (two-state funnel per segment)
    bc = json.loads((OUT / "business_case.json").read_text())
    A = bc["assumptions"]
    scen = {}
    for k, sc in enumerate(["conservative", "expected", "ambitious"]):
        adopt, disc = A["adoption"][sc], A["downstream_discount"][sc]
        acts_total = 0.0
        st_in, st_out = [0.0] * 5, [0.0] * 5
        for _, g in leads.groupby("segment"):
            ent = [int((g["idx"] >= i).sum()) for i in range(6)]
            orig, rec = float(len(g)), 0.0
            for i in range(5):
                p = ent[i + 1] / ent[i] if ent[i] else 0.0
                lost = g[(g["idx"] == i)]["drop_reason"].fillna("Unknown").value_counts()
                share = sum(A["recovery"].get(r, {"rates": {sc: 0}})["rates"][sc] * adopt * c / ent[i]
                            for r, c in lost.items()) if ent[i] else 0.0
                st_in[i] += orig + rec
                orig, rec = orig * p, rec * disc * p + (orig + rec * disc) * share
                st_out[i] += orig + rec
            acts_total += orig + rec
        sessions = n * adopt
        kyc_cases = acts_total / 0.75 * adopt
        m = A["manual_review"]
        platform = (A["hosting_per_quarter"] + sessions * A["per_digital_session"] + kyc_cases * A["per_kyc_case"]
                    + kyc_cases * m["share"] * m["minutes"] / 60 * m["rate_per_hour"])
        days = adopt * A["digital_days_to_activate"] + (1 - adopt) * act["days_lead_to_activation"].mean()
        scen[sc] = {"activations": acts_total, "rate": acts_total / n, "cac": (spend + platform) / acts_total, "days": days,
                    "quote_acceptance": st_out[2] / st_in[2]}

    # ---------------------------------------------------------------- claims: (figure, shown, recomputed, where)
    stage_conv = [reached[i + 1] / reached[i] for i in range(5)]
    S = seg
    micro, prof = S["Micro retail & services"], S["Professional offices"]
    multi, mfg = S["Small multi-site businesses"], S["Small manufacturers"]
    claims = [
        ("Leads in the data", "5,000", f"{n:,}", "deck 2, README"),
        ("Activated customers", "368", f"{a}", "deck 2, README"),
        ("Lead-to-activation rate", "7.36%", f"{a / n:.2%}", "deck 2 & 8, README"),
        ("Every step loses more than 30% (largest step pass rate)", "< 70%", f"{max(stage_conv):.1%}", "deck 2"),
        ("Lost between needs assessment and quote acceptance", "1,113", f"{reached[2] - reached[3]:,}", "deck 2, README"),
        ("... of which price (too high + cheaper competitor)", "621",
         f"{lost_needs.get('Price too high', 0) + lost_needs.get('Competitor offered cheaper plan', 0)}", "deck 2, README"),
        ("... of which slow or complex quote", "385",
         f"{lost_needs.get('Quote too complex to understand', 0) + lost_needs.get('Quote took too long to arrive', 0)}", "deck 2, README"),
        ("Lost because the needs visit never happened", "827",
         f"{lost_contacted.get('Owner had no time for a visit', 0) + lost_contacted.get('Visit not scheduled by sales', 0)}", "deck 2"),
        ("Accepted a quote, then dropped at paperwork", "273", f"{reached[3] - reached[4]}", "deck 2"),
        ("Lost after KYC", "220", f"{reached[4] - reached[5]}", "deck 2"),
        ("Activated bundles breaking a catalogue eligibility rule", "56", f"{rule_breaking}", "deck 2"),
        ("CAC via field sales", "₹24,335", inr(src_cac["Field sales"]), "deck 2"),
        ("Lowest CAC among web, WhatsApp, referral, inbound", "₹4,026", inr(min(remote)), "deck 2"),
        ("Highest CAC among web, WhatsApp, referral, inbound", "6,352", f"{max(remote):,.0f}", "deck 2"),
        ("6-month churn, activated customers with 4-5 status calls", "23.0%", f"{churn_many:.1%}", "deck 2"),
        ("6-month churn, activated customers with 1-2 status calls", "11.9%", f"{churn_few:.1%}", "deck 2"),
        ("Blended CAC (spend / activations)", "₹15,053", inr(spend / a), "deck 8, README"),
        ("Days lead to activation (mean)", "17.6", f"{act['days_lead_to_activation'].mean():.1f}", "deck 8"),
        ("Status calls per activated customer", "3.0", f"{act['customer_follow_up_calls'].mean():.1f}", "deck 8, README"),
        ("Quote acceptance today (quote accepted / needs assessed)", "43.6%", f"{reached[3] / reached[2]:.1%}", "deck 8"),
        ("NPS index of activated customers", "-25", f"{nps_index:.0f}", "README"),
        ("Micro: leads", "2,709", f"{micro['leads']:,}", "deck 3"),
        ("Micro: activation", "4.1%", f"{micro['rate']:.1%}", "deck 3"),
        ("Micro: CAC", "₹20,007", inr(micro["cac"]), "deck 3"),
        ("Micro: share of new MRR", "6%", f"{micro['mrr'] / total_mrr:.0%}", "deck 3"),
        ("Micro: median bundle", "₹2,470", inr(seg_med["Micro retail & services"][0]), "deck 3"),
        ("Micro: median contract", "12 months", f"{seg_med['Micro retail & services'][1]:.0f} months", "deck 3"),
        ("Professional: leads", "1,247", f"{prof['leads']:,}", "deck 3"),
        ("Professional: activation", "11.1%", f"{prof['rate']:.1%}", "deck 3"),
        ("Professional: CAC", "₹10,695", inr(prof["cac"]), "deck 3"),
        ("Professional: share of new MRR", "21%", f"{prof['mrr'] / total_mrr:.0%}", "deck 3"),
        ("Professional: months of bundle revenue to recover CAC", "1.6-month", f"{prof['payback']:.1f}-month", "deck 3"),
        ("Professional: median bundle", "₹6,575", inr(seg_med["Professional offices"][0]), "deck 3"),
        ("Professional: median contract", "12 months", f"{seg_med['Professional offices'][1]:.0f} months", "deck 3"),
        ("Multi-site: leads", "755", f"{multi['leads']:,}", "deck 3"),
        ("Multi-site: activation", "11.0%", f"{multi['rate']:.1%}", "deck 3"),
        ("Multi-site: CAC", "₹15,614", inr(multi["cac"]), "deck 3"),
        ("Multi-site: share of new MRR", "57%", f"{multi['mrr'] / total_mrr:.0%}", "deck 3"),
        ("Multi-site: median bundle", "₹28,080", inr(seg_med["Small multi-site businesses"][0]), "deck 3"),
        ("Multi-site: median contract", "12 months", f"{seg_med['Small multi-site businesses'][1]:.0f} months", "deck 3"),
        ("Manufacturers: leads", "289", f"{mfg['leads']:,}", "deck 3"),
        ("Manufacturers: activation", "12.8%", f"{mfg['rate']:.1%}", "deck 3"),
        ("Manufacturers: CAC", "₹15,324", inr(mfg["cac"]), "deck 3"),
        ("Manufacturers: share of new MRR", "16%", f"{mfg['mrr'] / total_mrr:.0%}", "deck 3"),
        ("Manufacturers: median bundle", "₹15,910", inr(seg_med["Small manufacturers"][0]), "deck 3"),
        ("Manufacturers: median contract", "24 months", f"{seg_med['Small manufacturers'][1]:.0f} months", "deck 3"),
        ("Manufacturers: bundles with a leased line", "73%", f"{mfg_leased:.0%}", "deck 3"),
        ("Multi-site + manufacturing share of new MRR", "73%", f"{(multi['mrr'] + mfg['mrr']) / total_mrr:.0%}", "deck 3"),
        ("Catalogue-midpoint price vs historic revenue", "100.2%", f"{midpoint_ratio:.1%}", "deck 3, README"),
        ("K11 address proof age on 15 Jul 2026", "257 days", f"{k11_age} days", "deck 7"),
        ("K06 certificate GSTIN fails its checksum", "fails", "fails" if k06_checksum_fails else "passes", "deck 7"),
        ("Expected: activation rate", "10.0%", f"{scen['expected']['rate']:.1%}", "deck 8"),
        ("Expected: CAC", "₹11,761", inr(scen["expected"]["cac"]), "deck 8"),
        ("Expected: days to activate", "10.8", f"{scen['expected']['days']:.1f}", "deck 8"),
        ("Expected: quote acceptance", "49.1%", f"{scen['expected']['quote_acceptance']:.1%}", "deck 8"),
        ("Conservative: activations per quarter", "405", f"{scen['conservative']['activations']:.0f}", "BUSINESS_CASE"),
        ("Expected: activations per quarter", "500", f"{scen['expected']['activations']:.0f}", "BUSINESS_CASE"),
        ("Ambitious: activations per quarter", "763", f"{scen['ambitious']['activations']:.0f}", "BUSINESS_CASE"),
        ("Conservative: CAC", "₹14,484", inr(scen["conservative"]["cac"]), "BUSINESS_CASE"),
        ("Conservative: days to activate", "13.1", f"{scen['conservative']['days']:.1f}", "BUSINESS_CASE"),
        ("Ambitious: CAC", "₹7,751", inr(scen["ambitious"]["cac"]), "BUSINESS_CASE"),
        ("Ambitious: days to activate", "8.6", f"{scen['ambitious']['days']:.1f}", "BUSINESS_CASE"),
    ]
    text, chart_numbers = deck_text(DECK)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    business = (ROOT / "docs" / "business" / "BUSINESS_CASE.md").read_text(encoding="utf-8")
    rows, failures = [], 0
    for figure, shown, recomputed, where in claims:
        if shown.startswith("<"):
            value_ok = float(recomputed.rstrip("%")) < float(shown.strip("< %"))
        else:
            value_ok = shown == recomputed
        token = shown.replace("₹", "").replace("-month", "").replace(" days", "")
        try:
            number = round(float(token.replace(",", "")), 2)
        except ValueError:
            number = None
        in_deck = token in text or (number is not None and number in chart_numbers)
        in_readme = token in readme or token.replace("₹", "Rs ") in readme
        in_business = token in business or ("Rs " + token) in business or ("₹" + token) in business
        found = (("deck" not in where or in_deck or shown.startswith("<")) and ("README" not in where or in_readme)
                 and ("BUSINESS_CASE" not in where or in_business))
        ok = value_ok and found
        failures += not ok
        rows.append({"figure": figure, "shown": shown, "recomputed": recomputed, "where": where,
                     "value_matches": value_ok, "found_in_document": found, "ok": ok})

    extra = {"stage_pass_rates": [round(x, 4) for x in stage_conv], "k06_gstin_masked": k06[:2] + "*" * 10 + k06[-3:],
             "specimen_gstin_checksum_failures": checksum_failures, "specimen_gstins_checked": len(gstins),
             "scenarios": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in scen.items()}}
    (OUT / "figure_check.json").write_text(json.dumps({"rows": rows, "failures": failures, **extra}, indent=1,
                                                      ensure_ascii=False))
    md = ["# Independent figure check", "",
          "Every headline figure on the deck, in the README and in the business case, recomputed from `data/raw` with plain pandas (no project "
          "code imported). Scenario rows redo the business-case arithmetic from the assumptions declared in "
          "`business_case.json`; they check the arithmetic, not the assumptions. Produced by `analysis/06_figure_check.py`.", "",
          f"**{len(rows) - failures} of {len(rows)} figures match** what the documents show.", "",
          "| Figure | Shown | Recomputed | Where | Match |", "|---|---:|---:|---|---|"]
    md += [f"| {r['figure']} | {r['shown']} | {r['recomputed']} | {r['where']} | {'yes' if r['ok'] else '**NO**'} |"
           for r in rows]
    md += ["", f"Step pass rates (lead to activation): {', '.join(f'{x:.1%}' for x in stage_conv)}.",
           f"Specimen GSTINs failing the checksum (ground truth, {len(gstins)} checked): {', '.join(checksum_failures) or 'none'}.", ""]
    (OUT / "figure_check.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(rows) - failures}/{len(rows)} figures match")
    for r in rows:
        if not r["ok"]:
            print("  MISMATCH:", r)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
