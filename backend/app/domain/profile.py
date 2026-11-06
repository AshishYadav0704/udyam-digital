"""Structured business profile collected by the advisor (and validated server-side)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

NEED_TAGS = (
    "internet", "backup_internet", "dedicated_line", "mobile_lines", "cloud_email", "backup_storage",
    "website", "billing_pos", "endpoint_security", "firewall", "wifi_guest", "cctv", "machine_iot",
    "fleet", "cloud_telephony", "toll_free", "sms", "whatsapp", "static_ip", "multi_site_mgmt",
    "high_speed",
)
NeedTag = Literal[NEED_TAGS]  # type: ignore[valid-type]
CurrentInternet = Literal["None", "Mobile hotspot", "Home broadband", "Business broadband", "Leased line", "Mixed per site"]


class BusinessProfile(BaseModel):
    business_name: str | None = Field(None, max_length=120)
    business_type: str | None = Field(None, max_length=60)
    segment: Literal["micro", "prof", "multi", "mfg"] | None = None
    city: str | None = Field(None, max_length=60)
    city_tier: Literal[1, 2, 3] | None = None
    state: str | None = None
    employees: int | None = Field(None, ge=1, le=5000)
    sites: int | None = Field(None, ge=1, le=200)
    has_gstin: bool | None = None
    gstin: str | None = Field(None, max_length=15)
    gstin_status: Literal["Active", "Suspended", "Cancelled", "NotFound"] | None = None
    has_udyam: bool | None = None
    udyam_number: str | None = Field(None, max_length=19)
    current_internet: CurrentInternet | None = None
    current_provider: str | None = Field(None, max_length=40)
    monthly_spend: int | None = Field(None, ge=0, le=10_000_000)
    budget: int | None = Field(None, ge=0, le=10_000_000)
    fibre_available: bool | None = None
    needs: list[NeedTag] = Field(default_factory=list)  # type: ignore[valid-type]
    excluded_needs: list[NeedTag] = Field(default_factory=list)  # type: ignore[valid-type]
    # optional quantity hints the owner can give ("8 cameras", "5 delivery vans")
    cameras: int | None = Field(None, ge=0, le=500)
    vehicles: int | None = Field(None, ge=0, le=500)
    machines: int | None = Field(None, ge=0, le=500)
    mobile_lines: int | None = Field(None, ge=0, le=500)
    email_users: int | None = Field(None, ge=0, le=5000)
    counters: int | None = Field(None, ge=0, le=500)
    only_mobile: bool = False
    language: Literal["en", "hi"] = "en"

    @field_validator("needs", "excluded_needs")
    @classmethod
    def _dedupe(cls, v):
        seen, out = set(), []
        for x in v:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def merge(self, update: dict) -> "BusinessProfile":
        """Merge an extracted update; lists are unioned, scalars overwrite only when provided."""
        data = self.model_dump()
        for k, v in update.items():
            if v is None or k not in data:
                continue
            if k in ("needs", "excluded_needs"):
                data[k] = list(dict.fromkeys([*data[k], *v]))
            else:
                data[k] = v
        # an explicitly excluded need wins over an inferred one
        data["needs"] = [n for n in data["needs"] if n not in set(data["excluded_needs"])]
        return BusinessProfile.model_validate(data)

    def missing_required(self) -> list[str]:
        order = []
        if not self.business_type and not self.segment:
            order.append("business_type")
        if not self.city and not self.city_tier:
            order.append("city")
        if self.employees is None:
            order.append("employees")
        if self.sites is None:
            order.append("sites")
        if self.has_gstin is None:
            order.append("gstin")
        return order
