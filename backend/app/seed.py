"""Create tables and demo data: staff users, partners and a win-back lead queue scored by the model."""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.domain.routing import ADDRESSABLE_DROPS, route
from app.kyc.registry import get_registry
from app.ml.propensity import get_model
from app.models import Lead, Partner, StaffUser
from app.security import hash_password

log = logging.getLogger("app.seed")
SEG = {"Micro retail & services": "micro", "Professional offices": "prof", "Small multi-site businesses": "multi",
       "Small manufacturers": "mfg"}
PARTNERS = [("PTN-LKO-01", "Awadh Digital Solutions", "Lucknow"), ("PTN-JAI-02", "Pink City Telecom Services", "Jaipur"),
            ("PTN-PAT-03", "Magadh Connect", "Patna"), ("PTN-NAG-04", "Orange City Networks", "Nagpur"),
            ("PTN-PUN-05", "Deccan SME Partners", "Pune"), ("PTN-DEL-06", "Capital Business Connect", "Delhi")]
STAFF = [("sales@accel.demo", "Ritu (Inside sales)", "sales", None),
         ("partner@accel.demo", "Awadh Digital (Partner)", "partner", "PTN-LKO-01"),
         ("kyc@accel.demo", "Imran (KYC reviewer)", "kyc_reviewer", None),
         ("admin@accel.demo", "Admin", "admin", None)]


def init_db(seed_leads: bool = True, max_leads: int = 600):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if not db.query(Partner).first():
            for code, name, city in PARTNERS:
                db.add(Partner(code=code, name=name, city=city))
        if not db.query(StaffUser).first():
            for email, name, role, pc in STAFF:
                db.add(StaffUser(email=email, name=name, role=role, partner_code=pc,
                                 password_hash=hash_password(settings.demo_staff_password)))
        db.commit()
        if seed_leads and not db.query(Lead).filter(Lead.origin == "historic_winback").first():
            _seed_winback(db, max_leads)
            db.commit()
    finally:
        db.close()


def _seed_winback(db, max_leads: int):
    model = get_model()
    reg = get_registry()
    partner_by_city = {city: code for code, _, city in PARTNERS}
    rows = [r for r in csv.DictReader(open(settings.data_dir / "smb_leads.csv", newline="", encoding="utf-8"))
            if r["outcome"] == "Dropped" and r["created_date"] >= "2026-06-01" and r["drop_reason"] in ADDRESSABLE_DROPS]
    rows = rows[:max_leads]
    for r in rows:
        status = None
        if r["gstin"]:
            rec = reg.gstin(r["gstin"])
            status = rec.status if rec else None
        score = model.score(r, status) if model else {"probability": None, "band": None, "drivers": []}
        seg = SEG[r["segment"]]
        pc = partner_by_city.get(r["city"]) if r["lead_source"] == "Channel partner" else None
        rt = route(segment=seg, city_tier=int(r["city_tier"]), band=score["band"], partner_code=pc,
                   drop_reason=r["drop_reason"], origin="historic_winback")
        db.add(Lead(ref=r["lead_id"], origin="historic_winback", source=r["lead_source"], segment=seg,
                    business_type=r["business_type"], business_name=r["business_name"], city=r["city"],
                    city_tier=int(r["city_tier"]), has_gstin=r["has_gstin"] == "Y", stage=r["stage_reached"],
                    drop_reason=r["drop_reason"], features={k: r[k] for k in (
                        "lead_source", "segment", "business_type", "city_tier", "state", "preferred_language",
                        "employee_count", "num_sites", "annual_turnover_band", "has_gstin", "has_udyam",
                        "current_internet", "current_provider", "monthly_telecom_spend_inr", "products_of_interest",
                        "contact_role", "created_date")},
                    propensity=score["probability"], band=score["band"], explanation=score["drivers"], routing=rt,
                    partner_code=pc, created_at=datetime.fromisoformat(r["created_date"]).replace(tzinfo=timezone.utc)))
    log.info("seeded %d win-back leads", len(rows))
