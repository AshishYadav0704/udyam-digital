"""Offline, deterministic language understanding for the advisor (English, Hinglish and Hindi).

Runs on every message, with or without an LLM. When an LLM is configured its structured output is
merged on top; when the LLM is unavailable or returns something invalid, this extractor alone keeps
the journey working. Everything it returns is validated by BusinessProfile.
"""
from __future__ import annotations

import re
import unicodedata

from app.domain import cities
from app.domain.business_types import match_business_type
from app.domain.identifiers import normalise_gstin, normalise_udyam, validate_gstin

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "twenty five": 25, "thirty": 30, "forty": 40, "fifty": 50,
    "hundred": 100, "a hundred": 100,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20, "pachchis": 25, "tees": 30,
    "chalis": 40, "pachas": 50, "pachaas": 50, "sau": 100,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9,
    "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50, "सौ": 100,
}
B = r"(?<![\wऀ-ॿ])"     # word boundary that also respects Devanagari
E = r"(?![\wऀ-ॿ])"

NEED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "backup_internet": ("backup internet", "internet backup", "failover", "net goes down", "internet goes down", "downtime",
                        "net chala jata", "net chala jaata", "net band", "नेट चला जाता", "इंटरनेट बंद", "बैकअप इंटरनेट", "always on internet"),
    "dedicated_line": ("leased line", "dedicated line", "dedicated internet", "guaranteed bandwidth", " sla", "ill line", "लीज़्ड लाइन", "लीज्ड लाइन"),
    "mobile_lines": ("sim", "sims", "mobile line", "mobile lines", "postpaid", "mobile connection", "mobile connections", "phone lines for staff",
                     "सिम", "मोबाइल कनेक्शन", "मोबाइल लाइन", "staff phones", "business numbers"),
    "cloud_email": ("email", "e-mail", "emails", "mailbox", "office suite", "google workspace", "microsoft 365", "office 365", "ईमेल", "मेल"),
    "backup_storage": (
    "backup", "data backup", "backup of data", "cloud storage",
    "file backup", "backup my data", "डेटा बैकअप", "डाटा बैकअप"
),
    "website": ("website", "web site", "online presence", "वेबसाइट"),
    "billing_pos": ("billing", "pos", "point of sale", "upi", "card machine", "card payments", "invoice", "बिलिंग", "बिल बनाने", "भुगतान मशीन"),
    "endpoint_security": ("antivirus", "anti-virus", "virus", "ransomware", "malware", "एंटीवायरस", "वायरस"),
    "firewall": ("firewall", "network security", "hacking", "hackers", "फ़ायरवॉल", "फायरवॉल"),
   "wifi_guest": (
    "guest wifi", "guest wi-fi", "guest network",
    "customer wifi", "customer wi-fi", "wifi for customers",
    "wi-fi for customers", "guests need wifi",
    "free wifi", "visitor wifi", "wifi for visitors",
    "ग्राहकों के लिए वाईफाई",
    "ग्राहकों के लिए वाई-फाई",
    "ग्राहकों के लिए वाई-फ़ाई",
    "ग्राहकों के लिए वाईफ़ाई"
),
    "cctv": ("cctv", "camera", "cameras", "surveillance", "सीसीटीवी", "कैमरा", "कैमरे"),
    "machine_iot": ("machine monitoring", "iot", "sensor", "sensors", "machine uptime", "energy monitoring", "मशीन मॉनिटरिंग", "मशीनों"),
    "fleet": ("vehicle", "vehicles", "van", "vans", "truck", "trucks", "delivery bikes", "gps", "fleet", "गाड़ी", "गाड़ियाँ", "वाहन", "ट्रक"),
    "cloud_telephony": (
    "ivr", "call center", "call centre", "landline",
    "phone system", "call recording", "cloud telephony",
    "call management", "calls from customers",
    "कॉल रिकॉर्डिंग", "कॉल सेंटर", "कॉल मैनेज करना"
),
    "toll_free": ("toll free", "toll-free", "1800 number", "टोल फ्री", "टोल-फ़्री"),
    "sms": ("sms", "bulk sms", "text alerts", "text message", "एसएमएस"),
    "whatsapp": ("whatsapp", "whats app", "व्हाट्सएप", "वॉट्सऐप"),
    "static_ip": ("static ip", "fixed ip", "remote access", "server access", "स्टैटिक आईपी"),
    "multi_site_mgmt": ("central management", "manage all branches", "manage all stores", "one dashboard", "single dashboard", "sd-wan", "sdwan",
                        "सभी ब्रांच", "एक डैशबोर्ड"),
    "high_speed": ("1 gbps", "1gbps", "gigabit", "very fast", "high speed", "heavy files", "large files", "video editing", "बहुत तेज़", "तेज़ इंटरनेट"),
    "internet": ("internet", "wifi", "wi-fi", "broadband", "net connection", "इंटरनेट", "नेट", "वाईफाई", "वाई-फ़ाई"),
}
QTY_PATTERNS = {
    "cameras": r"(\d+)\s*(?:cctv\s*)?(?:cameras?|कैमरे|कैमरा)",
    "vehicles": r"(\d+)\s*(?:delivery\s*)?(?:vehicles?|vans?|trucks?|bikes?|गाड़ियाँ|गाड़ी|वाहन|ट्रक)",
    "machines": r"(\d+)\s*(?:machines?|मशीनें|मशीन)",
    "mobile_lines": r"(\d+)\s*(?:mobile\s*)?(?:sims?|lines?|mobile connections?|connections?|सिम|लाइनें|लाइन)",
    "counters": r"(\d+)\s*(?:billing\s*)?(?:counters?|काउंटर)",
    "email_users": r"(\d+)\s*(?:email (?:ids?|accounts?|users?)|mailboxes)",
}
EMPLOYEE_WORDS = r"(?:employees?|staff|people|persons?|workers?|members|team members|log|logon|karmchari|helpers?|लोग|कर्मचारी|स्टाफ|आदमी|व्यक्ति|मज़दूर|मजदूर)"
SITE_WORDS = r"(?:shops?|stores?|branch(?:es)?|outlets?|locations?|offices?|sites?|units?|factories|plants?|clinics?|centres?|centers?|restaurants?|dukaan(?:en)?|dukane|दुकानें|दुकान|ब्रांच|शाखाएं|शाखा|ऑफिस|आउटलेट|फैक्ट्री|सेंटर)"
YES = ("yes", "yeah", "yep", "haan", "han", "ha", "ji", "ji haan", "हाँ", "हां", "जी", "जी हाँ", "have gst", "gst hai", "registered")
NO = ("no", "nope", "nahi", "nahin", "na", "नहीं", "नही", "ना", "not registered", "no gst", "gst nahi", "without gst", "जीएसटी नहीं")
ESCALATE = ("talk to a human", "talk to human", "talk to someone", "talk to a person", "speak to someone", "call me", "callback",
            "call back", "expert", "real person", "agent", "insaan se", "baat karni", "बात करनी", "कॉल करो", "कॉल करें", "इंसान")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text).translate(DEV_DIGITS)
    return re.sub(r"\s+", " ", t).strip()


