"""End-to-end API tests: journey, validation, RBAC, privacy controls, upload hardening, failure modes."""
from __future__ import annotations

import io
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings


@pytest.fixture(scope="module")
def client():
    shutil.rmtree(settings.storage_dir, ignore_errors=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    from app.db import Base, engine
    Base.metadata.drop_all(engine)
    from app.main import app
    with TestClient(app) as c:
        yield c


def new_session(c, lang="en", partner=None):
    r = c.post("/api/advisor/sessions", json={"language": lang, "partner_code": partner})
    assert r.status_code == 200
    j = r.json()
    return j["session_id"], {"X-Session-Token": j["session_token"]}


def say(c, sid, H, **body):
    r = c.post(f"/api/advisor/sessions/{sid}/messages", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def login_customer(c, mobile="9876543210", name="Test Owner"):
    o = c.post("/api/auth/otp/request", json={"mobile": mobile}).json()
    v = c.post("/api/auth/otp/verify", json={"mobile": mobile, "otp": o["demo_otp"], "name": name})
    assert v.status_code == 200
    return {"Authorization": "Bearer " + v.json()["token"]}


_STAFF_TOKENS: dict[str, str] = {}


def login_staff(c, email):
    """Staff logins are rate-limited per client (10 per 5 min), so tests reuse one token per account."""
    if email not in _STAFF_TOKENS:
        r = c.post("/api/auth/staff/login", json={"email": email, "password": settings.demo_staff_password})
        assert r.status_code == 200, r.text
        _STAFF_TOKENS[email] = r.json()["token"]
    return {"Authorization": "Bearer " + _STAFF_TOKENS[email]}


def recommended(c, text="I run a CA firm in Delhi, 12 employees, one office, GST registered"):
    sid, H = new_session(c)
    r = say(c, sid, H, text=text)
    if r["state"] != "recommended":
        r = say(c, sid, H, action="show_plan")
    assert r["state"] == "recommended", r
    return sid, H, r["recommendation"]


# ------------------------------------------------------------------ advisor
def test_health(client):
    j = client.get("/api/health").json()
    assert j["status"] == "ok" and j["llm_provider"] == "offline" and j["propensity_model"] is True
    assert j["ocr_engine"] is True                          # Tesseract present in the test environment


def test_one_message_profile_needs_at_most_one_more_turn(client):
    sid, H = new_session(client)
    r = say(client, sid, H, text="We are a CA firm in Delhi with 12 employees in one office, GST registered, need email and data backup")
    assert r["state"] == "recommended"
    ids = [i["product_id"] for i in r["recommendation"]["items"]]
    assert "P16" in ids and "P17" in ids


def test_slot_filling_order_and_chips(client):
    sid, H = new_session(client)
    r = say(client, sid, H, text="salon")
    assert r["expecting"] == "city" and r["chips"]
    r = say(client, sid, H, text="Pune")
    assert r["expecting"] == "employees"
    r = say(client, sid, H, text="2-5")
    assert r["expecting"] == "sites"
    r = say(client, sid, H, text="1")
    assert r["expecting"] == "gstin"
    r = say(client, sid, H, text="No GSTIN")
    assert r["expecting"] == "needs" and r["multi_select"]
    r = say(client, sid, H, needs=["billing_pos"], action="show_plan")
    assert r["state"] == "recommended"
    assert all(not i["requires_gstin"] for i in r["recommendation"]["items"])


def test_hindi_conversation(client):
    sid, H = new_session(client, "hi")
    r = say(client, sid, H, text="मेरी जयपुर में दवाई की दुकान है, 3 लोग काम करते हैं, जीएसटी नहीं है, एक दुकान")
    assert r["language"] == "hi"
    assert any("ऀ" <= ch <= "ॿ" for m in r["messages"] for ch in m["text"])


def test_unserviceable_city_routes_to_partner(client):
    sid, H = new_session(client)
    r = say(client, sid, H, text="kirana store in Basti, 2 people, 1 shop, no GST")
    assert r["state"] == "not_serviceable" and r.get("not_serviceable")


def test_escalation_is_always_available(client):
    sid, H = new_session(client)
    r = say(client, sid, H, text="I want to talk to a human")
    assert r["state"] == "escalated" and r.get("escalated")


def test_faq_answers_from_catalogue(client):
    sid, H = new_session(client)
    r = say(client, sid, H, text="what is Managed SD-WAN?")
    assert any("Managed SD-WAN" in m["text"] for m in r["messages"])


def test_session_token_required(client):
    sid, H = new_session(client)
    r = client.post(f"/api/advisor/sessions/{sid}/messages", json={"text": "hi"}, headers={"X-Session-Token": "wrong"})
    assert r.status_code == 404


def test_profile_form_alternative(client):
    sid, H = new_session(client)
    r = client.patch(f"/api/advisor/sessions/{sid}/profile", headers=H, json={
        "business_type": "Gym chain", "city": "Hyderabad", "employees": 40, "sites": 4, "has_gstin": True})
    assert r.status_code == 200 and r.json()["recommendation"]["status"] == "ok"
    r = client.patch(f"/api/advisor/sessions/{sid}/profile", headers=H, json={"employees": -3})
    assert r.status_code == 422


# ------------------------------------------------------------------ quote integrity
def test_quote_preview_validates_bundle(client):
    sid, H, rec = recommended(client)
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]]
    ok = client.post("/api/quotes/preview", json={"session_id": sid, "items": items}, headers=H)
    assert ok.status_code == 200 and ok.json()["monthly_subtotal"] == rec["quote"]["monthly_subtotal"]
    bad = client.post("/api/quotes/preview", json={"session_id": sid, "items": [{"product_id": "P09", "qty": 1}]}, headers=H)
    assert bad.status_code == 422 and bad.json()["detail"]["messages"]
    neg = client.post("/api/quotes/preview", json={"session_id": sid, "items": [{"product_id": "P01", "qty": -1}]}, headers=H)
    assert neg.status_code == 422


