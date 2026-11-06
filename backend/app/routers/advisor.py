"""Conversational advisor API. Sessions are anonymous until checkout and protected by a per-session secret."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.advisor.orchestrator import Advisor, build_recommendation_payload
from app.db import get_db
from app.domain.profile import BusinessProfile
from app.domain.recommender import resolve_profile
from app.leads import upsert_digital_lead
from app.models import AdvisorSession, Escalation
from app.domain.identifiers import mask_mobile, normalise_gstin, scrub, validate_gstin
from app.kyc.registry import get_registry
from app.kyc import storage
from app.routers.auth import clean_mobile
from app.security import client_key, limiter, token_hash

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


class NewSession(BaseModel):
    language: str = Field("en", pattern="^(en|hi)$")
    source: str = Field("Website", max_length=30)
    partner_code: str | None = Field(None, max_length=20, pattern=r"^[A-Z0-9-]*$")


class Turn(BaseModel):
    text: str | None = Field(None, max_length=600)
    needs: list[str] | None = Field(None, max_length=20)
    action: str | None = Field(None, pattern="^(show_plan|skip|human)$")
    language: str | None = Field(None, pattern="^(en|hi)$")   # owner switched language mid-conversation


class EscalationIn(BaseModel):
    reason: str = Field("advisor_help", max_length=60)
    preferred_time: str | None = Field(None, pattern="^(morning|afternoon|evening)$")
    note: str | None = Field(None, max_length=500)
    mobile: str | None = Field(None, min_length=10, max_length=14)


def load_session(session_id: str, x_session_token: str | None, db: Session) -> AdvisorSession:
    s = db.get(AdvisorSession, session_id)
    if not s or not x_session_token or not secrets.compare_digest(s.token_hash, token_hash(x_session_token)):
        raise HTTPException(404, "session not found")
    return s


@router.post("/sessions")
def new_session(body: NewSession, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"adv-new:{client_key(request)}", limit=30, window_s=600)
    tok = secrets.token_urlsafe(24)
    s = AdvisorSession(token_hash=token_hash(tok), language=body.language, source=body.source,
                       partner_code=body.partner_code, profile={"language": body.language}, asked=[])
    db.add(s)
    db.flush()
    resp = Advisor(db).greeting(s)
    db.commit()
    return {"session_id": s.id, "session_token": tok, "language": s.language, **resp, "profile": s.profile, "state": s.state}


@router.post("/sessions/{session_id}/messages")
def message(session_id: str, body: Turn, request: Request, x_session_token: str | None = Header(default=None),
            db: Session = Depends(get_db)):
    limiter.check(f"adv-msg:{session_id}", limit=60, window_s=300)
    s = load_session(session_id, x_session_token, db)
    if not (body.text or body.needs or body.action):
        raise HTTPException(422, "send text, needs or an action")
    if body.language:
        s.language = body.language
    resp = Advisor(db).handle(s, body.text, body.needs, body.action)
    rec = resp.get("recommendation") or {}
    if resp.get("state") in ("recommended", "escalated", "not_serviceable"):
        upsert_digital_lead(db, s, stage=resp["state"], monthly_value=(rec.get("quote") or {}).get("monthly_subtotal"),
                            wants_human=bool(resp.get("escalated") or resp.get("not_serviceable")))
    if resp.get("escalated") or resp.get("not_serviceable"):
        db.add(Escalation(session_id=s.id, reason="partner_serviceability" if resp.get("not_serviceable") else "advisor_help",
                          language=s.language))
    db.commit()
    return resp


@router.patch("/sessions/{session_id}/profile")
def edit_profile(session_id: str, body: dict, x_session_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Form-based alternative to chat: validated partial update, then recommendation if complete."""
    s = load_session(session_id, x_session_token, db)
    allowed = set(BusinessProfile.model_fields) - {"segment", "city_tier", "state", "gstin_status"}
    upd = {k: v for k, v in body.items() if k in allowed}
    if upd.get("language") in ("en", "hi"):
        s.language = upd["language"]
    if upd.get("has_gstin") is False:
        upd["gstin"] = None
    if upd.get("gstin"):
        g = normalise_gstin(str(upd["gstin"]))
        if validate_gstin(g):
            raise HTTPException(422, {"messages": ["That GSTIN doesn't look right - please check the 15 characters."],
                                      "field": "gstin"})
        upd["gstin"], upd["has_gstin"] = g, True
    try:
        p = resolve_profile(BusinessProfile.model_validate(s.profile or {}).merge(upd))
    except Exception as e:
        raise HTTPException(422, f"invalid profile: {e}")
    if upd.get("gstin"):
        try:
            rec = get_registry().gstin(p.gstin)
        except ConnectionError:
            rec = None
        p = p.model_copy(update={"gstin_status": rec.status if rec else "NotFound",
                                 "business_name": p.business_name or (rec.trade_name if rec else None)})
    elif p.has_gstin is False:
        p = p.model_copy(update={"gstin_status": None})
    s.profile = p.model_dump()
    payload = build_recommendation_payload(p, s.language) if not p.missing_required() else None
    if payload and payload["status"] == "ok":
        s.state = "recommended"
        s.recommendation = {"items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in payload["items"]]}
        upsert_digital_lead(db, s, "recommended", payload["quote"]["monthly_subtotal"])
    db.commit()
    return {"profile": s.profile, "missing": p.missing_required(), "recommendation": payload, "state": s.state}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, x_session_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    s = load_session(session_id, x_session_token, db)
    payload = None
    if s.state == "recommended":
        payload = build_recommendation_payload(BusinessProfile.model_validate(s.profile), s.language)
    return {"session_id": s.id, "language": s.language, "state": s.state, "profile": s.profile,
            "messages": [{"role": m.role, "text": m.text, **(m.meta or {})} for m in s.messages], "recommendation": payload}


@router.post("/sessions/{session_id}/escalate")
def escalate(session_id: str, body: EscalationIn, x_session_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    s = load_session(session_id, x_session_token, db)
    limiter.check(f"adv-esc:{session_id}", limit=5, window_s=600)
    # one open call-back per session: a chat "talk to a person" already opened one, so update it
    e = (db.query(Escalation).filter(Escalation.session_id == s.id, Escalation.status == "open")
         .order_by(Escalation.created_at.desc()).first())
    if not e:
        e = Escalation(session_id=s.id, reason=body.reason, language=s.language)
        db.add(e)
    e.preferred_time, e.note, e.language = body.preferred_time or e.preferred_time, scrub(body.note) if body.note else e.note, s.language
    if body.mobile:
        m = clean_mobile(body.mobile)
        e.contact_enc, e.contact_masked = storage.encrypt_text(m), mask_mobile(m)
    upsert_digital_lead(db, s, stage=s.state, wants_human=True)
    db.flush()
    db.commit()
    return {"escalation_id": e.id, "status": "open", "contact": e.contact_masked,
            "message": "A specialist will call you back within one working day."}
