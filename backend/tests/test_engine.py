"""Recommendation, eligibility and quote engine tests (catalogue rules are the oracle)."""
from __future__ import annotations

import csv
import random

import pytest

from app.config import settings
from app.domain.catalogue import get_catalogue
from app.domain.eligibility import hard, product_rule_violations, validate_bundle
from app.domain.pricing import InvalidBundle, build_quote
from app.domain.profile import BusinessProfile
from app.domain.recommender import bundle_from_items, recommend

CAT = get_catalogue()
ACTIVE = dict(has_gstin=True, gstin_status="Active")


def rec(**kw):
    return recommend(BusinessProfile(**kw))


def ids(items):
    return [i.product_id for i in items]


def assert_valid(r):
    """Every recommended/starter bundle and every add-on must satisfy catalogue rules."""
    assert r.status == "ok"
    for bundle in (r.recommended, r.starter):
        assert not hard(validate_bundle(bundle_from_items(bundle), r.profile, CAT)), bundle
    for a in r.add_ons:
        assert not product_rule_violations(CAT[a.product_id], r.profile)
        combo = bundle_from_items(r.recommended) + [(a.product_id, a.qty)]
        assert not hard(validate_bundle(combo, r.profile, CAT)), (a.product_id, combo)


# ----------------------------------------------------------------------------- catalogue integrity
def test_catalogue_has_25_products_and_valid_dependencies():
    assert len(CAT) == 25
    for p in CAT:
        assert p.price_min <= p.price_max
        assert all(d in CAT for d in p.requires_one_of)


def test_list_price_is_inside_catalogue_range():
    for p in CAT:
        assert p.price_min <= p.list_price() <= p.price_max


# ----------------------------------------------------------------------------- the 13 required profiles
def test_kirana_without_gstin_gets_no_gst_products():
    r = rec(business_type="Kirana store", city="Lucknow", employees=2, sites=1, has_gstin=False)
    assert_valid(r)
    assert r.profile.segment == "micro" and r.profile.city_tier == 2
    assert {"P01", "P07"} <= set(ids(r.recommended))
    for i in r.recommended + r.add_ons:
        assert not CAT[i.product_id].requires_gstin


def test_salon_whatsapp_request_needs_gstin():
    r = rec(business_type="Salon", city="Pune", employees=4, sites=1, has_gstin=False, needs=["whatsapp"])
    assert_valid(r)
    assert "P15" not in ids(r.recommended)
    assert any(e.product_id == "P15" and e.violations[0]["code"] == "GSTIN_REQUIRED" for e in r.excluded)
    r2 = rec(business_type="Salon", city="Pune", employees=4, sites=1, needs=["whatsapp"], **ACTIVE)
    assert "P15" in ids(r2.recommended)


def test_pharmacy():
    r = rec(business_type="pharmacy", city="Indore", employees=3, sites=1, has_gstin=False)
    assert_valid(r)
    assert r.profile.business_type == "Pharmacy"


def test_clinic_gets_cloud_email_and_security():
    r = rec(business_type="Dental clinic", city="Kochi", employees=9, sites=1, **ACTIVE)
    assert_valid(r)
    assert r.profile.segment == "prof"
    assert "P16" in ids(r.recommended)


def test_ca_firm():
    r = rec(business_type="CA firm", city="Delhi", employees=12, sites=1, **ACTIVE)
    assert_valid(r)
    assert ids(r.recommended)[0] in ("P01", "P02", "P03")
    assert "P16" in ids(r.recommended)


def test_coaching_centre_sms_and_telephony_respect_minimums():
    r = rec(business_type="coaching centre", city="Patna", employees=2, sites=1, needs=["cloud_telephony"], **ACTIVE)
    assert_valid(r)
    # Cloud telephony needs 3+ employees
    assert "P12" not in ids(r.recommended)
    assert any(e.product_id == "P12" and e.violations[0]["code"] == "MIN_EMPLOYEES" for e in r.excluded)