def test_checkout_recomputes_price_server_side(client):
    sid, H, rec = recommended(client)
    A = {**login_customer(client), **H}
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]]
    r = client.post("/api/checkout", headers=A, json={"session_id": sid, "items": items, "contact_name": "Owner",
                    "install_address": "12 MG Road, Delhi", "pincode": "110001", "accept_terms": True})
    assert r.status_code == 200
    assert r.json()["quote"]["monthly_subtotal"] == rec["quote"]["monthly_subtotal"]


def test_checkout_requires_login_and_terms(client):
    sid, H, rec = recommended(client)
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]]
    body = {"session_id": sid, "items": items, "contact_name": "Owner", "install_address": "12 MG Road, Delhi",
            "pincode": "110001", "accept_terms": False}
    assert client.post("/api/checkout", headers=H, json=body).status_code == 401
    assert client.post("/api/checkout", headers={**H, **login_customer(client)}, json=body).status_code == 422


# ------------------------------------------------------------------ order + KYC journey
@pytest.fixture(scope="module")
def order(client):
    sid, H, rec = recommended(client)
    A = {**login_customer(client, "9988776655", "Pooja Agarwal"), **H}
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]]
    r = client.post("/api/checkout", headers=A, json={"session_id": sid, "items": items, "contact_name": "Pooja",
                    "install_address": "Shop 216 Nehru Nagar", "pincode": "530001", "accept_terms": True,
                    "simulate_payment_failure": True})
    assert r.json()["payment_status"] == "failed"
    return r.json()["order_id"], A


def test_payment_retry(client, order):
    oid, A = order
    r = client.post(f"/api/orders/{oid}/payment", headers=A, json={"method": "upi_autopay"})
    assert r.json()["payment_status"] in ("paid", "mandate_set")
    assert client.post(f"/api/orders/{oid}/payment", headers=A, json={"method": "card"}).status_code == 409


def test_kyc_requires_consent(client, order):
    oid, A = order
    r = client.post("/api/kyc/cases", headers=A, json={"order_id": oid, "declaration": {"business_name": "Star", "signatory_name": "Pooja"}})
    assert r.status_code == 403
    assert client.post("/api/consent", headers=A, json={"purposes": {"kyc_verification": True, "marketing": False},
                                                        "notice_version": "old"}).status_code == 409


