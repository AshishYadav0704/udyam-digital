"""Catalogue-driven bundle recommendation (deterministic; no LLM involvement).

Selection logic
---------------
1. Resolve segment (business type + sites) and city tier.
2. Build the need set: segment core needs + up to two typical needs for the business type
   (from activated bundles in the data) + whatever the owner explicitly asked for.
3. Map each need to catalogue products in priority order; the first product that passes every
   catalogue rule wins. Products that fail are reported with the exact rule they fail.
4. Default quantities come from the median purchase pattern in smb_leads.csv and can be edited
   by the owner; every edit is re-validated by eligibility.validate_bundle before quoting.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from app.domain import cities
from app.domain.business_types import get_type, match_business_type, resolve_segment
from app.domain.catalogue import Catalogue, get_catalogue
from app.domain.eligibility import hard, product_rule_violations, validate_bundle
from app.domain.insights import penetration
from app.domain.profile import BusinessProfile

PRIMARY_IDS = ("P01", "P02", "P03", "P04", "P05", "P06")
LINE_IDS = ("P07", "P08")
CORE_NEEDS = {
    "micro": ("internet", "mobile_lines"),
    "prof": ("internet", "mobile_lines", "cloud_email"),
    "multi": ("internet", "mobile_lines", "backup_internet"),
    "mfg": ("dedicated_line", "mobile_lines", "cloud_email"),
}
# need -> candidate products in priority order (primary connectivity handled separately)
NEED_PRODUCTS = {
    "backup_internet": ("P09",), "cloud_email": ("P16",), "backup_storage": ("P17",), "website": ("P18",),
    "billing_pos": ("P19",), "endpoint_security": ("P20",), "firewall": ("P21",), "wifi_guest": ("P22",),
    "cctv": ("P23",), "machine_iot": ("P24",), "fleet": ("P25",), "cloud_telephony": ("P12",),
    "toll_free": ("P13",), "sms": ("P14",), "whatsapp": ("P15",), "static_ip": ("P11",),
    "multi_site_mgmt": ("P10",),
}
MAX_TYPICAL = {"micro": 1, "prof": 2, "multi": 2, "mfg": 2}  # micro is the most price-sensitive segment


@dataclass
class Item:
    product_id: str
    qty: int
    reason: str                     # CORE | REQUESTED | TYPICAL | OPTIONAL
    need: str | None = None
    share_of_similar: float | None = None   # share of activated bundles in the segment with this product

    def to_dict(self):
        return asdict(self)


@dataclass
class Exclusion:
    product_id: str
    need: str | None
    violations: list[dict]


@dataclass
class Recommendation:
    status: str                              # ok | not_serviceable | needs_info
    profile: BusinessProfile
    recommended: list[Item] = field(default_factory=list)
    add_ons: list[Item] = field(default_factory=list)
    starter: list[Item] = field(default_factory=list)
    excluded: list[Exclusion] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "status": self.status,
            "profile": self.profile.model_dump(),
            "recommended": [i.to_dict() for i in self.recommended],
            "add_ons": [i.to_dict() for i in self.add_ons],
            "starter": [i.to_dict() for i in self.starter],
            "excluded": [asdict(e) for e in self.excluded],
            "notes": self.notes,
            "missing": self.missing,
        }


# ----------------------------------------------------------------------------- profile resolution
def resolve_profile(profile: BusinessProfile) -> BusinessProfile:
    upd: dict = {}
    bt = get_type(profile.business_type) or (match_business_type(profile.business_type) if profile.business_type else None)
    bt2, seg = resolve_segment(bt, profile.employees, profile.sites)
    if bt2:
        upd["business_type"] = bt2.name
    if seg and not (profile.segment and bt2 is None):
        upd["segment"] = seg
    if profile.city:
        hit = cities.lookup_city(profile.city)
        if hit:
            upd.update(city=hit[0], city_tier=hit[1], state=hit[2] or profile.state)
        elif profile.city_tier is None:
            upd["city_tier"] = 3
    if profile.has_gstin is False:
        upd["gstin_status"] = None
    return profile.merge(upd)


# ----------------------------------------------------------------------------- quantities
def default_qty(pid: str, p: BusinessProfile, cat: Catalogue, connected_sites: int) -> int:
    seg, emp, sites = p.segment, p.employees or 1, p.sites or 1
    prod = cat[pid]
    if prod.is_per_site:
        if pid in ("P09", "P21", "P22", "P10"):
            return max(1, min(sites, connected_sites or sites))
        return sites
    if pid == "P07":
        return p.mobile_lines or 2
    if pid == "P08":
        return p.mobile_lines or (3 if seg == "prof" else 4)
    if pid == "P16":
        ratio = {"prof": 0.7, "mfg": 0.13, "multi": 0.1}.get(seg or "", 0.7)
        return max(1, min(emp, p.email_users or round(emp * ratio)))
    if pid == "P20":
        ratio = {"prof": 0.5, "mfg": 0.13, "multi": 0.1}.get(seg or "", 0.5)
        return max(1, round(emp * ratio))
    if pid == "P23":
        return p.cameras or {"micro": 1, "multi": 2 * sites, "mfg": 4}.get(seg or "", 2)
    if pid == "P19":
        return p.counters or sites
    if pid == "P24":
        return p.machines or 10
    if pid == "P25":
        return p.vehicles or 4
    if pid == "P12":
        return max(1, min(3, emp))
    return 1


# ----------------------------------------------------------------------------- primary connectivity
def primary_candidates(p: BusinessProfile, needs: set[str]) -> tuple[str, ...]:
    seg, emp, sites = p.segment, p.employees or 1, p.sites or 1
    if p.fibre_available is False:
        return ("P05", "P04") if (seg == "mfg" or "dedicated_line" in needs) else ("P04",)
    if seg == "mfg" or "dedicated_line" in needs:
        big = emp >= 100 or "high_speed" in needs
        return ("P06", "P05", "P03", "P02", "P01") if big else ("P05", "P06", "P03", "P02", "P01")
    if seg == "multi":
        return ("P02", "P01") if emp / sites >= 15 or "high_speed" in needs else ("P01", "P02")
    if seg == "prof":
        if "high_speed" in needs:
            return ("P03", "P02", "P01")
        return ("P02", "P01") if emp >= 6 else ("P01", "P02")
    return ("P01", "P04")


def _pick(cands, p, cat):
    rejected = []
    for pid in cands:
        v = product_rule_violations(cat[pid], p)
        if not v:
            return pid, rejected
        rejected.append((pid, [x.to_dict() for x in v]))
    return None, rejected


# ----------------------------------------------------------------------------- main entry point
def recommend(profile: BusinessProfile, cat: Catalogue | None = None) -> Recommendation:
    cat = cat or get_catalogue()
    p = resolve_profile(profile)
    rec = Recommendation(status="ok", profile=p)
    rec.missing = p.missing_required()
    if rec.missing:
        rec.status = "needs_info"
        return rec
    if p.city_tier not in (1, 2):
        rec.status = "not_serviceable"
        rec.notes.append({"code": "NOT_SERVICEABLE", "params": {"city": p.city}})
        return rec

    seg = p.segment or "micro"
    bt = get_type(p.business_type)
    explicit = [n for n in p.needs if n not in p.excluded_needs]
    if p.only_mobile:
        core: tuple[str, ...] = ("mobile_lines",)
        typical: list[str] = []
    else:
        core = CORE_NEEDS[seg]
        typical = [n for n in (bt.needs if bt else ()) if n not in core and n not in explicit
                   and n not in p.excluded_needs and n not in ("internet", "dedicated_line")][:MAX_TYPICAL[seg]]
    needs_all = set(core) | set(explicit) | set(typical)
    chosen: dict[str, Item] = {}

    def add(pid, need, reason):
        if pid in chosen:
            return
        chosen[pid] = Item(pid, 0, reason, need, penetration(seg, pid))

    # 1. primary connectivity
    primary = None
    if not p.only_mobile:
        want_conn = {"internet", "dedicated_line"} & needs_all or {"internet"}
        primary, rejected = _pick(primary_candidates(p, needs_all), p, cat)
        if primary:
            add(primary, sorted(want_conn)[0], "CORE")
            if p.fibre_available is False and primary == "P04":
                rec.notes.append({"code": "FIBRE_FALLBACK", "params": {"product_id": "P04"}})
        for pid, v in rejected:
            if "dedicated_line" in explicit or pid in ("P05", "P06", "P03"):
                rec.excluded.append(Exclusion(pid, "dedicated_line" if pid in ("P05", "P06") else "internet", v))

    # 2. mobile lines
    if "mobile_lines" in needs_all:
        line = "P07" if seg == "micro" or (seg == "prof" and (p.employees or 1) < 10) else "P08"
        add(line, "mobile_lines", "CORE" if "mobile_lines" in core else "REQUESTED")

    # 3. other needs in a stable order: core, requested, typical
    ordered = [(n, "CORE") for n in core] + [(n, "REQUESTED") for n in explicit] + [(n, "TYPICAL") for n in typical]
    for need, reason in ordered:
        for pid in NEED_PRODUCTS.get(need, ()):
            prod = cat[pid]
            v = [x.to_dict() for x in product_rule_violations(prod, p)]
            dep_ok = not prod.requires_one_of or any(d in chosen for d in prod.requires_one_of)
            if not dep_ok:
                v.append({"product_id": pid, "code": "DEPENDENCY_MISSING",
                          "params": {"needs_one_of": list(prod.requires_one_of), "have": primary}, "hard": True})
            if v:
                if reason != "TYPICAL":
                    rec.excluded.append(Exclusion(pid, need, v))
                continue
            add(pid, need, reason)

    # 4. quantities
    connected = p.sites or 1
    for it in chosen.values():
        it.qty = default_qty(it.product_id, p, cat, connected)
    if primary and cat[primary].is_per_site:
        chosen[primary].qty = p.sites or 1

    rec.recommended = list(chosen.values())

    # 5. optional add-ons: other eligible products aimed at this segment
    for prod in cat:
        pid = prod.product_id
        if pid in chosen or pid in PRIMARY_IDS or pid in LINE_IDS or p.only_mobile:
            continue
        if seg not in prod.target_segments:
            continue
        if product_rule_violations(prod, p):
            continue
        if prod.requires_one_of and not any(d in chosen for d in prod.requires_one_of):
            continue
        need = next((n for n, ids in NEED_PRODUCTS.items() if pid in ids), None)
        if need in p.excluded_needs:
            continue
        it = Item(pid, 0, "OPTIONAL", need, penetration(seg, pid))
        it.qty = default_qty(pid, p, cat, p.sites or 1)
        rec.add_ons.append(it)
    rec.add_ons.sort(key=lambda i: -(i.share_of_similar or 0))

    # 6. starter = connectivity + lines only
    rec.starter = [Item(i.product_id, i.qty, i.reason, i.need, i.share_of_similar)
                   for i in rec.recommended if i.product_id in PRIMARY_IDS + LINE_IDS] or list(rec.recommended)

    # 7. safety net: the bundle we return must pass full validation
    for bundle_name in ("recommended", "starter"):
        items = getattr(rec, bundle_name)
        viol = hard(validate_bundle([(i.product_id, i.qty) for i in items], p, cat))
        if viol:  # should never happen; drop offending lines rather than quote something invalid
            bad = {v.product_id for v in viol}
            setattr(rec, bundle_name, [i for i in items if i.product_id not in bad])
            rec.notes.append({"code": "INTERNAL_DROPPED_INVALID", "params": {"bundle": bundle_name, "products": sorted(bad)}})

    # 8. context notes
    gst_products = [e.product_id for e in rec.excluded if any(v["code"] in ("GSTIN_REQUIRED", "GSTIN_NOT_ACTIVE") for v in e.violations)]
    if gst_products:
        rec.notes.append({"code": "GST_BLOCKED", "params": {"products": gst_products, "status": p.gstin_status}})
    rec_month = sum(cat[i.product_id].list_price() * i.qty for i in rec.recommended)
    start_month = sum(cat[i.product_id].list_price() * i.qty for i in rec.starter)
    if p.monthly_spend:
        rec.notes.append({"code": "SPEND_COMPARISON", "params": {
            "current": p.monthly_spend, "recommended": round(rec_month, 2), "starter": round(start_month, 2),
            "ratio": round(rec_month / p.monthly_spend, 2) if p.monthly_spend else None}})
    if p.budget and rec_month > p.budget:
        rec.notes.append({"code": "BUDGET_OVER", "params": {
            "budget": p.budget, "recommended": round(rec_month, 2), "starter": round(start_month, 2),
            "starter_fits": start_month <= p.budget}})
    return rec


def bundle_from_items(items: list[Item]) -> list[tuple[str, int]]:
    return [(i.product_id, i.qty) for i in items]


def ceil_div(a: int, b: int) -> int:
    return math.ceil(a / b)
