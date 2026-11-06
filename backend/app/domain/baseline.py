"""Historic baseline KPIs from smb_leads.csv (Apr-Jun 2026) for the back-office dashboard."""
from __future__ import annotations

import csv
from collections import defaultdict
from functools import lru_cache

from app.config import settings

STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
SEG = {"Micro retail & services": "micro", "Professional offices": "prof", "Small multi-site businesses": "multi",
       "Small manufacturers": "mfg"}


@lru_cache(maxsize=1)
def baseline() -> dict:
    rows = list(csv.DictReader(open(settings.data_dir / "smb_leads.csv", newline="", encoding="utf-8")))
    idx = {s: i for i, s in enumerate(STAGES)}

    def agg(rs):
        n = len(rs)
        act = [r for r in rs if r["outcome"] == "Activated"]
        spend = sum(float(r["acquisition_cost_inr"]) for r in rs)
        mrr = sum(float(r["monthly_bundle_value_inr"]) for r in act)
        return {"leads": n, "activated": len(act), "activation_rate": len(act) / n if n else 0,
                "cac": spend / len(act) if act else None, "mrr": mrr,
                "avg_bundle": mrr / len(act) if act else None,
                "churn_6m": sum(r["churned_within_6_months"] == "Y" for r in act) / len(act) if act else None,
                "days_to_activate": sum(int(r["days_lead_to_activation"]) for r in act) / len(act) if act else None,
                "status_calls": sum(int(r["customer_follow_up_calls"]) for r in act) / len(act) if act else None}

    funnel = [sum(1 for r in rows if idx[r["stage_reached"]] >= i) for i in range(len(STAGES))]
    by_seg, by_src = defaultdict(list), defaultdict(list)
    for r in rows:
        by_seg[SEG[r["segment"]]].append(r)
        by_src[r["lead_source"]].append(r)
    drops = defaultdict(int)
    for r in rows:
        if r["outcome"] != "Activated":
            drops[(r["stage_reached"], r["drop_reason"])] += 1
    return {
        "period": "Apr-Jun 2026 (synthetic smb_leads.csv)",
        "overall": agg(rows),
        "funnel": [{"stage": s, "count": c, "conversion": (c / funnel[i - 1]) if i else None} for i, (s, c) in enumerate(zip(STAGES, funnel))],
        "segments": {k: agg(v) for k, v in by_seg.items()},
        "channels": {k: agg(v) for k, v in by_src.items()},
        "top_drop_reasons": sorted([{"after_stage": k[0], "reason": k[1], "leads": v} for k, v in drops.items()],
                                   key=lambda x: -x["leads"])[:10],
    }