@pytest.fixture(scope="module")
def case(client, order):
    oid, A = order
    client.post("/api/consent", headers=A, json={"purposes": {"kyc_verification": True, "marketing": False}})
    r = client.post("/api/kyc/cases", headers=A, json={"order_id": oid, "declaration": {"business_name": "Star Electronics", "signatory_name": "Pooja Agarwal"}})
    assert r.status_code == 200
    return r.json()["case_id"], oid, A


def test_specimen_clean_applicant_verifies_and_installation_can_proceed(client, case):
    cid, oid, A = case
    client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K12"})
    r = client.post(f"/api/kyc/cases/{cid}/evaluate", headers=A).json()
    assert r["decision"] == "verified"
    gst = next(d for d in r["documents"] if d["slot"] == "gst_certificate")
    assert "*" in gst["fields"]["gstin"]["value"]          # identifiers are masked in API responses
    t = client.post(f"/api/orders/{oid}/advance", headers=A).json()
    assert any(s["stage"] == "installation_scheduled" and s["status"] == "done" for s in t["tracker"]["steps"])


@pytest.mark.parametrize("applicant,decision,code", [
    ("K11", "action_required", "ADDRESS_PROOF_TOO_OLD"),
    ("K04", "action_required", "UNREADABLE_DOCUMENT"),
    ("K06", "manual_review", "GSTIN_MISMATCH"),
    ("K07", "manual_review", "LEGAL_NAME_MISMATCH"),
    ("K10", "manual_review", "SIGNATORY_MISMATCH"),
    ("K01", "manual_review", "GSTIN_NOT_ACTIVE"),
])
def test_specimen_problem_applicants(client, case, applicant, decision, code):
    cid, oid, A = case
    client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": applicant})
    r = client.post(f"/api/kyc/cases/{cid}/evaluate", headers=A).json()
    assert r["decision"] == decision
    assert code in [f["code"] for f in r["findings"]]


def test_lead_search_and_follow_up_history(client):
    S = login_staff(client, "sales@accel.demo")
    first = client.get("/api/backoffice/leads?limit=1", headers=S).json()["leads"][0]
    hit = client.get(f"/api/backoffice/leads?q={first['ref'].lower()}", headers=S).json()
    assert hit["total"] == 1 and hit["leads"][0]["id"] == first["id"]
    city = first["city"]
    by_city = client.get(f"/api/backoffice/leads?q={city}", headers=S).json()
    assert by_city["total"] >= 1 and all(city.lower() in (l["city"] or "").lower() or city.lower() in (l["business_type"] or "").lower()
                                         or city.lower() in (l["business_name"] or "").lower() for l in by_city["leads"])
    assert client.get("/api/backoffice/leads?q=zzzz-no-such-lead", headers=S).json()["total"] == 0
    r = client.post(f"/api/backoffice/leads/{first['id']}/assign", headers=S,
                    json={"status": "contacted", "assigned_to": "Sales demo", "note": "Called, asked for a quote; mobile 9876543210"})
    assert r.status_code == 200, r.text
    act = r.json()["activity"]
    assert act[0]["status"] == "contacted" and act[0]["by"] and "9876543210" not in act[0]["note"]      # number masked
    detail = client.get(f"/api/backoffice/leads/{first['id']}", headers=S).json()
    assert detail["status"] == "contacted" and detail["activity"][0]["note"] == act[0]["note"]
    assert client.post(f"/api/backoffice/leads/{first['id']}/assign", headers=S, json={"note": "x" * 301}).status_code == 422
    P = login_staff(client, "partner@accel.demo")
    others = [l for l in client.get("/api/backoffice/leads?limit=200", headers=S).json()["leads"] if l["partner_code"] != "PTN-LKO-01"]
    if others:      # a partner cannot read or annotate another partner's lead
        assert client.get(f"/api/backoffice/leads/{others[0]['id']}", headers=P).status_code == 404
        assert client.post(f"/api/backoffice/leads/{others[0]['id']}/assign", headers=P, json={"note": "hi"}).status_code == 404


