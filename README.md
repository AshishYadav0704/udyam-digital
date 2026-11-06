# Udyam Digital - Accel Business MSME journey

Team **Shankhnad**, MMMUT Gorakhpur. Airtel SYNC 2026, Digital Track, Enterprise Track A: *Project Udyam Digital*.

A working prototype of a guided, bilingual (Hindi and English) journey that takes a small business from "what do I need?"
to an activated, KYC-verified connection, plus the back office that sales, partners and KYC reviewers use behind it.

**Demo video:** https://youtu.be/M5kciftmRfQ

> **Data notice.** Accel Telecom / Accel Business is the case study's fictional operator. Every lead, document and
> registry record here is the synthetic competition data. Nothing in this repository is real Airtel customer data or
> real Airtel business performance. The GST and Udyam "registries" are local mocks built from that data, not
> government APIs.

## What is in the box

| Area | What it does | Where |
|---|---|---|
| Data diagnosis | Funnel, segments, channels, unit economics, drop reasons mapped to product levers | `analysis/02_business_diagnosis.py`, `analysis/outputs/business_diagnosis.md` |
| Advisor | Chat or form; understands English, Hinglish and Devanagari; asks only what is missing; optional LLM provider, never trusted for prices or rules | `backend/app/advisor/` |
| Rules engine | Catalogue-driven eligibility, dependencies, quantities, contract term, install schedule, GST shown separately | `backend/app/domain/` |
| Quote and checkout | One published price per product, server-side re-pricing, saved quotes, OTP login, payment retry | `backend/app/routers/commerce.py` |
| Smart KYC | Consent first; upload hardening; deskew, blur check, watermark suppression, OCR ensemble; GSTIN checksum, registry cross-checks, address-proof age, signatory match, duplicate detection; verified / action needed / human review | `backend/app/kyc/` |
| Propensity model | Leakage-free lead scoring (chronological split), calibrated, explained per lead; ranks who to call first, never changes price or eligibility | `ml/train_propensity.py`, `backend/app/ml/` |
| Routing | Self-serve, assisted digital, partner, field sales or KYC review, with reasons and SLA | `backend/app/domain/routing.py` |
| Back office | Overview (live vs synthetic baseline), leads with score drivers, search, filters and follow-up history, KYC queue and decisions, orders, partners, call-backs, audit log | `frontend/src/pages/ops/` |
| Customer web app | 15 mobile-first screens, Hindi and English | `frontend/src/pages/` |

Screens, in journey order: landing, language, onboarding, advisor (chat or form), recommendation, add-ons, quotation,
checkout, KYC consent, document upload, verification result, confirmation, order tracker, support, call-back
(human escalation), plus "My privacy". Screenshots of each are in `docs/screenshots/`.

## Results you can reproduce

All numbers below are produced by the scripts in this repository from the competition data.

| Finding | Value | Source |
|---|---|---|
| Lead-to-activation, Apr-Jun 2026 | 368 of 5,000 = 7.36% | `analysis/outputs/metrics.json` |
| Blended acquisition cost (total spend / activations) | ₹15,053 | same |
| Biggest single loss | 1,113 leads lost between needs assessment and quote acceptance (price 621, quote experience 385) | same |
| Status calls per activated customer | 3.0; NPS index -25 | same |
| Advisor extraction, 40 held-out utterances | 94.0% of fields, 85% of utterances fully right | `analysis/outputs/advisor_eval.md` |
| Lead model (logistic regression, test month = June) | PR-AUC 0.155 vs 0.106 for a segment x GSTIN baseline; top-20% lift 2.28x | `analysis/outputs/ml_report.md` |
| OCR on the 47 specimen images (149 labelled fields) | 98.7% field accuracy for the shipped pipeline | `analysis/outputs/ocr_benchmark.md` |
| KYC decisions on the 12 specimen applicants | 6 verified, 2 action needed, 4 human review | `analysis/outputs/kyc_specimen_results.md` |

The KYC decisions are this system's own evaluation of the specimens, not the organisers' answer key, which we do not have.

## Run it

Requirements: Python 3.11+ (tested on 3.13), Node 20+, and the Tesseract 5 binary (`apt install tesseract-ocr`;
macOS `brew install tesseract`; Windows: the UB Mannheim installer, then add it to `PATH`). Without Tesseract the app
still runs, `/api/health` reports `"ocr_engine": false`, and uploaded KYC documents go to a human reviewer instead of
being read automatically. `backend/constraints.txt` pins every package version we verified
(`pip install -r requirements.txt -c constraints.txt`).

