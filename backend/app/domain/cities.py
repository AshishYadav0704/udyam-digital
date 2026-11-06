"""City -> tier / state lookup.

Source of truth for the 22 cities in smb_leads.csv is the dataset itself. Other cities use
the Government of India HRA city classification (X = tier 1, Y = tier 2) as a proxy; this is
an ASSUMPTION for the prototype - production would use Accel's serviceability master.
Cities not found are treated as tier 3, which no catalogue product is sold in, so the
journey routes them to a partner instead of quoting.
"""
from __future__ import annotations

import re
import unicodedata

# (tier, state) - the 22 dataset cities first
DATASET_CITIES = {
    "Ahmedabad": (1, "Gujarat"), "Bengaluru": (1, "Karnataka"), "Chennai": (1, "Tamil Nadu"),
    "Delhi": (1, "Delhi"), "Hyderabad": (1, "Telangana"), "Kolkata": (1, "West Bengal"),
    "Mumbai": (1, "Maharashtra"), "Pune": (1, "Maharashtra"),
    "Bhopal": (2, "Madhya Pradesh"), "Coimbatore": (2, "Tamil Nadu"), "Indore": (2, "Madhya Pradesh"),
    "Jaipur": (2, "Rajasthan"), "Kochi": (2, "Kerala"), "Lucknow": (2, "Uttar Pradesh"),
    "Ludhiana": (2, "Punjab"), "Mysuru": (2, "Karnataka"), "Nagpur": (2, "Maharashtra"),
    "Nashik": (2, "Maharashtra"), "Patna": (2, "Bihar"), "Surat": (2, "Gujarat"),
    "Vadodara": (2, "Gujarat"), "Visakhapatnam": (2, "Andhra Pradesh"),
}

# HRA 'Y' class cities (proxy for tier 2) - not exhaustive, extend from the serviceability master
Y_CITIES = {
    "Agra": "Uttar Pradesh", "Ajmer": "Rajasthan", "Aligarh": "Uttar Pradesh", "Amravati": "Maharashtra",
    "Amritsar": "Punjab", "Asansol": "West Bengal", "Aurangabad": "Maharashtra", "Bareilly": "Uttar Pradesh",
    "Belagavi": "Karnataka", "Bhavnagar": "Gujarat", "Bhubaneswar": "Odisha", "Bikaner": "Rajasthan",
    "Bilaspur": "Chhattisgarh", "Chandigarh": "Chandigarh", "Cuttack": "Odisha", "Dehradun": "Uttarakhand",
    "Dhanbad": "Jharkhand", "Durgapur": "West Bengal", "Erode": "Tamil Nadu", "Faridabad": "Haryana",
    "Ghaziabad": "Uttar Pradesh", "Gorakhpur": "Uttar Pradesh", "Gurugram": "Haryana", "Guntur": "Andhra Pradesh",
    "Guwahati": "Assam", "Gwalior": "Madhya Pradesh", "Hubballi": "Karnataka", "Jabalpur": "Madhya Pradesh",
    "Jalandhar": "Punjab", "Jammu": "Jammu and Kashmir", "Jamnagar": "Gujarat", "Jamshedpur": "Jharkhand",
    "Jhansi": "Uttar Pradesh", "Jodhpur": "Rajasthan", "Kakinada": "Andhra Pradesh", "Kalaburagi": "Karnataka",
    "Kanpur": "Uttar Pradesh", "Kolhapur": "Maharashtra", "Kollam": "Kerala", "Kota": "Rajasthan",
    "Kozhikode": "Kerala", "Kurnool": "Andhra Pradesh", "Madurai": "Tamil Nadu", "Malappuram": "Kerala",
    "Mangaluru": "Karnataka", "Mathura": "Uttar Pradesh", "Meerut": "Uttar Pradesh", "Moradabad": "Uttar Pradesh",
    "Nanded": "Maharashtra", "Nellore": "Andhra Pradesh", "Noida": "Uttar Pradesh", "Prayagraj": "Uttar Pradesh",
    "Puducherry": "Puducherry", "Raipur": "Chhattisgarh", "Rajahmundry": "Andhra Pradesh", "Rajkot": "Gujarat",
    "Ranchi": "Jharkhand", "Rourkela": "Odisha", "Salem": "Tamil Nadu", "Sangli": "Maharashtra",
    "Shimla": "Himachal Pradesh", "Siliguri": "West Bengal", "Solapur": "Maharashtra", "Srinagar": "Jammu and Kashmir",
    "Thiruvananthapuram": "Kerala", "Thrissur": "Kerala", "Tiruchirappalli": "Tamil Nadu", "Tirunelveli": "Tamil Nadu",
    "Tiruppur": "Tamil Nadu", "Ujjain": "Madhya Pradesh", "Varanasi": "Uttar Pradesh", "Vasai-Virar": "Maharashtra",
    "Vellore": "Tamil Nadu", "Vijayawada": "Andhra Pradesh", "Warangal": "Telangana", "Gandhinagar": "Gujarat",
}

