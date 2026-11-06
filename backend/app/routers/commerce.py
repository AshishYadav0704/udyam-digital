"""Quote, checkout, orders and tracker."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.advisor.orchestrator import violation_text
from app import retention
from app.audit import audit
from app.config import settings
from app.db import get_db
from app.domain.pricing import InvalidBundle, build_quote
from app.domain.profile import BusinessProfile
from app.leads import upsert_digital_lead
from app.models import AdvisorSession, Escalation, KycCase, Order, Quote
from app.orders import FLOW, TERMINAL, add_event, new_order_no, tracker
from app.routers.advisor import load_session
from app.security import Principal, current_principal, require_customer

router = APIRouter(prefix="/api", tags=["commerce"])


class Line(BaseModel):
    product_id: str = Field(..., pattern=r"^P\d{2}$")
    qty: int = Field(..., ge=0, le=1000)


class PreviewIn(BaseModel):
    session_id: str
    items: list[Line] = Field(..., max_length=25)


class CheckoutIn(BaseModel):
    session_id: str
    items: list[Line] = Field(..., min_length=1, max_length=25)
    package: str = Field("recommended", pattern="^(recommended|starter|custom)$")
    contact_name: str = Field(..., min_length=2, max_length=120)
    install_address: str = Field(..., min_length=8, max_length=300)
    pincode: str = Field(..., pattern=r"^\d{6}$")
    accept_terms: bool
    payment_method: str = Field("upi_autopay", pattern="^(upi_autopay|card|netbanking|pay_on_install)$")
    simulate_payment_failure: bool = False


class PaymentIn(BaseModel):
    method: str = Field("upi_autopay", pattern="^(upi_autopay|card|netbanking|pay_on_install)$")
    simulate_failure: bool = False


class HelpIn(BaseModel):
    reason: str = Field("order_help", max_length=60)
    note: str | None = Field(None, max_length=500)


def _quote_or_422(items, profile: BusinessProfile, lang: str):
    try:
        return build_quote([(i.product_id, i.qty) for i in items if i.qty > 0], profile)
    except InvalidBundle as e:
        raise HTTPException(422, {"violations": e.violations,
                                  "messages": [violation_text(v, lang) for v in e.violations]})


@router.post("/quotes/preview")
def preview(body: PreviewIn, x_session_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    s = load_session(body.session_id, x_session_token, db)
    q = _quote_or_422(body.items, BusinessProfile.model_validate(s.profile), s.language)
    return q.to_dict()


@router.post("/quotes")
def save_quote(body: PreviewIn, x_session_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Save a quote to come back to later (addresses 'decided to wait')."""
    s = load_session(body.session_id, x_session_token, db)
    q = _quote_or_422(body.items, BusinessProfile.model_validate(s.profile), s.language)
    row = Quote(session_id=s.id, profile=s.profile, items=[i.model_dump() for i in body.items], quote=q.to_dict(),
                fingerprint=q.fingerprint)
    db.add(row)
    s.state = "quoted"
    upsert_digital_lead(db, s, "quoted", q.monthly_subtotal, [i.product_id for i in body.items])
    db.commit()
    return {"quote_id": row.id, "valid_until": q.valid_until, "quote": q.to_dict()}


@router.post("/checkout")
def checkout(body: CheckoutIn, x_session_token: str | None = Header(default=None),
             p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    s = load_session(body.session_id, x_session_token, db)
    if not body.accept_terms:
        raise HTTPException(422, "please accept the terms to place the order")
    profile = BusinessProfile.model_validate(s.profile)
    q = _quote_or_422(body.items, profile, s.language)        # server recomputes - client prices are never trusted
    s.customer_id = p.sub
    quote = Quote(session_id=s.id, customer_id=p.sub, profile=s.profile, items=[i.model_dump() for i in body.items if i.qty > 0],
                  quote=q.to_dict(), package=body.package, status="accepted", fingerprint=q.fingerprint)
    db.add(quote)
    db.flush()
    order = Order(order_no=new_order_no(), quote_id=quote.id, customer_id=p.sub, install_address=body.install_address + " - " + body.pincode,
                  contact_name=body.contact_name, partner_code=s.partner_code, status="payment_pending")
    db.add(order)
    db.flush()
    add_event(order, "order_placed", f"{len(quote.items)} products, Rs {q.monthly_subtotal:,.2f}/month")
    _pay(order, body.payment_method, body.simulate_payment_failure, q.setup_subtotal)
    lead = upsert_digital_lead(db, s, "ordered", q.monthly_subtotal, [i.product_id for i in body.items])
    order.routing = lead.routing
    audit(db, "order.placed", p, "order", order.id, monthly=q.monthly_subtotal, items=len(quote.items))
    db.commit()
    return _order_view(order, quote, s.language, db)


def _pay(order: Order, method: str, fail: bool, setup: float):
    if fail:
        add_event(order, "payment_failed", f"{method} declined (simulated) - you can retry or choose another method")
        return
    order.payment_status = "paid" if setup else "mandate_set"
    note = "AutoPay mandate set" + (f"; setup fee Rs {setup:,.0f} paid" if setup else "")
    if method == "pay_on_install":
        order.payment_status = "pay_on_install"
        note = "Setup fee payable at installation"
    add_event(order, "payment_done", note)


def _owned_order(order_id: str, p: Principal, db: Session) -> Order:
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "order not found")
    if p.role == "customer" and o.customer_id != p.sub:
        raise HTTPException(404, "order not found")
    if p.role == "partner" and o.partner_code != p.partner_code:
        raise HTTPException(404, "order not found")
    return o


