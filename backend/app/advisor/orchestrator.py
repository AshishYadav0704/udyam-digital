"""Advisor dialogue policy.

Slot-filling with the fewest useful questions: business type -> city -> people -> sites -> GSTIN are
required; needs (one multi-select question) and current spend (micro businesses only) are optional and
skipped if the owner already volunteered them. Every message goes through the offline extractor and,
when configured, an LLM extractor; the merged result is validated by BusinessProfile. Recommendations,
prices and eligibility always come from the deterministic engine.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.advisor import llm as llm_mod
from app.advisor.nlu import NEED_KEYWORDS, extract, is_hindi
from app.domain import insights
from app.domain.business_types import GENERIC_TYPES
from app.domain.catalogue import get_catalogue
from app.domain.identifiers import mask_gstin, scrub, validate_gstin
from app.domain.pricing import build_quote
from app.domain.profile import NEED_TAGS, BusinessProfile
from app.domain.recommender import bundle_from_items, recommend, resolve_profile
from app.i18n import LANGUAGE_NAMES, fmt_inr, t
from app.kyc.registry import get_registry
from app.models import AdvisorMessage, AdvisorSession

log = logging.getLogger("app.advisor")
OPTIONAL_NEEDS_CHIPS = ["backup_internet", "mobile_lines", "cloud_email", "backup_storage", "billing_pos", "cctv",
                        "wifi_guest", "whatsapp", "sms", "website", "endpoint_security", "cloud_telephony", "toll_free",
                        "fleet", "machine_iot", "multi_site_mgmt"]
REMOVE_WORDS = r"(remove|drop|without|don't want|dont want|no need for|hata do|hatao|हटा दो|हटाइए|नहीं चाहिए)"
FAQ_WORDS = r"(what is|what's|what does|explain|meaning of|kya hai|kya hota|क्या है|क्या होता)"


def _unit_short(unit: str, lang: str) -> str:
    cat = get_catalogue()
    for p in cat:
        if p.unit == unit:
            return p.unit_label(1, lang)
    return unit


def _desc(pid: str, lang: str) -> str:
    if lang == "hi":
        hi = t("hi", f"products.{pid}")
        if hi != f"products.{pid}":
            return hi
    return get_catalogue()[pid].description


def _summary(p: BusinessProfile, lang: str) -> str:
    parts = []
    if p.business_type:
        parts.append(p.business_type)
    if p.city:
        parts.append(p.city)
    if p.employees:
        parts.append(f"{p.employees} " + ("लोग" if lang == "hi" else ("person" if p.employees == 1 else "people")))
    if p.sites:
        parts.append(f"{p.sites} " + ("साइट" if lang == "hi" else ("site" if p.sites == 1 else "sites")))
    if p.has_gstin is True:
        parts.append("GSTIN ✓")
    elif p.has_gstin is False:
        parts.append("GSTIN ✗" if lang != "hi" else "GSTIN नहीं")
    return ", ".join(parts)


def violation_text(v: dict, lang: str) -> str:
    cat = get_catalogue()
    name = cat[v["product_id"]].name if v["product_id"] in cat else v["product_id"]
    params = {k: v2 for k, v2 in (v.get("params") or {}).items() if not isinstance(v2, (list, dict))}
    return t(lang, f"violations.{v['code']}", name=name, **params)


def present_items(items, lang: str, quote: dict | None = None) -> list[dict]:
    cat = get_catalogue()
    qlines = {l["product_id"]: l for l in (quote or {}).get("lines", [])}
    out = []
    for it in items:
        p = cat[it.product_id]
        need_label = t(lang, f"needs.{it.need}") if it.need else ""
        pct = round((it.share_of_similar or 0) * 100)
        reason_key = it.reason if not (it.reason == "TYPICAL" and pct == 0) else "OPTIONAL"
        line = qlines.get(p.product_id)
        out.append({
            "product_id": p.product_id, "name": p.name, "category": p.category, "unit": p.unit,
            "unit_label": p.unit_label(it.qty, lang), "qty": it.qty, "unit_price": p.list_price(),
            "monthly": line["monthly"] if line else round(p.list_price() * it.qty, 2),
            "setup": p.setup_fee * it.qty, "min_contract_months": p.min_contract_months, "install_days": p.install_days,
            "reason": it.reason, "need": it.need, "share_of_similar": it.share_of_similar,
            "description": _desc(p.product_id, lang), "requires_gstin": p.requires_gstin,
            "reason_text": t(lang, f"reasons.{reason_key}", name=p.name, description=_desc(p.product_id, lang),
                             need=need_label, pct=pct),
        })
    return out


def build_recommendation_payload(profile: BusinessProfile, lang: str, provider=None) -> dict:
    rec = recommend(profile)
    payload: dict = {"status": rec.status, "missing": rec.missing, "profile": rec.profile.model_dump()}
    notes = []
    for n in rec.notes:
        params = {k: (fmt_inr(v) if isinstance(v, (int, float)) and k != "ratio" else v)
                  for k, v in n["params"].items() if not isinstance(v, (list, dict, bool))}
        notes.append({"code": n["code"], "text": t(lang, f"notes.{n['code']}", **params)})
    payload["notes"] = notes
    if rec.status != "ok":
        return payload
    q = build_quote(bundle_from_items(rec.recommended), rec.profile).to_dict()
    sq = build_quote(bundle_from_items(rec.starter), rec.profile).to_dict()
    payload["items"] = present_items(rec.recommended, lang, q)
    payload["add_ons"] = present_items(rec.add_ons, lang)
    payload["starter_ids"] = [i.product_id for i in rec.starter]
    payload["excluded"] = []
    seen = set()
    for e in rec.excluded:
        if e.product_id in seen:
            continue
        seen.add(e.product_id)
        payload["excluded"].append({"product_id": e.product_id, "name": get_catalogue()[e.product_id].name,
                                    "codes": [v["code"] for v in e.violations],
                                    "text": " ".join(violation_text(v, lang) for v in e.violations[:2])})
    payload["quote"] = q
    payload["starter_quote"] = {"monthly_subtotal": sq["monthly_subtotal"], "setup_subtotal": sq["setup_subtotal"],
                                "contract_months": sq["contract_months"]}
    business = rec.profile.business_type or t(lang, f"segments.{rec.profile.segment}")
    intro = t(lang, "advisor.recommend_intro", business=business, city=rec.profile.city or "")
    summary = t(lang, "advisor.recommend_summary", monthly=fmt_inr(q["monthly_subtotal"]), setup=fmt_inr(q["setup_subtotal"]),
                contract=q["contract_months"], days=q["expected_activation_days"])
    template = intro + " " + "; ".join(i["name"] for i in payload["items"]) + ". " + summary
    payload["explanation"], payload["explanation_source"] = template, "template"
    if provider:
        facts = {"business": business, "city": rec.profile.city, "people": rec.profile.employees, "sites": rec.profile.sites,
                 "plan": [{"name": i["name"], "why": i["reason_text"], "qty": i["qty"]} for i in payload["items"]],
                 "monthly_price_ex_gst": fmt_inr(q["monthly_subtotal"]), "one_time_setup": fmt_inr(q["setup_subtotal"]),
                 "contract_months": q["contract_months"], "ready_in_days": q["expected_activation_days"],
                 "left_out": [e["text"] for e in payload["excluded"]]}
        try:
            text = provider.explain(facts, lang)
            allowed = {str(x).replace(",", "").rstrip("0").rstrip(".") for x in
                       (q["monthly_subtotal"], q["setup_subtotal"], int(q["monthly_subtotal"]), q["setup_subtotal"])}
            names_all = {p.name for p in get_catalogue()}
            if text and llm_mod.explanation_is_grounded(text, allowed, {i["name"] for i in payload["items"]}, names_all):
                payload["explanation"], payload["explanation_source"] = text + " " + summary, "llm"
        except Exception as e:  # noqa: BLE001 - never fail the journey because of the LLM
            log.warning("LLM explanation failed: %s", type(e).__name__)
    return payload


class Advisor:
    def __init__(self, db: Session):
        self.db = db
        self.provider = llm_mod.get_provider()

    # ------------------------------------------------------------------ helpers
    def _say(self, s: AdvisorSession, text: str, **meta) -> dict:
        self.db.add(AdvisorMessage(session_id=s.id, role="assistant", text=text, meta=meta))
        return {"role": "assistant", "text": text, **meta}

    def _chips(self, slot: str | None, lang: str):
        if slot == "needs":
            return [{"value": n, "label": t(lang, f"needs.{n}")} for n in OPTIONAL_NEEDS_CHIPS]
        if slot in ("business_type", "city", "employees", "sites", "gstin", "spend"):
            return [{"value": c, "label": c} for c in t(lang, f"advisor.chips.{slot}")]
        return []

    def greeting(self, s: AdvisorSession) -> dict:
        lang = s.language
        msg = self._say(s, t(lang, "advisor.greeting"))
        s.asked = ["business_type"]
        return {"messages": [msg], "expecting": "business_type", "chips": self._chips("business_type", lang),
                "multi_select": False}

    def _next_slot(self, p: BusinessProfile, s: AdvisorSession) -> str | None:
        missing = p.missing_required()
        if p.only_mobile:
            if p.mobile_lines is None and "mobile_lines" not in s.asked:
                return "mobile_lines"
            missing = [m for m in missing if m in ("city", "gstin")]
        if missing:
            return missing[0]
        if p.city_tier not in (1, 2):
            return None          # not serviceable online: hand over to a partner instead of asking more
        if not p.only_mobile and not p.needs and "needs" not in s.asked:
            return "needs"
        if p.segment == "micro" and p.monthly_spend is None and p.budget is None and "spend" not in s.asked and not p.only_mobile:
            return "spend"
        return None

    def _faq(self, text: str, lang: str) -> str | None:
        low = text.lower()
        if not re.search(FAQ_WORDS, low):
            return None
        cat = get_catalogue()
        for p in cat:
            if p.name.lower() in low or p.product_id.lower() in low:
                return t(lang, "advisor.faq_prefix", name=p.name, description=_desc(p.product_id, lang),
                         price=fmt_inr(p.list_price()), unit=p.unit_label(1, lang), contract=p.min_contract_months)
        for need, kws in NEED_KEYWORDS.items():
            if any(k in low for k in kws) or need.replace("_", "-") in low or "sd-wan" in low and need == "multi_site_mgmt":
                from app.domain.recommender import NEED_PRODUCTS
                pids = NEED_PRODUCTS.get(need) or (("P05",) if need == "dedicated_line" else None)
                if pids:
                    p = cat[pids[0]]
                    return t(lang, "advisor.faq_prefix", name=p.name, description=_desc(p.product_id, lang),
                             price=fmt_inr(p.list_price()), unit=p.unit_label(1, lang), contract=p.min_contract_months)
        return None

    # ------------------------------------------------------------------ main turn
    def handle(self, s: AdvisorSession, text: str | None = None, needs: list[str] | None = None,
               action: str | None = None) -> dict:
        text = (text or "").strip()[:600]
        if text and is_hindi(text) and s.language != "hi":
            s.language = "hi"
        lang = s.language
        expecting = s.asked[-1] if s.asked else None
        out_msgs, flags = [], {}
        if text:
            self.db.add(AdvisorMessage(session_id=s.id, role="user", text=scrub(text)))

        # 1. understand
        update = extract(text, expecting) if text else {"needs": [], "excluded_needs": []}
        used_llm = False
        if self.provider and text and len(text) > 3 and not re.fullmatch(r"[\d\s,+\-₹rs.]+", text.lower()):
            try:
                history = [{"role": m.role, "text": m.text} for m in s.messages[-8:]]
                llm_update = llm_mod.normalise_llm_extraction(self.provider.extract(history, text))
                for k, v in llm_update.items():
                    if k in ("needs", "excluded_needs"):
                        update[k] = list(dict.fromkeys([*update.get(k, []), *v]))
                    elif k.startswith("_") or k not in update:
                        update[k] = v            # offline wins on fields it found (regex-exact numbers/identifiers)
                used_llm = True
            except Exception as e:  # noqa: BLE001
                log.warning("LLM extraction failed (%s); offline extractor used", type(e).__name__)
        if needs:
            update["needs"] = list(dict.fromkeys([*update.get("needs", []), *[n for n in needs if n in NEED_TAGS]]))
        if text and re.search(REMOVE_WORDS, text.lower()) and update.get("needs"):
            update["excluded_needs"] = list(dict.fromkeys([*update.get("excluded_needs", []), *update["needs"]]))
            update["needs"] = []

        # 2. control intents
        if update.pop("_escalate", False) or action == "human":
            flags["escalate"] = True
        update.pop("_lang", None)
        gstin_invalid = update.pop("_gstin_invalid", False)
        update.pop("_skip", None)
        if action == "skip" and expecting:
            s.asked = [*s.asked, f"{expecting}:skipped"]

        # 3. merge + validate
        profile = BusinessProfile.model_validate(s.profile or {})
        clean = {k: v for k, v in update.items() if not k.startswith("_")}
        # a generic type picked up from a passing word ("one clinic", "3 branches") never replaces a specific one
        if (clean.get("business_type") in GENERIC_TYPES and profile.business_type
                and profile.business_type not in GENERIC_TYPES and expecting != "business_type"):
            clean.pop("business_type")
        try:
            profile = profile.merge(clean)
        except Exception:
            out_msgs.append(self._say(s, t(lang, "advisor.fallback")))
        if profile.has_gstin is False:
            profile = profile.model_copy(update={"gstin": None, "gstin_status": None})

        # 4. GSTIN verification against the (mock) registry
        if "gstin" in clean and clean["gstin"]:
            g = clean["gstin"]
            if validate_gstin(g):
                out_msgs.append(self._say(s, t(lang, "advisor.gstin_invalid")))
                profile = profile.model_copy(update={"gstin": None})
            else:
                try:
                    rec = get_registry().gstin(g)
                except ConnectionError:
                    rec = None
                if rec is None:
                    profile = profile.model_copy(update={"gstin_status": "NotFound"})
                    out_msgs.append(self._say(s, t(lang, "advisor.gstin_not_found")))
                else:
                    upd = {"gstin_status": rec.status, "business_name": profile.business_name or rec.trade_name}
                    profile = profile.model_copy(update=upd)
                    key = "advisor.gstin_verified" if rec.status == "Active" else "advisor.gstin_inactive"
                    out_msgs.append(self._say(s, t(lang, key, name=rec.trade_name, status=rec.status),
                                              gstin=mask_gstin(g)))
        elif gstin_invalid:
            out_msgs.append(self._say(s, t(lang, "advisor.gstin_invalid")))
        if profile.gstin_status == "NotFound":
            # unverifiable GSTIN: treat as not active for product rules until KYC verifies it
            pass
        profile = resolve_profile(profile)
        s.profile = profile.model_dump()

        # 5. escalation to a person (never a dead end)
        if flags.get("escalate"):
            s.state = "escalated"
            out_msgs.append(self._say(s, t(lang, "advisor.escalate", language=LANGUAGE_NAMES.get(lang, "English"))))
            return self._response(s, out_msgs, None, used_llm, escalated=True)

        # 6. FAQ (answered from the catalogue, then continue)
        faq = self._faq(text, lang) if text else None
        if faq:
            out_msgs.append(self._say(s, faq))

        # 7. next question or recommendation
        if action == "show_plan" and expecting == "needs":
            s.asked = [*s.asked, "needs:done"]
        nxt = None if action == "show_plan" and not profile.missing_required() else self._next_slot(profile, s)
        if nxt:
            volunteered = [k for k in ("business_type", "city", "employees", "sites", "has_gstin") if k in clean]
            if not faq and (len(volunteered) >= 2 or (volunteered and volunteered != [expecting] and expecting != "gstin")):
                out_msgs.append(self._say(s, t(lang, "advisor.understood", summary=_summary(profile, lang))))
            key = "advisor.only_mobile" if nxt == "mobile_lines" else f"advisor.ask.{nxt}"
            out_msgs.append(self._say(s, t(lang, key), expecting=nxt))
            s.asked = [*s.asked, nxt]
            return self._response(s, out_msgs, None, used_llm, expecting=nxt)

        payload = build_recommendation_payload(profile, lang, self.provider)
        if payload["status"] == "not_serviceable":
            s.state = "not_serviceable"
            out_msgs.append(self._say(s, t(lang, "advisor.not_serviceable", city=profile.city or "")))
            return self._response(s, out_msgs, payload, used_llm, not_serviceable=True)
        s.state = "recommended"
        s.recommendation = {"items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in payload["items"]]}
        out_msgs.append(self._say(s, payload["explanation"], kind="recommendation"))
        for n in payload["notes"]:
            if n["code"] in ("FIBRE_FALLBACK", "GST_BLOCKED", "BUDGET_OVER", "SPEND_COMPARISON"):
                out_msgs.append(self._say(s, n["text"], kind="note"))
        return self._response(s, out_msgs, payload, used_llm)

    def _response(self, s, msgs, payload, used_llm, expecting=None, **flags):
        lang = s.language
        return {"session_id": s.id, "language": lang, "messages": msgs, "expecting": expecting,
                "chips": self._chips(expecting, lang), "multi_select": expecting == "needs",
                "profile": s.profile, "missing": BusinessProfile.model_validate(s.profile).missing_required(),
                "state": s.state, "recommendation": payload,
                "llm": {"provider": self.provider.name if self.provider else "offline", "used": used_llm}, **flags}
