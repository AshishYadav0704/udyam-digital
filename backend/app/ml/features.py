"""Creation-time features for the lead-propensity model.

Shared by training (ml/train_propensity.py) and inference (app/ml/propensity.py) so the two can
never drift. ONLY information available when a lead is created is used. Explicitly excluded
(post-creation or outcome-derived, i.e. target leakage): outcome, drop_reason, stage_reached,
every stage date, days_lead_to_activation, customer_follow_up_calls, bundle_products,
monthly_bundle_value_inr, one_time_setup_inr, contract_months, churned_within_6_months,
nps_score and acquisition_cost_inr (spend accrues as a lead moves down the funnel).
Direct identifiers (lead_id, business_name, contact_name, gstin, udyam_number) are dropped;
only the GST registry *status* lookup is kept.
"""
from __future__ import annotations

import math

CATEGORICAL = ["lead_source", "segment", "business_type", "state", "preferred_language", "current_internet",
               "current_provider", "contact_role", "gstin_status"]
NUMERIC = ["city_tier", "log_employees", "num_sites", "turnover_ord", "has_gstin", "has_udyam", "log_spend",
           "n_interest", "log_interest_floor", "log_price_to_spend", "gst_conflict", "tier_conflict"]
PRODUCT_FLAGS = [f"poi_P{i:02d}" for i in range(1, 26)]
FEATURES = CATEGORICAL + NUMERIC + PRODUCT_FLAGS

# Candidate feature sets compared by cross-validation in ml/train_propensity.py
FEATURE_SETS = {
    "full": (CATEGORICAL, NUMERIC + PRODUCT_FLAGS),
    "no_product_flags": (CATEGORICAL, NUMERIC),
    "lean": (["lead_source", "segment", "current_internet", "current_provider", "gstin_status"], NUMERIC),
}

LEAKAGE_COLUMNS = ["outcome", "drop_reason", "stage_reached", "contacted_date", "needs_assessed_date",
                   "quote_accepted_date", "kyc_complete_date", "activated_date", "days_lead_to_activation",
                   "customer_follow_up_calls", "bundle_products", "monthly_bundle_value_inr", "one_time_setup_inr",
                   "contract_months", "churned_within_6_months", "nps_score", "acquisition_cost_inr"]
IDENTIFIER_COLUMNS = ["lead_id", "business_name", "contact_name", "gstin", "udyam_number"]

TURNOVER_ORDER = {"< 40 lakh": 0, "40 lakh - 1.5 cr": 1, "1.5 - 5 cr": 2, "5 - 25 cr": 3, "25 - 100 cr": 4}


def _f(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)) or x == "":
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def build_row(lead: dict, catalogue_floor: dict[str, int], gst_tier1_only: set[str], gst_required: set[str],
              gstin_status: str | None) -> dict:
    """lead: raw creation-time fields (CSV row or API payload)."""
    poi = [p for p in str(lead.get("products_of_interest") or "").split(";") if p]
    has_gst = 1.0 if str(lead.get("has_gstin", "N")).upper() in ("Y", "TRUE", "1") else 0.0
    has_udy = 1.0 if str(lead.get("has_udyam", "N")).upper() in ("Y", "TRUE", "1") else 0.0
    tier = _f(lead.get("city_tier"), 2.0)
    spend = max(_f(lead.get("monthly_telecom_spend_inr")), 1.0)
    floor = sum(catalogue_floor.get(p, 0) for p in poi)
    row = {
        "lead_source": lead.get("lead_source") or "Unknown",
        "segment": lead.get("segment") or "Unknown",
        "business_type": lead.get("business_type") or "Unknown",
        "state": lead.get("state") or "Unknown",
        "preferred_language": lead.get("preferred_language") or "Unknown",
        "current_internet": lead.get("current_internet") or "Unknown",
        "current_provider": lead.get("current_provider") or "Unknown",
        "contact_role": lead.get("contact_role") or "Unknown",
        "gstin_status": (gstin_status or "None") if has_gst else "None",
        "city_tier": tier,
        "log_employees": math.log1p(_f(lead.get("employee_count"), 1.0)),
        "num_sites": _f(lead.get("num_sites"), 1.0),
        "turnover_ord": float(TURNOVER_ORDER.get(str(lead.get("annual_turnover_band")), 1)),
        "has_gstin": has_gst,
        "has_udyam": has_udy,
        "log_spend": math.log(spend),
        "n_interest": float(len(poi)),
        "log_interest_floor": math.log1p(floor),
        "log_price_to_spend": math.log((floor + 1) / spend),
        "gst_conflict": 1.0 if (not has_gst and any(p in gst_required for p in poi)) else 0.0,
        "tier_conflict": 1.0 if (tier != 1 and any(p in gst_tier1_only for p in poi)) else 0.0,
    }
    for i in range(1, 26):
        row[f"poi_P{i:02d}"] = 1.0 if f"P{i:02d}" in poi else 0.0
    return row


def catalogue_lookups(cat) -> tuple[dict[str, int], set[str], set[str]]:
    floor = {p.product_id: p.price_min for p in cat}
    tier1_only = {p.product_id for p in cat if tuple(p.city_tiers) == (1,)}
    gst_req = {p.product_id for p in cat if p.requires_gstin}
    return floor, tier1_only, gst_req