```bash
# 1. backend
cd backend
python -m pip install -r requirements.txt
cp ../.env.example ../.env            # optional in development; relative paths in it resolve from backend/
python -m uvicorn app.main:app --port 8000

# 2. web app (second terminal)
cd frontend
npm ci
npm run dev                            # http://127.0.0.1:5173, proxies /api to :8000
```

Or `scripts/run_dev.sh` starts both. For a single process, `npm run build` in `frontend/` and the API serves the built
app at http://127.0.0.1:8000.

On first start the API creates a SQLite database under `storage/`, seeds six demo partners, four staff users and 600
June "win-back" leads scored by the model.

Demo access (development only; disabled or hidden when `APP_ENV=production`):

- Customer OTP: the code is shown on screen (`123456` by default). No SMS is sent.
- Staff: `sales@accel.demo`, `partner@accel.demo` (partner PTN-LKO-01), `kyc@accel.demo`, `admin@accel.demo`, password `demo1234`.
- KYC: "Demo: load a sample applicant" loads any of the 12 specimen applicants (K01-K12) from the data pack.

## Test it

```bash
cd backend && python -m pytest -q                 # 125 tests: engine, API journey, RBAC, KYC, NLU, privacy, retention,
                                                  #   .env loading, LLM adapters (recorded responses, no network)
cd frontend && npm test && npm run typecheck      # unit tests + strict TypeScript
node scripts/e2e_journey.cjs                      # 39 browser checks over every screen (needs both servers running)
node scripts/ui_audit.cjs http://127.0.0.1:8000   # 81 screens at 390/768/1280 px: console errors, overflow, small targets
python scripts/eval_advisor.py                    # held-out advisor extraction accuracy
python scripts/red_team.py                        # 25 scripted attacks (IDOR, JWT forgery, price tampering, uploads...)
python scripts/perf_probe.py                      # indicative endpoint latencies
node scripts/a11y_check.cjs <path/to/axe.min.js>  # axe-core WCAG 2.1 A/AA scan of 14 screens
```

On the submitted version every suite passes: 125 backend tests, the frontend unit tests, 39 of 39 end-to-end checks,
0 accessibility violations and 25 of 25 attack probes held. The red-team and accessibility scripts write their results
to `test-results/`.

The end-to-end script drives Chromium through two complete journeys (a clean applicant and a GSTIN mismatch that goes
to human review), a Hindi journey, the form and unserviceable-city paths, and the back office; it writes screenshots and
`docs/screenshots/e2e_results.json`.

## Reproduce the analysis

```bash
cd analysis
python -I 01_data_audit.py         # 27 data-quality checks -> outputs/data_quality_report.md
python -I 02_business_diagnosis.py # funnel, segments, channels -> outputs/metrics.json + charts
python -I 02b_segment_bundles.py    # bundle, median price and term per segment -> outputs/segment_bundles.json
python -I 03_kyc_specimen_eval.py  # pipeline on the 12 specimen applicants
python -I 04_ocr_benchmark.py      # OCR engine comparison (needs requirements-dev.txt)
python -I 05_business_case.py      # three scenarios, KPIs, payback -> outputs/business_case.json/.md
cd ../ml && python -I train_propensity.py   # model comparison, calibration, fairness -> artifacts/ + ml_report.md
cd .. && python -I analysis/06_figure_check.py   # recomputes every deck/README figure from the CSVs; exit 1 on mismatch
```

Re-running these on a clean copy reproduces the committed outputs exactly, apart from timings and run dates; the
figure check currently matches 62 of 62 figures (`analysis/outputs/figure_check.md`).

## How it is built

A modular monolith: one FastAPI service with clear internal modules, one React app, one database. See
`docs/architecture/` for the diagram and the reasoning.

- `backend/app/domain` - catalogue, eligibility, recommender, pricing, routing, identifiers (pure functions, no I/O)
- `backend/app/advisor` - offline extractor, optional LLM providers, dialogue policy
- `backend/app/kyc` - document AI, checks, registry adapters, encrypted storage
- `backend/app/routers` - HTTP API (`docs/api/API.md`, OpenAPI at `/docs`)
- `frontend/src` - React 19 + TypeScript + Tailwind; customer pages and the code-split back office