def test_restaurant_chain_multi_site_quantities_follow_sites():
    r = rec(business_type="restaurant", city="Bengaluru", employees=60, sites=6, needs=["multi_site_mgmt", "cctv"], **ACTIVE)
    assert_valid(r)
    q = {i.product_id: i.qty for i in r.recommended}
    assert r.profile.segment == "multi"
    primary = next(p for p in q if p in ("P01", "P02"))
    assert q[primary] == 6 and q["P09"] == 6 and q["P10"] == 6


def test_multi_site_retailer_without_enough_staff_cannot_get_sdwan():
    r = rec(business_type="retail chain", city="Surat", employees=8, sites=4, needs=["multi_site_mgmt"], **ACTIVE)
    assert_valid(r)
    assert "P10" not in ids(r.recommended)
    assert any(e.product_id == "P10" for e in r.excluded)


def test_auto_parts_manufacturer_gets_leased_line_and_iot():
    r = rec(business_type="Auto-parts unit", city="Pune", employees=80, sites=1, needs=["machine_iot"], **ACTIVE)
    assert_valid(r)
    assert r.profile.segment == "mfg"
    assert ids(r.recommended)[0] in ("P05", "P06")
    assert "P24" in ids(r.recommended)


def test_textile_unit_static_ip_dependency_reported():
    r = rec(business_type="textile unit", city="Surat", employees=40, sites=1, needs=["static_ip"], **ACTIVE)
    assert_valid(r)
    # P11 needs Biz Fibre (P01|P02|P03); a leased line does not satisfy the catalogue dependency
    assert "P11" not in ids(r.recommended)
    assert any(e.product_id == "P11" and e.violations[-1]["code"] == "DEPENDENCY_MISSING" for e in r.excluded)


def test_business_without_gstin_mfg_falls_back_to_fibre():
    r = rec(business_type="Packaging unit", city="Nagpur", employees=30, sites=1, has_gstin=False)
    assert_valid(r)
    assert ids(r.recommended)[0] in ("P01", "P02")
    assert any(n["code"] == "GST_BLOCKED" for n in r.notes)


@pytest.mark.parametrize("status", ["Cancelled", "Suspended"])
def test_inactive_gstin_blocks_gst_products(status):
    r = rec(business_type="CA firm", city="Mumbai", employees=10, sites=1, has_gstin=True, gstin_status=status,
            needs=["sms", "cloud_telephony", "toll_free"])
    assert_valid(r)
    for i in r.recommended + r.add_ons:
        assert not CAT[i.product_id].requires_gstin
    assert {e.product_id for e in r.excluded} >= {"P12", "P13", "P14"}


def test_two_site_professional_office_gets_two_connections():
    r = rec(business_type="Diagnostic lab", city="Chennai", employees=20, sites=2, **ACTIVE)
    assert_valid(r)
    assert r.profile.segment == "prof"
    assert r.recommended[0].qty == 2


# ----------------------------------------------------------------------------- edge cases
def test_unknown_city_is_not_serviceable():
    r = rec(business_type="Kirana store", city="Basti", employees=2, sites=1, has_gstin=False)
    assert r.status == "not_serviceable"
    assert r.recommended == []


def test_missing_information_is_reported_not_guessed():
    r = rec(business_type="Salon", city="Pune")
    assert r.status == "needs_info"
    assert r.missing == ["employees", "sites", "gstin"]


def test_tier2_never_gets_biz_fibre_1g():
    r = rec(business_type="Law office", city="Jaipur", employees=15, sites=1, needs=["high_speed"], **ACTIVE)
    assert_valid(r)
    assert "P03" not in ids(r.recommended)
    assert any(e.product_id == "P03" and e.violations[0]["code"] == "TIER_NOT_SERVED" for e in r.excluded)


