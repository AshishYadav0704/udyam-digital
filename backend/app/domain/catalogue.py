"""Product catalogue: the only source of products, prices and eligibility rules.

Loaded verbatim from product_catalogue.csv. Nothing in the advisor, the LLM layer or
the quote can introduce a product, price or rule that is not in this file.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.config import settings

UNIT_LABELS = {
    "per site": ("site", "sites", "साइट"),
    "per line": ("line", "lines", "लाइन"),
    "per IP": ("IP", "IPs", "आईपी"),
    "per channel": ("channel", "channels", "चैनल"),
    "per number": ("number", "numbers", "नंबर"),
    "per pack": ("pack", "packs", "पैक"),
    "per account": ("account", "accounts", "अकाउंट"),
    "per user": ("user", "users", "यूज़र"),
    "per counter": ("counter", "counters", "काउंटर"),
    "per device": ("device", "devices", "डिवाइस"),
    "per camera": ("camera", "cameras", "कैमरा"),
    "per vehicle": ("vehicle", "vehicles", "वाहन"),
}


@dataclass(frozen=True)
class Product:
    product_id: str
    category: str
    name: str
    description: str
    unit: str
    price_min: int
    price_max: int
    setup_fee: int
    min_contract_months: int
    city_tiers: tuple[int, ...]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: tuple[str, ...] = field(default_factory=tuple)
    install_days: int = 0
    target_segments: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_per_site(self) -> bool:
        return self.unit == "per site"

    def list_price(self, policy: str | None = None) -> float:
        """Single published monthly unit price derived from the catalogue range.

        midpoint (default): realised historic prices averaged 48% of the range, so a
        midpoint list price is revenue-neutral (see analysis/outputs/metrics.json).
        """
        policy = policy or settings.price_policy
        if policy == "floor":
            return float(self.price_min)
        if policy == "ceiling":
            return float(self.price_max)
        return (self.price_min + self.price_max) / 2

    def unit_label(self, qty: int, lang: str = "en") -> str:
        one, many, hi = UNIT_LABELS.get(self.unit, ("unit", "units", "यूनिट"))
        if lang == "hi":
            return hi
        return one if qty == 1 else many


class Catalogue:
    def __init__(self, products: list[Product]):
        self.products = {p.product_id: p for p in products}
        if len(self.products) != len(products):
            raise ValueError("duplicate product_id in catalogue")
        for p in products:
            for dep in p.requires_one_of:
                if dep not in self.products:
                    raise ValueError(f"{p.product_id} depends on unknown product {dep}")

    def __getitem__(self, pid: str) -> Product:
        return self.products[pid]

    def __contains__(self, pid: str) -> bool:
        return pid in self.products

    def __iter__(self):
        return iter(self.products.values())

    def __len__(self) -> int:
        return len(self.products)

    def by_name(self, name: str) -> Product | None:
        n = name.strip().lower()
        for p in self:
            if p.name.lower() == n:
                return p
        return None

    @classmethod
    def from_csv(cls, path: Path) -> "Catalogue":
        products = []
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                products.append(Product(
                    product_id=r["product_id"].strip(),
                    category=r["category"].strip(),
                    name=r["product_name"].strip(),
                    description=r["description"].strip(),
                    unit=r["unit"].strip(),
                    price_min=int(r["price_min_inr_per_month"]),
                    price_max=int(r["price_max_inr_per_month"]),
                    setup_fee=int(r["one_time_setup_inr"]),
                    min_contract_months=int(r["min_contract_months"]),
                    city_tiers=tuple(int(t) for t in r["available_city_tiers"].split(";") if t.strip()),
                    min_employees=int(r["min_employees"]),
                    min_sites=int(r["min_sites"]),
                    requires_gstin=r["requires_gstin"].strip().upper() == "Y",
                    requires_one_of=tuple(x for x in r["requires_one_of"].split("|") if x.strip()),
                    install_days=int(r["typical_install_days"]),
                    target_segments=tuple(x for x in r["target_segments"].split(";") if x.strip()),
                ))
        return cls(products)


@lru_cache(maxsize=1)
def get_catalogue() -> Catalogue:
    return Catalogue.from_csv(settings.data_dir / "product_catalogue.csv")
