"""Quote computation - one transparent monthly price, add-ons the owner can toggle.

Price policy (configurable, default 'midpoint'): each product is quoted at the midpoint of its
catalogue range. Historic bundles were realised at 48% of the range on average, so the midpoint
reproduces 100.2% of realised MRR - transparency without giving revenue away
(analysis/outputs/metrics.json -> price_realisation).

GST: the catalogue does not say whether prices include tax. The quote therefore shows prices
excluding GST and a separate GST estimate at settings.gst_rate (18%), labelled as an estimate.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from app.config import settings
from app.domain.catalogue import Catalogue, get_catalogue
from app.domain.eligibility import hard, validate_bundle
from app.domain.profile import BusinessProfile


@dataclass
class QuoteLine:
    product_id: str
    name: str
    category: str
    unit: str
    qty: int
    unit_price: float
    monthly: float
    setup_unit: int
    setup: int
    min_contract_months: int
    install_days: int
    install_start_day: int
    install_done_day: int


@dataclass
class Quote:
    lines: list[QuoteLine]
    monthly_subtotal: float
    monthly_gst: float
    monthly_total: float
    setup_subtotal: int
    setup_gst: float
    setup_total: float
    contract_months: int
    contract_driver: str
    total_contract_value: float
    expected_activation_days: int
    price_policy: str
    gst_rate: float
    valid_until: str
    warnings: list[dict] = field(default_factory=list)
    fingerprint: str = ""

    def to_dict(self):
        d = asdict(self)
        return d


class InvalidBundle(ValueError):
    def __init__(self, violations):
        super().__init__("bundle failed validation")
        self.violations = violations


def _round2(x: float) -> float:
    return float(f"{x:.2f}")


def install_schedule(items: list[tuple[str, int]], cat: Catalogue) -> dict[str, tuple[int, int]]:
    """Products with a dependency start when the earliest qualifying connection is live."""
    ids = [pid for pid, _ in items]
    done: dict[str, tuple[int, int]] = {}
    for pid in sorted(ids, key=lambda x: bool(cat[x].requires_one_of)):
        p = cat[pid]
        start = 0
        deps = [d for d in p.requires_one_of if d in ids]
        if deps:
            start = min(done[d][1] if d in done else cat[d].install_days for d in deps)
        done[pid] = (start, start + p.install_days)
    return done


def build_quote(items: list[tuple[str, int]], profile: BusinessProfile, cat: Catalogue | None = None,
                today: date | None = None) -> Quote:
    cat = cat or get_catalogue()
    violations = validate_bundle(items, profile, cat)
    if hard(violations):
        raise InvalidBundle([v.to_dict() for v in hard(violations)])
    sched = install_schedule(items, cat)
    lines = []
    for pid, qty in items:
        p = cat[pid]
        up = p.list_price()
        s0, s1 = sched[pid]
        lines.append(QuoteLine(pid, p.name, p.category, p.unit, qty, _round2(up), _round2(up * qty),
                               p.setup_fee, p.setup_fee * qty, p.min_contract_months, p.install_days, s0, s1))
    order = {"Connectivity": 0, "Communication": 1, "Cloud & Productivity": 2, "Security": 3, "IoT & Physical": 4}
    lines.sort(key=lambda l: (order.get(l.category, 9), l.product_id))
    monthly = _round2(sum(l.monthly for l in lines))
    setup = sum(l.setup for l in lines)
    driver = max(lines, key=lambda l: (l.min_contract_months, l.monthly))
    contract = driver.min_contract_months
    gst = settings.gst_rate
    today = today or date.today()
    q = Quote(
        lines=lines,
        monthly_subtotal=monthly,
        monthly_gst=_round2(monthly * gst),
        monthly_total=_round2(monthly * (1 + gst)),
        setup_subtotal=setup,
        setup_gst=_round2(setup * gst),
        setup_total=_round2(setup * (1 + gst)),
        contract_months=contract,
        contract_driver=driver.product_id,
        total_contract_value=_round2(monthly * contract + setup),
        expected_activation_days=max(l.install_done_day for l in lines),
        price_policy=settings.price_policy,
        gst_rate=gst,
        valid_until=(today + timedelta(days=settings.quote_validity_days)).isoformat(),
        warnings=[v.to_dict() for v in violations if not v.hard],
    )
    q.fingerprint = hashlib.sha256(json.dumps(
        {"items": sorted(items), "monthly": monthly, "setup": setup, "policy": q.price_policy},
        sort_keys=True).encode()).hexdigest()[:16]
    return q
