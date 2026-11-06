"""Document retention, as promised in the consent notice.

- Uploaded documents get a backstop deletion date of upload + DOC_RETENTION_DAYS (abandoned applications).
- When the order is activated: activation + DOC_RETENTION_DAYS (180 by default).
- When the application is rejected or cancelled: decision date + 30 days.
- Withdrawing KYC consent deletes the documents immediately (app/routers/kyc.py).

`purge_expired` deletes every active document whose date has passed. It runs at start-up and from the admin
endpoint; production schedules it daily. The verification result (masked identifiers, decision, reasons) is kept,
as the notice says, because telecom licence conditions require a record of the verification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.kyc import storage
from app.models import AuditEvent, KycCase, KycDocument

CANCELLED_DAYS = 30


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def backstop(uploaded_at: datetime | None = None) -> datetime:
    return _aware(uploaded_at or datetime.now(timezone.utc)) + timedelta(days=settings.doc_retention_days_after_activation)


def set_for_case(db: Session, case: KycCase, when: datetime) -> int:
    n = 0
    for d in case.documents:
        if d.active:
            d.delete_after = _aware(when)
            n += 1
    return n


def on_activation(db: Session, order_id: str, activated_at: datetime | None = None) -> int:
    at = _aware(activated_at or datetime.now(timezone.utc)) + timedelta(days=settings.doc_retention_days_after_activation)
    return sum(set_for_case(db, c, at) for c in db.query(KycCase).filter(KycCase.order_id == order_id).all())


def on_closed(db: Session, case: KycCase, closed_at: datetime | None = None) -> int:
    """Rejected or cancelled before activation: keep 30 days for disputes, then delete."""
    return set_for_case(db, case, _aware(closed_at or datetime.now(timezone.utc)) + timedelta(days=CANCELLED_DAYS))


def purge_expired(db: Session, now: datetime | None = None) -> int:
    now = _aware(now or datetime.now(timezone.utc))
    n = 0
    for d in db.query(KycDocument).filter(KycDocument.active.is_(True), KycDocument.delete_after.isnot(None)).all():
        if _aware(d.delete_after) <= now:
            storage.delete(d.storage_key)
            d.active = False
            n += 1
    if n:
        db.add(AuditEvent(actor_type="system", actor_id=None, action="retention.purged", entity="kyc_document",
                          entity_id=None, details={"documents": n}))
    db.commit()
    return n
