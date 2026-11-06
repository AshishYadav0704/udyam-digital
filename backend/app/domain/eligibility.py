"""Deterministic eligibility and bundle validation.

Hard rules come only from product_catalogue.csv:
  available_city_tiers, min_employees, min_sites, requires_gstin (valid AND active), requires_one_of.
Two physical-consistency rules are added and documented as ASSUMPTIONS:
  * a per-site product cannot be ordered for more sites than the business has;
  * a per-site add-on that depends on a connection (failover, firewall, Wi-Fi, SD-WAN) cannot
    exceed the number of sites that have a qualifying connection in the same bundle.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.catalogue import Catalogue, Product
from app.domain.profile import BusinessProfile


@dataclass
class Violation:
    product_id: str
    code: str
    params: dict = field(default_factory=dict)
    hard: bool = True

    def to_dict(self):
        return {"product_id": self.product_id, "code": self.code, "params": self.params, "hard": self.hard}


def gstin_ok(profile: BusinessProfile) -> tuple[bool, str | None]:
    if not profile.has_gstin:
        return False, "GSTIN_REQUIRED"
    if profile.gstin_status and profile.gstin_status != "Active":
        return False, "GSTIN_NOT_ACTIVE"
    return True, None


def product_rule_violations(p: Product, profile: BusinessProfile) -> list[Violation]:
    """Business-level rules for a single product (dependencies are checked at bundle level)."""
    out: list[Violation] = []
    tier = profile.city_tier
    if tier is None or tier not in p.city_tiers:
        out.append(Violation(p.product_id, "TIER_NOT_SERVED", {"tier": tier, "allowed": list(p.city_tiers)}))
    if profile.employees is not None and profile.employees < p.min_employees:
        out.append(Violation(p.product_id, "MIN_EMPLOYEES", {"min": p.min_employees, "have": profile.employees}))
    if profile.sites is not None and profile.sites < p.min_sites:
        out.append(Violation(p.product_id, "MIN_SITES", {"min": p.min_sites, "have": profile.sites}))
    if p.requires_gstin:
        ok, code = gstin_ok(profile)
        if not ok:
            out.append(Violation(p.product_id, code, {"status": profile.gstin_status}))
    return out


def is_eligible(p: Product, profile: BusinessProfile) -> bool:
    return not product_rule_violations(p, profile)


def validate_bundle(items: list[tuple[str, int]], profile: BusinessProfile, cat: Catalogue) -> list[Violation]:
    """Validate a complete bundle before any quote is produced. Returns all violations."""
    out: list[Violation] = []
    qty = {}
    for pid, q in items:
        if pid not in cat:
            out.append(Violation(pid, "UNKNOWN_PRODUCT"))
            continue
        if not isinstance(q, int) or q < 1:
            out.append(Violation(pid, "INVALID_QUANTITY", {"qty": q}))
            continue
        if pid in qty:
            out.append(Violation(pid, "DUPLICATE_LINE"))
        qty[pid] = qty.get(pid, 0) + q
    if not qty:
        out.append(Violation("-", "EMPTY_BUNDLE"))
        return out
    sites = profile.sites or 1
    for pid, q in qty.items():
        p = cat[pid]
        out.extend(product_rule_violations(p, profile))
        if p.requires_one_of and not any(d in qty for d in p.requires_one_of):
            out.append(Violation(pid, "DEPENDENCY_MISSING", {"needs_one_of": list(p.requires_one_of)}))
        if p.is_per_site and q > sites:
            out.append(Violation(pid, "QTY_EXCEEDS_SITES", {"qty": q, "sites": sites}))
        if p.is_per_site and p.requires_one_of:
            covered = sum(qty.get(d, 0) for d in p.requires_one_of if cat[d].is_per_site)
            if covered and q > covered:
                out.append(Violation(pid, "QTY_EXCEEDS_CONNECTED_SITES", {"qty": q, "connected_sites": covered}))
        if p.product_id == "P10" and q < p.min_sites:
            out.append(Violation(pid, "QTY_BELOW_MIN_SITES", {"qty": q, "min": p.min_sites}))
        if p.unit == "per user" and profile.employees and q > profile.employees * 2:
            out.append(Violation(pid, "QTY_UNUSUAL", {"qty": q, "employees": profile.employees}, hard=False))
    return out


def hard(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.hard]
