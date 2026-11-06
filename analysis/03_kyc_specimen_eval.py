"""Step 3 - run Smart KYC end-to-end on all 47 specimen documents (12 applicants).

Usage:  python -I analysis/03_kyc_specimen_eval.py [data_dir]
Writes: analysis/outputs/kyc_specimen_results.json, analysis/outputs/kyc_specimen_results.md

The applicant's *declaration* (what they would type in the journey: business name, GSTIN, Udyam
number, signatory) is taken from the matching lead in smb_leads.csv. The match is made from the
address-proof's 'billed to' name plus its city - no identifiers are copied from the documents.
This is our own evaluation; the judges' answer key was not available to us.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import imagehash  # noqa: E402
from PIL import Image  # noqa: E402

from app.kyc.checks import Declaration, evaluate  # noqa: E402
from app.kyc.document_ai import extract  # noqa: E402
from app.kyc.registry import MockRegistry  # noqa: E402

D = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "data" / "raw"
OUT = ROOT / "analysis" / "outputs"
K = D / "kyc_documents"
SLOTS = ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id")

leads = list(csv.DictReader(open(D / "smb_leads.csv", newline="", encoding="utf-8")))
registry = MockRegistry()
applicants = sorted({p.name[:3] for p in K.glob("K*.png")})

# global duplicate index across ALL uploaded images (exact + perceptual)
sha, phash = {}, {}
for p in sorted(K.glob("*.png")):
    sha[p.stem] = hashlib.sha256(p.read_bytes()).hexdigest()
    phash[p.stem] = imagehash.phash(Image.open(p))
exact_dupes = defaultdict(list)
for k, h in sha.items():
    exact_dupes[h].append(k)
# Perceptual hashing is reported but NOT used as a duplicate signal: every specimen of a type shares one
# template and watermark, so pHash distances between different businesses are 0-2 (false positives).
same_template_pairs = 0
keys = sorted(phash)
for i, a in enumerate(keys):
    for b in keys[i + 1:]:
        if a[:3] != b[:3] and a[4:] == b[4:] and phash[a] - phash[b] <= 2:
            same_template_pairs += 1
near_dupes = []   # content-based duplicates are computed after extraction (key identifiers per slot)
KEY_FIELD = {"address_proof": "consumer_no", "signatory_id": "id_no", "gst_certificate": "gstin", "udyam_certificate": "udyam_number"}
content_index = defaultdict(list)

results, t0 = {}, time.time()
for app_id in applicants:
    docs, timings = {}, {}
    for slot in SLOTS:
        f = K / f"{app_id}_{slot}.png"
        if f.exists():
            t = time.time()
            docs[slot] = extract(f.read_bytes(), slot)
            timings[slot] = round(time.time() - t, 2)
        else:
            docs[slot] = None
    for slot, ex in docs.items():
        if ex is not None and KEY_FIELD[slot] in ex.fields and ex.fields[KEY_FIELD[slot]].value:
            content_index[(slot, ex.fields[KEY_FIELD[slot]].value)].append(app_id)
    ap = docs.get("address_proof")
    billed = ap.fields["billed_to"].value if ap and "billed_to" in ap.fields else None
    addr = ap.fields["supply_address"].value if ap and "supply_address" in ap.fields else ""
    # word-boundary match: 'Patna' must not match inside 'Visakhapatnam'
    match = [r for r in leads if r["business_name"] == billed
             and re.search(r"\b" + re.escape(r["city"]) + r"\b", addr or "", re.IGNORECASE)]
    lead = match[0] if len(match) == 1 else None
    decl = Declaration(
        business_name=lead["business_name"] if lead else (billed or ""),
        signatory_name=lead["contact_name"] if lead else "",
        gstin=(lead["gstin"] or None) if lead else None,
        udyam_number=(lead["udyam_number"] or None) if lead else None,
        city=lead["city"] if lead else None, state=lead["state"] if lead else None)
    dup_map = {}
    for slot, ex in docs.items():
        if ex is not None:
            h = sha[f"{app_id}_{slot}"]
            others = [x for x in exact_dupes[h] if x != f"{app_id}_{slot}"]
            if others:
                dup_map[h] = [slot] + others
    res = evaluate(decl, {k: v for k, v in docs.items() if v is not None} | {k: None for k, v in docs.items() if v is None},
                   registry, duplicate_hashes=dup_map or None)
    results[app_id] = {"lead_id": lead["lead_id"] if lead else None, "declared_business": decl.business_name,
                       "declared_signatory": decl.signatory_name, "has_gstin": bool(decl.gstin),
                       "has_udyam": bool(decl.udyam_number), "timings_s": timings, **res.to_dict()}
    codes = [f"{f.code}[{f.severity}]" for f in res.findings]
    print(f"{app_id} {lead['lead_id'] if lead else '-':7s} {res.decision:16s} {', '.join(codes)}")

near_dupes = [{"slot": k[0], "key": k[1][:4] + "...", "applicants": v} for k, v in content_index.items() if len(set(v)) > 1]
summary = {
    "applicants": len(applicants), "documents": sum(1 for _ in K.glob("*.png")),
    "decisions": {d: sorted(a for a, r in results.items() if r["decision"] == d) for d in ("verified", "action_required", "manual_review")},
    "exact_duplicates_across_applicants": [v for v in exact_dupes.values() if len(v) > 1],
    "content_duplicates_across_applicants": near_dupes,
    "phash_same_template_pairs_ignored": same_template_pairs,
    "seconds_total": round(time.time() - t0, 1),
}
(OUT / "kyc_specimen_results.json").write_text(json.dumps({"summary": summary, "applicants": results}, indent=1, default=str))

SEV = {"block": "BLOCK", "review": "review", "resubmit": "customer fix", "info": "info"}
lines = ["# Smart KYC - specimen run (our evaluation, not the judges' answer key)", "",
         f"{summary['documents']} documents, {summary['applicants']} applicants, reference date 2026-07-15, "
         f"address proof max age 90 days. Run time {summary['seconds_total']} s on 2 CPU cores.", "",
         "| Applicant | Lead | Decision | What the engine found |", "|---|---|---|---|"]
for a, r in results.items():
    found = "; ".join(f"{f['code']} ({SEV[f['severity']]}{', ' + f['document'] if f['document'] else ''})"
                      for f in r["findings"] if f["severity"] != "info" or f["code"] in ("MISSING_DOCUMENT", "AUTO_DESKEWED", "OCR_CORRECTED", "ACTIVITY_DIFFERS")) or "all checks passed"
    lines.append(f"| {a} | {r['lead_id']} | **{r['decision']}** | {found} |")
lines += ["", f"Exact duplicate images across applicants: {len(summary['exact_duplicates_across_applicants'])}; "
          f"content duplicates (same consumer no. / ID no. / GSTIN / Udyam on two applicants): {len(near_dupes)}. "
          f"Perceptual hashing was rejected as a duplicate signal: {same_template_pairs} cross-applicant pairs of different "
          "businesses scored as near-identical because the specimens share one template.", "",
          "Notes", "- Severity 'customer fix' -> the owner is told exactly what to re-upload; 'review' -> a KYC reviewer sees the case;",
          "  'BLOCK' -> a product rule is affected (GST-only products cannot be activated).",
          "- Udyam certificate dates and the 'Services'/'Trading' activity label differ from the registry on every specimen;",
          "  they are treated as informational so they cannot cause false rejections."]
(OUT / "kyc_specimen_results.md").write_text("\n".join(lines) + "\n")
print(json.dumps(summary["decisions"]), "| exact dupes:", summary["exact_duplicates_across_applicants"], "| content dupes:", near_dupes, "| pHash template pairs ignored:", same_template_pairs)