def is_hindi(text: str) -> bool:
    return bool(re.search(r"[ऀ-ॿ]", text))


def _num(tok: str) -> int | None:
    tok = tok.strip().lower().replace(",", "")
    if tok.isdigit():
        return int(tok)
    return WORD_NUMS.get(tok)


def _word_num_pattern() -> str:
    words = sorted(WORD_NUMS, key=len, reverse=True)
    return r"(\d+|" + "|".join(re.escape(w) for w in words) + r")"


NUM = _word_num_pattern()


def _has(t: str, kw: str) -> bool:
    k = kw.strip().lower()
    return re.search(B + re.escape(k) + E, t) is not None


def parse_range_answer(t: str) -> int | None:
    """Chip answers like '2-5', '100+', 'Just me', 'More than 10' -> conservative lower bound."""
    t = t.strip().lower()
    if t in ("just me", "only me", "sirf main", "सिर्फ़ मैं", "सिर्फ मैं", "akela", "अकेला"):
        return 1
    m = re.fullmatch(r"(\d+)\s*[-–to]+\s*(\d+)", t)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"(\d+)\s*\+", t) or re.fullmatch(r"(?:more than|over|above|से ज़्यादा)\s*(\d+)", t) \
        or re.fullmatch(r"(\d+)\s*(?:से ज़्यादा|से ज्यादा|se zyada)", t)
    if m:
        return int(m.group(1)) + (0 if "+" in t else 1)
    return None