def test_tier1_high_speed_gets_biz_fibre_1g_when_eligible():
    r = rec(business_type="Architecture studio", city="Mumbai", employees=12, sites=1, needs=["high_speed"], **ACTIVE)
    assert "P03" in ids(r.recommended)


def test_no_fibre_uses_airfiber_and_failover_dependency_fails():
    r = rec(business_type="Pharmacy", city="Indore", employees=3, sites=1, has_gstin=False, fibre_available=False,
            needs=["backup_internet"])
    assert_valid(r)
    assert ids(r.recommended)[0] == "P04"
    assert any(n["code"] == "FIBRE_FALLBACK" for n in r.notes)
    assert any(e.product_id == "P09" and e.violations[-1]["code"] == "DEPENDENCY_MISSING" for e in r.excluded)


def test_only_mobile_plan_is_allowed():
    r = rec(business_type="Boutique", city="Mumbai", employees=3, sites=1, has_gstin=False, only_mobile=True, mobile_lines=3)
    assert ids(r.recommended) == ["P07"] and r.recommended[0].qty == 3


def test_excluded_need_is_respected():
    r = rec(business_type="Kirana store", city="Lucknow", employees=2, sites=1, has_gstin=False, excluded_needs=["wifi_guest"])
    assert "P22" not in ids(r.recommended + r.add_ons)


def test_budget_note_when_recommended_exceeds_budget():
    r = rec(business_type="CA firm", city="Delhi", employees=12, sites=1, budget=2000, **ACTIVE)
    assert any(n["code"] == "BUDGET_OVER" for n in r.notes)


# ----------------------------------------------------------------------------- bundle validation
def profile(**kw):
    base = dict(business_type="CA firm", segment="prof", city="Delhi", city_tier=1, employees=12, sites=1, **ACTIVE)
    base.update(kw)
    return BusinessProfile(**base)


def codes(v):
    return {x.code for x in v}


def test_dependency_violation_detected():
    assert "DEPENDENCY_MISSING" in codes(validate_bundle([("P09", 1)], profile(), CAT))


def test_quantity_rules():
    p = profile(sites=2)
    assert "INVALID_QUANTITY" in codes(validate_bundle([("P01", 0)], p, CAT))
    assert "QTY_EXCEEDS_SITES" in codes(validate_bundle([("P01", 3)], p, CAT))
    assert "QTY_EXCEEDS_CONNECTED_SITES" in codes(validate_bundle([("P01", 1), ("P09", 2)], p, CAT))
    assert "UNKNOWN_PRODUCT" in codes(validate_bundle([("P99", 1)], p, CAT))
    assert "EMPTY_BUNDLE" in codes(validate_bundle([], p, CAT))


def test_sdwan_needs_three_sites():
    p = profile(employees=40, sites=2)
    assert "MIN_SITES" in codes(validate_bundle([("P01", 2), ("P10", 2)], p, CAT))


def test_invalid_bundle_cannot_be_quoted():
    with pytest.raises(InvalidBundle):
        build_quote([("P03", 1)], profile(city="Jaipur", city_tier=2), CAT)


# ----------------------------------------------------------------------------- quote arithmetic
def test_quote_totals_and_contract():
    p = profile()
    q = build_quote([("P02", 1), ("P08", 3), ("P16", 8), ("P12", 3)], p, CAT)
    expected = 1649 + 3 * 699 + 8 * 137.5 + 3 * 1250
    assert q.monthly_subtotal == pytest.approx(expected)
    assert q.monthly_gst == pytest.approx(round(expected * settings.gst_rate, 2))
    assert q.setup_subtotal == 3 * 2000
    assert q.contract_months == 12
    assert q.total_contract_value == pytest.approx(expected * 12 + 6000)


def test_contract_is_longest_minimum_term():
    p = profile(business_type="Auto-parts unit", segment="mfg", employees=60)
    q = build_quote([("P05", 1), ("P08", 2), ("P21", 1)], p, CAT)
    assert q.contract_months == 24 and q.contract_driver == "P21"


