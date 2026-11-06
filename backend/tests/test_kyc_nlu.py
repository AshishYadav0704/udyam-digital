"""Identifier validators, KYC rules, NLU extraction and LLM-output guards."""
from __future__ import annotations

from datetime import date

import pytest

from app.advisor.llm import explanation_is_grounded, normalise_llm_extraction
from app.advisor.nlu import extract
from app.config import settings
from app.domain.identifiers import (gstin_checksum_ok, mask_gstin, normalise_gstin, normalise_udyam, scrub,
                                    validate_gstin, validate_udyam)
from app.kyc.checks import Declaration, evaluate, ocr_variant_of
from app.kyc.document_ai import Extraction, Field, Quality
from app.kyc.registry import MockRegistry, UnavailableRegistry


# ------------------------------------------------------------------ identifiers
def test_gstin_rules():
    assert validate_gstin("27XUIXG0767D1ZP") == []
    assert "GSTIN_CHECKSUM" in validate_gstin("08YKZXS8189L1Z0")      # K06 certificate value
    assert validate_gstin("27XUIXG0767") == ["GSTIN_FORMAT"]


def test_synthetic_pan_x_only_in_synthetic_mode(monkeypatch):
    monkeypatch.setattr(settings, "synthetic_identifier_mode", False)
    assert "GSTIN_PAN_HOLDER_TYPE" in validate_gstin("27XUIXG0767D1ZP")
    assert "UDYAM_DISTRICT_CODE" in validate_udyam("UDYAM-MH-00-9516696")
    monkeypatch.setattr(settings, "synthetic_identifier_mode", True)
    assert validate_udyam("UDYAM-MH-00-9516696") == []


def test_ocr_repair_never_invents_a_valid_gstin():
    assert normalise_gstin("27XUIXGO767D1ZP") == "27XUIXG0767D1ZP"      # letter O in a digit position
    assert not gstin_checksum_ok(normalise_gstin("08YKZXS8189L1Z0"))    # genuinely wrong stays wrong
    assert normalise_udyam("UDYAM-MH- 00-6131836") == "UDYAM-MH-00-6131836"


def test_confusable_match():
    assert ocr_variant_of("27QHIXK0658U1ZL", "27QHJXK0658U1ZL")          # I/J look-alike
    assert not ocr_variant_of("08YKZXS8189L1Z0", "08YKZXS5189L1ZO")      # 8 vs 5 is not a look-alike


def test_masking_and_scrub():
    assert mask_gstin("27XUIXG0767D1ZP") == "27**********1ZP"
    s = scrub("call 9876543210 about 27XUIXG0767D1ZP and UDYAM-MH-00-9516696")
    assert "9876543210" not in s and "27XUIXG0767D1ZP" not in s and "9516696" not in s


# ------------------------------------------------------------------ KYC rules on synthetic extractions
def ex(doc_type, **fields):
    return Extraction(doc_type, 1.0, Quality(1240, 1754, 900.0, 0.0, False, False),
                      {k: Field(v, 0.95, True, 1.0) for k, v in fields.items()}, 0.0, 3, "")


REG = MockRegistry()
GOOD = {
    "gst_certificate": ex("gst_certificate", gstin="27XUIXG0767D1ZP", legal_name="Joseph Singh (Prop. Ganesh Woodcraft)",
                          trade_name="Ganesh Woodcraft", address="Shop/Unit 80, Civil Lines, Nagpur, Maharashtra - 411231",
                          date_of_liability="2020-02-10"),
    "udyam_certificate": ex("udyam_certificate", udyam_number="UDYAM-MH-00-9516696", enterprise_name="Ganesh Woodcraft",
                            major_activity="Manufacturing", city="Nagpur", state="Maharashtra"),
    "address_proof": ex("address_proof", billed_to="Ganesh Woodcraft", bill_date="2026-05-30",
                        supply_address="Shop/Unit 80, Civil Lines, Nagpur, Maharashtra - 411231"),
    "signatory_id": ex("signatory_id", name="Joseph Singh", business="Ganesh Woodcraft", valid_till="2028-07-04"),
}
DECL = Declaration("Ganesh Woodcraft", "Joseph Singh", "27XUIXG0767D1ZP", "UDYAM-MH-00-9516696", "Nagpur", "Maharashtra")


def codes(r):
    return {f.code for f in r.findings}


