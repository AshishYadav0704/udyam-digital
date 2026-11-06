"""Turn digital-journey activity into scored, routed leads for the back-office."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.routing import route
from app.ml.propensity import get_model
from app.models import AdvisorSession, Lead

SEG_FULL = {"micro": "Micro retail & services", "prof": "Professional offices", "multi": "Small multi-site businesses",
            "mfg": "Small manufacturers"}
SPEND_DEFAULT = {"micro": 900, "prof": 2600, "multi": 9150, "mfg": 14300}   # segment medians from smb_leads.csv


def lead_features(profile: dict, source: str, product_ids: list[str]) -> dict:
    seg = profile.get("segment") or "micro"
    return {
        "lead_source": source, "segment": SEG_FULL.get(seg, seg), "business_type": profile.get("business_type") or "",
        "city_tier": profile.get("city_tier") or 2, "state": profile.get("state") or "", "preferred_language":
            "Hindi" if profile.get("language") == "hi" else "English", "employee_count": profile.get("employees") or 1,
        "num_sites": profile.get("sites") or 1, "annual_turnover_band": "", "has_gstin": "Y" if profile.get("has_gstin") else "N",
        "has_udyam": "Y" if profile.get("has_udyam") else "N", "current_internet": profile.get("current_internet") or "",
        "current_provider": "", "monthly_telecom_spend_inr": profile.get("monthly_spend") or SPEND_DEFAULT.get(seg, 900),
        "products_of_interest": ";".join(product_ids), "contact_role": "Owner",
        "created_date": datetime.now(timezone.utc).date().isoformat(),
    }


KNOWN_SOURCES = {"Field sales", "Channel partner", "Website form", "Inbound call", "Referral", "WhatsApp campaign"}


def _model_source(s: AdvisorSession) -> str:
    """Map where a digital session came from onto the lead sources the propensity model was trained on."""
    if s.partner_code:
        return "Channel partner"
    src = (s.source or "").strip()
    if src in KNOWN_SOURCES:
        return src
    if "whatsapp" in src.lower():
        return "WhatsApp campaign"
    if "referral" in src.lower():
        return "Referral"
    return "Website form"


def upsert_digital_lead(db: Session, s: AdvisorSession, stage: str, monthly_value: float | None = None,
                        product_ids: list[str] | None = None, wants_human: bool = False, kyc_decision: str | None = None,
                        kyc_codes: list[str] | None = None) -> Lead:
    p = s.profile or {}
    source = _model_source(s)
    pids = product_ids or [i["product_id"] for i in (s.recommendation or {}).get("items", [])]
    feats = lead_features(p, source, pids)
    model = get_model()
    score = model.score(feats, p.get("gstin_status")) if model else {"probability": None, "band": None, "drivers": []}
    lead = db.query(Lead).filter(Lead.session_id == s.id).first()
    if not lead:
        lead = Lead(ref="D-" + s.id[:8].upper(), origin="digital", session_id=s.id, source="Digital advisor" + (" (partner)" if s.partner_code else ""),
                    segment=p.get("segment") or "micro", features=feats, stage=stage)
        db.add(lead)
    lead.business_type = p.get("business_type")
    lead.business_name = p.get("business_name")
    lead.city, lead.city_tier, lead.has_gstin = p.get("city"), p.get("city_tier"), bool(p.get("has_gstin"))
    lead.segment = p.get("segment") or lead.segment
    lead.stage, lead.features = stage, feats
    lead.propensity, lead.band, lead.explanation = score["probability"], score["band"], score["drivers"]
    lead.partner_code = s.partner_code
    if monthly_value is not None:
        lead.monthly_value = monthly_value
    lead.routing = route(segment=lead.segment, city_tier=lead.city_tier, monthly_value=lead.monthly_value,
                         product_ids=pids, band=lead.band, wants_human=wants_human, kyc_decision=kyc_decision,
                         kyc_codes=kyc_codes, partner_code=s.partner_code)
    if stage in ("activated",):
        lead.status = "won"
    return lead
