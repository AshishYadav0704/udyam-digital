"""Public endpoints: health, catalogue, cities, consent notice, mock registry lookups."""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.consent import NOTICE_VERSION, notice
from app.domain import cities
from app.domain.catalogue import get_catalogue
from app.domain.identifiers import mask_gstin, normalise_gstin, normalise_udyam, validate_gstin, validate_udyam
from app.i18n import t
from app.kyc.registry import SOURCE, get_registry
from app.ml.propensity import get_model
from app.advisor.llm import get_provider
from app.security import client_key, limiter

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/health")
def health():
    p = get_provider()
    return {"status": "ok", "llm_provider": p.name if p else "offline", "propensity_model": get_model() is not None,
            "synthetic_identifier_mode": settings.synthetic_identifier_mode, "price_policy": settings.price_policy,
            "ocr_engine": _ocr_ok(), "env": settings.env}


@lru_cache(maxsize=1)
def _ocr_ok() -> bool:
    from app.kyc.document_ai import ocr_engine_available
    return ocr_engine_available()


@router.get("/catalogue/products")
def products(lang: str = "en"):
    out = []
    for p in get_catalogue():
        desc = t("hi", f"products.{p.product_id}") if lang == "hi" else p.description
        out.append({"product_id": p.product_id, "category": p.category, "name": p.name, "description": desc,
                    "unit": p.unit, "list_price": p.list_price(), "price_min": p.price_min, "price_max": p.price_max,
                    "setup_fee": p.setup_fee, "min_contract_months": p.min_contract_months,
                    "city_tiers": list(p.city_tiers), "min_employees": p.min_employees, "min_sites": p.min_sites,
                    "requires_gstin": p.requires_gstin, "requires_one_of": list(p.requires_one_of),
                    "install_days": p.install_days})
    return {"price_policy": settings.price_policy, "gst_rate": settings.gst_rate, "products": out}


@router.get("/catalogue/cities")
def city_list():
    return {"cities": cities.all_known_cities(),
            "note": "Tier from dataset for its 22 cities; HRA X/Y classification used as a proxy elsewhere (assumption)."}


@router.get("/catalogue/business-types")
def business_type_list():
    """Business types the advisor understands (same registry as the chat extractor), for the form fallback."""
    from app.domain.business_types import TYPES
    return {"business_types": [{"name": b.name, "segment": b.segment, "needs": list(b.needs)} for b in TYPES]}


@router.get("/consent/notice")
def consent_notice(lang: str = "en"):
    return {"version": NOTICE_VERSION, **notice(lang)}


@router.get("/registry/gstin/{gstin}")
def gstin_lookup(gstin: str, request: Request):
    """Pre-fill helper. Returns only what onboarding needs (data minimisation) and is rate limited."""
    limiter.check(f"gst:{client_key(request)}", limit=20, window_s=60)
    g = normalise_gstin(gstin.upper())
    problems = validate_gstin(g)
    if problems:
        raise HTTPException(422, {"valid": False, "problems": problems})
    try:
        rec = get_registry().gstin(g)
    except ConnectionError:
        raise HTTPException(503, "registry unavailable, please retry")
    if not rec:
        raise HTTPException(404, {"valid": True, "found": False})
    return {"valid": True, "found": True, "gstin": mask_gstin(g), "trade_name": rec.trade_name, "status": rec.status,
            "state": rec.state, "constitution": rec.constitution, "source": SOURCE}


@router.get("/registry/udyam/{number}")
def udyam_lookup(number: str, request: Request):
    limiter.check(f"udyam:{client_key(request)}", limit=20, window_s=60)
    u = normalise_udyam(number.upper())
    problems = validate_udyam(u)
    if problems:
        raise HTTPException(422, {"valid": False, "problems": problems})
    rec = get_registry().udyam(u)
    if not rec:
        raise HTTPException(404, {"valid": True, "found": False})
    return {"valid": True, "found": True, "enterprise_name": rec.enterprise_name, "enterprise_type": rec.enterprise_type,
            "major_activity": rec.major_activity, "city": rec.city, "state": rec.state, "source": SOURCE}
