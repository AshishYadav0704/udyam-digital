"""Explainable lead / order routing: who should help this business next, and why.

Commercial rationale (from smb_leads.csv): field sales costs Rs 24,335 per activation and partners
Rs 20,851, against Rs 4-6k for digital-origin channels. Multi-site and manufacturing customers carry
73% of activated MRR. So people are reserved for complexity and value; everyone else self-serves, with
a call-back the moment they ask for one or stall.
"""
from __future__ import annotations

ROUTES = {
    "self_serve": "Continue self-service",
    "assisted": "Assisted digital (inside-sales call-back, same screen)",
    "partner": "Local channel partner",
    "sales": "Field / key-account sales",
    "kyc_review": "KYC reviewer",
}
SLA_HOURS = {"self_serve": None, "assisted": 24, "partner": 48, "sales": 24, "kyc_review": 4}
COMPLEX_PRODUCTS = {"P05", "P06", "P10", "P21"}
ADDRESSABLE_DROPS = {
    "Owner had no time for a visit", "Visit not scheduled by sales", "Quote too complex to understand",
    "Quote took too long to arrive", "Price too high", "Competitor offered cheaper plan", "Decided to wait",
    "Found paperwork too long", "Missing GST or Udyam document", "Authorised signatory not available",
    "Document details did not match", "Only wanted a mobile plan", "Unreachable after 3 attempts",
}


def route(*, segment: str | None, city_tier: int | None, monthly_value: float | None = None,
          product_ids: list[str] | None = None, band: str | None = None, wants_human: bool = False,
          kyc_decision: str | None = None, kyc_codes: list[str] | None = None, stalled_hours: float = 0,
          partner_code: str | None = None, drop_reason: str | None = None, origin: str = "digital") -> dict:
    reasons: list[str] = []
    pids = set(product_ids or [])
    if kyc_decision == "manual_review":
        reasons.append("KYC needs a human check: " + ", ".join((kyc_codes or [])[:3]))
        r = "kyc_review"
    elif city_tier not in (1, 2):
        reasons.append("City not yet open for online sign-up - a local partner can check serviceability")
        r = "partner"
    elif segment in ("multi", "mfg") and ((monthly_value or 0) >= 25000 or pids & COMPLEX_PRODUCTS):
        if (monthly_value or 0) >= 25000:
            reasons.append(f"High value (Rs {monthly_value:,.0f}/month)")
        if pids & COMPLEX_PRODUCTS:
            reasons.append("Needs site survey / complex installation (" + ", ".join(sorted(pids & COMPLEX_PRODUCTS)) + ")")
        r = "sales"
    elif wants_human:
        reasons.append("Customer asked to talk to a person")
        r = "partner" if partner_code else "assisted"
    elif origin == "historic_winback":
        if drop_reason in ADDRESSABLE_DROPS:
            reasons.append(f"Lost for a reason the digital journey removes: '{drop_reason}'")
        if partner_code and segment == "micro":
            reasons.append(f"Partner {partner_code} already knows this business")
            r = "partner"
        else:
            r = "assisted"
    elif stalled_hours >= 48 and band in ("priority", "watch"):
        reasons.append(f"Stalled for {stalled_hours:.0f} h with a {band} propensity score")
        r = "assisted"
    else:
        reasons.append("Standard bundle, eligible online - no human needed")
        r = "self_serve"
    if band and r != "kyc_review":
        reasons.append(f"Propensity band: {band}")
    if segment == "micro" and r == "assisted" and band == "standard":
        reasons.append("Reserved capacity for micro / non-GST businesses so low scores are not ignored")
    return {"route": r, "label": ROUTES[r], "reasons": reasons, "sla_hours": SLA_HOURS[r]}
