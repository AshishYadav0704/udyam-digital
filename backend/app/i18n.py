"""Server-side message catalogue. Adding a language = adding app/locales/<code>.json (missing keys fall back to English)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES = Path(__file__).parent / "locales"
SUPPORTED = ("en", "hi")
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi"}


@lru_cache(maxsize=8)
def _catalog(lang: str) -> dict:
    p = LOCALES / f"{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _get(d: dict, path: str):
    for part in path.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def t(lang: str, key: str, **kw):
    lang = lang if lang in SUPPORTED else "en"
    val = _get(_catalog(lang), key)
    if val is None:
        val = _get(_catalog("en"), key)
    if val is None:
        return key
    if isinstance(val, str) and kw:
        return val.format_map(_SafeDict(**kw))
    return val


def fmt_inr(x: float) -> str:
    """Indian digit grouping: 1234567.5 -> 12,34,567.50 (paise only when non-zero)."""
    neg = x < 0
    x = abs(x)
    whole = int(x)
    paise = round((x - whole) * 100)
    if paise == 100:
        whole, paise = whole + 1, 0
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    out = s + (f".{paise:02d}" if paise else "")
    return ("-" if neg else "") + out
