// Mirrors backend UNIT_LABELS (app/domain/catalogue.py) so quote lines read naturally in Hindi.
const HI: Record<string, string> = {
  "per site": "प्रति साइट",
  "per line": "प्रति लाइन",
  "per IP": "प्रति आईपी",
  "per channel": "प्रति चैनल",
  "per number": "प्रति नंबर",
  "per pack": "प्रति पैक",
  "per account": "प्रति अकाउंट",
  "per user": "प्रति यूज़र",
  "per counter": "प्रति काउंटर",
  "per device": "प्रति डिवाइस",
  "per camera": "प्रति कैमरा",
  "per vehicle": "प्रति वाहन",
};

export const unitText = (unit: string, lang: string) => (lang === "hi" ? HI[unit] || unit : unit);
