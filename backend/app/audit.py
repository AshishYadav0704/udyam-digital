"""Audit trail for sensitive actions. Details are scrubbed of identifiers before they are stored."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.domain.identifiers import scrub
from app.models import AuditEvent
from app.security import Principal


def audit(db: Session, action: str, principal: Principal | None = None, entity: str | None = None,
          entity_id: str | None = None, actor_type: str | None = None, **details) -> None:
    safe = json.loads(scrub(json.dumps(details, default=str)))
    db.add(AuditEvent(actor_type=actor_type or (principal.role if principal else "anonymous"),
                      actor_id=principal.sub if principal else None, action=action, entity=entity,
                      entity_id=entity_id, details=safe))
