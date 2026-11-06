"""Consent, privacy rights and Smart KYC endpoints."""
from __future__ import annotations

import csv
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.consent import NOTICE_VERSION, OPTIONAL, PURPOSES, REQUIRED
from app.db import get_db
from app.domain.identifiers import mask_gstin, mask_udyam, normalise_gstin, normalise_udyam
from app.kyc import service, storage
from app.leads import upsert_digital_lead
from app.models import AdvisorSession, Consent, Customer, KycCase, KycDocument, Order, Quote
from app.orders import add_event
from app.security import Principal, current_principal, require_customer

router = APIRouter(prefix="/api", tags=["kyc"])

# Specimen applicant -> matching lead, derived by analysis/03_kyc_specimen_eval.py (billed-to name + city)
SPECIMEN_LEADS = {"K01": "L00045", "K02": "L01287", "K03": "L03571", "K04": "L01014", "K05": "L04014", "K06": "L00115",
                  "K07": "L03349", "K08": "L03473", "K09": "L04779", "K10": "L04525", "K11": "L03485", "K12": "L03558"}


class ConsentIn(BaseModel):
    purposes: dict[str, bool]
    notice_version: str = NOTICE_VERSION
    language: str = Field("en", pattern="^(en|hi)$")


class WithdrawIn(BaseModel):
    purpose: str


class Declaration(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=120)
    signatory_name: str = Field(..., min_length=2, max_length=120)
    gstin: str | None = Field(None, max_length=20)
    udyam_number: str | None = Field(None, max_length=25)
    city: str | None = Field(None, max_length=60)
    state: str | None = Field(None, max_length=60)


class CaseIn(BaseModel):
    order_id: str
    declaration: Declaration


class SpecimenIn(BaseModel):
    applicant: str = Field(..., pattern=r"^K(0[1-9]|1[0-2])$")


# ------------------------------------------------------------------ consent
def _active_consents(db, customer_id) -> dict[str, Consent]:
    out = {}
    for c in db.query(Consent).filter(Consent.customer_id == customer_id).order_by(Consent.at).all():
        out[c.purpose] = c
    return {k: v for k, v in out.items() if v.granted and not v.withdrawn_at}