def test_missing_ocr_engine_keeps_documents_and_sends_to_review(client, case, monkeypatch):
    """No Tesseract (or a crash): uploads still succeed and a person reads them - no 500, no false 're-upload'."""
    import pytesseract

    from app.kyc import document_ai

    def no_engine(*_a, **_k):
        raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(document_ai, "_ocr_lines", no_engine)
    cid, oid, A = case
    r = client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K03"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/kyc/cases/{cid}/evaluate", headers=A).json()
    assert r["decision"] == "manual_review"
    ocr = [f for f in r["findings"] if f["code"] == "OCR_UNAVAILABLE"]
    assert ocr and all(f["severity"] == "review" for f in ocr)
    assert "check by hand" in ocr[0]["text"]
    assert not any(f["code"] in ("UNREADABLE_DOCUMENT", "FIELD_MISSING") for f in r["findings"])


def test_tracker_shows_customers_plain_text_not_codes(client, case):
    import re
    cid, oid, A = case
    o = client.get(f"/api/orders/{oid}", headers=A).json()
    notes = [b["note"] or "" for b in o["tracker"]["blockers"] if b["stage"] in ("kyc_review", "kyc_action_required")]
    assert notes, o["tracker"]["blockers"]
    assert not any(re.search(r"[A-Z]{3,}_[A-Z_]{3,}", n) for n in notes), notes      # e.g. GSTIN_MISMATCH stays staff-side
    hi = client.get(f"/api/orders/{oid}?lang=hi", headers=A).json()
    assert any("बिंदु" in (b["note"] or "") for b in hi["tracker"]["blockers"])


def test_document_access_control(client, case):
    cid, oid, A = case
    doc = client.get(f"/api/kyc/cases/{cid}", headers=A).json()["documents"][0]
    other = login_customer(client, "9123456780")
    assert client.get(f"/api/kyc/cases/{cid}", headers=other).status_code == 404
    assert client.get(f"/api/kyc/cases/{cid}/documents/{doc['id']}/image", headers=other).status_code == 404
    sales = login_staff(client, "sales@accel.demo")
    assert client.get(f"/api/kyc/cases/{cid}/documents/{doc['id']}/image", headers=sales).status_code == 403
    kyc = login_staff(client, "kyc@accel.demo")
    assert client.get(f"/api/kyc/cases/{cid}/documents/{doc['id']}/image", headers=kyc).status_code == 200
    assert client.get(f"/api/kyc/cases/{cid}/documents/{doc['id']}/image").status_code == 401


def test_documents_encrypted_at_rest(client, case):
    for f in (settings.storage_dir / "docs").glob("*.bin"):
        head = f.read_bytes()[:16]
        assert not head.startswith(b"\x89PNG")


def _png(w=800, h=600):
    b = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(b, "PNG")
    return b.getvalue()


def test_upload_hardening(client, case):
    cid, oid, A = case
    url = f"/api/kyc/cases/{cid}/documents"
    r = client.post(url, headers=A, data={"slot": "address_proof"}, files={"file": ("x.exe", b"MZ\x90\x00binary", "application/octet-stream")})
    assert r.status_code == 415
    r = client.post(url, headers=A, data={"slot": "bogus"}, files={"file": ("a.png", _png(), "image/png")})
    assert r.status_code == 422
    big = b"\x89PNG\r\n\x1a\n" + b"0" * int(settings.max_upload_mb * 1024 * 1024 + 10)
    assert client.post(url, headers=A, data={"slot": "address_proof"}, files={"file": ("a.png", big, "image/png")}).status_code == 413
    r = client.post(url, headers=A, data={"slot": "address_proof"}, files={"file": ("a.png", _png(), "image/png")})
    assert r.status_code == 200            # a blank page is accepted as an upload but cannot pass KYC


def test_reviewer_decision_and_queue(client, case):
    cid, oid, A = case
    client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K07"})
    client.post(f"/api/kyc/cases/{cid}/evaluate", headers=A)
    kyc = login_staff(client, "kyc@accel.demo")
    q = client.get("/api/backoffice/kyc-queue", headers=kyc).json()["cases"]
    assert any(x["case_id"] == cid for x in q)
    r = client.post(f"/api/backoffice/kyc/{cid}/decision", headers=kyc, json={"decision": "request_resubmission", "note": "Legal name differs from registry"})
    assert r.json()["status"] == "action_required"


