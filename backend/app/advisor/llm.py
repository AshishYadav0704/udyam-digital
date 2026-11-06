"""Configurable GenAI provider layer.

The LLM is used for two narrow jobs only:
  1. extract a structured business-profile update from free text (tool / JSON-schema output), and
  2. rephrase an already-computed recommendation in plain Hindi or English.
It never decides eligibility, products, quantities or prices - those come from the deterministic engine -
and anything it returns is schema-validated (and, for explanations, fact-checked) before use.
Identifiers are masked before any text leaves the server. On timeout, error or invalid output the
advisor silently falls back to the offline extractor / template text.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from app.config import settings
from app.domain.business_types import TYPES
from app.domain.identifiers import scrub
from app.domain.profile import NEED_TAGS

log = logging.getLogger("app.llm")

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "business_type": {"type": "string", "description": "Closest canonical business type, or empty",
                          "enum": [t.name for t in TYPES] + [""]},
        "city": {"type": "string", "description": "City name in English, or empty"},
        "employees": {"type": "integer", "description": "People working in the business incl. owner; 0 if unknown"},
        "sites": {"type": "integer", "description": "Number of shops/branches/offices/factories; 0 if unknown"},
        "has_gstin": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "gst_status_declared": {"type": "string", "enum": ["active", "cancelled", "suspended", "unknown"]},
        "needs": {"type": "array", "items": {"type": "string", "enum": list(NEED_TAGS)}},
        "excluded_needs": {"type": "array", "items": {"type": "string", "enum": list(NEED_TAGS)}},
        "monthly_spend": {"type": "integer", "description": "Current monthly telecom spend in INR; 0 if unknown"},
        "budget": {"type": "integer", "description": "Stated monthly budget in INR; 0 if unknown"},
        "fibre_available": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "only_mobile": {"type": "boolean"},
        "wants_human": {"type": "boolean"},
        "quantities": {"type": "object", "properties": {k: {"type": "integer"} for k in
                       ("cameras", "vehicles", "machines", "mobile_lines", "email_users", "counters")}},
        "language": {"type": "string", "enum": ["en", "hi"]},
    },
    "required": ["business_type", "city", "employees", "sites", "has_gstin", "needs", "wants_human", "language"],
}

SYSTEM_EXTRACT = (
    "You extract facts about an Indian small business from a conversation with its owner, for a telecom "
    "onboarding advisor. Owners write in English, Hindi (Devanagari) or Hinglish. Extract ONLY what the owner "
    "stated or clearly implied in the latest message (use earlier turns for context). Never guess sizes. Map "
    "needs only to the allowed tags. Do not recommend products and do not mention prices. Always answer by "
    "calling the tool."
)
SYSTEM_EXPLAIN = (
    "You rewrite a telecom plan recommendation for an Indian small-business owner in plain, warm, short language. "
    "Use ONLY the facts provided: do not add products, features, prices, discounts or promises. Mention at most "
    "the numbers given. 2-4 sentences. No markdown. Reply in {language}."
)


class ProviderError(Exception):
    pass


class BaseProvider:
    name = "base"

    def extract(self, history: list[dict], latest: str) -> dict | None:
        raise NotImplementedError

    def explain(self, facts: dict, lang: str) -> str | None:
        raise NotImplementedError


def _history_text(history: list[dict], latest: str) -> str:
    lines = [f"{m['role']}: {scrub(m['text'])}" for m in history[-8:]]
    lines.append(f"user (latest): {scrub(latest)}")
    return "\n".join(lines)


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def _post(self, body: dict) -> dict:
        r = httpx.post(self.URL, json=body, timeout=settings.llm_timeout_s, headers={
            "x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        if r.status_code != 200:
            raise ProviderError(f"anthropic {r.status_code}")
        return r.json()

    def extract(self, history, latest):
        body = {"model": settings.anthropic_model, "max_tokens": 600, "system": SYSTEM_EXTRACT,
                "tools": [{"name": "update_business_profile", "description": "Record facts about the business",
                           "input_schema": EXTRACT_SCHEMA}],
                "tool_choice": {"type": "tool", "name": "update_business_profile"},
                "messages": [{"role": "user", "content": _history_text(history, latest)}]}
        data = self._post(body)
        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                return block.get("input")
        raise ProviderError("no tool_use block")

    def explain(self, facts, lang):
        body = {"model": settings.anthropic_model, "max_tokens": 300,
                "system": SYSTEM_EXPLAIN.format(language="Hindi" if lang == "hi" else "English"),
                "messages": [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]}
        data = self._post(body)
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip() or None


class OpenAIProvider(BaseProvider):
    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def _post(self, body):
        r = httpx.post(self.URL, json=body, timeout=settings.llm_timeout_s,
                       headers={"Authorization": f"Bearer {settings.openai_api_key}"})
        if r.status_code != 200:
            raise ProviderError(f"openai {r.status_code}")
        return r.json()

    def extract(self, history, latest):
        body = {"model": settings.openai_model, "messages": [
            {"role": "system", "content": SYSTEM_EXTRACT}, {"role": "user", "content": _history_text(history, latest)}],
            "tools": [{"type": "function", "function": {"name": "update_business_profile", "parameters": EXTRACT_SCHEMA}}],
            "tool_choice": {"type": "function", "function": {"name": "update_business_profile"}}}
        data = self._post(body)
        calls = data["choices"][0]["message"].get("tool_calls") or []
        if not calls:
            raise ProviderError("no tool call")
        return json.loads(calls[0]["function"]["arguments"])

    def explain(self, facts, lang):
        body = {"model": settings.openai_model, "messages": [
            {"role": "system", "content": SYSTEM_EXPLAIN.format(language="Hindi" if lang == "hi" else "English")},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]}
        return (self._post(body)["choices"][0]["message"].get("content") or "").strip() or None


def gemini_schema(node):
    """Gemini's `responseSchema` takes the OpenAPI subset, whose type names are upper case (OBJECT, STRING, ...)."""
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "type" and isinstance(v, str):
            out[k] = v.upper()
        elif k == "properties" and isinstance(v, dict):
            out[k] = {name: gemini_schema(s) for name, s in v.items()}
        elif k == "items":
            out[k] = gemini_schema(v)
        else:
            out[k] = v
    return out


