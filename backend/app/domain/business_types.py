"""Business-type taxonomy for the advisor.

The 35 canonical types and their segments come straight from smb_leads.csv. Typical needs
per type are derived from the activated bundles in the same file (product penetration by
business type, see analysis/outputs/tables/product_penetration_by_segment.csv). Keywords
cover English, romanised Hindi and Devanagari so a Hindi-speaking owner can describe the
business in their own words.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SEGMENTS = {
    "micro": "Micro retail & services",
    "prof": "Professional offices",
    "multi": "Small multi-site businesses",
    "mfg": "Small manufacturers",
}


@dataclass(frozen=True)
class BusinessType:
    name: str
    segment: str
    keywords: tuple[str, ...]
    needs: tuple[str, ...]          # capability tags typical for this type (from activated bundles)


_T = BusinessType
TYPES: list[BusinessType] = [
    # ---- micro retail & services (single site, 1-6 staff in the data)
    _T("Kirana store", "micro", ("kirana", "grocery", "general store", "provision store", "किराना", "किराने", "राशन", "जनरल स्टोर", "kirane"), ("internet", "mobile_lines", "wifi_guest", "website", "billing_pos")),
    _T("Salon", "micro", ("salon", "parlour", "parlor", "beauty", "barber", "hair", "सैलून", "पार्लर", "नाई", "ब्यूटी"), ("internet", "mobile_lines", "billing_pos", "wifi_guest")),
    _T("Pharmacy", "micro", ("pharmacy", "chemist", "medical store", "medical shop", "dawai", "दवाई", "दवा", "केमिस्ट", "मेडिकल स्टोर", "फार्मेसी"), ("internet", "mobile_lines", "billing_pos", "cctv")),
    _T("Bakery", "micro", ("bakery", "cake shop", "बेकरी"), ("internet", "mobile_lines", "billing_pos")),
    _T("Boutique", "micro", ("boutique", "tailor", "garment shop", "clothes shop", "बुटीक", "दर्जी", "कपड़े की दुकान"), ("internet", "mobile_lines")),
    _T("Mobile repair shop", "micro", ("mobile repair", "phone repair", "mobile shop", "मोबाइल रिपेयर", "मोबाइल की दुकान"), ("internet", "mobile_lines", "billing_pos", "cctv")),
    _T("Sweet shop", "micro", ("sweet shop", "mithai", "halwai", "मिठाई", "हलवाई"), ("internet", "mobile_lines", "cctv", "billing_pos")),
    _T("Hardware store", "micro", ("hardware", "paint shop", "sanitary", "हार्डवेयर"), ("internet", "mobile_lines", "wifi_guest")),
    _T("Optician", "micro", ("optician", "optical", "spectacles", "चश्मे", "ऑप्टिकल"), ("internet", "mobile_lines")),
    _T("Stationery shop", "micro", ("stationery", "book shop", "bookstore", "स्टेशनरी", "किताब"), ("internet", "mobile_lines", "billing_pos", "cctv")),
    # ---- professional offices (1-2 sites, 3-25 staff)
    _T("CA firm", "prof", ("ca firm",  "ca फर्म","chartered accountant", "accountant", "tax consultant", "audit firm", "सीए", "चार्टर्ड अकाउंटेंट", "अकाउंटेंट"), ("internet", "mobile_lines", "cloud_email", "backup_storage", "cloud_telephony")),
    _T("Dental clinic", "prof", ("dental", "dentist", "दांत", "डेंटल"), ("internet", "mobile_lines", "cloud_email", "endpoint_security", "backup_storage")),
    _T("Physiotherapy clinic", "prof", ("physiotherapy", "physio", "फिजियो"), ("internet", "mobile_lines", "cloud_email", "endpoint_security")),
    _T("Diagnostic lab", "prof", ("diagnostic", "pathology", "lab ", "laboratory", "path lab", "जांच केंद्र", "पैथोलॉजी", "लैब"), ("internet", "mobile_lines", "cloud_email", "endpoint_security", "backup_storage")),
    _T("Coaching centre", "prof", ("coaching", "tuition", "classes", "institute", "academy", "कोचिंग", "ट्यूशन"), ("internet", "mobile_lines", "cloud_email", "cloud_telephony", "sms")),
    _T("Law office", "prof", ("law office", "lawyer", "advocate", "legal", "law firm", "वकील", "एडवोकेट"), ("internet", "mobile_lines", "cloud_email", "backup_storage", "endpoint_security")),
    _T("Travel agency", "prof", ("travel agency", "travel agent", "tours", "travels", "ट्रैवल", "टूर"), ("internet", "mobile_lines", "cloud_email", "backup_storage", "endpoint_security")),
    _T("Architecture studio", "prof", ("architecture studio","architect", "interior design", "design studio", "आर्किटेक्ट"), ("internet", "mobile_lines", "cloud_email", "backup_storage", "endpoint_security")),
    _T("Real estate agency", "prof", ("real estate", "property dealer", "realty", "broker", "प्रॉपर्टी", "रियल एस्टेट"), ("internet", "mobile_lines", "cloud_email", "endpoint_security", "backup_storage")),
    _T("Insurance agency", "prof", ("insurance", "lic agent", "बीमा", "इंश्योरेंस"), ("internet", "mobile_lines", "cloud_email", "endpoint_security")),
    _T("Clinic", "prof", ("clinic", "doctor", "medical practice", "polyclinic", "क्लिनिक", "डॉक्टर", "दवाखाना"), ("internet", "mobile_lines", "cloud_email", "endpoint_security", "backup_storage")),
    # ---- small multi-site businesses (3-12 sites)
    _T("Restaurant chain", "multi", ("restaurant", "cafe", "café", "dhaba", "food outlet", "cloud kitchen", "रेस्टोरेंट", "ढाबा", "कैफे"), ("internet", "mobile_lines", "billing_pos", "wifi_guest", "backup_internet", "whatsapp")),
    _T("Pharmacy chain", "multi", ("pharmacy chain", "chemist chain", "medical stores", "दवा की दुकानें"), ("internet", "mobile_lines", "cctv", "billing_pos", "backup_internet")),
    _T("Gym chain", "multi", ("gym", "fitness", "जिम"), ("internet", "mobile_lines", "backup_internet", "billing_pos", "wifi_guest", "toll_free")),
    _T("Budget hotel group", "multi", ("hotel", "guest house", "lodge", "hostel", "stays", "होटल", "गेस्ट हाउस"), ("internet", "mobile_lines", "billing_pos", "backup_internet", "wifi_guest")),
    _T("Electronics retail chain", "multi", ("electronics", "appliance", "इलेक्ट्रॉनिक्स"), ("internet", "mobile_lines", "backup_internet", "whatsapp", "billing_pos")),
    _T("Apparel retail chain", "multi", ("apparel", "garment stores", "fashion stores", "कपड़ों की दुकानें"), ("internet", "mobile_lines", "cctv", "toll_free", "wifi_guest")),
    _T("Bakery chain", "multi", ("bakery chain", "bakeries", "बेकरी चेन"), ("internet", "mobile_lines", "billing_pos", "backup_internet", "whatsapp")),
    _T("Pre-school chain", "multi", ("pre-school", "preschool", "play school", "playschool", "daycare", "प्ले स्कूल"), ("internet", "mobile_lines", "cctv", "backup_internet")),
    _T("Retail chain", "multi", ("retail chain", "stores", "outlets", "branches", "chain of", "दुकानें", "दुकानों", "चेन", "शाखाएं", "ब्रांच"), ("internet", "mobile_lines", "billing_pos", "cctv", "backup_internet")),
    # ---- small manufacturers
    _T("Auto-parts unit", "mfg", ("auto parts", "auto-parts", "automobile parts", "ऑटो पार्ट्स"), ("dedicated_line", "mobile_lines", "cloud_email", "static_ip", "endpoint_security")),
    _T("Textile unit", "mfg", ("textile", "weaving", "spinning", "powerloom", "कपड़ा मिल", "टेक्सटाइल", "बुनाई"), ("dedicated_line", "mobile_lines", "cloud_email", "firewall")),
    _T("Packaging unit", "mfg", ("packaging", "carton", "पैकेजिंग"), ("dedicated_line", "mobile_lines", "cloud_email", "endpoint_security")),
    _T("Plastic moulding unit", "mfg", ("plastic", "moulding", "molding", "प्लास्टिक"), ("dedicated_line", "mobile_lines", "cloud_email", "endpoint_security", "machine_iot")),
    _T("Printing press", "mfg", ("printing", "press", "प्रिंटिंग", "छपाई"), ("dedicated_line", "mobile_lines", "cloud_email")),
    _T("Furniture workshop", "mfg", ("furniture", "woodcraft", "carpentry", "फर्नीचर"), ("dedicated_line", "mobile_lines", "cloud_email", "static_ip")),
    _T("Food processing unit", "mfg", ("food processing", "masala", "spices unit", "flour mill", "फूड प्रोसेसिंग", "आटा चक्की"), ("dedicated_line", "mobile_lines", "cloud_email", "endpoint_security", "cctv")),
    _T("Manufacturing unit", "mfg", ("factory", "manufacturing", "manufacturer", "plant", "workshop", "fabrication", "फैक्ट्री", "कारखाना", "उत्पादन"), ("dedicated_line", "mobile_lines", "cloud_email", "endpoint_security")),
    # ---- single-site versions of chain trades. NOT in the dataset (it only has these trades as 3-12 site
    # chains); reached via resolve_segment when sites < 3 so a single cafe is not quoted a multi-site bundle.
    # Typical needs are an assumption to validate in the pilot.
    _T("Restaurant / cafe", "micro", (), ("internet", "billing_pos", "wifi_guest", "mobile_lines", "whatsapp")),
    _T("Gym", "micro", (), ("internet", "billing_pos", "wifi_guest", "mobile_lines")),
    _T("Hotel / guest house", "micro", (), ("internet", "wifi_guest", "billing_pos", "mobile_lines", "cctv")),
    _T("Pre-school", "micro", (), ("internet", "cctv", "mobile_lines")),
]
NOT_IN_DATASET = {"Clinic", "Restaurant / cafe", "Gym", "Hotel / guest house", "Pre-school"}

_BY_NAME = {t.name.lower(): t for t in TYPES}
# generic types are only used when nothing more specific matched ("gym chain with 4 branches" is a gym chain)
GENERIC_TYPES = {"Retail chain", "Manufacturing unit", "Clinic"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s).lower()).strip()


def get_type(name: str | None) -> BusinessType | None:
    return _BY_NAME.get(name.lower()) if name else None


def match_business_type(text: str) -> BusinessType | None:
    """Pick the business type whose longest keyword appears in the text.

    Chains are disambiguated later from the number of sites, so 'pharmacy' with 5 sites
    becomes 'Pharmacy chain'.
    """
    t = " " + _norm(text) + " "
    best: tuple[int, BusinessType] | None = None
    fallback: tuple[int, BusinessType] | None = None
    for bt in TYPES:
        for kw in bt.keywords:
            k = _norm(kw).strip()
            plural = r"(?:s|es)?" if re.fullmatch(r"[a-z .&-]+", k) else ""
            if re.search(r"(?<![a-zऀ-ॿ])" + re.escape(k) + plural + r"(?![a-zऀ-ॿ])", t):
                score = len(k)
                if bt.name in GENERIC_TYPES:
                    if fallback is None or score > fallback[0]:
                        fallback = (score, bt)
                elif best is None or score > best[0]:
                    best = (score, bt)
    if best:
        return best[1]
    return fallback[1] if fallback else None


CHAIN_OF = {
    "Pharmacy": "Pharmacy chain", "Bakery": "Bakery chain", "Kirana store": "Retail chain",
    "Boutique": "Apparel retail chain", "Sweet shop": "Retail chain", "Hardware store": "Retail chain",
    "Optician": "Retail chain", "Stationery shop": "Retail chain", "Mobile repair shop": "Electronics retail chain",
    "Salon": "Retail chain", "Restaurant / cafe": "Restaurant chain", "Gym": "Gym chain",
    "Hotel / guest house": "Budget hotel group", "Pre-school": "Pre-school chain",
}
# a chain trade at 1-2 sites is a single business, not a multi-site account
SINGLE_OF = {"Restaurant chain": "Restaurant / cafe", "Gym chain": "Gym", "Budget hotel group": "Hotel / guest house",
             "Pre-school chain": "Pre-school", "Pharmacy chain": "Pharmacy", "Bakery chain": "Bakery",
             "Apparel retail chain": "Boutique"}


def resolve_segment(bt: BusinessType | None, employees: int | None, sites: int | None) -> tuple[BusinessType | None, str | None]:
    """Segment from type + size. 3+ sites is a multi-site business regardless of trade."""
    if sites is not None and sites >= 3:
        if bt is None:
            return get_type("Retail chain"), "multi"
        if bt.segment == "micro" and bt.name in CHAIN_OF:
            return get_type(CHAIN_OF[bt.name]), "multi"
        if bt.segment in ("micro", "prof"):
            return bt, "multi"
        return bt, bt.segment
    if bt is not None:
        if bt.segment == "multi" and sites is not None and sites < 3:
            return (get_type(SINGLE_OF.get(bt.name)) or bt), "micro"
        return bt, bt.segment
    if employees is None:
        return None, None
    return None, "micro" if employees <= 6 else "prof"
