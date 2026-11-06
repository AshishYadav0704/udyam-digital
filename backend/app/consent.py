"""Consent notice (itemised, purpose-specific, bilingual) and purpose registry.

Design follows the notice and consent model of the DPDP Act 2023 / DPDP Rules 2025 (core obligations
in force from May 2027). This is a prototype notice - wording must be reviewed by Legal before use.
Contacts are fictional (Accel is a fictional operator).
"""
from __future__ import annotations

NOTICE_VERSION = "2026-11-v1"
REQUIRED = {"kyc_verification"}
OPTIONAL = {"partner_assist", "marketing"}
PURPOSES = REQUIRED | OPTIONAL

_NOTICE = {
    "en": {
        "title": "Before you share documents",
        "intro": "We need a few details to verify your business, as telecom rules require before connections are activated. "
                 "Here is exactly what we collect, why, and for how long.",
        "purposes": [
            {"id": "kyc_verification", "required": True, "title": "Verify your business and authorised signatory",
             "data": ["GSTIN and/or Udyam number", "GST and Udyam certificates", "Signatory's photo ID", "Address proof (utility bill, last 90 days)",
                      "Contact name and mobile number"],
             "why": "To confirm the business exists and is active, that you are authorised to sign, and the installation address - "
                    "required before telecom connections can be activated.",
             "who": "Accel's automated verification and, only if something needs checking, a KYC reviewer. Registry lookups use the "
                    "GSTIN/Udyam number only.",
             "retention": "Document images: deleted 180 days after activation, or 30 days after an application is cancelled or rejected. "
                          "Verification result with masked identifiers: kept for the period telecom licence conditions require."},
            {"id": "partner_assist", "required": False, "title": "Let a local Accel partner help you",
             "data": ["Name, mobile, business name and address"],
             "why": "So a nearby partner can visit for installation or help with documents.",
             "who": "The one partner assigned to your order.", "retention": "Until your order is activated plus 90 days."},
            {"id": "marketing", "required": False, "title": "Offers and product updates",
             "data": ["Mobile number, business type"], "why": "To tell you about other Accel Business products.",
             "who": "Accel Business marketing.", "retention": "Until you withdraw consent."},
        ],
        "always": "Order and installation updates are part of the service you are buying and are sent regardless of these choices.",
        "rights": ["See a summary of the data we hold about you", "Correct or update it", "Ask us to erase it (except what the law requires us to keep)",
                   "Withdraw any consent at any time from 'My privacy' - withdrawing KYC consent stops the order before activation",
                   "Nominate someone to exercise these rights", "Complain to our Grievance Officer, and then to the Data Protection Board of India"],
        "contact": "Grievance Officer, Accel Business (fictional): privacy@accelbusiness.example - we reply within 7 days.",
        "language_note": "This notice is available in English and Hindi.",
    },
    "hi": {
        "title": "दस्तावेज़ देने से पहले",
        "intro": "टेलीकॉम नियमों के अनुसार कनेक्शन चालू करने से पहले हमें आपके व्यवसाय का सत्यापन करना होता है। "
                 "यहाँ साफ़ लिखा है कि हम क्या लेते हैं, क्यों, और कितने समय तक रखते हैं।",
        "purposes": [
            {"id": "kyc_verification", "required": True, "title": "आपके व्यवसाय और अधिकृत हस्ताक्षरकर्ता का सत्यापन",
             "data": ["GSTIN और/या उद्यम नंबर", "GST और उद्यम सर्टिफ़िकेट", "हस्ताक्षरकर्ता का फ़ोटो पहचान-पत्र", "पते का प्रमाण (पिछले 90 दिनों का बिल)",
                      "संपर्क नाम और मोबाइल नंबर"],
             "why": "यह पक्का करने के लिए कि व्यवसाय मौजूद और सक्रिय है, आप हस्ताक्षर के लिए अधिकृत हैं, और इंस्टॉलेशन का पता सही है - "
                    "टेलीकॉम कनेक्शन चालू करने से पहले यह ज़रूरी है।",
             "who": "Accel का स्वचालित सत्यापन, और सिर्फ़ ज़रूरत पड़ने पर एक KYC समीक्षक। रजिस्ट्री जाँच में सिर्फ़ GSTIN/उद्यम नंबर जाता है।",
             "retention": "दस्तावेज़ों की इमेज: चालू होने के 180 दिन बाद, या आवेदन रद्द/अस्वीकार होने के 30 दिन बाद हटा दी जाती है। "
                          "मास्क किए पहचान-नंबर के साथ सत्यापन परिणाम: टेलीकॉम लाइसेंस शर्तों में तय अवधि तक।"},
            {"id": "partner_assist", "required": False, "title": "स्थानीय Accel पार्टनर से मदद",
             "data": ["नाम, मोबाइल, व्यवसाय का नाम और पता"], "why": "ताकि पास का पार्टनर इंस्टॉलेशन या दस्तावेज़ों में मदद कर सके।",
             "who": "आपके ऑर्डर के लिए तय एक पार्टनर।", "retention": "ऑर्डर चालू होने के बाद 90 दिन तक।"},
            {"id": "marketing", "required": False, "title": "ऑफ़र और प्रोडक्ट अपडेट",
             "data": ["मोबाइल नंबर, व्यवसाय का प्रकार"], "why": "Accel Business के दूसरे प्रोडक्ट के बारे में बताने के लिए।",
             "who": "Accel Business मार्केटिंग।", "retention": "जब तक आप सहमति वापस न लें।"},
        ],
        "always": "ऑर्डर और इंस्टॉलेशन की जानकारी आपकी खरीदी गई सेवा का हिस्सा है और इन विकल्पों से अलग भेजी जाती है।",
        "rights": ["आपके बारे में रखे डेटा का सारांश देखें", "उसे सुधारें या अपडेट करें", "उसे मिटाने को कहें (कानून के अनुसार रखना ज़रूरी डेटा छोड़कर)",
                   "'मेरी प्राइवेसी' से कभी भी सहमति वापस लें - KYC सहमति वापस लेने पर ऑर्डर चालू होने से पहले रुक जाता है",
                   "इन अधिकारों के लिए किसी को नामित करें", "हमारे शिकायत अधिकारी से, फिर भारतीय डेटा संरक्षण बोर्ड से शिकायत करें"],
        "contact": "शिकायत अधिकारी, Accel Business (काल्पनिक): privacy@accelbusiness.example - 7 दिन में जवाब।",
        "language_note": "यह सूचना हिंदी और अंग्रेज़ी में उपलब्ध है।",
    },
}


def notice(lang: str) -> dict:
    return _NOTICE.get(lang, _NOTICE["en"])
