"""GSTIN / Udyam / PAN validation, OCR-confusion repair and masking.

Production vs synthetic
-----------------------
Real GSTINs embed a PAN whose 4th character is the holder type (P, C, H, F, A, T, B, L, J, G).
The competition data uses 'X' there so no record can collide with a real taxpayer, and Udyam
numbers use district code '00'. Both are accepted ONLY when settings.synthetic_identifier_mode
is on (the default for this prototype); with it off the validators apply the real rules.
"""
from __future__ import annotations

import re

from app.config import settings

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PAN_HOLDER_TYPES = set("PCHFATBLJG")
GST_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}
UDYAM_STATE_CODES = {
    "AP": "Andhra Pradesh", "BR": "Bihar", "DL": "Delhi", "GJ": "Gujarat", "KR": "Karnataka", "KA": "Karnataka",
    "KL": "Kerala", "MP": "Madhya Pradesh", "MH": "Maharashtra", "PB": "Punjab", "RJ": "Rajasthan",
    "TN": "Tamil Nadu", "TS": "Telangana", "TG": "Telangana", "UP": "Uttar Pradesh", "WB": "West Bengal",
    "HR": "Haryana", "UK": "Uttarakhand", "OD": "Odisha", "CG": "Chhattisgarh", "JH": "Jharkhand", "AS": "Assam",
    "GA": "Goa", "HP": "Himachal Pradesh", "JK": "Jammu and Kashmir", "CH": "Chandigarh", "PY": "Puducherry",
}

_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "T": "7"}
_TO_ALPHA = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "7": "T", "4": "A"}
# position classes of a GSTIN: D digit, A letter, N alphanumeric, Z literal Z
_GSTIN_SHAPE = "DDAAAAADDDDANZN"


def gstin_checksum(g: str) -> str:
    total = 0
    for i, ch in enumerate(g[:14]):
        v = GSTIN_CHARS.index(ch)
        p = v * (1 if i % 2 == 0 else 2)
        total += p // 36 + p % 36
    return GSTIN_CHARS[(36 - total % 36) % 36]


def normalise_gstin(raw: str | None) -> str | None:
    """Repair OCR confusions using the positional shape only (never changes a valid character class)."""
    if not raw:
        return None
    s = re.sub(r"[^0-9A-Za-z|]", "", raw).upper()
    if len(s) != 15:
        return s or None
    out = []
    for ch, cls in zip(s, _GSTIN_SHAPE):
        if cls == "D" and not ch.isdigit():
            ch = _TO_DIGIT.get(ch, ch)
        elif cls == "A" and not ch.isalpha():
            ch = _TO_ALPHA.get(ch, ch)
        elif cls == "Z" and ch == "2":
            ch = "Z"
        out.append(ch)
    g = "".join(out)
    # positions 13 and 15 are alphanumeric; only try the classic O/0 and I/1 swaps and keep the
    # variant whose checksum validates (never invents other characters)
    if gstin_checksum_ok(g):
        return g
    for i in (12, 14):
        for a, b in (("O", "0"), ("0", "O"), ("I", "1"), ("1", "I")):
            if g[i] == a:
                cand = g[:i] + b + g[i + 1:]
                if gstin_checksum_ok(cand):
                    return cand
    return g


def gstin_checksum_ok(g: str) -> bool:
    try:
        return len(g) == 15 and gstin_checksum(g) == g[14]
    except ValueError:
        return False


def validate_gstin(g: str | None) -> list[str]:
    """Return a list of problems (empty == structurally valid)."""
    if not g:
        return ["GSTIN_MISSING"]
    errs = []
    if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", g):
        return ["GSTIN_FORMAT"]
    if g[:2] not in GST_STATE_CODES:
        errs.append("GSTIN_STATE_CODE")
    holder = g[5]
    if holder not in PAN_HOLDER_TYPES and not (settings.synthetic_identifier_mode and holder == "X"):
        errs.append("GSTIN_PAN_HOLDER_TYPE")
    if not gstin_checksum_ok(g):
        errs.append("GSTIN_CHECKSUM")
    return errs


def normalise_udyam(raw: str | None) -> str | None:
    if not raw:
        return None
    s = re.sub(r"\s+", "", raw).upper().replace("—", "-").replace("–", "-")
    m = re.search(r"UDYAM-?([A-Z0-9]{2})-?([0-9OIL]{2})-?([0-9OILSB]{7})", s)
    if not m:
        return s or None
    st, dist, num = m.groups()
    st = "".join(_TO_ALPHA.get(c, c) for c in st)
    dist = "".join(_TO_DIGIT.get(c, c) for c in dist)
    num = "".join(_TO_DIGIT.get(c, c) for c in num)
    return f"UDYAM-{st}-{dist}-{num}"


def validate_udyam(u: str | None) -> list[str]:
    if not u:
        return ["UDYAM_MISSING"]
    m = re.fullmatch(r"UDYAM-([A-Z]{2})-(\d{2})-(\d{7})", u)
    if not m:
        return ["UDYAM_FORMAT"]
    errs = []
    if m.group(1) not in UDYAM_STATE_CODES:
        errs.append("UDYAM_STATE_CODE")
    if m.group(2) == "00" and not settings.synthetic_identifier_mode:
        errs.append("UDYAM_DISTRICT_CODE")
    return errs


def gstin_state(g: str) -> str | None:
    return GST_STATE_CODES.get(g[:2]) if g else None


def udyam_state(u: str) -> str | None:
    m = re.fullmatch(r"UDYAM-([A-Z]{2})-\d{2}-\d{7}", u or "")
    return UDYAM_STATE_CODES.get(m.group(1)) if m else None


# ------------------------------------------------------------------ masking (UI + logs)
def mask_gstin(g: str | None) -> str | None:
    if not g or len(g) < 6:
        return g
    return g[:2] + "*" * (len(g) - 5) + g[-3:]


def mask_udyam(u: str | None) -> str | None:
    if not u:
        return u
    return re.sub(r"(\d{3})(\d{4})$", r"***\2", u)


def mask_mobile(m: str | None) -> str | None:
    if not m:
        return m
    d = re.sub(r"\D", "", m)
    return "*" * max(0, len(d) - 4) + d[-4:]


def mask_name(n: str | None) -> str | None:
    if not n:
        return n
    return " ".join(p[0] + "." for p in n.split() if p)


_PII_PATTERNS = [
    (re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b"), lambda m: mask_gstin(m.group(0))),
    (re.compile(r"UDYAM-[A-Z]{2}-\d{2}-\d{7}"), lambda m: mask_udyam(m.group(0))),
    (re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"), lambda m: mask_mobile(m.group(0))),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), lambda m: m.group(0)[:2] + "*****" + m.group(0)[-3:]),
]


def scrub(text: str) -> str:
    """Mask identifiers in free text before it is logged or sent to an external model."""
    for pat, fn in _PII_PATTERNS:
        text = pat.sub(fn, text)
    return text