def test_consent_withdrawal_deletes_documents(client):
    sid, H, rec = recommended(client)
    A = {**login_customer(client, "9000000001"), **H}
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]]
    oid = client.post("/api/checkout", headers=A, json={"session_id": sid, "items": items, "contact_name": "X Y",
                      "install_address": "1 Some Road, Delhi", "pincode": "110001", "accept_terms": True}).json()["order_id"]
    client.post("/api/consent", headers=A, json={"purposes": {"kyc_verification": True}})
    cid = client.post("/api/kyc/cases", headers=A, json={"order_id": oid, "declaration": {"business_name": "AB", "signatory_name": "CD"}}).json()["case_id"]
    client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K03"})
    keys = [d["id"] for d in client.get(f"/api/kyc/cases/{cid}", headers=A).json()["documents"]]
    assert keys
    r = client.post("/api/consent/withdraw", headers=A, json={"purpose": "kyc_verification"}).json()
    assert "deleted" in r["effect"]
    assert client.get(f"/api/kyc/cases/{cid}", headers=A).json()["documents"] == []
    assert client.get(f"/api/orders/{oid}", headers=A).json()["status"] == "cancelled_by_customer"


def test_privacy_summary_is_masked(client, case):
    cid, oid, A = case
    s = client.get("/api/privacy/summary", headers=A).json()
    assert "*" in s["customer"]["mobile"]


# ------------------------------------------------------------------ back-office RBAC
def test_backoffice_roles(client):
    cust = login_customer(client, "9000000002")
    assert client.get("/api/backoffice/overview", headers=cust).status_code == 403
    kyc = login_staff(client, "kyc@accel.demo")
    assert client.get("/api/backoffice/leads", headers=kyc).status_code == 403
    assert client.get("/api/backoffice/audit", headers=kyc).status_code == 403
    admin = login_staff(client, "admin@accel.demo")
    ov = client.get("/api/backoffice/overview", headers=admin).json()
    assert ov["baseline"]["overall"]["leads"] == 5000
    leads = client.get("/api/backoffice/leads?limit=5", headers=admin).json()
    assert leads["total"] > 0 and leads["leads"][0]["reasons"]
    partner = login_staff(client, "partner@accel.demo")
    pl = client.get("/api/backoffice/leads?limit=200", headers=partner).json()
    assert all(l["partner_code"] == "PTN-LKO-01" for l in pl["leads"])


def test_audit_log_has_no_raw_identifiers(client):
    admin = login_staff(client, "admin@accel.demo")
    import json
    import re
    blob = json.dumps(client.get("/api/backoffice/audit?limit=500", headers=admin).json())
    assert not re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b", blob)
    assert not re.search(r"(?<!\d)[6-9]\d{9}(?!\d)", blob)


def test_jwt_tampering_rejected(client):
    tok = login_customer(client, "9000000003")["Authorization"].split()[1]
    head, body, sig = tok.split(".")
    bad = f"{head}.{body}.{sig[::-1]}"
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_otp_rate_limit(client):
    codes = [client.post("/api/auth/otp/request", json={"mobile": "9555555555"}).status_code for _ in range(7)]
    assert 429 in codes


def test_registry_lookup_minimal_response(client):
    r = client.get("/api/registry/gstin/27XUIXG0767D1ZP").json()
    assert r["found"] and r["status"] == "Active" and "*" in r["gstin"] and "principal_place_of_business" not in r
    assert client.get("/api/registry/gstin/27XUIXG0767D1ZQ").status_code == 422   # checksum failure
    assert "source" in r and "MOCK" in r["source"]


# ------------------------------------------------------------------ regressions added during UI integration
def test_team_size_phrasings_and_generic_type_guard(client):
    sid, H = new_session(client)
    r = say(client, sid, H, text="We run a dental clinic in Kolkata, 5 of us")
    assert r["profile"]["business_type"] == "Dental clinic" and r["profile"]["employees"] == 5
    r = say(client, sid, H, text="one clinic")              # answering 'sites' must not downgrade the type
    assert r["profile"]["business_type"] == "Dental clinic" and r["profile"]["sites"] == 1


def test_branches_do_not_turn_a_ca_firm_into_a_retail_chain(client):
    sid, H = new_session(client)
    say(client, sid, H, text="I run a CA firm in Pune")
    r = say(client, sid, H, text="we have 3 branches and 20 staff")
    assert r["profile"]["business_type"] == "CA firm" and r["profile"]["sites"] == 3
    assert r["profile"]["segment"] == "multi"


