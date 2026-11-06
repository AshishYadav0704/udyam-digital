"""Sales / partner / KYC back-office API (staff roles only; partners see only their own attributed work)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import retention
from app.audit import audit
from app.db import get_db
from app.domain.baseline import baseline
from app.domain.identifiers import mask_gstin, mask_udyam
from app.kyc import service
from app.ml.propensity import get_model
from app.models import AdvisorSession, AuditEvent, Customer, Escalation, KycCase, Lead, Order, Partner, Quote, StaffUser
from app.orders import add_event
from app.security import Principal, require_roles, require_staff

router = APIRouter(prefix="/api/backoffice", tags=["backoffice"])
reviewer = require_roles("kyc_reviewer", "admin")
admin_only = require_roles("admin")
sales_side = require_roles("sales", "partner", "admin")   # KYC reviewers do not need the sales pipeline


class AssignIn(BaseModel):
    assigned_to: str | None = Field(None, max_length=60)
    status: str | None = Field(None, pattern="^(open|contacted|won|lost|nurture)$")
    note: str | None = Field(None, max_length=300)      # follow-up note; identifiers are masked before it is stored


class DecisionIn(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|request_resubmission)$")
    note: str = Field(..., min_length=3, max_length=500)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _scope(q, model, p: Principal):
    if p.role == "partner":
        return q.filter(model.partner_code == p.partner_code)
    return q


@router.get("/overview")
def overview(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    sessions = _scope(db.query(AdvisorSession), AdvisorSession, p)
    orders = _scope(db.query(Order), Order, p).all()
    stages = Counter()
    for o in orders:
        for e in o.events:
            stages[e.stage] += 1
    n_sessions = sessions.count()
    recommended = sessions.filter(AdvisorSession.recommendation.isnot(None)).count()
    live = [{"stage": "Advisor started", "count": n_sessions}, {"stage": "Plan recommended", "count": recommended},
            {"stage": "Order placed", "count": len(orders)}, {"stage": "KYC verified", "count": stages["kyc_verified"]},
            {"stage": "Activated", "count": stages["activated"]}]
    now = datetime.now(timezone.utc)
    stuck = [o for o in orders if o.status not in ("active", "cancelled_by_customer")
             and _aware(max((e.at for e in o.events), default=o.created_at)) < now - timedelta(hours=48)]
    mrr = sum((db.get(Quote, o.quote_id).quote["monthly_subtotal"]) for o in orders if o.status == "active")
    pipeline = sum((db.get(Quote, o.quote_id).quote["monthly_subtotal"]) for o in orders if o.status != "active")
    leads = _scope(db.query(Lead), Lead, p)
    routes = Counter((l.routing or {}).get("route") for l in leads.all())
    return {
        "baseline": baseline(),
        "live": {"funnel": live, "orders": len(orders), "pending_kyc": sum(o.status in ("kyc_pending", "kyc_submitted", "kyc_action_required", "kyc_review") for o in orders),
                 "kyc_review": db.query(KycCase).filter(KycCase.status == "manual_review").count() if p.role != "partner" else None,
                 "stuck_orders": len(stuck), "activated_mrr": mrr, "pipeline_mrr": pipeline,
                 "open_escalations": db.query(Escalation).filter(Escalation.status == "open").count() if p.role != "partner" else None},
        "lead_routes": dict(routes),
        "model": {"available": get_model() is not None},
    }


def _lead_row(l: Lead) -> dict:
    return {"id": l.id, "ref": l.ref, "origin": l.origin, "source": l.source, "segment": l.segment,
            "business_type": l.business_type, "business_name": l.business_name, "city": l.city, "city_tier": l.city_tier,
            "has_gstin": l.has_gstin, "stage": l.stage, "drop_reason": l.drop_reason, "propensity": l.propensity,
            "band": l.band, "route": (l.routing or {}).get("route"), "route_label": (l.routing or {}).get("label"),
            "reasons": (l.routing or {}).get("reasons", []), "sla_hours": (l.routing or {}).get("sla_hours"),
            "drivers": l.explanation or [], "status": l.status, "assigned_to": l.assigned_to, "partner_code": l.partner_code,
            "monthly_value": l.monthly_value, "created_at": l.created_at.isoformat() if l.created_at else None}


def _activity(db: Session, lead_id: str) -> list[dict]:
    """Follow-up history of a lead, newest first, from the audit trail (who changed what, with their note)."""
    rows = (db.query(AuditEvent).filter(AuditEvent.entity == "lead", AuditEvent.entity_id == lead_id)
            .order_by(AuditEvent.at.desc()).limit(20).all())
    ids = [r.actor_id for r in rows if r.actor_id]
    names = {u.id: u.name for u in db.query(StaffUser).filter(StaffUser.id.in_(ids)).all()} if ids else {}
    return [{"at": _aware(r.at).isoformat(), "by": names.get(r.actor_id) or r.actor_type,
             "status": (r.details or {}).get("status"), "assigned_to": (r.details or {}).get("assigned_to"),
             "note": (r.details or {}).get("note")} for r in rows]


@router.get("/leads")
def list_leads(origin: str | None = None, band: str | None = None, route: str | None = None, segment: str | None = None,
               status: str | None = None, search: str | None = Query(None, alias="q", max_length=60), limit: int = 50, offset: int = 0,
               p: Principal = Depends(sales_side), db: Session = Depends(get_db)):
    q = _scope(db.query(Lead), Lead, p)
    if origin:
        q = q.filter(Lead.origin == origin)
    if band:
        q = q.filter(Lead.band == band)
    if segment:
        q = q.filter(Lead.segment == segment)
    if status:
        q = q.filter(Lead.status == status)
    rows = q.order_by(Lead.propensity.desc().nullslast(), Lead.created_at.desc()).all()
    if route:
        rows = [l for l in rows if (l.routing or {}).get("route") == route]
    if search and search.strip():
        needle = search.strip().lower()      # reference, business type or name, or city
        rows = [l for l in rows if needle in " ".join(filter(None, [l.ref, l.business_type, l.business_name, l.city])).lower()]
    total = len(rows)
    limit = max(1, min(limit, 200))
    return {"total": total, "leads": [_lead_row(l) for l in rows[offset:offset + limit]],
            "bands": dict(Counter(l.band for l in rows)), "routes": dict(Counter((l.routing or {}).get("route") for l in rows))}


@router.get("/leads/{lead_id}")
def lead_detail(lead_id: str, p: Principal = Depends(sales_side), db: Session = Depends(get_db)):
    l = db.get(Lead, lead_id)
    if not l or (p.role == "partner" and l.partner_code != p.partner_code):
        raise HTTPException(404, "lead not found")
    return {**_lead_row(l), "features": {k: v for k, v in (l.features or {}).items() if k not in ("gstin", "udyam_number")},
            "activity": _activity(db, l.id)}


@router.post("/leads/{lead_id}/assign")
def assign(lead_id: str, body: AssignIn, p: Principal = Depends(sales_side), db: Session = Depends(get_db)):
    l = db.get(Lead, lead_id)
    if not l or (p.role == "partner" and l.partner_code != p.partner_code):
        raise HTTPException(404, "lead not found")
    if body.assigned_to is not None:
        l.assigned_to = body.assigned_to
    if body.status:
        l.status = body.status
    note = (body.note or "").strip() or None
    audit(db, "lead.updated", p, "lead", l.id, assigned_to=body.assigned_to, status=body.status, note=note)
    db.commit()
    return {**_lead_row(l), "activity": _activity(db, l.id)}


@router.get("/kyc-queue")
def kyc_queue(p: Principal = Depends(reviewer), db: Session = Depends(get_db)):
    rows = db.query(KycCase).filter(KycCase.status.in_(["manual_review", "action_required"])).order_by(KycCase.updated_at).all()
    out = []
    for c in rows:
        res = c.result or {}
        out.append({"case_id": c.id, "status": c.status, "business": c.declaration.get("business_name"),
                    "gstin": mask_gstin(c.declaration.get("gstin")), "udyam": mask_udyam(c.declaration.get("udyam_number")),
                    "findings": [f["code"] for f in res.get("findings", []) if f["severity"] in ("review", "block", "resubmit")],
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None})
    return {"cases": out}


@router.get("/kyc/{case_id}")
def kyc_case(case_id: str, lang: str = "en", p: Principal = Depends(reviewer), db: Session = Depends(get_db)):
    c = db.get(KycCase, case_id)
    if not c:
        raise HTTPException(404, "case not found")
    audit(db, "kyc.case_viewed", p, "kyc_case", c.id)
    db.commit()
    return {**service.present(c, lang, audience="staff"), "declaration": {**c.declaration, "gstin": mask_gstin(c.declaration.get("gstin")),
                                                         "udyam_number": mask_udyam(c.declaration.get("udyam_number"))}}


@router.post("/kyc/{case_id}/decision")
def kyc_decision(case_id: str, body: DecisionIn, p: Principal = Depends(reviewer), db: Session = Depends(get_db)):
    c = db.get(KycCase, case_id)
    if not c:
        raise HTTPException(404, "case not found")
    c.status = {"approve": "verified", "reject": "rejected", "request_resubmission": "action_required"}[body.decision]
    c.reviewer_id, c.reviewer_note = p.sub, body.note
    o = db.get(Order, c.order_id) if c.order_id else None
    if o:
        stage = {"verified": "kyc_verified", "rejected": "kyc_review", "action_required": "kyc_action_required"}[c.status]
        add_event(o, stage, f"Reviewer: {body.note}", actor="kyc_reviewer")
        if c.status == "rejected":
            o.status = "kyc_rejected"
    if c.status == "rejected":
        retention.on_closed(db, c)          # keep 30 days for disputes, then delete (consent notice)
    audit(db, "kyc.decision", p, "kyc_case", c.id, decision=body.decision)
    db.commit()
    return {"case_id": c.id, "status": c.status}


@router.get("/orders")
def staff_orders(stuck: bool = False, p: Principal = Depends(sales_side), db: Session = Depends(get_db)):
    rows = _scope(db.query(Order), Order, p).order_by(Order.created_at.desc()).all()
    now = datetime.now(timezone.utc)
    out = []
    for o in rows:
        last = _aware(max((e.at for e in o.events), default=o.created_at))
        is_stuck = o.status not in ("active", "cancelled_by_customer") and last < now - timedelta(hours=48)
        if stuck and not is_stuck:
            continue
        q = db.get(Quote, o.quote_id)
        out.append({"order_id": o.id, "order_no": o.order_no, "status": o.status, "payment_status": o.payment_status,
                    "monthly": q.quote["monthly_subtotal"], "business": (q.profile or {}).get("business_type"),
                    "city": (q.profile or {}).get("city"), "route": (o.routing or {}).get("route"), "stuck": is_stuck,
                    "last_update": last.isoformat(), "partner_code": o.partner_code})
    return {"orders": out}


class EscalationUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|resolved)$")
    assigned_to: str | None = Field(None, max_length=60)


def _esc_contact(e: Escalation, db: Session) -> tuple[str | None, str | None]:
    """(masked, encrypted) call-back number: the one given for the call-back, else the verified login mobile."""
    if e.contact_enc:
        return e.contact_masked, e.contact_enc
    if e.customer_id:
        c = db.get(Customer, e.customer_id)
        if c and c.mobile_enc:
            return c.mobile_masked, c.mobile_enc
    if e.session_id:
        s = db.get(AdvisorSession, e.session_id)
        if s and s.customer_id:
            c = db.get(Customer, s.customer_id)
            if c and c.mobile_enc:
                return c.mobile_masked, c.mobile_enc
    return None, None


@router.get("/escalations")
def escalations(p: Principal = Depends(require_roles("sales", "admin")), db: Session = Depends(get_db)):
    rows = db.query(Escalation).order_by(Escalation.created_at.desc()).limit(100).all()
    out = []
    for e in rows:
        masked, _ = _esc_contact(e, db)
        order = db.get(Order, e.order_id) if e.order_id else None
        s = db.get(AdvisorSession, e.session_id) if e.session_id else None
        prof = (s.profile if s else None) or {}
        out.append({"id": e.id, "reason": e.reason, "status": e.status, "language": e.language,
                    "preferred_time": e.preferred_time, "note": e.note, "order_no": order.order_no if order else None,
                    "business": prof.get("business_type"), "city": prof.get("city"), "contact": masked,
                    "assigned_to": e.assigned_to, "created_at": e.created_at.isoformat()})
    return {"escalations": out}


@router.post("/escalations/{esc_id}/reveal")
def reveal_contact(esc_id: str, p: Principal = Depends(require_roles("sales", "admin")), db: Session = Depends(get_db)):
    """Show the full call-back number to the person making the call. Every reveal is audited."""
    e = db.get(Escalation, esc_id)
    if not e:
        raise HTTPException(404, "escalation not found")
    _, enc = _esc_contact(e, db)
    if not enc:
        raise HTTPException(404, "no call-back number on this request")
    audit(db, "escalation.contact_revealed", p, "escalation", e.id)
    db.commit()
    from app.kyc import storage
    return {"mobile": storage.decrypt_text(enc)}


@router.post("/escalations/{esc_id}")
def update_escalation(esc_id: str, body: EscalationUpdate, p: Principal = Depends(require_roles("sales", "admin")),
                      db: Session = Depends(get_db)):
    e = db.get(Escalation, esc_id)
    if not e:
        raise HTTPException(404, "escalation not found")
    e.status = body.status
    if body.assigned_to is not None:
        e.assigned_to = body.assigned_to
    audit(db, "escalation.updated", p, "escalation", e.id, status=body.status)
    db.commit()
    return {"id": e.id, "status": e.status, "assigned_to": e.assigned_to}


@router.get("/partners")
def partners(p: Principal = Depends(sales_side), db: Session = Depends(get_db)):
    parts = db.query(Partner).all()
    if p.role == "partner":
        parts = [x for x in parts if x.code == p.partner_code]
    leads = defaultdict(Counter)
    for l in db.query(Lead).filter(Lead.partner_code.isnot(None)).all():
        leads[l.partner_code][l.band or "unscored"] += 1
    orders = defaultdict(lambda: {"orders": 0, "mrr": 0.0})
    for o in db.query(Order).filter(Order.partner_code.isnot(None)).all():
        q = db.get(Quote, o.quote_id)
        orders[o.partner_code]["orders"] += 1
        orders[o.partner_code]["mrr"] += q.quote["monthly_subtotal"]
    return {"partners": [{"code": x.code, "name": x.name, "city": x.city, "leads": dict(leads[x.code]),
                          "lead_total": sum(leads[x.code].values()), **orders[x.code]} for x in parts]}


@router.post("/retention/run")
def run_retention(p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    """Delete documents past their retention date. Production runs this daily from a scheduler."""
    n = retention.purge_expired(db)
    audit(db, "retention.run", p, "kyc_document", None, deleted=n)
    db.commit()
    return {"deleted": n}


@router.get("/audit")
def audit_log(limit: int = 100, p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.query(AuditEvent).order_by(AuditEvent.at.desc()).limit(min(limit, 500)).all()
    return {"events": [{"at": a.at.isoformat(), "actor_type": a.actor_type, "action": a.action, "entity": a.entity,
                        "details": a.details} for a in rows]}


@router.post("/score")
def score(lead: dict, p: Principal = Depends(require_staff)):
    m = get_model()
    if not m:
        raise HTTPException(503, "model not available")
    return m.score(lead, lead.get("gstin_status"))
