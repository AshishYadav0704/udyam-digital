"""Shared loaders and helpers for the Udyam Digital analysis scripts.

Every script takes the extracted dataset directory as its first argument
(default: ../data/raw relative to this file) so the analysis is reproducible
against the untouched competition ZIP contents.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "raw"
OUT = ROOT / "analysis" / "outputs"
CHARTS = OUT / "charts"
TABLES = OUT / "tables"

REFERENCE_DATE = pd.Timestamp("2026-07-15")  # README: use as "today" for date checks
STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
STAGE_DATE_COLS = ["created_date", "contacted_date", "needs_assessed_date",
                   "quote_accepted_date", "kyc_complete_date", "activated_date"]
SEGMENT_SHORT = {
    "Micro retail & services": "micro",
    "Professional offices": "prof",
    "Small multi-site businesses": "multi",
    "Small manufacturers": "mfg",
}


def data_dir() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return DEFAULT_DATA


def load(d: Path | None = None) -> dict[str, pd.DataFrame]:
    d = d or data_dir()
    leads = pd.read_csv(d / "smb_leads.csv", keep_default_na=True)
    for c in STAGE_DATE_COLS:
        leads[c] = pd.to_datetime(leads[c])
    leads["activated"] = (leads["outcome"] == "Activated").astype(int)
    leads["stage_idx"] = leads["stage_reached"].map({s: i for i, s in enumerate(STAGES)})
    cat = pd.read_csv(d / "product_catalogue.csv", keep_default_na=False)
    gst = pd.read_csv(d / "mock_gstin_registry.csv", dtype=str, keep_default_na=False)
    udy = pd.read_csv(d / "mock_udyam_registry.csv", dtype=str, keep_default_na=False)
    return {"leads": leads, "catalogue": cat, "gstin": gst, "udyam": udy}


def parse_bundle(s: str) -> list[tuple[str, int]]:
    """'P01x1;P07x2' -> [('P01', 1), ('P07', 2)]"""
    if not isinstance(s, str) or not s:
        return []
    out = []
    for item in s.split(";"):
        pid, qty = item.split("x")
        out.append((pid, int(qty)))
    return out


def cumulative_funnel(df: pd.DataFrame) -> pd.Series:
    """Leads that reached at least each stage (stage_reached is the LAST stage reached)."""
    return pd.Series({s: int((df["stage_idx"] >= i).sum()) for i, s in enumerate(STAGES)})


def write_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (pd.Timestamp,)):
            return o.strftime("%Y-%m-%d")
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(type(o))

    path.write_text(json.dumps(obj, indent=2, default=default, ensure_ascii=False))


GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum(g: str) -> str:
    total = 0
    for i, ch in enumerate(g[:14]):
        v = GSTIN_CHARS.index(ch)
        p = v * (1 if i % 2 == 0 else 2)
        total += p // 36 + p % 36
    return GSTIN_CHARS[(36 - total % 36) % 36]