### The rules the GenAI layer cannot break

The language model, when one is configured, may only (1) turn the owner's words into profile fields that are then
validated, and (2) rephrase an explanation that is checked to contain only the plan's own product names and prices.
It never sees documents, never chooses products, never sets prices and never decides eligibility or KYC. With no API key
the advisor runs fully offline.

### Security and privacy, as implemented

- Consent is itemised by purpose before any document is collected; withdrawing KYC consent deletes documents and stops
  the order before activation.
- Documents are validated (type by magic bytes, size, dimensions), re-encoded to strip metadata, and stored encrypted
  (Fernet: AES-128-CBC + HMAC). Every view is written to the audit log.
- Identifiers are masked in API responses, the UI and logs; mobile numbers are stored as a keyed hash plus an encrypted
  copy that staff can reveal only for a call-back, with an audit entry.
- Role-based access (customer, sales, partner scoped to its own records, KYC reviewer, admin); JWT with expiry;
  rate limits on OTP, login, registry lookups and the advisor.
- Production refuses to start without its secrets or with synthetic-identifier mode on.

The one-page privacy and security note (`docs/privacy_security_note.pdf`) maps this to the DPDP Act 2023 and the DPDP
Rules 2025, including which obligations apply now and which from May 2027.

## Known limitations

- **Mock integrations.** GST and Udyam lookups use local registries built from the synthetic data. Production needs a
  GST Suvidha Provider (or GSTN-authorised API), an Udyam data source, DigiLocker / Entity Locker via API Setu, an
  eSign service provider, an SMS gateway and a payment gateway. None of these is called here.
- **Synthetic identifiers.** The pack's PANs use 'X' as the fourth character and its Udyam numbers use district 00;
  both are accepted only in `SYNTHETIC_IDENTIFIER_MODE`.
- **Small, synthetic training data.** The lead model is trained on three months of synthetic leads; its lift is modest
  (2.3x in the top 20%) and must be re-validated on real data before it influences anyone's queue.
- **OCR scope.** Tuned and measured on 47 clean synthetic specimens; real phone photos (glare, folds, regional
  layouts) will score lower. Low-confidence reads go to a person, not to rejection.
- **Prices.** Each product uses one published price at the midpoint of its catalogue range (revenue-neutral against
  the historic average, 100.2%); GST at 18% is shown as an estimate. Final tax treatment needs Finance sign-off.
- **Single instance.** SQLite and an in-memory rate limiter; production would use PostgreSQL, Redis, object storage
  with KMS-managed keys, and SSO with MFA for staff.
- **Languages.** Hindi and English today; other languages need a translation file each (UI) and NLU keywords.

## Documents

| Document | Where |
|---|---|
| Submission deck (cover + 7 content slides, PPTX + PDF) | `docs/deck/Shankhnad_MMMUT_GORAKHPUR.pptx` / `.pdf`; links to the code and demo video go in `docs/deck/links.json` (see `links.example.json`) |
| One-page privacy and security note | `docs/privacy_security_note.pdf` |
| Business case, segments, channel model, KPIs, rollout, risks | `docs/business/BUSINESS_CASE.md` |
| Architecture (diagram + explanation) | `docs/architecture/ARCHITECTURE.md` |
| API reference | `docs/api/API.md`, `docs/api/openapi.json` |
| Data diagnosis, ML, OCR, KYC and advisor reports | `analysis/outputs/*.md` |
| Independent check of every headline figure | `analysis/outputs/figure_check.md` |
| Market, competitor, regulation and integration research (cited) | `docs/research/research_notes.md` |
| Screenshots of every screen | `docs/screenshots/` (journeys) and `docs/screenshots/responsive/` (81 screens at three widths) |
| Demo video | https://youtu.be/M5kciftmRfQ |

## Repository map

```
analysis/        data audit, diagnosis, KYC and OCR evaluations (+ outputs/)
backend/         FastAPI app, tests, requirements
data/raw/        the competition pack as supplied (README, 4 CSVs, 47 KYC images)
docs/            API reference, architecture, business case, research notes, privacy note, screenshots, deck
frontend/        React web app
ml/              propensity model training and artifacts
scripts/         run, end-to-end and evaluation scripts
```
