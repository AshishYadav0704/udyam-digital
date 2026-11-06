# API reference

FastAPI serves interactive docs at `/docs` (Swagger) and `/redoc` while the API runs; the full machine-readable
spec is [`openapi.json`](openapi.json). Every price, eligibility rule and KYC decision is computed on the server;
the web app only displays what these endpoints return.

Errors use FastAPI's shape: `{"detail": ...}`. Bundle-rule failures return 422 with
`detail.violations` (machine codes) and `detail.messages` (customer-language text).

| Area | Method | Path | Who can call it | What it does |
|---|---|---|---|---|
| advisor | POST | `/api/advisor/sessions` | public, rate-limited | Start a conversation; returns the session id and its secret token |
| advisor | GET | `/api/advisor/sessions/{session_id}` | advisor session token (X-Session-Token) | Get Session |
| advisor | POST | `/api/advisor/sessions/{session_id}/escalate` | advisor session token (X-Session-Token) | Escalate |
| advisor | POST | `/api/advisor/sessions/{session_id}/messages` | advisor session token (X-Session-Token) | Message |
| advisor | PATCH | `/api/advisor/sessions/{session_id}/profile` | advisor session token (X-Session-Token) | Form-based alternative to chat: validated partial update, then recommendation if complete. |
| auth | GET | `/api/auth/me` | any JWT | Me |
| auth | POST | `/api/auth/otp/request` | public, rate-limited | Otp Request |
| auth | POST | `/api/auth/otp/verify` | public, rate-limited | Otp Verify |
| auth | POST | `/api/auth/staff/login` | public, rate-limited | Staff Login |
| backoffice | GET | `/api/backoffice/audit` | staff: admin | Audit Log |
| backoffice | GET | `/api/backoffice/escalations` | staff: sales, admin | Escalations |
| backoffice | POST | `/api/backoffice/escalations/{esc_id}` | staff: sales, admin | Update Escalation |
| backoffice | POST | `/api/backoffice/escalations/{esc_id}/reveal` | staff: sales, admin | Show the full call-back number to the person making the call. Every reveal is audited. |
| backoffice | GET | `/api/backoffice/kyc-queue` | staff: kyc_reviewer, admin | Kyc Queue |
| backoffice | GET | `/api/backoffice/kyc/{case_id}` | staff: kyc_reviewer, admin | Kyc Case |
| backoffice | POST | `/api/backoffice/kyc/{case_id}/decision` | staff: kyc_reviewer, admin | Kyc Decision |
| backoffice | GET | `/api/backoffice/leads` | staff: sales, partner (own records only), admin | List Leads |
| backoffice | GET | `/api/backoffice/leads/{lead_id}` | staff: sales, partner (own records only), admin | Lead Detail |
| backoffice | POST | `/api/backoffice/leads/{lead_id}/assign` | staff: sales, partner (own records only), admin | Assign |
| backoffice | GET | `/api/backoffice/orders` | staff: sales, partner (own records only), admin | Staff Orders |
| backoffice | GET | `/api/backoffice/overview` | staff: any role | Overview |
| backoffice | GET | `/api/backoffice/partners` | staff: sales, partner (own records only), admin | Partners |
| backoffice | POST | `/api/backoffice/score` | staff: any role | Score |
| commerce | POST | `/api/checkout` | customer JWT + session token | Checkout |
| commerce | GET | `/api/orders` | customer JWT (own orders); partner sees attributed orders | My Orders |
| commerce | GET | `/api/orders/{order_id}` | customer JWT (own orders); partner sees attributed orders | Get Order |
| commerce | POST | `/api/orders/{order_id}/advance` | staff: sales, admin; customer only outside production | Move an order to its next milestone. Staff in any environment; customers only in demo mode. |
| commerce | POST | `/api/orders/{order_id}/help` | customer JWT (own orders); partner sees attributed orders | Order Help |
| commerce | POST | `/api/orders/{order_id}/payment` | customer JWT (own orders); partner sees attributed orders | Retry Payment |
| commerce | POST | `/api/quotes` | advisor session token (X-Session-Token) | Save a quote to come back to later (addresses 'decided to wait'). |
| commerce | POST | `/api/quotes/preview` | advisor session token (X-Session-Token) | Preview |
| kyc | GET | `/api/consent` | customer JWT (own data) | My Consents |
| kyc | POST | `/api/consent` | customer JWT (own data) | Give Consent |
| kyc | POST | `/api/consent/withdraw` | customer JWT (own data) | Withdraw |
| kyc | POST | `/api/kyc/cases` | customer JWT (own data) | Create Case |
| kyc | GET | `/api/kyc/cases/{case_id}` | customer JWT (own case) or kyc_reviewer/admin; image views audited | Get Case |
| kyc | POST | `/api/kyc/cases/{case_id}/documents` | customer JWT (own data) | Upload |
| kyc | DELETE | `/api/kyc/cases/{case_id}/documents/{doc_id}` | customer JWT (own data) | Delete Doc |
| kyc | GET | `/api/kyc/cases/{case_id}/documents/{doc_id}/image` | customer JWT (own case) or kyc_reviewer/admin; image views audited | Doc Image |
| kyc | POST | `/api/kyc/cases/{case_id}/evaluate` | customer JWT (own data) | Evaluate Case |
| kyc | POST | `/api/kyc/cases/{case_id}/specimen` | customer JWT; disabled in production | Demo helper (disabled in production): load one of the 12 specimen applicants as if uploaded. |
| kyc | GET | `/api/privacy/summary` | customer JWT (own data) | Right to access: a summary of what we hold, with identifiers masked. |
| public | GET | `/api/catalogue/business-types` | public | Business types the advisor understands (same registry as the chat extractor), for the form fallback. |
| public | GET | `/api/catalogue/cities` | public | City List |
| public | GET | `/api/catalogue/products` | public | Products |
| public | GET | `/api/consent/notice` | public | Consent Notice |
| public | GET | `/api/health` | public | Status and configuration: LLM provider in use, lead model loaded, OCR engine available, synthetic-identifier mode, price policy |
| public | GET | `/api/registry/gstin/{gstin}` | public, rate-limited, minimal response | Pre-fill helper. Returns only what onboarding needs (data minimisation) and is rate limited. |
| public | GET | `/api/registry/udyam/{number}` | public, rate-limited, minimal response | Udyam Lookup |

49 operations.

## Typical call sequence (customer journey)

1. `POST /api/advisor/sessions` - returns `session_id` and a one-time `session_token` (send it as `X-Session-Token`).
2. `POST /api/advisor/sessions/{id}/messages` - free text, chip answers, `needs`, or `action` = `show_plan` / `skip` / `human`.
   Alternative: `PATCH /api/advisor/sessions/{id}/profile` with the form fields.
3. `POST /api/quotes/preview` for live re-pricing of add-ons; `POST /api/quotes` to save a quote (15-day validity).
4. `POST /api/auth/otp/request` then `/otp/verify` (mobile OTP) - returns a customer JWT.
5. `POST /api/checkout` - server recomputes the quote and places the order; `POST /api/orders/{id}/payment` retries payment.
6. `POST /api/consent` (itemised purposes), `POST /api/kyc/cases`, `POST /api/kyc/cases/{id}/documents` (multipart, one per slot),
   `POST /api/kyc/cases/{id}/evaluate` - returns the decision (`verified`, `action_required`, `manual_review`) with findings.
7. `GET /api/orders/{id}` - tracker with milestones, blockers and installation dates; `POST /api/orders/{id}/help` for a call-back.
