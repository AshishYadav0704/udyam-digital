"""KYC application service: upload validation, extraction, evaluation, presentation."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone  # noqa: F401

import cv2
import numpy as np
from fastapi import HTTPException

from app.config import settings
from app.i18n import t
from app.kyc import storage
from app.kyc.checks import Declaration, KycResult, evaluate
from app.kyc.document_ai import DOC_TYPES, Extraction, Field, Quality, extract
from app.kyc.registry import get_registry
from app.models import KycCase, KycDocument

MAGIC = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}
MAX_PIXELS = 40_000_000


def sniff(data: bytes) -> str | None:
    for sig, mime in MAGIC.items():
        if data.startswith(sig):
            return mime
    return None


def validate_upload(data: bytes, slot: str) -> bytes:
    """Reject anything that is not a sane PNG/JPEG within limits; return a re-encoded PNG (metadata stripped)."""
    if slot not in DOC_TYPES:
        raise HTTPException(422, f"unknown document slot '{slot}'")
    if len(data) == 0:
        raise HTTPException(422, "empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"file larger than {settings.max_upload_mb:g} MB")
    if sniff(data) is None:
        raise HTTPException(415, "only PNG or JPEG photos/scans are accepted")
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(422, "the file could not be decoded as an image")
    h, w = img.shape[:2]
    if h * w > MAX_PIXELS or min(h, w) < 200:
        raise HTTPException(422, "image dimensions out of range")
    ok, png = cv2.imencode(".png", img)
    if not ok:
        raise HTTPException(500, "could not process image")
    return png.tobytes()


def add_document(db, case: KycCase, slot: str, raw: bytes) -> KycDocument:
    clean = validate_upload(raw, slot)
    ex = extract(clean, slot)
    for d in case.documents:
        if d.slot == slot and d.active:
            d.active = False
            storage.delete(d.storage_key)
    from app.retention import backstop
    doc = KycDocument(case_id=case.id, slot=slot, sha256=hashlib.sha256(raw).hexdigest(), size=len(raw),
                      storage_key=storage.put(clean), extraction=ex.to_dict(), delete_after=backstop())
    db.add(doc)
    case.documents.append(doc)
    case.status = "collecting"
    return doc


def _rehydrate(d: dict) -> Extraction:
    q = Quality(**d["quality"])
    fields = {k: Field(v["value"], v["confidence"], v["validated"], v.get("agreement", 0.0)) for k, v in d["fields"].items()}
    return Extraction(d["doc_type"], d["type_confidence"], q, fields, d["deskewed_by"], d["variants_used"], "",
                      d.get("ocr_failed", False))


def run_checks(db, case: KycCase) -> KycResult:
    active = [d for d in case.documents if d.active]
    docs = {slot: None for slot in DOC_TYPES}
    for d in active:
        docs[d.slot] = _rehydrate(d.extraction)
    declared_slots = {"gst_certificate": bool(case.declaration.get("gstin")),
                      "udyam_certificate": bool(case.declaration.get("udyam_number"))}
    # don't flag documents the applicant did not need and did not upload
    docs = {k: v for k, v in docs.items() if v is not None or k in ("address_proof", "signatory_id") or declared_slots.get(k)}
    hashes: dict[str, list[str]] = {}
    for d in active:
        hashes.setdefault(d.sha256, []).append(d.slot)
    # same file reused by another customer's case is a fraud signal
    for d in active:
        others = db.query(KycDocument).filter(KycDocument.sha256 == d.sha256, KycDocument.case_id != case.id).count()
        if others:
            hashes.setdefault(d.sha256, []).append("another_application")
    decl = Declaration(**{k: case.declaration.get(k) for k in Declaration.__dataclass_fields__})
    res = evaluate(decl, docs, get_registry(), duplicate_hashes={h: s for h, s in hashes.items() if len(s) > 1} or None)
    case.result = res.to_dict()
    case.status = res.decision
    return res


# Findings that are internal signals (e.g. a known artefact of the synthetic certificate generator) are kept for
# reviewers but not shown to applicants; resolution notes are written for staff and are never shown to applicants.
CUSTOMER_HIDDEN_CODES = {"ACTIVITY_DIFFERS"}


def present(case: KycCase, lang: str, audience: str = "customer") -> dict:
    res = case.result or {}
    findings = []
    for f in res.get("findings", []):
        if audience == "customer" and f["code"] in CUSTOMER_HIDDEN_CODES:
            continue
        params = {k: v for k, v in (f.get("detail") or {}).items() if isinstance(v, (str, int, float))}
        doc = f.get("document") or ""
        doc_label = t(lang, f"documents.{doc}") if doc in DOC_TYPES else doc
        if "detected" in params:
            params["detected"] = t(lang, f"documents.{params['detected']}")
        if "field" in params:
            params["field"] = params["field"].replace("_", " ")
        findings.append({"code": f["code"], "severity": f["severity"], "document": doc or None,
                         "text": t(lang, f"kyc.{f['code']}", document=doc_label, **params),
                         "resolution": f.get("resolution") if audience == "staff" else None})
    docs = []
    for d in case.documents:
        if not d.active:
            continue
        ex = d.extraction
        docs.append({"id": d.id, "slot": d.slot, "label": t(lang, f"documents.{d.slot}"), "doc_type": ex["doc_type"],
                     "quality": ex["quality"], "deskewed_by": ex["deskewed_by"],
                     "fields": {k: {"value": _mask_field(k, v["value"]), "confidence": v["confidence"], "validated": v["validated"]}
                                for k, v in ex["fields"].items()},
                     "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None})
    return {"id": case.id, "status": case.status, "decision": res.get("decision"),
            "decision_label": t(lang, f"decision.{res['decision']}") if res.get("decision") else None,
            "findings": findings, "registry": res.get("registry", {}), "documents": docs,
            "reference_date": res.get("reference_date"), "reviewer_note": case.reviewer_note}


def _mask_field(name: str, value):
    from app.domain.identifiers import mask_gstin, mask_udyam
    if value is None:
        return None
    if name == "gstin":
        return mask_gstin(value)
    if name == "udyam_number":
        return mask_udyam(value)
    if name in ("consumer_no", "id_no") and isinstance(value, str) and len(value) > 4:
        return "*" * (len(value) - 4) + value[-4:]
    return value