def test_clean_case_verifies():
    assert evaluate(DECL, dict(GOOD), REG).decision == "verified"


@pytest.mark.parametrize("bill_date,expected", [("2026-04-16", "verified"), ("2026-04-15", "action_required"),
                                                ("2026-07-16", "manual_review")])
def test_address_proof_age_boundary(bill_date, expected):
    docs = dict(GOOD)
    docs["address_proof"] = ex("address_proof", billed_to="Ganesh Woodcraft", bill_date=bill_date,
                               supply_address="Shop/Unit 80, Civil Lines, Nagpur, Maharashtra - 411231")
    r = evaluate(DECL, docs, REG, today=date(2026, 7, 15))
    assert r.decision == expected          # 90 days before 15 Jul 2026 is 16 Apr 2026


def test_missing_udyam_certificate_resolved_by_registry():
    docs = dict(GOOD)
    docs["udyam_certificate"] = None
    r = evaluate(DECL, docs, REG)
    assert r.decision == "verified" and "MISSING_DOCUMENT" in codes(r)


def test_missing_signatory_id_requires_action():
    docs = dict(GOOD)
    docs["signatory_id"] = None
    assert evaluate(DECL, docs, REG).decision == "action_required"


def test_blurry_document():
    docs = dict(GOOD)
    docs["gst_certificate"] = Extraction("gst_certificate", 0.5, Quality(1240, 1754, 2.0, 0.0, True, False), {}, 0.0, 3, "")
    r = evaluate(DECL, docs, REG)
    assert "UNREADABLE_DOCUMENT" in codes(r) and r.decision == "action_required"


def test_wrong_document_in_slot():
    docs = dict(GOOD)
    docs["address_proof"] = GOOD["signatory_id"]
    assert "WRONG_DOCUMENT_TYPE" in codes(evaluate(DECL, docs, REG))


def test_expired_signatory_id():
    docs = dict(GOOD)
    docs["signatory_id"] = ex("signatory_id", name="Joseph Singh", business="Ganesh Woodcraft", valid_till="2026-01-01")
    assert "SIGNATORY_ID_EXPIRED" in codes(evaluate(DECL, docs, REG))


def test_duplicate_upload_flagged():
    r = evaluate(DECL, dict(GOOD), REG, duplicate_hashes={"abc": ["address_proof", "signatory_id"]})
    assert "DUPLICATE_DOCUMENT" in codes(r) and r.decision == "manual_review"


def test_registry_outage_routes_to_review_not_rejection():
    r = evaluate(DECL, dict(GOOD), UnavailableRegistry())
    assert "REGISTRY_UNAVAILABLE" in codes(r) and r.decision == "manual_review"


def test_no_gst_no_udyam_path():
    decl = Declaration("Tiny Kirana", "Ramesh Kumar")
    docs = {"address_proof": ex("address_proof", billed_to="Tiny Kirana", bill_date="2026-07-01", supply_address="1 Main Road"),
            "signatory_id": ex("signatory_id", name="Ramesh Kumar", business="Tiny Kirana", valid_till="2030-01-01")}
    r = evaluate(decl, docs, REG)
    assert r.decision == "verified" and "NO_BUSINESS_REGISTRATION" in codes(r)


# ------------------------------------------------------------------ NLU
@pytest.mark.parametrize("text,expect", [
    ("I run a kirana store in Lucknow with 2 staff, no GST", {"business_type": "Kirana store", "city": "Lucknow", "employees": 2, "has_gstin": False}),
    ("Restaurant chain with 6 outlets in Bengaluru, about 60 people", {"business_type": "Restaurant chain", "sites": 6, "employees": 60}),
    ("मेरी जयपुर में दवाई की दुकान है, 3 लोग काम करते हैं, जीएसटी नहीं है", {"business_type": "Pharmacy", "city": "Jaipur", "employees": 3, "has_gstin": False}),
    ("Hum Patna mein coaching centre chalate hain, 8 log hain", {"business_type": "Coaching centre", "city": "Patna", "employees": 8}),
    ("gym chain 4 branches hyderabad 30 staff", {"business_type": "Gym chain", "sites": 4, "employees": 30}),
    ("textile unit in Surat, 40 people, our GST is cancelled", {"has_gstin": True, "gstin_status": "Cancelled"}),
    ("dental clinic in Kochi, we spend Rs 2,500 a month, budget under ₹6000", {"monthly_spend": 2500, "budget": 6000}),
    ("We have 2 clinics in Chennai, 20 staff, GST registered", {"business_type": "Clinic", "sites": 2, "has_gstin": True}),
])
def test_nlu_extraction(text, expect):
    out = extract(text)
    for k, v in expect.items():
        assert out.get(k) == v, (k, out)