@router.post("/consent")
def give_consent(body: ConsentIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    unknown = set(body.purposes) - PURPOSES
    if unknown:
        raise HTTPException(422, f"unknown purposes: {sorted(unknown)}")
    if body.notice_version != NOTICE_VERSION:
        raise HTTPException(409, "the notice has changed - please review it again")
    for purpose, granted in body.purposes.items():
        db.add(Consent(customer_id=p.sub, purpose=purpose, granted=bool(granted), notice_version=body.notice_version,
                       language=body.language))
    audit(db, "consent.recorded", p, "customer", p.sub, purposes={k: bool(v) for k, v in body.purposes.items()})
    db.commit()
    return {"active": sorted(_active_consents(db, p.sub))}


@router.get("/consent")
def my_consents(p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    act = _active_consents(db, p.sub)
    return {"notice_version": NOTICE_VERSION, "purposes": {k: (k in act) for k in sorted(PURPOSES)},
            "required": sorted(REQUIRED), "optional": sorted(OPTIONAL)}


@router.post("/consent/withdraw")
def withdraw(body: WithdrawIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    if body.purpose not in PURPOSES:
        raise HTTPException(422, "unknown purpose")
    now = datetime.now(timezone.utc)
    for c in db.query(Consent).filter(Consent.customer_id == p.sub, Consent.purpose == body.purpose,
                                      Consent.withdrawn_at.is_(None)).all():
        c.withdrawn_at = now
    effect = "recorded"
    if body.purpose == "kyc_verification":
        for case in db.query(KycCase).filter(KycCase.customer_id == p.sub).all():
            for d in case.documents:
                if d.active:
                    storage.delete(d.storage_key)
                    d.active = False
            case.status = "withdrawn"
            if case.order_id:
                o = db.get(Order, case.order_id)
                if o and o.status != "active":
                    o.status = "cancelled_by_customer"
        effect = "KYC documents deleted and pending orders stopped"
    audit(db, "consent.withdrawn", p, "customer", p.sub, purpose=body.purpose)
    db.commit()
    return {"withdrawn": body.purpose, "effect": effect}


@router.get("/privacy/summary")
def privacy_summary(p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    """Right to access: a summary of what we hold, with identifiers masked."""
    c = db.get(Customer, p.sub)
    cases = db.query(KycCase).filter(KycCase.customer_id == p.sub).all()
    return {"customer": {"name": c.name, "mobile": c.mobile_masked, "language": c.language},
            "consents": sorted(_active_consents(db, p.sub)),
            "orders": [{"order_no": o.order_no, "status": o.status} for o in db.query(Order).filter(Order.customer_id == p.sub)],
            "kyc_cases": [{"id": k.id, "status": k.status,
                           "gstin": mask_gstin(k.declaration.get("gstin")), "udyam": mask_udyam(k.declaration.get("udyam_number")),
                           "documents": [{"slot": d.slot, "uploaded_at": d.uploaded_at.isoformat(),
                                          "delete_after": d.delete_after.isoformat() if d.delete_after else None}
                                         for d in k.documents if d.active]} for k in cases]}


# ------------------------------------------------------------------ KYC
def _view(case: KycCase, lang: str) -> dict:
    """Case as shown to its owner: findings, masked fields and the (masked) declaration they made."""
    d = case.declaration or {}
    return {**service.present(case, lang),
            "declaration": {"business_name": d.get("business_name"), "signatory_name": d.get("signatory_name"),
                            "gstin": mask_gstin(d.get("gstin")), "udyam_number": mask_udyam(d.get("udyam_number")),
                            "city": d.get("city"), "state": d.get("state")}}


def _case(case_id: str, p: Principal, db: Session) -> KycCase:
    c = db.get(KycCase, case_id)
    if not c:
        raise HTTPException(404, "case not found")
    if p.role == "customer" and c.customer_id != p.sub:
        raise HTTPException(404, "case not found")
    if p.role not in ("customer", "kyc_reviewer", "admin"):
        raise HTTPException(403, "not permitted")
    return c


@router.post("/kyc/cases")
def create_case(body: CaseIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    if "kyc_verification" not in _active_consents(db, p.sub):
        raise HTTPException(403, "consent for KYC verification is required before documents can be collected")
    o = db.get(Order, body.order_id)
    if not o or o.customer_id != p.sub:
        raise HTTPException(404, "order not found")
    d = body.declaration.model_dump()
    d["gstin"] = normalise_gstin(d["gstin"]) if d.get("gstin") else None
    d["udyam_number"] = normalise_udyam(d["udyam_number"]) if d.get("udyam_number") else None
    case = KycCase(order_id=o.id, customer_id=p.sub, declaration=d, status="collecting")
    db.add(case)
    audit(db, "kyc.case_created", p, "kyc_case", None, order=o.order_no)
    db.commit()
    return {"case_id": case.id, "status": case.status}


@router.post("/kyc/cases/{case_id}/documents")
async def upload(case_id: str, slot: str = Form(...), file: UploadFile = File(...), lang: str = "en",
                 p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    case = _case(case_id, p, db)
    if case.status in ("verified", "withdrawn"):
        raise HTTPException(409, "case is closed")
    data = await file.read(int(settings.max_upload_mb * 1024 * 1024) + 1)
    doc = service.add_document(db, case, slot, data)
    audit(db, "kyc.document_uploaded", p, "kyc_case", case.id, slot=slot, size=len(data))
    db.commit()
    return {"document_id": doc.id, "case": _view(case, lang)}


@router.post("/kyc/cases/{case_id}/specimen")
def load_specimen(case_id: str, body: SpecimenIn, lang: str = "en", p: Principal = Depends(require_customer),
                  db: Session = Depends(get_db)):
    """Demo helper (disabled in production): load one of the 12 specimen applicants as if uploaded."""
    if settings.is_production:
        raise HTTPException(404, "not found")
    case = _case(case_id, p, db)
    lead_id = SPECIMEN_LEADS[body.applicant]
    lead = next(r for r in csv.DictReader(open(settings.data_dir / "smb_leads.csv", newline="", encoding="utf-8"))
                if r["lead_id"] == lead_id)
    case.declaration = {"business_name": lead["business_name"], "signatory_name": lead["contact_name"],
                        "gstin": lead["gstin"] or None, "udyam_number": lead["udyam_number"] or None,
                        "city": lead["city"], "state": lead["state"]}
    for d in case.documents:
        d.active = False
    for slot in ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id"):
        f = settings.data_dir / "kyc_documents" / f"{body.applicant}_{slot}.png"
        if f.exists():
            service.add_document(db, case, slot, f.read_bytes())
    audit(db, "kyc.specimen_loaded", p, "kyc_case", case.id, applicant=body.applicant)
    db.commit()
    return _view(case, lang)


@router.post("/kyc/cases/{case_id}/evaluate")
def evaluate_case(case_id: str, lang: str = "en", p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    case = _case(case_id, p, db)
    res = service.run_checks(db, case)
    o = db.get(Order, case.order_id) if case.order_id else None
    if o:
        if not any(e.stage == "kyc_submitted" for e in o.events):
            add_event(o, "kyc_submitted")
        if res.decision == "verified":
            add_event(o, "kyc_verified", "All checks passed automatically")
        elif res.decision == "action_required":
            add_event(o, "kyc_action_required", ", ".join(f.code for f in res.findings if f.severity == "resubmit"))
        else:
            add_event(o, "kyc_review", "A KYC reviewer is checking: " + ", ".join(f.code for f in res.findings if f.severity in ("review", "block")))
        q = db.get(Quote, o.quote_id)
        s = db.get(AdvisorSession, q.session_id) if q and q.session_id else None
        if s:
            lead = upsert_digital_lead(db, s, f"kyc_{res.decision}", q.quote["monthly_subtotal"],
                                       kyc_decision=res.decision, kyc_codes=[f.code for f in res.findings if f.severity in ("review", "block")])
            o.routing = lead.routing
    audit(db, "kyc.evaluated", p, "kyc_case", case.id, decision=res.decision, codes=[f.code for f in res.findings])
    db.commit()
    return _view(case, lang)


@router.get("/kyc/cases/{case_id}")
def get_case(case_id: str, lang: str = "en", p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return _view(_case(case_id, p, db), lang)


@router.get("/kyc/cases/{case_id}/documents/{doc_id}/image")
def doc_image(case_id: str, doc_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    case = _case(case_id, p, db)
    d = db.get(KycDocument, doc_id)
    if not d or d.case_id != case.id or not d.active:
        raise HTTPException(404, "document not found")
    audit(db, "kyc.document_viewed", p, "kyc_document", d.id, slot=d.slot)
    db.commit()
    return Response(storage.get(d.storage_key), media_type="image/png",
                    headers={"Cache-Control": "no-store", "Content-Disposition": "inline"})


@router.delete("/kyc/cases/{case_id}/documents/{doc_id}")
def delete_doc(case_id: str, doc_id: str, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    case = _case(case_id, p, db)
    d = db.get(KycDocument, doc_id)
    if not d or d.case_id != case.id:
        raise HTTPException(404, "document not found")
    storage.delete(d.storage_key)
    d.active = False
    audit(db, "kyc.document_deleted", p, "kyc_document", d.id, slot=d.slot)
    db.commit()
    return {"deleted": True}
