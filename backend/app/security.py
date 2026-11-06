"""Authentication, authorisation, hashing, rate limiting and log scrubbing."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from app.config import settings
from app.domain.identifiers import scrub

ROLES = {"customer", "sales", "partner", "kyc_reviewer", "admin"}
STAFF_ROLES = {"sales", "partner", "kyc_reviewer", "admin"}


# ------------------------------------------------------------------ hashing
def pepper_hash(value: str) -> str:
    """Keyed hash for lookups of identifiers we must not store in clear (e.g. mobile numbers)."""
    return hmac.new(settings.pii_pepper.encode(), value.encode(), hashlib.sha256).hexdigest()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(24)


def token_hash(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


# ------------------------------------------------------------------ JWT
@dataclass
class Principal:
    sub: str
    role: str
    partner_code: str | None = None
    name: str | None = None

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES


def issue_jwt(sub: str, role: str, partner_code: str | None = None, name: str | None = None) -> str:
    assert role in ROLES
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "role": role, "pc": partner_code, "name": name, "iat": now,
               "exp": now + timedelta(minutes=settings.jwt_ttl_minutes), "iss": "udyam-digital"}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode(token: str) -> Principal:
    try:
        p = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer="udyam-digital")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    if p.get("role") not in ROLES:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid role")
    return Principal(p["sub"], p["role"], p.get("pc"), p.get("name"))


def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return _decode(authorization.split(" ", 1)[1])


def optional_principal(authorization: str | None = Header(default=None)) -> Principal | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return _decode(authorization.split(" ", 1)[1])


def require_roles(*roles: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not permitted for this role")
        return p
    return dep


require_customer = require_roles("customer")
require_staff = require_roles(*STAFF_ROLES)


# ------------------------------------------------------------------ rate limiting (single-process prototype)
class RateLimiter:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: int):
        q = self.hits[key]
        t = time.monotonic()
        while q and t - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many requests, please wait a moment")
        q.append(t)


limiter = RateLimiter()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------------ logging
class ScrubFilter(logging.Filter):
    """Masks GSTIN, Udyam, PAN and mobile numbers in every log line."""
    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub the template and each argument separately so formatters that unpack record.args
        # (e.g. uvicorn's access log expects a 5-tuple) keep working.
        try:
            if isinstance(record.msg, str):
                record.msg = scrub(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(a if isinstance(a, (int, float, bool, type(None))) else scrub(str(a)) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: (scrub(v) if isinstance(v, str) else v) for k, v in record.args.items()}
        except Exception:  # never let logging break a request
            pass
        return True


def configure_logging():
    root = logging.getLogger()
    if not any(isinstance(f, ScrubFilter) for f in root.filters):
        root.addFilter(ScrubFilter())
    for h in root.handlers:
        if not any(isinstance(f, ScrubFilter) for f in h.filters):
            h.addFilter(ScrubFilter())
    for name in ("uvicorn.access", "uvicorn.error", "app"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, ScrubFilter) for f in lg.filters):
            lg.addFilter(ScrubFilter())
