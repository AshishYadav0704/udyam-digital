"""Configuration loading (.env) and the GenAI provider adapters, tested without network access.

The provider tests replace httpx.post with a recorder that returns canned responses in each vendor's documented
shape, so they check what we send (URL, auth header, tool/schema contract, masked text) and how we parse the reply.
They do not prove that a live key works; `scripts/eval_advisor.py --provider` does that with a real key.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app import config
from app.advisor import llm
from app.config import settings

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
CONFIG_KEYS = ("APP_ENV", "JWT_SECRET", "DOC_ENCRYPTION_KEY", "PII_PEPPER", "DATA_DIR", "STORAGE_DIR", "DATABASE_URL",
               "PROPENSITY_MODEL_PATH", "PRICE_POLICY", "GST_RATE", "QUOTE_VALIDITY_DAYS", "KYC_REFERENCE_DATE",
               "ADDRESS_PROOF_MAX_AGE_DAYS", "SYNTHETIC_IDENTIFIER_MODE", "DEMO_OTP", "DEMO_STAFF_PASSWORD",
               "LLM_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_MODEL",
               "OPENAI_MODEL", "GEMINI_MODEL", "CORS_ORIGINS")


# ------------------------------------------------------------------ .env handling
def test_env_example_parses_to_clean_values():
    env = config.parse_dotenv(ROOT / ".env.example")
    assert env["APP_ENV"] == "development"
    assert env["KYC_REFERENCE_DATE"] == "2026-07-15"
    assert env["SYNTHETIC_IDENTIFIER_MODE"] == "true"
    assert env["PRICE_POLICY"] == "midpoint"
    assert env["LLM_PROVIDER"] == "auto"
    assert env["JWT_SECRET"] == "" and env["DOC_ENCRYPTION_KEY"] == "" and env["PII_PEPPER"] == ""
    assert not any("#" in v for v in env.values()), "a comment leaked into a value"


def test_parse_dotenv_comments_quotes_and_export(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A=1   # trailing comment\n"
                 'B="x # not a comment"  # comment\n'
                 "C='single'\n"
                 "export D=4\n"
                 "E=#kept-because-no-space-before-hash\n"
                 "F=\n"
                 "G=    # only a comment\n"
                 "# H=commented out\n"
                 "I=http://a:1,http://b:2\n", encoding="utf-8")
    env = config.parse_dotenv(f)
    assert env == {"A": "1", "B": "x # not a comment", "C": "single", "D": "4",
                   "E": "#kept-because-no-space-before-hash", "F": "", "G": "", "I": "http://a:1,http://b:2"}


def test_settings_load_from_env_example_from_any_directory(tmp_path):
    """Regression: `cp .env.example .env` used to crash startup (inline comments were read as part of values)."""
    env = {k: v for k, v in os.environ.items() if k not in CONFIG_KEYS}
    env.update(config.parse_dotenv(ROOT / ".env.example"))
    env.update({
        "DATA_DIR": "../data/raw",                                         # relative: resolved from backend/
        "PROPENSITY_MODEL_PATH": "../ml/artifacts/propensity_model.joblib",
        "STORAGE_DIR": str(tmp_path / "storage"),                          # keep the test away from real storage
        "DATABASE_URL": f"sqlite:///{tmp_path / 'storage' / 'x.db'}",
        "PYTHONPATH": str(BACKEND),
    })
    code = ("import json; from app.config import settings as s; print(json.dumps({'env': s.env, "
            "'date': str(s.kyc_reference_date), 'synthetic': s.synthetic_identifier_mode, 'policy': s.price_policy, "
            "'provider': s.llm_provider, 'data_dir': str(s.data_dir), 'model': s.model_path.exists(), "
            "'gst': s.gst_rate}))")
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got == {"env": "development", "date": "2026-07-15", "synthetic": True, "policy": "midpoint",
                   "provider": "auto", "data_dir": str(ROOT / "data" / "raw"), "model": True, "gst": 0.18}


def test_empty_kyc_reference_date_means_today(monkeypatch):
    monkeypatch.setenv("X_KYC_DATE_TEST", "")
    assert config._optional_date("X_KYC_DATE_TEST", "2026-07-15") is None
    monkeypatch.delenv("X_KYC_DATE_TEST")
    assert config._optional_date("X_KYC_DATE_TEST", "2026-07-15") == date(2026, 7, 15)


def test_relative_sqlite_url_is_anchored_to_backend():
    assert config.resolve_sqlite_url("sqlite:///../storage/udyam.db") == f"sqlite:///{ROOT / 'storage' / 'udyam.db'}"
    assert config.resolve_sqlite_url("sqlite:////abs/x.db") == "sqlite:////abs/x.db"
    assert config.resolve_sqlite_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert config.resolve_sqlite_url("postgresql://u@h/db") == "postgresql://u@h/db"


# ------------------------------------------------------------------ provider adapters (no network)
class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def _record(monkeypatch, payload: dict, status: int = 200) -> list[dict]:
    calls: list[dict] = []

    def fake_post(url, json=None, timeout=None, headers=None, **_):
        calls.append({"url": url, "body": json, "headers": headers or {}, "timeout": timeout})
        return _Resp(status, payload)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    return calls


PROFILE = {"business_type": "Pharmacy", "city": "Lucknow", "employees": 4, "sites": 1, "has_gstin": "yes",
           "gst_status_declared": "active", "needs": ["billing_pos", "cctv"], "excluded_needs": [],
           "wants_human": False, "language": "en", "quantities": {"cameras": 4}}
HISTORY = [{"role": "user", "text": "Call me on 9876543210, GSTIN 09ABCDE1234F1Z5"}]
LATEST = "We are a chemist shop in Lucknow, 4 of us, need billing and 4 cameras"


def _assert_masked(body: dict):
    blob = json.dumps(body)
    assert "9876543210" not in blob and "09ABCDE1234F1Z5" not in blob, "identifiers must be masked before leaving"


def test_anthropic_adapter_request_and_parsing(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    calls = _record(monkeypatch, {"content": [{"type": "text", "text": "Recording."},
                                              {"type": "tool_use", "name": "update_business_profile", "input": PROFILE}]})
    raw = llm.AnthropicProvider().extract(HISTORY, LATEST)
    c = calls[0]
    assert c["url"] == "https://api.anthropic.com/v1/messages"
    assert c["headers"]["x-api-key"] == "sk-ant-test" and c["headers"]["anthropic-version"] == "2023-06-01"
    assert c["body"]["model"] == settings.anthropic_model
    assert c["body"]["tool_choice"] == {"type": "tool", "name": "update_business_profile"}
    assert c["body"]["tools"][0]["input_schema"]["properties"]["needs"]["items"]["enum"]
    assert c["timeout"] == settings.llm_timeout_s
    _assert_masked(c["body"])
    upd = llm.normalise_llm_extraction(raw)
    assert upd["business_type"] == "Pharmacy" and upd["employees"] == 4 and upd["cameras"] == 4
    assert upd["has_gstin"] is True and set(upd["needs"]) == {"billing_pos", "cctv"}


def test_anthropic_adapter_errors_raise(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    _record(monkeypatch, {"type": "error"}, status=529)
    with pytest.raises(llm.ProviderError):
        llm.AnthropicProvider().extract([], LATEST)
    _record(monkeypatch, {"content": [{"type": "text", "text": "no tool"}]})
    with pytest.raises(llm.ProviderError):
        llm.AnthropicProvider().extract([], LATEST)


def test_openai_adapter_request_and_parsing(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-oa-test")
    calls = _record(monkeypatch, {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function",
         "function": {"name": "update_business_profile", "arguments": json.dumps(PROFILE)}}]}}]})
    raw = llm.OpenAIProvider().extract(HISTORY, LATEST)
    c = calls[0]
    assert c["url"] == "https://api.openai.com/v1/chat/completions"
    assert c["headers"]["Authorization"] == "Bearer sk-oa-test"
    assert c["body"]["model"] == settings.openai_model
    assert c["body"]["tools"][0]["type"] == "function"
    assert c["body"]["tools"][0]["function"]["parameters"]["type"] == "object"
    assert c["body"]["tool_choice"] == {"type": "function", "function": {"name": "update_business_profile"}}
    _assert_masked(c["body"])
    assert llm.normalise_llm_extraction(raw)["city"] == "Lucknow"
    _record(monkeypatch, {"choices": [{"message": {"content": "  Your plan, in short.  "}}]})
    assert llm.OpenAIProvider().explain({"plan": []}, "en") == "Your plan, in short."


def test_gemini_adapter_request_and_parsing(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "gm-test")
    calls = _record(monkeypatch, {"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(PROFILE)}]}}]})
    raw = llm.GeminiProvider().extract(HISTORY, LATEST)
    c = calls[0]
    assert c["url"] == f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    assert c["headers"]["x-goog-api-key"] == "gm-test"
    gc = c["body"]["generationConfig"]
    assert gc["responseMimeType"] == "application/json"
    types = []

    def walk(n):
        if isinstance(n, dict):
            if isinstance(n.get("type"), str):
                types.append(n["type"])
            for k, v in n.items():
                if k in ("properties",):
                    for s in v.values():
                        walk(s)
                elif k == "items":
                    walk(v)
    walk(gc["responseSchema"])
    assert types and all(t == t.upper() for t in types), types      # OpenAPI-subset casing
    assert gc["responseSchema"]["properties"]["quantities"]["properties"]["cameras"]["type"] == "INTEGER"
    _assert_masked(c["body"])
    assert llm.normalise_llm_extraction(raw)["sites"] == 1
    _record(monkeypatch, {"candidates": [{"content": {"parts": [{"text": "Short plan."}]}}]})
    assert llm.GeminiProvider().explain({"plan": []}, "hi") == "Short plan."
    _record(monkeypatch, {"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(llm.ProviderError):
        llm.GeminiProvider().extract([], LATEST)


def test_provider_selection(monkeypatch):
    for k in ("anthropic_api_key", "openai_api_key", "gemini_api_key"):
        monkeypatch.setattr(settings, k, "")
    monkeypatch.setattr(settings, "llm_provider", "auto")
    assert llm.get_provider() is None
    monkeypatch.setattr(settings, "gemini_api_key", "g")
    assert isinstance(llm.get_provider(), llm.GeminiProvider)
    monkeypatch.setattr(settings, "anthropic_api_key", "a")
    assert isinstance(llm.get_provider(), llm.AnthropicProvider)          # auto order: anthropic, openai, gemini
    monkeypatch.setattr(settings, "llm_provider", "openai")
    assert llm.get_provider() is None                                     # named provider without its key
    monkeypatch.setattr(settings, "llm_provider", "offline")
    assert llm.get_provider() is None


# ------------------------------------------------------------------ the journey survives a bad or failing model
class _FailingProvider(llm.BaseProvider):
    name = "failing"

    def extract(self, history, latest):
        raise llm.ProviderError("timeout")

    def explain(self, facts, lang):
        raise llm.ProviderError("timeout")


class _OverreachingProvider(llm.BaseProvider):
    """Returns out-of-range fields and an explanation with an invented price and an extra product."""
    name = "overreaching"

    def extract(self, history, latest):
        return {"business_type": "Space agency", "employees": 999999, "sites": -2, "needs": ["free_iphone"],
                "city": "Delhi", "has_gstin": "yes", "wants_human": False, "language": "en"}

    def explain(self, facts, lang):
        return "Great news: everything is only ₹99 a month, and we add a Leased line for free."


def _advise(monkeypatch, provider, text="I run a CA firm in Delhi, 12 employees, one office, GST registered"):
    """One owner message through the real API with `provider` plugged in; returns (first reply, final reply)."""
    from fastapi.testclient import TestClient

    from app.main import app
    monkeypatch.setattr(llm, "get_provider", lambda: provider)
    with TestClient(app) as c:
        s = c.post("/api/advisor/sessions", json={"language": "en"}).json()
        H = {"X-Session-Token": s["session_token"]}
        url = f"/api/advisor/sessions/{s['session_id']}/messages"
        r = c.post(url, headers=H, json={"text": text})
        assert r.status_code == 200, r.text
        first = last = r.json()
        if last["state"] != "recommended":
            last = c.post(url, headers=H, json={"action": "show_plan"}).json()
    return first, last


class _HonestProvider(llm.BaseProvider):
    name = "honest"

    def extract(self, history, latest):
        return {"business_type": "", "city": "", "employees": 0, "sites": 0, "has_gstin": "unknown", "needs": [],
                "wants_human": False, "language": "en"}

    def explain(self, facts, lang):
        return "This plan keeps your office online and your client files backed up."


def test_grounded_explanation_from_provider_is_used(monkeypatch):
    """Control for the test below: the explanation path is exercised, so a 'template' result there is a rejection."""
    _, last = _advise(monkeypatch, _HonestProvider())
    assert last["recommendation"]["explanation_source"] == "llm"
    assert last["recommendation"]["explanation"].startswith("This plan keeps your office online")


def test_failing_provider_falls_back_to_offline(monkeypatch):
    first, last = _advise(monkeypatch, _FailingProvider())
    assert first["llm"] == {"provider": "failing", "used": False}
    assert first["profile"]["business_type"] == "CA firm" and first["profile"]["employees"] == 12
    assert last["state"] == "recommended"
    assert last["recommendation"]["explanation_source"] == "template"


def test_overreaching_provider_cannot_change_rules_or_prices(monkeypatch):
    first, last = _advise(monkeypatch, _OverreachingProvider())
    assert first["llm"]["used"] is True
    prof = last["profile"]
    assert prof["business_type"] == "CA firm" and prof["employees"] == 12 and prof["sites"] == 1
    assert last["state"] == "recommended"
    rec = last["recommendation"]
    assert rec["explanation_source"] == "template"                        # invented ₹99 and extra product rejected
    assert "free_iphone" not in json.dumps(last) and "Space agency" not in json.dumps(last)
    assert rec["quote"]["monthly_subtotal"] > 99


# ------------------------------------------------------------------ the evaluation script's provider path
def test_eval_script_merges_provider_output():
    spec = importlib.util.spec_from_file_location("eval_advisor", ROOT / "scripts" / "eval_advisor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class Stub(llm.BaseProvider):
        name = "stub"

        def extract(self, history, latest):
            return {"business_type": "Pharmacy", "city": "Kanpur", "employees": 3, "sites": 1, "has_gstin": "unknown",
                    "needs": ["cctv"], "wants_human": False, "language": "en"}

    got = mod.with_provider(Stub())("dawai ki dukaan hai, camera chahiye")
    assert got["business_type"] == "Pharmacy" and got["employees"] == 3 and "cctv" in got["needs"]
    failing = mod.with_provider(_FailingProvider())("we have 5 people")
    assert failing.get("employees") == 5                                   # offline result kept on provider failure