def test_language_switch_mid_conversation(client):
    sid, H = new_session(client, lang="en")
    r = say(client, sid, H, text="kirana store", language="hi")
    assert r["language"] == "hi"
    assert any("ऀ" <= ch <= "ॿ" for ch in r["messages"][-1]["text"])


def test_form_profile_verifies_gstin_against_registry(client):
    sid, H = new_session(client)
    bad = client.patch(f"/api/advisor/sessions/{sid}/profile", headers=H,
                       json={"business_type": "Salon", "city": "Jaipur", "employees": 3, "sites": 1, "gstin": "08YKZXS5189L1Z1"})
    assert bad.status_code == 422 and bad.json()["detail"]["field"] == "gstin"
    ok = client.patch(f"/api/advisor/sessions/{sid}/profile", headers=H,
                      json={"business_type": "Salon", "city": "Jaipur", "employees": 3, "sites": 1, "gstin": "08YKZXS5189L1ZO"})
    assert ok.status_code == 200
    assert ok.json()["profile"]["gstin_status"] in ("Active", "Cancelled", "Suspended")
    assert ok.json()["profile"]["has_gstin"] is True


def test_callback_is_one_request_with_encrypted_number_and_audited_reveal(client):
    sid, H = new_session(client)
    say(client, sid, H, text="I want to talk to a person")             # chat escalation opens one request
    r = client.post(f"/api/advisor/sessions/{sid}/escalate", headers=H,
                    json={"preferred_time": "evening", "note": "call after 6", "mobile": "9811122233"})
    assert r.status_code == 200 and r.json()["contact"].endswith("2233") and "98111" not in r.json()["contact"]
    from app.db import SessionLocal
    from app.models import AuditEvent, Escalation
    with SessionLocal() as db:
        rows = db.query(Escalation).filter(Escalation.session_id == sid).all()
        assert len(rows) == 1                                           # updated, not duplicated
        assert rows[0].contact_enc and "9811122233" not in rows[0].contact_enc
    sales = login_staff(client, "sales@accel.demo")
    lst = client.get("/api/backoffice/escalations", headers=sales).json()["escalations"]
    row = next(e for e in lst if e["id"] == rows[0].id)
    assert row["contact"] and "9811122233" not in str(lst)
    kyc = login_staff(client, "kyc@accel.demo")
    assert client.post(f"/api/backoffice/escalations/{row['id']}/reveal", headers=kyc).status_code == 403
    rev = client.post(f"/api/backoffice/escalations/{row['id']}/reveal", headers=sales)
    assert rev.status_code == 200 and rev.json()["mobile"] == "9811122233"
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter(AuditEvent.action == "escalation.contact_revealed").all()
        assert ev and all("9811122233" not in str(e.details) for e in ev)
    up = client.post(f"/api/backoffice/escalations/{row['id']}", headers=sales, json={"status": "resolved"})
    assert up.status_code == 200 and up.json()["status"] == "resolved"


def test_customer_case_view_masks_declaration(client, case):
    cid, _, CH = case
    v = client.get(f"/api/kyc/cases/{cid}", headers=CH).json()
    g = v["declaration"]["gstin"]
    assert g is None or "*" in g