def parse_money(t: str) -> int | None:
    cur = r"(?:(?<![a-z])(?:rs\.?|inr|rupees?)(?![a-z])|₹|रुपये|रुपए)"
    m = re.search(cur + r"\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|हज़ार|hazar)?(?![a-z])", t) or \
        re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|हज़ार|hazar)?\s*" + cur, t)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    if m.group(2):
        v *= 1000
    return int(v)


def extract(text: str, expecting: str | None = None) -> dict:
    """Return a partial BusinessProfile dict plus control flags (keys starting with '_')."""
    raw = _norm(text)
    t = raw.lower()
    out: dict = {"needs": [], "excluded_needs": []}
    if is_hindi(raw):
        out["_lang"] = "hi"

    # ---------------------------------------------------------------- control intents
    if any(_has(t, k) for k in ESCALATE):
        out["_escalate"] = True
    if re.search(r"(only|just|sirf|सिर्फ़|सिर्फ)\s+(?:a\s+)?(?:few\s+)?(mobile|sim|सिम|postpaid)", t) or "only want mobile" in t:
        out["only_mobile"] = True
    if re.search(r"(no|not|nahi|नहीं)\s+(?:any\s+)?(fibre|fiber|फ़ाइबर|फाइबर)", t) or "fibre not available" in t or "fiber not available" in t:
        out["fibre_available"] = False

    # ---------------------------------------------------------------- identifiers
    gm = re.search(r"\b([0-9O]{2}[A-Z0-9]{5}[0-9OISBZ]{4}[A-Z0-9][0-9A-Z][Z2][0-9A-Z])\b", raw.upper())
    if gm:
        g = normalise_gstin(gm.group(1))
        out["gstin"] = g
        out["has_gstin"] = True
        if validate_gstin(g):
            out["_gstin_invalid"] = True
    elif re.search(r"\b[0-9A-Z]{13,16}\b", raw.upper()) and expecting == "gstin":
        out["_gstin_invalid"] = True
    um = re.search(r"UDYAM[\s-]*[A-Z]{2}[\s-]*\d{2}[\s-]*\d{7}", raw.upper())
    if um:
        out["udyam_number"] = normalise_udyam(um.group(0))
        out["has_udyam"] = True

    # ---------------------------------------------------------------- business type + city
    bt = match_business_type(raw)
    if bt:
        out["business_type"] = bt.name
    hit = cities.find_city_in_text(raw)
    if hit:
        out["city"], out["city_tier"], out["state"] = hit[0], hit[1], hit[2] or None
    elif expecting == "city" and raw and len(raw) <= 40 and not re.search(r"\d", raw):
        out["city"] = raw.strip().title()     # unknown city: resolved to tier 3 (partner-assisted) by the recommender
    else:
        m = re.search(r"\b(?:in|at|from|near)\s+([A-Z][a-zA-Z]{2,}(?:\s[A-Z][a-zA-Z]{2,})?)", raw)
        if m and m.group(1).split()[0] not in {"GST", "India", "Hindi", "English", "One", "The", "My", "Our", "Tier", "Delhi-NCR"}:
            out["city"] = m.group(1)         # not in our city list -> tier 3, partner-assisted

    # ---------------------------------------------------------------- sizes
    m = re.search(NUM + r"\s*(?:full[- ]time\s*)?" + EMPLOYEE_WORDS + E, t) or re.search(r"team of " + NUM, t) \
        or re.search(NUM + r"\s+of us" + E, t) or re.search(r"\bwe(?:'re| are)\s+" + NUM + r"\s*(?:in all|in total|total)?\s*(?:$|[,.!])", t) \
        or re.search(r"(?<![\wऀ-ॿ])(?:हम|ham)\s+" + NUM + E + r"(?!\s*(?:\S+\s)?" + SITE_WORDS + ")", t) \
        or re.search(EMPLOYEE_WORDS + r"\s*(?:is|are|:|=)?\s*" + NUM + E, t)
    if m:
        n = _num(m.group(1))
        if n:
            out["employees"] = n
    elif re.search(r"(me and|myself and|main aur|मैं और)\s+" + NUM, t):
        n = _num(re.search(r"(me and|myself and|main aur|मैं और)\s+" + NUM, t).group(2))
        out["employees"] = (n or 0) + 1
    elif re.search(r"(me and my|main aur mera|main aur meri|मैं और मेरा|मैं और मेरी|मैं और मेरे)\s+\S+", t):
        out["employees"] = 2
    elif re.search(r"(just me|only me|alone|sirf main|akela|अकेला|सिर्फ़ मैं|सिर्फ मैं)", t):
        out["employees"] = 1
    m = re.search(NUM + r"\s*(?:[\wऀ-ॿ]+\s){0,2}?" + SITE_WORDS + E, t)
    if m and not re.search(NUM + r"\s*(?:cctv\s*)?(?:cameras?|कैमरे)", t[m.start():m.end()]):
        n = _num(m.group(1))
        if n and n <= 200:
            out["sites"] = n
    if "sites" not in out and re.search(r"(single|one|ek|एक)\s+(shop|store|office|clinic|location|branch|outlet|dukaan|दुकान|ऑफिस)", t):
        out["sites"] = 1
    m = re.search(r"chain of " + NUM, t)
    if m and _num(m.group(1)):
        out["sites"] = _num(m.group(1))

    # ---------------------------------------------------------------- GST yes/no in free text
    if "has_gstin" not in out:
        if re.search(r"(no|not|without|nahi|nahin|नहीं)\s+(?:a\s+)?(?:gst|gstin|जीएसटी)", t) or re.search(r"(gst|gstin|जीएसटी)\s*(?:registration\s*)?(nahi|नहीं|not)", t) \
                or "not registered" in t or "unregistered" in t:
            out["has_gstin"] = False
        elif re.search(r"(gst|gstin|जीएसटी)\s*(?:registration\s*)?(?:is|was|has been|हो गया|है)?\s*(cancelled|canceled|suspended|रद्द|निलंबित)", t):
            out["has_gstin"] = True
            out["gstin_status"] = "Suspended" if re.search(r"suspended|निलंबित", t) else "Cancelled"
        elif re.search(r"(have|got|with|registered under|हमारे पास)\s+(?:a\s+)?(?:gst|gstin|जीएसटी)", t) \
                or re.search(r"(gst|gstin|जीएसटी)\s*(hai|है|registered)", t) or re.search(r"(gst|gstin)[- ]registered", t):
            out["has_gstin"] = True

    # ---------------------------------------------------------------- money (each amount classified by the words around it)
    if expecting != "spend":
        cur = r"(?:(?<![a-z])(?:rs\.?|inr|rupees?)(?![a-z])|₹)"
        for m in re.finditer(cur + r"\s*(\d[\d,]*)\s*(k|thousand)?(?![a-z\d])|(\d[\d,]*)\s*(k|thousand)?\s*(?:" + cur + r"|रुपये|रुपए)", t):
            amount = int((m.group(1) or m.group(3)).replace(",", "")) * (1000 if (m.group(2) or m.group(4)) else 1)
            before = t[max(0, m.start() - 30):m.start()]
            after = t[m.end():m.end() + 12]
            if re.search(r"(budget|under|within|max|upto|up to|बजट)", before) or "से कम" in after:
                out["budget"] = amount
            elif re.search(r"(spend|pay|paying|bill|kharch|खर्च|देते)", before + after):
                out["monthly_spend"] = amount

    # ---------------------------------------------------------------- current internet
    if re.search(r"hotspot|mobile data|phone (?:ka|se) (?:net|internet)|हॉटस्पॉट", t):
        out["current_internet"] = "Mobile hotspot"
    elif "leased line" in t and re.search(r"(have|already|existing|current)", t):
        out["current_internet"] = "Leased line"
    elif re.search(r"home (broadband|wifi|wi-fi)", t):
        out["current_internet"] = "Home broadband"
    elif re.search(r"(no internet|internet nahi|इंटरनेट नहीं)", t):
        out["current_internet"] = "None"

    # ---------------------------------------------------------------- needs (+ explicit exclusions)
    for need, kws in NEED_KEYWORDS.items():
        for kw in kws:
            k = kw.strip().lower()
            if not _has(t, k):
                continue
            if re.search(r"(no|not|don't need|dont need|do not need|without|nahi chahiye|नहीं चाहिए)\s+(?:\w+\s){0,2}" + re.escape(k), t) \
                    or re.search(re.escape(k) + r"\s+(nahi chahiye|नहीं चाहिए|not needed|not required)", t):
                out["excluded_needs"].append(need)
            else:
                out["needs"].append(need)
            break
    if "backup_internet" in out["needs"] and "backup_storage" in out["needs"] and not re.search(r"data|file|storage|डेटा|डाटा", t):
        out["needs"].remove("backup_storage")
    if "internet" in out["needs"]:
        out["needs"].remove("internet")       # connectivity is always part of the core bundle

    for key, pat in QTY_PATTERNS.items():
        m = re.search(pat, t)
        if m:
            out[key] = int(m.group(1))
    if out.get("only_mobile") and "mobile_lines" not in out:
        m = re.search(NUM + r"\s*(?:sims?|lines?|connections?)", t)
        if m and _num(m.group(1)):
            out["mobile_lines"] = _num(m.group(1))

    # ---------------------------------------------------------------- answers to the slot we just asked
    if expecting in ("employees", "sites") and expecting not in out:
        n = parse_range_answer(raw)
        if n is None:
            m = re.fullmatch(NUM, t)
            n = _num(m.group(1)) if m else None
        if n is None:
            m = re.search(r"\b(\d+)\b", t)
            n = int(m.group(1)) if m else None
        if n:
            out[expecting] = n
    if expecting == "gstin" and "has_gstin" not in out:
        if any(_has(t, y) for y in YES):
            out["has_gstin"] = True
        elif any(_has(t, n) for n in NO):
            out["has_gstin"] = False
    if expecting == "spend" and "monthly_spend" not in out:
        rng = re.search(r"(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)", t)
        if rng:
            out["monthly_spend"] = (int(rng.group(1).replace(",", "")) + int(rng.group(2).replace(",", ""))) // 2
        elif re.search(r"(under|below|से कम)", t) and re.search(r"(\d[\d,]*)", t):
            out["monthly_spend"] = int(re.search(r"(\d[\d,]*)", t).group(1).replace(",", "")) // 2
        elif re.search(r"(over|above|से ज़्यादा|से ज्यादा)", t) and re.search(r"(\d[\d,]*)", t):
            out["monthly_spend"] = int(re.search(r"(\d[\d,]*)", t).group(1).replace(",", ""))
        elif re.fullmatch(r"\d[\d,]*", t):
            out["monthly_spend"] = int(t.replace(",", ""))
        elif t in ("skip", "छोड़ें", "chhodo"):
            out["_skip"] = True
    if expecting == "mobile_lines" and "mobile_lines" not in out:
        m = re.search(r"\b(\d+)\b", t)
        if m:
            out["mobile_lines"] = int(m.group(1))

    out["needs"] = list(dict.fromkeys(out["needs"]))
    out["excluded_needs"] = list(dict.fromkeys(out["excluded_needs"]))
    return out