def _order_view(order: Order, quote: Quote, lang: str, db: Session) -> dict:
    case = db.query(KycCase).filter(KycCase.order_id == order.id).order_by(KycCase.created_at.desc()).first()
    return {"order_id": order.id, "order_no": order.order_no, "status": order.status, "payment_status": order.payment_status,
            "created_at": order.created_at.isoformat(), "install_address": order.install_address,
            "quote": quote.quote, "profile": quote.profile, "routing": order.routing,
            "kyc": {"case_id": case.id, "status": case.status} if case else None,
            "tracker": tracker(order, quote.quote, lang)}


@router.post("/orders/{order_id}/payment")
def retry_payment(order_id: str, body: PaymentIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    o = _owned_order(order_id, p, db)
    if o.payment_status in ("paid", "mandate_set", "pay_on_install"):
        raise HTTPException(409, "payment already completed")
    q = db.get(Quote, o.quote_id)
    _pay(o, body.method, body.simulate_failure, q.quote["setup_subtotal"])
    db.commit()
    return _order_view(o, q, (q.profile or {}).get("language", "en"), db)


@router.get("/orders")
def my_orders(lang: str = "en", p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    rows = db.query(Order).filter(Order.customer_id == p.sub).order_by(Order.created_at.desc()).all()
    return {"orders": [_order_view(o, db.get(Quote, o.quote_id), lang, db) for o in rows]}


@router.get("/orders/{order_id}")
def get_order(order_id: str, lang: str = "en", p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    o = _owned_order(order_id, p, db)
    return _order_view(o, db.get(Quote, o.quote_id), lang, db)


@router.post("/orders/{order_id}/help")
def order_help(order_id: str, body: HelpIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    o = _owned_order(order_id, p, db)
    e = Escalation(customer_id=p.sub, order_id=o.id, reason=body.reason, note=body.note)
    db.add(e)
    add_event(o, "escalated", "Specialist assigned - call-back within 4 working hours")
    db.commit()
    return {"escalation_id": e.id, "status": "open"}


@router.post("/orders/{order_id}/advance")
def advance(order_id: str, lang: str = "en", p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Move an order to its next milestone. Staff in any environment; customers only in demo mode."""
    if p.role == "customer" and settings.is_production:
        raise HTTPException(403, "not permitted")
    if p.role not in ("customer", "admin", "sales"):
        raise HTTPException(403, "not permitted")
    o = _owned_order(order_id, p, db)
    q = db.get(Quote, o.quote_id)
    done = {e.stage for e in o.events}
    if "payment_done" not in done:
        raise HTTPException(409, "payment pending")
    if "kyc_verified" not in done:
        raise HTTPException(409, "KYC must be verified before installation can be scheduled")
    has_lines = any(l["product_id"] in ("P07", "P08") for l in q.quote["lines"])
    for stage in FLOW:
        if stage == "end_user_kyc" and not has_lines:
            continue
        if stage not in done:
            add_event(o, stage, "simulated progression (demo)" if p.role == "customer" else f"updated by {p.role}", actor=p.role)
            if stage in TERMINAL:
                retention.on_activation(db, o.id)
                s = db.get(AdvisorSession, q.session_id) if q.session_id else None
                if s:
                    upsert_digital_lead(db, s, "activated", q.quote["monthly_subtotal"])
            break
    db.commit()
    return _order_view(o, q, lang, db)
