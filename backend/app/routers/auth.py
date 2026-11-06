"""Customer OTP login (mocked SMS gateway) and staff login."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.db import get_db
from app.kyc import storage
from app.domain.identifiers import mask_mobile
from app.models import Customer, OtpChallenge, StaffUser
from app.security import (Principal, client_key, current_principal, issue_jwt, limiter, pepper_hash, token_hash,
                          verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class OtpRequest(BaseModel):
    mobile: str = Field(..., min_length=10, max_length=14)


class OtpVerify(BaseModel):
    mobile: str = Field(..., min_length=10, max_length=14)
    otp: str = Field(..., min_length=4, max_length=8)
    name: str | None = Field(None, max_length=120)
    language: str = "en"
    partner_code: str | None = Field(None, max_length=20)


class StaffLogin(BaseModel):
    email: str = Field(..., max_length=120)
    password: str = Field(..., max_length=128)


def clean_mobile(m: str) -> str:
    d = re.sub(r"\D", "", m)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    if not re.fullmatch(r"[6-9]\d{9}", d):
        raise HTTPException(422, "enter a valid 10-digit Indian mobile number")
    return d


@router.post("/otp/request")
def otp_request(body: OtpRequest, request: Request, db: Session = Depends(get_db)):
    mobile = clean_mobile(body.mobile)
    limiter.check(f"otp:{mobile}", limit=5, window_s=600)
    limiter.check(f"otp-ip:{client_key(request)}", limit=20, window_s=600)
    code = settings.demo_otp if not settings.is_production else f"{secrets.randbelow(10**6):06d}"
    db.add(OtpChallenge(mobile_hash=pepper_hash(mobile), code_hash=token_hash(code),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
    db.commit()
    resp = {"sent": True, "masked": mask_mobile(mobile), "expires_in_s": 300}
    if not settings.is_production:
        resp["demo_note"] = "No SMS gateway in the prototype - use the demo OTP shown on screen."
        resp["demo_otp"] = code
    return resp


@router.post("/otp/verify")
def otp_verify(body: OtpVerify, db: Session = Depends(get_db)):
    mobile = clean_mobile(body.mobile)
    mh = pepper_hash(mobile)
    ch = (db.query(OtpChallenge).filter(OtpChallenge.mobile_hash == mh, OtpChallenge.used.is_(False))
          .order_by(OtpChallenge.expires_at.desc()).first())
    if not ch:
        raise HTTPException(400, "request an OTP first")
    exp = ch.expires_at if ch.expires_at.tzinfo else ch.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc) or ch.attempts >= 5:
        raise HTTPException(400, "OTP expired, please request a new one")
    ch.attempts += 1
    if not secrets.compare_digest(ch.code_hash, token_hash(body.otp)):
        db.commit()
        raise HTTPException(401, "incorrect OTP")
    ch.used = True
    cust = db.query(Customer).filter(Customer.mobile_hash == mh).first()
    if not cust:
        cust = Customer(mobile_hash=mh, mobile_masked=mask_mobile(mobile), name=body.name,
                        language=body.language if body.language in ("en", "hi") else "en", partner_code=body.partner_code)
        db.add(cust)
        db.flush()
    elif body.name:
        cust.name = body.name
    if not cust.mobile_enc:
        cust.mobile_enc = storage.encrypt_text(mobile)   # needed for call-backs; never returned by customer APIs
    p = Principal(cust.id, "customer")
    audit(db, "login.customer", p, "customer", cust.id)
    db.commit()
    return {"token": issue_jwt(cust.id, "customer", name=cust.name), "customer": {
        "id": cust.id, "name": cust.name, "mobile": cust.mobile_masked, "language": cust.language}}


@router.post("/staff/login")
def staff_login(body: StaffLogin, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"staff:{client_key(request)}", limit=10, window_s=300)
    u = db.query(StaffUser).filter(StaffUser.email == body.email.lower().strip()).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "invalid credentials")
    audit(db, "login.staff", Principal(u.id, u.role), "staff", u.id)
    db.commit()
    return {"token": issue_jwt(u.id, u.role, u.partner_code, u.name),
            "user": {"id": u.id, "name": u.name, "role": u.role, "partner_code": u.partner_code}}


@router.get("/me")
def me(p: Principal = Depends(current_principal)):
    return {"sub": p.sub, "role": p.role, "partner_code": p.partner_code, "name": p.name}
