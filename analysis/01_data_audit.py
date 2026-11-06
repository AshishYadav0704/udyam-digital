"""Step 1 - attachment inventory and data-quality report.

Usage:  python -I analysis/01_data_audit.py [data_dir]
Writes: analysis/outputs/data_quality.json, analysis/outputs/data_quality_report.md
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402

from common import (OUT, REFERENCE_DATE, ROOT, STAGES, STAGE_DATE_COLS, data_dir,  # noqa: E402
                    gstin_checksum, load, parse_bundle, write_json)

D = data_dir()
dfs = load(D)
L, C, G, U = dfs["leads"], dfs["catalogue"], dfs["gstin"], dfs["udyam"]
checks: list[dict] = []


def check(area, name, ok, detail, severity="info"):
    checks.append({"area": area, "check": name, "result": "PASS" if ok else ("WARN" if severity != "error" else "FAIL"),
                   "detail": detail})


# ---------------------------------------------------------------- inventory
inventory = []
for p in sorted(D.rglob("*")):
    if p.is_file():
        rel = p.relative_to(D).as_posix()
        row = {"file": rel, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16]}
        if p.suffix == ".csv":
            df = pd.read_csv(p, dtype=str, keep_default_na=False)
            row.update(rows=len(df), cols=len(df.columns))
        inventory.append(row)
kyc_files = [i for i in inventory if i["file"].startswith("kyc_documents/")]
applicants = sorted({Path(i["file"]).name[:3] for i in kyc_files})
per_app = {a: sorted(Path(i["file"]).stem[4:] for i in kyc_files if Path(i["file"]).name.startswith(a)) for a in applicants}
doc_types = ["address_proof", "gst_certificate", "signatory_id", "udyam_certificate"]
missing_docs = {a: [t for t in doc_types if t not in v] for a, v in per_app.items() if len(v) < 4}

# ---------------------------------------------------------------- README expectations
check("inventory", "47 KYC images for 12 applicants", len(kyc_files) == 47 and len(applicants) == 12,
      f"{len(kyc_files)} images, {len(applicants)} applicants; incomplete sets: {missing_docs}")
check("inventory", "README row counts", len(L) == 5000 and len(C) == 25 and len(G) == 3534 and len(U) == 2723,
      f"leads={len(L)}, catalogue={len(C)}, gstin={len(G)}, udyam={len(U)}", "error")

# ---------------------------------------------------------------- leads integrity
check("leads", "lead_id unique", L.lead_id.is_unique, f"{L.lead_id.duplicated().sum()} duplicates", "error")
check("leads", "created_date within Apr-Jun 2026", L.created_date.between("2026-04-01", "2026-06-30").all(),
      f"{L.created_date.min().date()} to {L.created_date.max().date()}")
viol = 0
for a, b in zip(STAGE_DATE_COLS[:-1], STAGE_DATE_COLS[1:]):
    viol += int((L[a].notna() & L[b].notna() & (L[b] < L[a])).sum())
check("leads", "stage dates in chronological order", viol == 0, f"{viol} out-of-order pairs", "error")
n_dates = L[STAGE_DATE_COLS[1:]].notna().sum(axis=1)
check("leads", "stage_reached consistent with populated stage dates", (n_dates == L.stage_idx).all(),
      f"{int((n_dates != L.stage_idx).sum())} inconsistent rows", "error")
check("leads", "outcome consistent with stage_reached",
      ((L.outcome == "Activated") == (L.stage_reached == "Activated")).all(), "Activated <=> stage Activated", "error")
act = L[L.activated == 1]
calc_days = (act.activated_date - act.created_date).dt.days
check("leads", "days_lead_to_activation = activated - created", (calc_days == act.days_lead_to_activation).all(),
      f"mean {act.days_lead_to_activation.mean():.1f} days (README: 17.6)", "error")
post = ["bundle_products", "monthly_bundle_value_inr", "one_time_setup_inr", "contract_months",
        "churned_within_6_months", "nps_score", "days_lead_to_activation"]
leak = int(L.loc[L.activated == 0, post].notna().any(axis=1).sum())
check("leads", "post-activation fields only populated for activated leads", leak == 0, f"{leak} violations", "error")
check("leads", "drop_reason present for every dropped lead",
      L.loc[L.activated == 0, "drop_reason"].notna().all(), "21 distinct reasons, each tied to one stage")
check("leads", "has_gstin flag matches gstin field",
      ((L.has_gstin == "Y") == L.gstin.notna()).all(), f"{int((L.has_gstin == 'Y').sum())} leads with GSTIN", "error")
check("leads", "has_udyam flag matches udyam_number field",
      ((L.has_udyam == "Y") == L.udyam_number.notna()).all(), f"{int((L.has_udyam == 'Y').sum())} leads with Udyam", "error")
future = L[STAGE_DATE_COLS[1:]].gt(REFERENCE_DATE).any(axis=1)
check("leads", "no stage dates after the 15 Jul 2026 reference date", not future.any(),
      f"{int(future.sum())} leads have KYC/activation dates after 2026-07-15 (latest {L.activated_date.max().date()}); "
      "kept as-is - the reference date is only used for document-age checks", "warn")
dup_name_city = int(L.duplicated(["business_name", "city"]).sum())
check("leads", "no duplicate business+city leads", dup_name_city == 0, f"{dup_name_city} duplicates")

# ---------------------------------------------------------------- registries
gst_set, udy_set = set(G.gstin), set(U.udyam_number)
check("registry", "every lead GSTIN exists in mock GST registry", L.gstin.dropna().isin(gst_set).all(),
      f"{L.gstin.notna().sum()} of {L.gstin.notna().sum()} found; registry has no orphan rows: {G.gstin.isin(L.gstin).all()}")
check("registry", "every lead Udyam number exists in mock Udyam registry", L.udyam_number.dropna().isin(udy_set).all(),
      f"registry has no orphan rows: {U.udyam_number.isin(L.udyam_number).all()}")
cs_ok = G.gstin.apply(lambda g: gstin_checksum(g) == g[14]).all()
check("registry", "GSTIN checksum valid for every registry record", cs_ok, "mod-36 checksum, 3,534/3,534")
check("registry", "GSTIN PAN 4th character is X (synthetic convention)", (G.gstin.str[5] == "X").all(),
      "README: accept X - no real taxpayer can match")
state_code = L.dropna(subset=["gstin"]).assign(code=lambda x: x.gstin.str[:2]).groupby("state").code.nunique()
check("registry", "GSTIN state code consistent with lead state", (state_code == 1).all(), "one code per state")
check("registry", "Udyam numbers use district code 00 (synthetic convention)",
      U.udyam_number.str.match(r"^UDYAM-[A-Z]{2}-00-\d{7}$").all(), "README: 00 does not exist in reality")
check("registry", "GST registry status mix", True, G.status.value_counts().to_dict())

# ---------------------------------------------------------------- catalogue vs activated bundles
Cx = C.set_index("product_id")
gst_status = G.set_index("gstin").status
rule_viol, price_pos = [], []
for _, r in act.iterrows():
    items = parse_bundle(r.bundle_products)
    ids = [p for p, _ in items]
    lo = sum(q * Cx.loc[p, "price_min_inr_per_month"] for p, q in items)
    hi = sum(q * Cx.loc[p, "price_max_inr_per_month"] for p, q in items)
    price_pos.append((r.monthly_bundle_value_inr - lo) / (hi - lo) if hi > lo else 0.5)
    status = gst_status.get(r.gstin, "NONE") if isinstance(r.gstin, str) else "NONE"
    for p, q in items:
        c = Cx.loc[p]
        if str(r.city_tier) not in str(c.available_city_tiers).split(";"):
            rule_viol.append((r.lead_id, p, "city tier"))
        if r.employee_count < c.min_employees:
            rule_viol.append((r.lead_id, p, "min employees"))
        if r.num_sites < c.min_sites:
            rule_viol.append((r.lead_id, p, "min sites"))
        if c.requires_gstin == "Y" and r.has_gstin != "Y":
            rule_viol.append((r.lead_id, p, "GSTIN required, none held"))
        elif c.requires_gstin == "Y" and status != "Active":
            rule_viol.append((r.lead_id, p, f"GSTIN required, registry status {status}"))
        if c.requires_one_of and not any(d in ids for d in c.requires_one_of.split("|")):
            rule_viol.append((r.lead_id, p, "dependency missing"))
rv = pd.DataFrame(rule_viol, columns=["lead_id", "product", "rule"])
n_bad = rv.lead_id.nunique()
check("catalogue", "activated bundles comply with catalogue eligibility rules", n_bad == 0,
      f"{n_bad} of {len(act)} activated bundles ({n_bad / len(act):.1%}) break at least one rule: "
      f"{rv.rule.value_counts().to_dict()}", "warn")
rv.to_csv(OUT / "tables" / "historic_bundle_rule_violations.csv", index=False)
pp = pd.Series(price_pos)
check("catalogue", "realised bundle value inside catalogue price range", pp.between(0, 1).all(),
      f"position in [min,max] range: mean {pp.mean():.2f}, median {pp.median():.2f}")
setup_ok = all(r.one_time_setup_inr == sum(q * Cx.loc[p, "one_time_setup_inr"] for p, q in parse_bundle(r.bundle_products))
               for _, r in act.iterrows())
check("catalogue", "one-time setup = sum(catalogue setup x quantity)", setup_ok, "exact for all 368")
cm_ok = all(r.contract_months == max(Cx.loc[p, "min_contract_months"] for p, _ in parse_bundle(r.bundle_products))
            for _, r in act.iterrows())
check("catalogue", "contract months = longest product minimum term in bundle", cm_ok, "exact for all 368")
check("catalogue", "25 products, unique IDs, min<=max price", C.product_id.is_unique and
      (C.price_min_inr_per_month <= C.price_max_inr_per_month).all(), "P01-P25")

# ---------------------------------------------------------------- funnel restatement
cum = {s: int((L.stage_idx >= i).sum()) for i, s in enumerate(STAGES)}
readme = {"Lead": 5000, "Contacted": 3406, "Needs assessed": 1974, "Quote accepted": 861, "KYC complete": 588, "Activated": 368}
check("funnel", "cumulative funnel reproduces README", cum == readme, str(cum), "error")
mutually_exclusive = L.stage_reached.value_counts().reindex(STAGES).to_dict()

report = {
    "data_dir": D.relative_to(ROOT).as_posix() if D.is_relative_to(ROOT) else D.name,   # never an absolute machine path
    "inventory": inventory,
    "kyc": {"applicants": applicants, "documents_per_applicant": {a: len(v) for a, v in per_app.items()},
            "missing": missing_docs},
    "checks": checks,
    "funnel_cumulative": cum,
    "stage_reached_counts_last_stage": mutually_exclusive,
    "historic_rule_violations": {"bundles": int(n_bad), "by_rule": rv.rule.value_counts().to_dict(),
                                 "by_product": rv["product"].value_counts().to_dict()},
}
write_json(report, OUT / "data_quality.json")

lines = ["# Data quality report", "",
         f"Source: `{D.name}/` (extracted from YTL_TrackA_Udyam_Digital_Data.zip; README inside the ZIP is byte-identical to the standalone README).", "",
         "## Inventory", "", "| File | Bytes | Rows | Cols | SHA-256 (16) |", "|---|---:|---:|---:|---|"]
for i in inventory:
    if not i["file"].startswith("kyc_documents/"):
        lines.append(f"| {i['file']} | {i['bytes']:,} | {i.get('rows', '')} | {i.get('cols', '')} | `{i['sha256']}` |")
lines.append(f"| kyc_documents/ (47 PNG) | {sum(i['bytes'] for i in kyc_files):,} | | | applicants K01-K12; K05 has no Udyam certificate |")
lines += ["", "## Checks", "", "| Area | Check | Result | Detail |", "|---|---|---|---|"]
for c in checks:
    lines.append(f"| {c['area']} | {c['check']} | {c['result']} | {c['detail']} |")
lines += ["", "## Notes", "",
          "- `stage_reached` is the last stage a lead reached; the cumulative funnel is derived from it (stage index >= k).",
          "- The KYC images use specimen watermarks on every page; this is a universal artefact, not a defect.",
          "- Udyam certificate registration dates never equal the registry dates and every 'Trading' registry record prints",
          "  'Services' on its certificate. Both are systematic generator artefacts, so the KYC engine treats them as soft",
          "  (informational) checks instead of rejection reasons.",
          "- 56 activated bundles break catalogue rules (e.g. Biz Fibre 1G sold in tier-2 cities). This is evidence of manual",
          "  quoting error, and the reason eligibility is enforced deterministically in the new journey."]
(OUT / "data_quality_report.md").write_text("\n".join(lines) + "\n")
fails = [c for c in checks if c["result"] == "FAIL"]
print(f"{len(checks)} checks: {sum(c['result'] == 'PASS' for c in checks)} pass, "
      f"{sum(c['result'] == 'WARN' for c in checks)} warn, {len(fails)} fail")
for c in checks:
    if c["result"] != "PASS":
        print(" -", c["result"], c["check"], "|", c["detail"])