def test_install_schedule_respects_dependencies():
    p = profile(business_type="Restaurant chain", segment="multi", employees=60, sites=6)
    q = build_quote([("P01", 6), ("P10", 6)], p, CAT)
    lines = {l.product_id: l for l in q.lines}
    assert lines["P10"].install_start_day == lines["P01"].install_done_day == 5
    assert q.expected_activation_days == 5 + 14


# ----------------------------------------------------------------------------- historic data cross-check
def test_engine_flags_the_historic_rule_breaks():
    """Re-validate the 368 activated bundles: the engine must flag the same 56 the analysis found."""
    gst = {}
    with open(settings.data_dir / "mock_gstin_registry.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            gst[r["gstin"]] = r["status"]
    flagged = 0
    with open(settings.data_dir / "smb_leads.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["outcome"] != "Activated":
                continue
            p = BusinessProfile(city=r["city"], city_tier=int(r["city_tier"]), employees=int(r["employee_count"]),
                                sites=int(r["num_sites"]), has_gstin=r["has_gstin"] == "Y",
                                gstin_status=gst.get(r["gstin"]) if r["gstin"] else None)
            items = [(x.split("x")[0], int(x.split("x")[1])) for x in r["bundle_products"].split(";")]
            v = [x for x in hard(validate_bundle(items, p, CAT)) if x.code not in ("QTY_EXCEEDS_SITES", "QTY_EXCEEDS_CONNECTED_SITES")]
            flagged += bool(v)
    assert flagged == 56


# ----------------------------------------------------------------------------- fuzz: random profiles never yield invalid bundles
def test_random_profiles_always_valid():
    rng = random.Random(7)
    types = ["Kirana store", "Salon", "CA firm", "Dental clinic", "Restaurant chain", "Gym chain", "Auto-parts unit",
             "Textile unit", "Printing press", "Budget hotel group", "Coaching centre", "Pharmacy"]
    cities_ = ["Delhi", "Mumbai", "Jaipur", "Patna", "Surat", "Kochi", "Pune", "Gorakhpur"]
    needs = ["backup_internet", "cloud_email", "backup_storage", "website", "billing_pos", "endpoint_security", "firewall",
             "wifi_guest", "cctv", "machine_iot", "fleet", "cloud_telephony", "toll_free", "sms", "whatsapp", "static_ip",
             "multi_site_mgmt", "high_speed", "dedicated_line"]
    for _ in range(400):
        has = rng.random() < 0.7
        r = rec(business_type=rng.choice(types), city=rng.choice(cities_), employees=rng.randint(1, 150),
                sites=rng.randint(1, 12), has_gstin=has,
                gstin_status=rng.choice(["Active", "Active", "Cancelled", "Suspended"]) if has else None,
                fibre_available=rng.choice([None, True, False]), needs=rng.sample(needs, rng.randint(0, 5)))
        assert_valid(r)
        build_quote(bundle_from_items(r.recommended), r.profile, CAT)


def test_single_site_chain_trade_is_quoted_as_a_single_business():
    """A cafe with one outlet must not get the multi-site restaurant-chain bundle (regression)."""
    from app.domain.profile import BusinessProfile
    from app.domain.recommender import recommend, resolve_profile
    p = resolve_profile(BusinessProfile(business_type="Restaurant chain", city="Pune", employees=6, sites=1,
                                        has_gstin=True, gstin_status="Active"))
    assert (p.business_type, p.segment) == ("Restaurant / cafe", "micro")
    r = recommend(p)
    assert r.status == "ok" and all(i.qty == 1 or i.product_id in ("P07", "P08") for i in r.recommended)
    chain = resolve_profile(BusinessProfile(business_type="Restaurant / cafe", city="Pune", employees=40, sites=5))
    assert (chain.business_type, chain.segment) == ("Restaurant chain", "multi")
