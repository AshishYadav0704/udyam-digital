# Commercial strategy and business case

All baseline figures are **observed** in the competition's synthetic data (`smb_leads.csv`, 5,000 leads, Apr-Jun 2026)
and computed by `analysis/02_business_diagnosis.py`. Scenario figures are **calculated** by
`analysis/05_business_case.py` from those observations plus **assumptions** that are listed, sized and justified there.
Accel is the case study's fictional operator; none of this is real Airtel performance.

## 1. What the data says

| | Observed | Why it matters |
|---|---|---|
| Lead to activation | 368 of 5,000 = **7.36%** | Every one of the five steps loses more than 30% of the leads that reach it |
| Blended CAC (spend / activations) | **₹15,053** (₹55.4 lakh / 368) | Field sales ₹24,335 and partners ₹20,851 per activation, against ₹4,026-6,352 for WhatsApp, referral, inbound and website |
| Largest single leak | Needs assessed to quote accepted: **1,113 lost** (price 621, quote experience 385, decided to wait 107) | The quote itself is the product's weakest moment |
| Visit friction | **827** lost because the owner had no time for a visit (531) or sales never scheduled one (296) | Needs discovery does not need a visit for standard bundles |
| KYC after a quote was accepted | **273 lost**: missing GST/Udyam document 94, paperwork too long 79, signatory unavailable 53, details mismatch 47 | Paperwork, not price, loses customers who already said yes |
| After KYC | **220 lost**: installation over 21 days 98, cancelled 53, fibre not feasible 41, first payment failed 28 | Operations and fallbacks, not sales |
| Status calls per activated customer | **3.0**; customers with 1 call: 5.9% churn and NPS 7.5; with 5 calls: 27.9% churn and NPS 6.0 | Correlation, not proof, but it points at visibility |
| Days lead to activation | **17.6** on average | Activations within 15 days score NPS 7.3 against 6.0 beyond 21 days |
| GSTIN holders | 9.6% activate vs 2.0% without; KYC completion after quote 81% vs 25% | Non-GST businesses need their own KYC path, not a dead end |
| Price vs current spend | Price objections rise from 26% to 36% across price-to-spend quintiles; micro owners are quoted a median 1.44x what they spend today | Right-sizing against today's spend is a conversion lever |

### Segments

| Segment | Leads | Activation | CAC | Monthly bundle | Share of new MRR | Revenue payback* | 6-month churn |
|---|---:|---:|---:|---:|---:|---:|---:|
| Micro retail & services | 2,709 (54%) | 4.1% | ₹20,007 | ₹2,505 | 6% | 8.0 months | 22.7% |
| Professional practices | 1,247 | 11.1% | ₹10,695 | ₹6,796 | 21% | 1.6 months | 13.8% |
| Multi-site businesses | 755 | 11.0% | ₹15,614 | ₹31,233 | 57% | 0.5 months | 10.8% |
| Small manufacturers | 289 | 12.8% | ₹15,324 | ₹19,980 | 16% | 0.8 months | 8.1% |

\* CAC divided by the monthly bundle value: months of revenue (not margin) to recover acquisition cost.

## 2. Segment strategy

- **Micro (self-serve first).** Half the leads, 6% of the revenue and an 8-month revenue payback: field sales cannot
  serve them profitably. The digital journey, a mobile-only checkout, the lowest-cost option and a non-GST KYC path are
  built for them. People help only when asked, or when a partner already knows the shop.
- **Professional practices (digital with an assisted safety net).** The best near-term return: 11% activation,
  1.6-month payback, mostly GST-registered (fast KYC). Cloud email, backup and telephony bundles are standard and
  quote well online.
- **Multi-site and manufacturing (sales-led, digitally assisted).** 73% of new monthly revenue. Bundles over ₹25,000 a
  month or with leased lines, SD-WAN or managed firewalls go to field or key-account sales. The same quote, KYC and
  tracker screens remove the paperwork and status calls from those deals.

## 3. Hybrid channel model and routing

Every lead and order gets a route, a reason and an SLA (`backend/app/domain/routing.py`), checked in this order:

| Condition | Route | SLA |
|---|---|---|
| KYC needs a person (any review or block finding) | KYC reviewer | 4 h |
| City not open for online sign-up (outside tier 1-2) | Local channel partner | 48 h |
| Multi-site or manufacturing, and ₹25,000+ a month or a complex product (P05, P06, P10, P21) | Field / key-account sales | 24 h |
| Owner asked for a person | Assisted digital (inside sales on the same screen), or the attributed partner | 24 h |
| Historic lead lost for a reason the journey removes | Assisted digital (win-back), or partner for micro shops they know | 24 h |
| Stalled 48 h with a priority or watch score | Assisted digital | 24 h |
| Everything else | Self-serve | none |

The propensity score orders queues; it never removes anyone from one. Because the model never ranks non-GST micro
leads highly (it learned that they rarely activated), assisted capacity is reserved for them explicitly.

Partners keep their role: QR codes and referral links carry the partner code, so partner-sourced digital sign-ups stay
attributed, and partners see only their own leads and orders in the back office.

## 4. Pricing policy

- One published price per product: the midpoint of the catalogue range. Against the historic bundles this is revenue
  neutral (**100.2%** of actual MRR; the floor would be 86.1%). No negotiation in the self-serve flow.
- Every plan shows a recommended option and a lower-cost Starter option side by side.
- GST at 18% (SAC 9984) is shown separately as an estimate, because the catalogue does not say whether its prices
  include tax.
