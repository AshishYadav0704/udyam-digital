"""Data-backed facts the advisor may quote (computed from smb_leads.csv at start-up).

Only aggregate, de-identified statistics leave this module.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from functools import lru_cache

from app.config import settings

SEG_SHORT = {"Micro retail & services": "micro", "Professional offices": "prof",
             "Small multi-site businesses": "multi", "Small manufacturers": "mfg"}


@lru_cache(maxsize=1)
def segment_penetration() -> dict[str, dict[str, float]]:
    """Share of activated bundles in each segment that contain each product."""
    per_seg_total: Counter = Counter()
    per_seg_prod: dict[str, Counter] = defaultdict(Counter)
    with open(settings.data_dir / "smb_leads.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["outcome"] != "Activated":
                continue
            seg = SEG_SHORT[r["segment"]]
            per_seg_total[seg] += 1
            for item in r["bundle_products"].split(";"):
                per_seg_prod[seg][item.split("x")[0]] += 1
    return {s: {p: c / per_seg_total[s] for p, c in per_seg_prod[s].items()} for s in per_seg_total}


def penetration(segment: str | None, product_id: str) -> float | None:
    if not segment:
        return None
    return segment_penetration().get(segment, {}).get(product_id)
