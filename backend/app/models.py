"""ORM models. Personal data is minimised: mobile numbers are stored as a salted hash plus a masked copy,
documents are encrypted on disk, and free text is PII-scrubbed before it is persisted."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    mobile_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mobile_masked: Mapped[str] = mapped_column(String(16))
    mobile_enc: Mapped[str | None] = mapped_column(Text)   # Fernet; only revealed to staff for a call-back, audited
    name: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(5), default="en")
    partner_code: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    mobile_hash: Mapped[str] = mapped_column(String(64), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Partner(Base):
    __tablename__ = "partners"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(60))


class StaffUser(Base):
    __tablename__ = "staff_users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))       # sales | partner | kyc_reviewer | admin
    partner_code: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(100))


class AdvisorSession(Base):
    __tablename__ = "advisor_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    token_hash: Mapped[str] = mapped_column(String(64))
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    language: Mapped[str] = mapped_column(String(5), default="en")
    source: Mapped[str] = mapped_column(String(30), default="Website")
    partner_code: Mapped[str | None] = mapped_column(String(20))
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(30), default="collecting")   # collecting | recommended | quoted | escalated
    asked: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[dict | None] = mapped_column(JSON)
    llm_provider: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    messages: Mapped[list["AdvisorMessage"]] = relationship(back_populates="session", order_by="AdvisorMessage.created_at")


class AdvisorMessage(Base):
    __tablename__ = "advisor_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("advisor_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))            # user | assistant
    text: Mapped[str] = mapped_column(Text)                  # scrubbed of identifiers
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    session: Mapped[AdvisorSession] = relationship(back_populates="messages")


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("advisor_sessions.id"))
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    profile: Mapped[dict] = mapped_column(JSON)
    items: Mapped[list] = mapped_column(JSON)
    quote: Mapped[dict] = mapped_column(JSON)
    package: Mapped[str] = mapped_column(String(20), default="recommended")
    status: Mapped[str] = mapped_column(String(20), default="draft")      # draft | accepted | expired
    fingerprint: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    order_no: Mapped[str] = mapped_column(String(20), unique=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="kyc_pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    install_address: Mapped[str | None] = mapped_column(String(300))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    routing: Mapped[dict] = mapped_column(JSON, default=dict)
    partner_code: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", order_by="OrderEvent.at")


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(300))
    actor: Mapped[str] = mapped_column(String(30), default="system")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    order: Mapped[Order] = relationship(back_populates="events")


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean)
    notice_version: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(5))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KycCase(Base):
    __tablename__ = "kyc_cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    declaration: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="collecting")
    result: Mapped[dict | None] = mapped_column(JSON)
    reviewer_id: Mapped[str | None] = mapped_column(String(32))
    reviewer_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    documents: Mapped[list["KycDocument"]] = relationship(back_populates="case")


class KycDocument(Base):
    __tablename__ = "kyc_documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("kyc_cases.id"), index=True)
    slot: Mapped[str] = mapped_column(String(30))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(80))
    extraction: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    case: Mapped[KycCase] = relationship(back_populates="documents")


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    ref: Mapped[str] = mapped_column(String(20), index=True)
    origin: Mapped[str] = mapped_column(String(20))          # historic_winback | digital
    source: Mapped[str] = mapped_column(String(30))
    segment: Mapped[str] = mapped_column(String(40))
    business_type: Mapped[str | None] = mapped_column(String(60))
    business_name: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(60))
    city_tier: Mapped[int | None] = mapped_column(Integer)
    has_gstin: Mapped[bool] = mapped_column(Boolean, default=False)
    stage: Mapped[str] = mapped_column(String(40))
    drop_reason: Mapped[str | None] = mapped_column(String(80))
    features: Mapped[dict] = mapped_column(JSON)
    propensity: Mapped[float | None] = mapped_column(Float)
    band: Mapped[str | None] = mapped_column(String(10))
    explanation: Mapped[list] = mapped_column(JSON, default=list)
    routing: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")
    assigned_to: Mapped[str | None] = mapped_column(String(60))
    partner_code: Mapped[str | None] = mapped_column(String(20))
    session_id: Mapped[str | None] = mapped_column(String(32))
    monthly_value: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Escalation(Base):
    __tablename__ = "escalations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    customer_id: Mapped[str | None] = mapped_column(String(32))
    session_id: Mapped[str | None] = mapped_column(String(32))
    order_id: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(5), default="en")
    preferred_time: Mapped[str | None] = mapped_column(String(40))
    contact_enc: Mapped[str | None] = mapped_column(Text)     # Fernet-encrypted call-back number
    contact_masked: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default="open")
    assigned_to: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