ALIASES = {
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru", "bombay": "Mumbai", "calcutta": "Kolkata",
    "madras": "Chennai", "new delhi": "Delhi", "dilli": "Delhi", "mysore": "Mysuru", "vizag": "Visakhapatnam",
    "cochin": "Kochi", "ernakulam": "Kochi", "baroda": "Vadodara", "gurgaon": "Gurugram", "allahabad": "Prayagraj",
    "trivandrum": "Thiruvananthapuram", "calicut": "Kozhikode", "mangalore": "Mangaluru", "hubli": "Hubballi",
    "belgaum": "Belagavi", "gulbarga": "Kalaburagi", "trichy": "Tiruchirappalli", "banaras": "Varanasi",
    "benares": "Varanasi", "kashi": "Varanasi",
    # Devanagari spellings used by Hindi-speaking owners
    "दिल्ली": "Delhi", "नई दिल्ली": "Delhi", "मुंबई": "Mumbai", "बेंगलुरु": "Bengaluru", "बैंगलोर": "Bengaluru",
    "कोलकाता": "Kolkata", "चेन्नई": "Chennai", "हैदराबाद": "Hyderabad", "अहमदाबाद": "Ahmedabad", "पुणे": "Pune",
    "जयपुर": "Jaipur", "लखनऊ": "Lucknow", "पटना": "Patna", "भोपाल": "Bhopal", "इंदौर": "Indore", "नागपुर": "Nagpur",
    "नासिक": "Nashik", "सूरत": "Surat", "वडोदरा": "Vadodara", "लुधियाना": "Ludhiana", "कोच्चि": "Kochi",
    "मैसूर": "Mysuru", "कोयंबटूर": "Coimbatore", "विशाखापत्तनम": "Visakhapatnam", "गोरखपुर": "Gorakhpur",
    "कानपुर": "Kanpur", "वाराणसी": "Varanasi", "आगरा": "Agra", "नोएडा": "Noida", "गुड़गांव": "Gurugram",
    "गुरुग्राम": "Gurugram", "प्रयागराज": "Prayagraj", "मेरठ": "Meerut", "चंडीगढ़": "Chandigarh", "देहरादून": "Dehradun",
    "रांची": "Ranchi", "रायपुर": "Raipur", "जोधपुर": "Jodhpur", "उदयपुर": "Udaipur", "अमृतसर": "Amritsar",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).strip().lower()
    return re.sub(r"\s+", " ", s)


_INDEX: dict[str, tuple[str, int, str]] = {}
for c, (t, st) in DATASET_CITIES.items():
    _INDEX[_norm(c)] = (c, t, st)
for c, st in Y_CITIES.items():
    _INDEX.setdefault(_norm(c), (c, 2, st))
for alias, c in ALIASES.items():
    if _norm(c) in _INDEX:
        _INDEX[_norm(alias)] = _INDEX[_norm(c)]
    else:
        _INDEX[_norm(alias)] = (c, 3, "")


def lookup_city(name: str | None) -> tuple[str, int, str] | None:
    """Return (canonical city, tier, state) or None if the text is not a known city."""
    if not name:
        return None
    return _INDEX.get(_norm(name))


def find_city_in_text(text: str) -> tuple[str, int, str] | None:
    """Longest known city/alias mentioned in free text (English or Devanagari)."""
    t = _norm(text)
    best = None
    for key, val in _INDEX.items():
        if len(key) < 3:
            continue
        pattern = r"(?<![\wऀ-ॿ])" + re.escape(key) + r"(?![\wऀ-ॿ])"
        if re.search(pattern, t):
            if best is None or len(key) > len(best[0]):
                best = (key, val)
    return best[1] if best else None


def tier_for(city: str | None, declared_tier: int | None = None) -> int:
    hit = lookup_city(city) if city else None
    if hit:
        return hit[1]
    return declared_tier or 3


def all_known_cities() -> list[dict]:
    seen = {}
    for c, t, st in _INDEX.values():
        seen.setdefault(c, {"city": c, "tier": t, "state": st})
    return sorted(seen.values(), key=lambda x: (x["tier"], x["city"]))
