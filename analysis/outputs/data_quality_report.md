# Data quality report

Source: `raw/` (extracted from YTL_TrackA_Udyam_Digital_Data.zip; README inside the ZIP is byte-identical to the standalone README).

## Inventory

| File | Bytes | Rows | Cols | SHA-256 (16) |
|---|---:|---:|---:|---|
| README.md | 4,238 |  |  | `9eadd69ff1174519` |
| mock_gstin_registry.csv | 628,438 | 3534 | 8 | `53f18df9ef8298df` |
| mock_udyam_registry.csv | 271,446 | 2723 | 8 | `588ae3503180dd34` |
| product_catalogue.csv | 4,080 | 25 | 16 | `5110529705bda36f` |
| smb_leads.csv | 1,517,309 | 5000 | 40 | `b2521e8cedcf3b57` |
| kyc_documents/ (47 PNG) | 5,538,229 | | | applicants K01-K12; K05 has no Udyam certificate |

## Checks

| Area | Check | Result | Detail |
|---|---|---|---|
| inventory | 47 KYC images for 12 applicants | PASS | 47 images, 12 applicants; incomplete sets: {'K05': ['udyam_certificate']} |
| inventory | README row counts | PASS | leads=5000, catalogue=25, gstin=3534, udyam=2723 |
| leads | lead_id unique | PASS | 0 duplicates |
| leads | created_date within Apr-Jun 2026 | PASS | 2026-04-01 to 2026-06-30 |
| leads | stage dates in chronological order | PASS | 0 out-of-order pairs |
| leads | stage_reached consistent with populated stage dates | PASS | 0 inconsistent rows |
| leads | outcome consistent with stage_reached | PASS | Activated <=> stage Activated |
| leads | days_lead_to_activation = activated - created | PASS | mean 17.6 days (README: 17.6) |
| leads | post-activation fields only populated for activated leads | PASS | 0 violations |
| leads | drop_reason present for every dropped lead | PASS | 21 distinct reasons, each tied to one stage |
| leads | has_gstin flag matches gstin field | PASS | 3534 leads with GSTIN |
| leads | has_udyam flag matches udyam_number field | PASS | 2723 leads with Udyam |
| leads | no stage dates after the 15 Jul 2026 reference date | WARN | 18 leads have KYC/activation dates after 2026-07-15 (latest 2026-07-26); kept as-is - the reference date is only used for document-age checks |
| leads | no duplicate business+city leads | PASS | 0 duplicates |
| registry | every lead GSTIN exists in mock GST registry | PASS | 3534 of 3534 found; registry has no orphan rows: True |
| registry | every lead Udyam number exists in mock Udyam registry | PASS | registry has no orphan rows: True |
| registry | GSTIN checksum valid for every registry record | PASS | mod-36 checksum, 3,534/3,534 |
| registry | GSTIN PAN 4th character is X (synthetic convention) | PASS | README: accept X - no real taxpayer can match |
| registry | GSTIN state code consistent with lead state | PASS | one code per state |
| registry | Udyam numbers use district code 00 (synthetic convention) | PASS | README: 00 does not exist in reality |
| registry | GST registry status mix | PASS | {'Active': 3266, 'Cancelled': 167, 'Suspended': 101} |
| catalogue | activated bundles comply with catalogue eligibility rules | WARN | 56 of 368 activated bundles (15.2%) break at least one rule: {'city tier': 24, 'GSTIN required, none held': 12, 'dependency missing': 9, 'min employees': 8, 'GSTIN required, registry status Cancelled': 7, 'GSTIN required, registry status Suspended': 3} |
| catalogue | realised bundle value inside catalogue price range | PASS | position in [min,max] range: mean 0.48, median 0.47 |
| catalogue | one-time setup = sum(catalogue setup x quantity) | PASS | exact for all 368 |
| catalogue | contract months = longest product minimum term in bundle | PASS | exact for all 368 |
| catalogue | 25 products, unique IDs, min<=max price | PASS | P01-P25 |
| funnel | cumulative funnel reproduces README | PASS | {'Lead': 5000, 'Contacted': 3406, 'Needs assessed': 1974, 'Quote accepted': 861, 'KYC complete': 588, 'Activated': 368} |

## Notes

- `stage_reached` is the last stage a lead reached; the cumulative funnel is derived from it (stage index >= k).
- The KYC images use specimen watermarks on every page; this is a universal artefact, not a defect.
- Udyam certificate registration dates never equal the registry dates and every 'Trading' registry record prints
  'Services' on its certificate. Both are systematic generator artefacts, so the KYC engine treats them as soft
  (informational) checks instead of rejection reasons.
- 56 activated bundles break catalogue rules (e.g. Biz Fibre 1G sold in tier-2 cities). This is evidence of manual
  quoting error, and the reason eligibility is enforced deterministically in the new journey.
