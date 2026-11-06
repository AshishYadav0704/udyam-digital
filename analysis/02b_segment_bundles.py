"""Step 2b - the bundle that fits each segment, read from what activated customers actually bought.

For each segment: median monthly bundle value, median contract length, and the share of activated bundles that
contain each product family. Answers the case's key question 1 (products, price point, contract length per segment)
from observed purchases rather than from assumptions.

    python -I analysis/02b_segment_bundles.py

Writes analysis/outputs/segment_bundles.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "analysis" / "outputs"
SHORT = {"Micro retail & services": "micro", "Professional offices": "prof",
         "Small multi-site businesses": "multi", "Small manufacturers": "mfg"}
FAMILIES = {
    "fibre": {"P01", "P02", "P03", "P04"},
    "postpaid_sim": {"P07", "P08"},
    "cloud_email": {"P16"},
    "leased_line": {"P05", "P06"},
    "endpoint_security": {"P20"},
    "cloud_backup": {"P17"},
    "failover_4g5g": {"P09"},
    "cloud_pos": {"P19"},
    "cloud_cctv": {"P23"},
    "secure_wifi": {"P22"},
    "managed_firewall": {"P21"},
    "whatsapp_api": {"P15"},
}


def main() -> None:
    leads = pd.read_csv(RAW / "smb_leads.csv")
    act = leads[leads["outcome"] == "Activated"]
    out = {}
    for name, g in act.groupby("segment"):
        products = g["bundle_products"].map(lambda b: {x.split("x")[0] for x in b.split(";")})
        out[SHORT[name]] = {
            "name": name,
            "activated": int(len(g)),
            "median_bundle_inr": float(g["monthly_bundle_value_inr"].median()),
            "median_contract_months": float(g["contract_months"].median()),
            "family_share": {f: round(float(products.map(lambda s, ids=ids: bool(s & ids)).mean()), 3)
                             for f, ids in FAMILIES.items()},
        }
    (OUT / "segment_bundles.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in out.items():
        top = {f: s for f, s in v["family_share"].items() if s >= 0.35}
        print(f"{k:6} median ₹{v['median_bundle_inr']:,.0f}, {v['median_contract_months']:.0f} months; {top}")


if __name__ == "__main__":
    main()