class GeminiProvider(BaseProvider):
    name = "gemini"

    def _url(self):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"

    def _post(self, body):
        r = httpx.post(self._url(), json=body, timeout=settings.llm_timeout_s,
                       headers={"x-goog-api-key": settings.gemini_api_key})
        if r.status_code != 200:
            raise ProviderError(f"gemini {r.status_code}")
        return r.json()

    @staticmethod
    def _text(data: dict) -> str:
        cands = data.get("candidates") or []
        if not cands:
            raise ProviderError("no candidates (blocked or empty)")
        parts = (cands[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    def extract(self, history, latest):
        schema = json.loads(json.dumps(EXTRACT_SCHEMA))
        schema["properties"]["business_type"].pop("enum", None)       # enum with "" is outside Gemini's subset
        body = {"systemInstruction": {"parts": [{"text": SYSTEM_EXTRACT}]},
                "contents": [{"role": "user", "parts": [{"text": _history_text(history, latest)}]}],
                "generationConfig": {"responseMimeType": "application/json", "responseSchema": gemini_schema(schema)}}
        return json.loads(self._text(self._post(body)))

    def explain(self, facts, lang):
        body = {"systemInstruction": {"parts": [{"text": SYSTEM_EXPLAIN.format(language="Hindi" if lang == "hi" else "English")}]},
                "contents": [{"role": "user", "parts": [{"text": json.dumps(facts, ensure_ascii=False)}]}]}
        return self._text(self._post(body)).strip() or None


def get_provider() -> BaseProvider | None:
    choice = settings.llm_provider
    if choice == "offline":
        return None
    order = [choice] if choice != "auto" else ["anthropic", "openai", "gemini"]
    for c in order:
        if c == "anthropic" and settings.anthropic_api_key:
            return AnthropicProvider()
        if c == "openai" and settings.openai_api_key:
            return OpenAIProvider()
        if c == "gemini" and settings.gemini_api_key:
            return GeminiProvider()
    return None


# ------------------------------------------------------------------ validation of model output
def normalise_llm_extraction(raw: dict | None) -> dict:
    """Convert the tool payload into BusinessProfile fields; drop anything out of range or unknown."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    names = {t.name for t in TYPES}
    if raw.get("business_type") in names:
        out["business_type"] = raw["business_type"]
    if isinstance(raw.get("city"), str) and 1 < len(raw["city"]) <= 40:
        out["city"] = raw["city"].strip()
    for k, lo, hi in (("employees", 1, 5000), ("sites", 1, 200), ("monthly_spend", 1, 10_000_000), ("budget", 1, 10_000_000)):
        v = raw.get(k)
        if isinstance(v, int) and lo <= v <= hi:
            out[k] = v
    if raw.get("has_gstin") in ("yes", "no"):
        out["has_gstin"] = raw["has_gstin"] == "yes"
    if raw.get("gst_status_declared") in ("cancelled", "suspended"):
        out["has_gstin"] = True
        out["gstin_status"] = raw["gst_status_declared"].title()
    if raw.get("fibre_available") in ("yes", "no"):
        out["fibre_available"] = raw["fibre_available"] == "yes"
    for k in ("needs", "excluded_needs"):
        v = raw.get(k)
        if isinstance(v, list):
            out[k] = [x for x in v if x in NEED_TAGS and x != "internet"]
    if raw.get("only_mobile") is True:
        out["only_mobile"] = True
    if raw.get("wants_human") is True:
        out["_escalate"] = True
    q = raw.get("quantities") or {}
    if isinstance(q, dict):
        for k in ("cameras", "vehicles", "machines", "mobile_lines", "email_users", "counters"):
            if isinstance(q.get(k), int) and 0 < q[k] <= 500:
                out[k] = q[k]
    if raw.get("language") == "hi":
        out["_lang"] = "hi"
    return out


_MONEY = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def explanation_is_grounded(text: str, allowed_numbers: set[str], bundle_names: set[str], all_names: set[str]) -> bool:
    """Reject explanations that mention a price we did not compute or a product outside the bundle."""
    for m in _MONEY.finditer(text):
        if m.group(1).replace(",", "").rstrip("0").rstrip(".") not in allowed_numbers:
            return False
    lowered = text.lower()
    for n in all_names - bundle_names:
        if n.lower() in lowered:
            return False
    return len(text) < 900
