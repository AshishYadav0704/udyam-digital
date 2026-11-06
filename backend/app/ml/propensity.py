"""Lead propensity scoring + per-lead explanation (used to order human follow-up, never to refuse service)."""
from __future__ import annotations

import logging
import math
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from app.config import settings
from app.domain.catalogue import get_catalogue
from app.ml.features import FEATURES, build_row, catalogue_lookups

log = logging.getLogger("app.ml")

READABLE = {
    "lead_source": "Lead source", "segment": "Segment", "current_internet": "Current internet",
    "current_provider": "Current provider", "gstin_status": "GST registry status", "city_tier": "City tier",
    "log_employees": "Team size", "num_sites": "Number of sites", "turnover_ord": "Turnover band", "has_gstin": "Has GSTIN",
    "has_udyam": "Has Udyam", "log_spend": "Current telecom spend", "n_interest": "Products asked about",
    "log_interest_floor": "Value of products asked about", "log_price_to_spend": "Asked-for price vs current spend",
    "gst_conflict": "Asked for GST-only products without GSTIN", "tier_conflict": "Asked for a tier-1-only product",
}


class PropensityModel:
    def __init__(self, path=None):
        self.art = joblib.load(path or settings.model_path)
        self.model = self.art["model"]
        self.cal = self.art["calibrator"]
        self.lr = self.art["lr_model"]
        self.priority = self.art["priority_threshold"]
        self.watch = self.art["watch_threshold"]
        floor, t1, gr = catalogue_lookups(get_catalogue())
        self._lk = (floor, t1, gr)

    def _frame(self, lead: dict, gstin_status: str | None) -> pd.DataFrame:
        return pd.DataFrame([build_row(lead, *self._lk, gstin_status)])[FEATURES]

    def score(self, lead: dict, gstin_status: str | None = None) -> dict:
        X = self._frame(lead, gstin_status)
        raw = float(self.model.predict_proba(X)[0, 1])
        z = math.log(max(raw, 1e-6) / max(1 - raw, 1e-6))
        p = float(self.cal.predict_proba(np.array([[z]]))[0, 1])
        band = "priority" if p >= self.priority else ("watch" if p >= self.watch else "standard")
        return {"probability": round(p, 4), "band": band, "drivers": self.explain(X)}

    def explain(self, X: pd.DataFrame, top: int = 4) -> list[dict]:
        """Signed contributions from the logistic-regression model (standardised inputs x coefficients)."""
        pre = self.lr.named_steps["pre"]
        coef = self.lr.named_steps["clf"].coef_[0]
        names = pre.get_feature_names_out()
        vec = pre.transform(X)[0]
        contrib = vec * coef
        out = []
        for i in np.argsort(-np.abs(contrib))[: top * 3]:
            if abs(contrib[i]) < 1e-3:
                continue
            n = names[i]
            if n.startswith("cat__"):
                base, _, val = n[5:].partition("_")
                for f in READABLE:
                    if n[5:].startswith(f + "_"):
                        base, val = f, n[5 + len(f) + 1:]
                        break
                label = f"{READABLE.get(base, base)}: {val}"
            else:
                f = n[5:]
                label = READABLE.get(f, f)
            out.append({"factor": label, "effect": "raises" if contrib[i] > 0 else "lowers", "weight": round(float(contrib[i]), 3)})
            if len(out) >= top:
                break
        return out


@lru_cache(maxsize=1)
def get_model() -> PropensityModel | None:
    try:
        return PropensityModel()
    except Exception as e:  # model file missing -> back-office still works, without scores
        log.warning("propensity model unavailable: %s", e)
        return None
