"""Document intelligence for Smart KYC: quality checks, OCR, classification, field extraction.

Pipeline (all local - documents never leave the server):
  1. decode + re-encode (strips metadata), size/dimension limits enforced by the caller
  2. quality: blur (variance of Laplacian at a fixed width), skew (projection profile), resolution
  3. deskew if |angle| >= 0.5 deg
  4. OCR an ensemble of 3 pre-processing variants with Tesseract 5 (watermark-suppressed binarisation,
     the same at 1.5x scale, plain greyscale) and keep word-level confidences
  5. classify the document from its text, extract labelled fields, repair OCR confusions with
     identifier-aware rules, and vote across variants (validator-passing values win)
Every field carries a confidence in [0,1]; anything below settings.ocr_min_field_confidence is sent to
a human instead of being trusted.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date

import cv2
import numpy as np
import pytesseract
from rapidfuzz import fuzz

from app.domain.identifiers import (gstin_checksum_ok, normalise_gstin, normalise_udyam, validate_gstin,
                                    validate_udyam)

DOC_TYPES = ("gst_certificate", "udyam_certificate", "signatory_id", "address_proof")
TITLE_KEYS = {
    "gst_certificate": ("gst registration certificate", "gst registration", "gstin"),
    "udyam_certificate": ("udyam registration certificate", "udyam reg", "enterprise name"),
    "signatory_id": ("authorised signatory", "authorized signatory", "signatory id", "valid till"),
    "address_proof": ("electricity bill", "consumer no", "supply address", "bill date"),
}
LABELS = {
    "gst_certificate": [("gstin", ("gstin",)), ("legal_name", ("legal name",)), ("trade_name", ("trade name",)),
                        ("constitution", ("constitution",)), ("address", ("address of principal",)),
                        ("address_cont", ("place of business",)), ("date_of_liability", ("date of liability",)),
                        ("registration_type", ("type of registration",))],
    "udyam_certificate": [("udyam_number", ("udyam reg. number", "udyam reg number", "udyam registration number")),
                          ("enterprise_name", ("enterprise name",)), ("major_activity", ("major activity",)),
                          ("city", ("city",)), ("state", ("state",)), ("date_of_registration", ("date of registration",))],
    "address_proof": [("consumer_no", ("consumer no.", "consumer no")), ("billed_to", ("billed to",)),
                      ("supply_address", ("supply address",)), ("bill_date", ("bill date",)),
                      ("units_consumed", ("units consumed",)), ("amount_due", ("amount due (inr)", "amount due"))],
    "signatory_id": [("name", ("name",)), ("designation", ("designation",)), ("business", ("for business",)),
                     ("id_no", ("id no.", "id no")), ("valid_till", ("valid till",))],
}
REQUIRED_FIELDS = {
    "gst_certificate": ("gstin", "legal_name", "trade_name", "address"),
    "udyam_certificate": ("udyam_number", "enterprise_name", "state"),
    "address_proof": ("billed_to", "supply_address", "bill_date"),
    "signatory_id": ("name", "business"),
}
ADDRESS_FIELDS = {"address", "supply_address"}
DATE_FIELDS = {"date_of_liability", "date_of_registration", "bill_date", "valid_till"}


@dataclass
class Quality:
    width: int
    height: int
    blur_score: float
    skew_degrees: float
    is_blurry: bool
    is_low_resolution: bool

    def problems(self) -> list[str]:
        out = []
        if self.is_blurry:
            out.append("BLURRY")
        if self.is_low_resolution:
            out.append("LOW_RESOLUTION")
        return out


@dataclass
class Field:
    value: str | None
    confidence: float
    validated: bool = False
    agreement: float = 0.0
    raw: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    doc_type: str | None
    type_confidence: float
    quality: Quality
    fields: dict[str, Field]
    deskewed_by: float
    variants_used: int
    text_sample: str
    ocr_failed: bool = False          # the OCR engine was missing or crashed: a person reads the document

    def to_dict(self) -> dict:
        return {"doc_type": self.doc_type, "type_confidence": round(self.type_confidence, 3),
                "quality": asdict(self.quality), "deskewed_by": self.deskewed_by, "variants_used": self.variants_used,
                "ocr_failed": self.ocr_failed,
                "fields": {k: {"value": v.value, "confidence": round(v.confidence, 3), "validated": v.validated,
                               "agreement": round(v.agreement, 2)} for k, v in self.fields.items()}}


# ------------------------------------------------------------------------------------- image helpers
def decode(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not a decodable image")
    return img


def _std_width(img: np.ndarray, width: int = 1240) -> np.ndarray:
    h, w = img.shape[:2]
    if w == width:
        return img
    return cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA if w > width else cv2.INTER_CUBIC)


def _suppress_watermark(img: np.ndarray) -> np.ndarray:
    """Pink/red specimen watermarks are bright in the red channel; dark text is not."""
    _, th = cv2.threshold(img[:, :, 2], 150, 255, cv2.THRESH_BINARY)
    return th


def skew_angle(img: np.ndarray) -> float:
    inv = 255 - _suppress_watermark(img)
    small = cv2.resize(inv, None, fx=0.35, fy=0.35, interpolation=cv2.INTER_AREA)
    h, w = small.shape
    best_a, best_s = 0.0, -1.0
    for a in np.arange(-12, 12.01, 0.25):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(a), 1.0)
        r = cv2.warpAffine(small, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        s = float(np.var(np.diff(r.sum(axis=1).astype(float))))
        if s > best_s:
            best_a, best_s = float(a), s
    return best_a


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def assess_quality(img: np.ndarray) -> Quality:
    h, w = img.shape[:2]
    g = cv2.cvtColor(_std_width(img, 1000), cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(g, cv2.CV_64F).var())
    ang = skew_angle(img)
    return Quality(width=w, height=h, blur_score=round(blur, 1), skew_degrees=ang,
                   is_blurry=blur < 100.0, is_low_resolution=min(w, h) < 500)


# ------------------------------------------------------------------------------------- OCR
def _ocr_lines(bin_img: np.ndarray) -> list[tuple[str, float]]:
    d = pytesseract.image_to_data(bin_img, config="--psm 6", output_type=pytesseract.Output.DICT)
    lines: dict[tuple, list] = {}
    for i, txt in enumerate(d["text"]):
        t = (txt or "").strip()
        if not t:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        lines.setdefault(key, []).append((d["left"][i], t, max(0.0, float(d["conf"][i])) / 100.0))
    out = []
    for key in sorted(lines):
        words = sorted(lines[key])
        out.append((" ".join(w[1] for w in words), [w[2] for w in words]))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def classify(text: str) -> tuple[str | None, float]:
    t = text.lower()
    scores = {}
    for dt, keys in TITLE_KEYS.items():
        scores[dt] = sum(2 if k in t else (1 if fuzz.partial_ratio(k, t) >= 90 else 0) for k in keys)
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if scores[best] == 0:
        return None, 0.0
    return best, scores[best] / total


def _match_label(line: str, labels) -> tuple[str | None, int]:
    """Return (field, number of words the label occupies) if the line starts with a known label."""
    words = line.split()
    nl = _norm(line)
    best = (None, 0, 0)
    for fname, variants in labels:
        for lab in variants:
            ln = len(lab.split())
            head = _norm(" ".join(words[:ln]))
            target = _norm(lab)
            score = 100 if nl.startswith(target) else fuzz.ratio(head, target)
            if score >= 85 and (score, ln) > (best[2], best[1]):
                best = (fname, ln, score)
    return best[0], best[1]


def _join_address(a: str, b: str) -> str:
    if not a:
        return b
    if b[:1].islower() or (a[-1:].isdigit() and b[:1].isdigit()):
        return a + b
    return a + " " + b


def parse_fields(doc_type: str, lines: list[tuple[str, list[float]]]) -> dict[str, tuple[str, float]]:
    labels = LABELS[doc_type]
    out: dict[str, tuple[str, float]] = {}
    pending = None       # signatory card: label on one line, value on the next
    last_field = None
    for text, confs in lines:
        if any(k in text.lower() for k in ("specimen", "hackathon", "fictional", "format for")):
            continue
        fname, nwords = _match_label(text, labels)
        words = text.split()
        if doc_type == "signatory_id":
            if fname and nwords == len(words):
                pending = fname
                continue
            if pending:
                out[pending] = (text, float(np.mean(confs)) if confs else 0.0)
                pending = None
            continue
        if fname:
            val_words, val_conf = words[nwords:], confs[nwords:]
            val = " ".join(val_words).strip(" :")
            c = float(np.mean(val_conf)) if val_conf else 0.0
            if fname == "address_cont":
                prev, pc = out.get("address", ("", c))
                out["address"] = (_join_address(prev, val), (pc + c) / 2)
                last_field = "address"
                continue
            out[fname] = (val, c)
            last_field = fname
        elif last_field in ADDRESS_FIELDS and text and not out.get("bill_date"):
            prev, pc = out[last_field]
            out[last_field] = (_join_address(prev, text), (pc + float(np.mean(confs))) / 2)
            last_field = None
    return out


# ------------------------------------------------------------------------------------- normalisation + validation
def norm_date(s: str | None) -> str | None:
    if not s:
        return None
    t = s.replace(" ", "").replace(".", "-").replace("/", "-").replace("O", "0").replace("o", "0")
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", t)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def normalise_field(name: str, value: str | None) -> tuple[str | None, bool]:
    """Return (normalised value, validated flag)."""
    if value is None:
        return None, False
    v = value.strip()
    if name == "gstin":
        g = normalise_gstin(v)
        return g, bool(g) and not validate_gstin(g)
    if name == "udyam_number":
        if not re.search(r"\d", v):
            return None, False
        u = normalise_udyam(v)
        return u, bool(u) and not validate_udyam(u)
    if name in DATE_FIELDS:
        d = norm_date(v)
        return d, d is not None
    if name == "amount_due":
        n = re.sub(r"[^\d]", "", v)
        return (n or None), bool(n)
    if name in ("consumer_no", "units_consumed"):
        n = re.sub(r"[^\d]", "", v)
        return (n or None), bool(n)
    if name == "id_no":
        return v.upper().replace(" ", ""), bool(re.fullmatch(r"[A-Z]{3}-ID-\d{6}", v.upper().replace(" ", "")))
    v = re.sub(r"\s+", " ", v).strip(" .,:;|")
    v = v.replace(" ,", ",")
    return (v or None), bool(v)


def _vote(name: str, candidates: list[tuple[str | None, float]]) -> Field:
    norm = [(normalise_field(name, v), c, v) for v, c in candidates if v]
    if not norm:
        return Field(None, 0.0, False, 0.0, [])
    validated = [x for x in norm if x[0][1]]
    pool = validated or norm
    counts = Counter(x[0][0] for x in pool)
    top_val, n = counts.most_common(1)[0]
    # prefer the value with most votes; break ties by confidence
    best = max((x for x in pool if x[0][0] == top_val), key=lambda x: x[1])
    agreement = n / len(norm)
    conf = best[1] * (0.6 + 0.4 * agreement)
    if name == "gstin" and top_val and gstin_checksum_ok(top_val):
        conf = max(conf, 0.9 * best[1] + 0.1)   # a checksum-valid GSTIN is strong evidence
    return Field(top_val, min(1.0, conf), bool(validated), agreement, [x[2] for x in norm])


def extract(data: bytes, declared_type: str | None = None) -> Extraction:
    img = decode(data)
    q = assess_quality(img)
    ang = q.skew_degrees if abs(q.skew_degrees) >= 0.5 else 0.0
    work = rotate(img, ang) if ang else img
    work = _std_width(work, 1240)
    variants = [_suppress_watermark(work),
                _suppress_watermark(cv2.resize(work, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)),
                cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)]
    try:
        all_lines = [_ocr_lines(v) for v in variants]
    except Exception as e:  # noqa: BLE001 - engine missing (TesseractNotFoundError) or crashed: keep the document
        logging.getLogger("app.kyc").error("OCR engine failed (%s); document kept for human review", type(e).__name__)
        return Extraction(None, 0.0, q, {}, ang, 0, "", ocr_failed=True)
    text = "\n".join(t for t, _ in all_lines[0])
    doc_type, tconf = classify("\n".join(t for lines in all_lines for t, _ in lines))
    parse_as = doc_type or declared_type
    fields: dict[str, Field] = {}
    if parse_as in LABELS and not q.is_blurry:
        per_variant = [parse_fields(parse_as, lines) for lines in all_lines]
        names = {n for pv in per_variant for n in pv}
        for n in names:
            fields[n] = _vote(n, [pv.get(n, (None, 0.0)) for pv in per_variant])
    return Extraction(doc_type, tconf, q, fields, ang, len(variants), text[:400])


def ocr_engine_available() -> bool:
    """True when the Tesseract binary can be called (reported by /api/health)."""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False