def test_retention_dates_follow_the_notice_and_purge_deletes(client):
    """Regression: delete_after used to be recorded but never acted on, and did not match the consent notice."""
    from datetime import datetime, timedelta, timezone
    from app.db import SessionLocal
    from app.kyc import storage
    from app.models import KycDocument
    from app.retention import purge_expired
    sid, H, rec = recommended(client)
    A = login_customer(client, mobile="9877711122")
    o = client.post("/api/checkout", headers={**H, **A}, json={
        "session_id": sid, "items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]],
        "contact_name": "Retention Test", "install_address": "1 Test Road, Delhi", "pincode": "110001", "accept_terms": True}).json()
    client.post("/api/consent", headers=A, json={"purposes": {"kyc_verification": True}})
    cid = client.post("/api/kyc/cases", headers=A, json={"order_id": o["order_id"], "declaration": {
        "business_name": "Retention Test", "signatory_name": "Retention Test"}}).json()["case_id"]
    client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K08"})
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        docs = db.query(KycDocument).filter(KycDocument.case_id == cid, KycDocument.active.is_(True)).all()
        assert docs and all(d.delete_after for d in docs)
        backstop_days = (docs[0].delete_after.replace(tzinfo=timezone.utc) - now).days
        assert 178 <= backstop_days <= 180                              # abandoned-application backstop
    # a reviewer rejection shortens retention to 30 days
    kyc = login_staff(client, "kyc@accel.demo")
    client.post(f"/api/kyc/cases/{cid}/evaluate", headers=A)
    assert client.post(f"/api/backoffice/kyc/{cid}/decision", headers=kyc,
                       json={"decision": "reject", "note": "test rejection"}).status_code == 200
    with SessionLocal() as db:
        docs = db.query(KycDocument).filter(KycDocument.case_id == cid, KycDocument.active.is_(True)).all()
        assert all(28 <= (d.delete_after.replace(tzinfo=timezone.utc) - now).days <= 30 for d in docs)
        keys = [d.storage_key for d in docs]
        # time passes: the purge removes the files and deactivates the rows
        assert purge_expired(db, now=now + timedelta(days=31)) >= len(docs)
    with SessionLocal() as db:
        assert db.query(KycDocument).filter(KycDocument.case_id == cid, KycDocument.active.is_(True)).count() == 0
    for k in keys:
        assert not (settings.storage_dir / "docs" / f"{k}.bin").exists()
    admin = login_staff(client, "admin@accel.demo")
    assert client.post("/api/backoffice/retention/run", headers=admin).status_code == 200
    assert client.post("/api/backoffice/retention/run", headers=kyc).status_code == 403


def test_activation_sets_180_day_retention(client):
    from datetime import datetime, timezone
    from app.db import SessionLocal
    from app.models import KycDocument
    sid, H, rec = recommended(client)
    A = login_customer(client, mobile="9877711133")
    o = client.post("/api/checkout", headers={**H, **A}, json={
        "session_id": sid, "items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]],
        "contact_name": "Activation Test", "install_address": "2 Test Road, Delhi", "pincode": "110001", "accept_terms": True}).json()
    oid = o["order_id"]
    client.post("/api/consent", headers=A, json={"purposes": {"kyc_verification": True}})
    cid = client.post("/api/kyc/cases", headers=A, json={"order_id": oid, "declaration": {
        "business_name": "Activation Test", "signatory_name": "Activation Test"}}).json()["case_id"]
    client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K09"})
    assert client.post(f"/api/kyc/cases/{cid}/evaluate", headers=A).json()["decision"] == "verified"
    for _ in range(8):
        r = client.post(f"/api/orders/{oid}/advance", headers=A)
        assert r.status_code == 200, r.text
        if r.json()["status"] == "active":
            break
    assert r.json()["status"] == "active"
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        docs = db.query(KycDocument).filter(KycDocument.case_id == cid, KycDocument.active.is_(True)).all()
        assert docs and all(178 <= (d.delete_after.replace(tzinfo=timezone.utc) - now).days <= 180 for d in docs)


def test_applicants_never_see_staff_notes_or_generator_artefacts(client):
    """Regression: applicants were shown reviewer-facing resolution notes and the 'major activity' generator artefact."""
    sid, H, rec = recommended(client)
    A = login_customer(client, mobile="9877711144")
    o = client.post("/api/checkout", headers={**H, **A}, json={
        "session_id": sid, "items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["items"]],
        "contact_name": "Audience Test", "install_address": "3 Test Road, Delhi", "pincode": "110001", "accept_terms": True}).json()
    client.post("/api/consent", headers=A, json={"purposes": {"kyc_verification": True}})
    cid = client.post("/api/kyc/cases", headers=A, json={"order_id": o["order_id"], "declaration": {
        "business_name": "Audience Test", "signatory_name": "Audience Test"}}).json()["case_id"]
    client.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K05"})
    mine = client.post(f"/api/kyc/cases/{cid}/evaluate", headers=A).json()
    assert all(f["resolution"] is None for f in mine["findings"])
    assert all(f["code"] != "ACTIVITY_DIFFERS" for f in mine["findings"])
    staff_view = client.get(f"/api/backoffice/kyc/{cid}", headers=login_staff(client, "kyc@accel.demo")).json()
    assert any(f["resolution"] for f in staff_view["findings"])          # reviewers still get the notes
