# Smart KYC - specimen run (our evaluation, not the judges' answer key)

47 documents, 12 applicants, reference date 2026-07-15, address proof max age 90 days. Run time 54.5 s on 2 CPU cores.

| Applicant | Lead | Decision | What the engine found |
|---|---|---|---|
| K01 | L00045 | **manual_review** | GSTIN_NOT_ACTIVE (BLOCK); UDYAM_UNVERIFIABLE (customer fix, udyam_certificate) |
| K02 | L01287 | **verified** | AUTO_DESKEWED (info, gst_certificate) |
| K03 | L03571 | **verified** | all checks passed |
| K04 | L01014 | **action_required** | UNREADABLE_DOCUMENT (customer fix, gst_certificate) |
| K05 | L04014 | **verified** | MISSING_DOCUMENT (info, udyam_certificate) |
| K06 | L00115 | **manual_review** | GSTIN_MISMATCH (review, gst_certificate); ACTIVITY_DIFFERS (info, udyam_certificate) |
| K07 | L03349 | **manual_review** | LEGAL_NAME_MISMATCH (review, gst_certificate); CERTIFICATE_INTERNALLY_INCONSISTENT (review, gst_certificate) |
| K08 | L03473 | **verified** | all checks passed |
| K09 | L04779 | **verified** | all checks passed |
| K10 | L04525 | **manual_review** | OCR_CORRECTED (info, gst_certificate); ACTIVITY_DIFFERS (info, udyam_certificate); SIGNATORY_MISMATCH (review, signatory_id) |
| K11 | L03485 | **action_required** | ACTIVITY_DIFFERS (info, udyam_certificate); ADDRESS_PROOF_TOO_OLD (customer fix, address_proof) |
| K12 | L03558 | **verified** | ACTIVITY_DIFFERS (info, udyam_certificate) |

Exact duplicate images across applicants: 0; content duplicates (same consumer no. / ID no. / GSTIN / Udyam on two applicants): 0. Perceptual hashing was rejected as a duplicate signal: 143 cross-applicant pairs of different businesses scored as near-identical because the specimens share one template.

Notes
- Severity 'customer fix' -> the owner is told exactly what to re-upload; 'review' -> a KYC reviewer sees the case;
  'BLOCK' -> a product rule is affected (GST-only products cannot be activated).
- Udyam certificate dates and the 'Services'/'Trading' activity label differ from the registry on every specimen;
  they are treated as informational so they cannot cause false rejections.
