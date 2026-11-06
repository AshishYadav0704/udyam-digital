"""MOCK registry adapters backed by the competition CSVs.

These are NOT government APIs. They emulate the shape of a GSTIN / Udyam verification response
so the KYC flow can be built and tested. The `source` field on every response says so, and the
production adapter (GSTN via a GSP / API Setu, Udyam verification) is a separate class behind the
same interface - see docs/research/government_integrations.md.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from functools import lru_cache

from app.config import settings

SOURCE = "MOCK registry (synthetic competition data) - not a government API"


@dataclass(frozen=True)
class GstRecord:
    gstin: str
    legal_name: str
    trade_name: str
    constitution: str
    principal_place_of_business: str
    state: str
    registration_date: str
    status: str

    def to_dict(self):
        return {**asdict(self), "source": SOURCE}


@dataclass(frozen=True)
class UdyamRecord:
    udyam_number: str
    enterprise_name: str
    enterprise_type: str
    major_activity: str
    nic_description: str
    state: str
    city: str
    date_of_registration: str

    def to_dict(self):
        return {**asdict(self), "source": SOURCE}


class RegistryAdapter:
    """Interface the KYC service depends on; swap for the production adapter."""
    def gstin(self, gstin: str) -> GstRecord | None: ...
    def udyam(self, number: str) -> UdyamRecord | None: ...


class MockRegistry(RegistryAdapter):
    def __init__(self):
        self._g = {}
        with open(settings.data_dir / "mock_gstin_registry.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                self._g[r["gstin"]] = GstRecord(**{k: r[k] for k in GstRecord.__dataclass_fields__})
        self._u = {}
        with open(settings.data_dir / "mock_udyam_registry.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                self._u[r["udyam_number"]] = UdyamRecord(**{k: r[k] for k in UdyamRecord.__dataclass_fields__})

    def gstin(self, gstin: str) -> GstRecord | None:
        return self._g.get((gstin or "").upper())

    def udyam(self, number: str) -> UdyamRecord | None:
        return self._u.get((number or "").upper())

    @property
    def sizes(self):
        return {"gstin": len(self._g), "udyam": len(self._u)}


class UnavailableRegistry(RegistryAdapter):
    """Used in tests to simulate an upstream outage."""
    def gstin(self, gstin):
        raise ConnectionError("registry unavailable")

    def udyam(self, number):
        raise ConnectionError("registry unavailable")


@lru_cache(maxsize=1)
def get_registry() -> RegistryAdapter:
    return MockRegistry()


def proprietor_from_legal_name(legal_name: str) -> str | None:
    """'Neha Kaur (Prop. Vindhya Tours & Travels)' -> 'Neha Kaur'"""
    if "(Prop." in legal_name:
        return legal_name.split("(Prop.")[0].strip()
    return None