- The server re-prices at checkout; the client cannot change a price.

## 5. Scenarios (one quarter at the dataset's scale)

| | Baseline (observed) | Conservative | Expected | Ambitious |
|---|---:|---:|---:|---:|
| Leads using the digital journey (assumption) | 0% | 40% | 60% | 80% |
| Activations | 368 | 405 | 500 | 763 |
| Lead to activation | 7.36% | 8.1% | 10.0% | 15.3% |
| New monthly revenue added in the quarter | ₹45.4 lakh | ₹49.4 lakh | ₹58.5 lakh | ₹81.5 lakh |
| Blended CAC, acquisition spend held at history | ₹15,053 | ₹14,484 | ₹11,761 | ₹7,751 |
| CAC if part of field effort moves to digital-first | - | ₹13,319 | ₹9,876 | ₹5,899 |
| Days lead to activation | 17.6 | 13.1 | 10.8 | 8.6 |
| Year-1 incremental revenue | - | ₹0.93 crore | ₹3.08 crore | ₹8.51 crore |
| Months to recover a ₹75 lakh build (35% contribution, assumption) | - | 23 | 11 | 6 |

How the scenarios are built: each loss reason that a module addresses gets a recovery rate (for example, "quote took
too long" 30/50/65%, "price too high" 3/7/12%, "locked in with current provider" 0%); recovery applies only to the
leads that use the digital journey; recovered leads convert at 60/75/90% of the normal rate at every later step; leads
won back from a price objection take a smaller bundle. Lower churn from fewer status calls is **not** counted.

## 6. KPIs

| KPI | Baseline | Target (expected scenario) | Calculation | Source | Frequency |
|---|---|---|---|---|---|
| Lead-to-activation rate | 7.36% | 10.0% (stretch 15%) | activated / leads created, by weekly cohort, read 30 days after creation | CRM leads + order events | Weekly |
| Blended CAC | ₹15,053 | ₹11,761 at today's spend; ₹9,876 with field effort reallocated | (acquisition spend + platform run cost) / activations | Finance ledger + order events | Monthly |
| Quote acceptance | 43.6% | 49.1% | quotes accepted / needs assessed (digital: plan recommended) | Advisor and quote events | Weekly |
| Days lead to activation | 17.6 | 10.8 (digital journeys: about 7) | median and mean days from lead creation to activation | Order milestones | Weekly |
| Status calls per activated customer | 3.0 | 1.5 or fewer (assumption: tracker visibility) | inbound status calls in the first 30 days / activations | Contact-centre logs | Monthly |

Guardrails reviewed with the KPIs: KYC false accepts found in a weekly audit sample (target 0), share of KYC cases
decided automatically, call-back SLA met, NPS index (baseline -25), lead-score calibration on live outcomes.

## 7. Rollout

| Phase | When | Scope | Gate to move on |
|---|---|---|---|
| 0. Foundations | Weeks 0-8 | GSP contract and GSTN adapter, SMS (DLT templates), payment gateway, security review, legal review of the consent notice, SSO for staff | Penetration test passed; consent notice signed off; adapters pass the same test suite as the mocks |
| 1. Pilot | Months 3-5 | Two cities (one tier 1, one tier 2), micro and professional segments, A/B against today's process | Activation uplift at least 1.1x with no rise in KYC false accepts; CAC down; NPS not lower |
| 2. Scale | Months 6-9 | Ten cities, partner QR programme, multi-site assisted flow, two more languages, DigiLocker / Entity Locker pull | Gates held for 8 consecutive weeks; partner attribution disputes under 2% |
| 3. National | Months 10-15 | All serviceable cities; lead model retrained on real outcomes; eSign; full DPDP Rules obligations in force from May 2027 | Model beats the segment x GSTIN baseline on live data; audit findings closed |

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Real phone photos read worse than the clean specimens | Low-confidence fields go to a person, not to rejection; re-measure OCR in the pilot; DigiLocker / Entity Locker pull reduces uploads |
| The lead model was trained on three months of synthetic data | It only orders queues; reserved capacity for low-score segments; retrain and recalibrate on pilot outcomes before scaling |
| Channel conflict with field sales and partners | Clear routing rules, partner attribution through QR links, sales keep high-value and complex deals |
| Regulatory change (DoT KYC, DPDP Rules) | KYC rules and consent notice are configuration and versioned; legal review per phase |
| LLM errors or unsafe output | The model never prices, decides eligibility or sees documents; grounding check; offline fallback |
| Document fraud and reuse | Checksums, registry cross-checks, cross-application duplicate detection, human review, audit trail |
| Owners not comfortable online | Hindi and English, chat or form, call-back on every screen, partner-assisted mode |

## 9. Competitive position (public sources, November 2026)

Telco offers for small businesses in India are mostly fixed packages with an enquiry form or an executive call-back:
Airtel Office Internet plans from ₹999 ("one plan, one bill"), JioBusiness plans from ₹901 to ₹10,001 a month with a
"register interest" flow, Tata Tele Business Services' consultative SmartOffice and Smartflo offers, and Vi Business's
ReadyForNext programme with a self-evaluation tool. In the public material we reviewed we did not find a telco offering
a multilingual advisor that assembles an eligibility-checked multi-product bundle and carries the owner through quote,
KYC and tracking in one session. That is our inference from public pages, not a claim about anyone's internal tools.
Sources are listed in `docs/research/research_notes.md`.