def test_nlu_needs_and_exclusions():
    out = extract("we don't need cctv, need whatsapp catalogue and backup internet")
    assert "cctv" in out["excluded_needs"] and {"whatsapp", "backup_internet"} <= set(out["needs"])


def test_nlu_city_substring_safety():
    assert extract("our shop is in Visakhapatnam").get("city") == "Visakhapatnam"


# ------------------------------------------------------------------ LLM guards
def test_llm_extraction_is_validated():
    out = normalise_llm_extraction({"business_type": "Spaceship yard", "employees": -4, "sites": 3, "needs": ["cctv", "free_money"],
                                    "has_gstin": "yes", "wants_human": False, "city": "Pune", "language": "en"})
    assert "business_type" not in out and "employees" not in out and out["needs"] == ["cctv"] and out["sites"] == 3


def test_llm_explanation_grounding():
    names = {"Biz Fibre 100", "Managed SD-WAN", "Cloud CCTV"}
    assert explanation_is_grounded("Biz Fibre 100 for ₹1,099 a month.", {"1099"}, {"Biz Fibre 100"}, names)
    assert not explanation_is_grounded("Biz Fibre 100 for ₹999 a month.", {"1099"}, {"Biz Fibre 100"}, names)
    assert not explanation_is_grounded("Add Managed SD-WAN too.", {"1099"}, {"Biz Fibre 100"}, names)


def test_log_scrubber_keeps_formatter_args_and_masks_pii():
    """Regression: the scrubber used to blank record.args, which crashed uvicorn's access-log formatter."""
    import logging
    from app.security import ScrubFilter
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:5000", "GET", "/api/registry/gstin/27XUIXG0767D1ZP", "1.1", 200), None)
    assert ScrubFilter().filter(rec)
    assert len(rec.args) == 5 and rec.args[4] == 200
    line = rec.getMessage()
    assert "27XUIXG0767D1ZP" not in line and "GET" in line and line.endswith("200")


def test_production_refuses_to_start_without_secrets(monkeypatch, tmp_path):
    """Fail closed: production must not run on generated development keys or synthetic-identifier mode."""
    import importlib
    import pytest
    import app.config as cfg
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    for k in ("JWT_SECRET", "DOC_ENCRYPTION_KEY", "PII_PEPPER"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="missing required secrets"):
        cfg.Settings(env="production", storage_dir=tmp_path, jwt_secret="", doc_encryption_key="", pii_pepper="")
    with pytest.raises(RuntimeError, match="SYNTHETIC_IDENTIFIER_MODE"):
        cfg.Settings(env="production", storage_dir=tmp_path, jwt_secret="a" * 48, doc_encryption_key="k", pii_pepper="p",
                     synthetic_identifier_mode=True)
    ok = cfg.Settings(env="production", storage_dir=tmp_path, jwt_secret="a" * 48, doc_encryption_key="k", pii_pepper="p",
                      synthetic_identifier_mode=False)
    assert ok.is_production and ok.pii_pepper == "p"


def test_mobile_lookup_hash_does_not_depend_on_jwt_secret():
    from app.config import settings
    from app.security import pepper_hash
    before = pepper_hash("9876543210")
    old = settings.jwt_secret
    try:
        settings.jwt_secret = "rotated-" + old
        assert pepper_hash("9876543210") == before      # rotating the JWT key must not orphan customers
    finally:
        settings.jwt_secret = old


def test_offline_extractor_held_out_accuracy_floor():
    """Regression guard on the held-out set (scripts/eval_advisor.py). Floor, not a target: the set is not tuned on."""
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("eval_advisor", root / "scripts" / "eval_advisor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import json
    cases = json.loads((root / "backend" / "tests" / "advisor_eval_set.json").read_text())["cases"]
    r = mod.evaluate(cases, mod.offline)
    assert r["field_accuracy"] >= 0.90 and r["per_field"]["city"]["accuracy"] >= 0.95
