# Business case (scenario model)

Scale: one quarter at the dataset's size (5,000 leads, Apr-Jun 2026, synthetic). Every figure below comes from
`analysis/05_business_case.py`; inputs marked *assumption* need validation in the pilot.

| | Baseline (observed) | Conservative | Expected | Ambitious |
|---|---:|---:|---:|---:|
| Leads using the digital journey (*assumption*) | 0% | 40% | 60% | 80% |
| Activations per quarter | 368 | 405 | 500 | 763 |
| Lead-to-activation | 7.36% | 8.09% | 10.00% | 15.26% |
| Uplift in activations | 1.00x | 1.10x | 1.36x | 2.07x |
| New monthly revenue added per quarter | Rs 45.4 lakh | Rs 49.4 lakh | Rs 58.5 lakh | Rs 81.5 lakh |
| Platform run cost per quarter (*assumption*) | - | Rs 3.2 lakh | Rs 3.4 lakh | Rs 3.8 lakh |
| Blended CAC (spend held at history) | Rs 15,053 | Rs 14,484 | Rs 11,761 | Rs 7,751 |
| CAC if part of field effort moves to digital | - | Rs 13,319 | Rs 9,876 | Rs 5,899 |
| Days lead to activation | 17.6 | 13.1 | 10.8 | 8.6 |
| Year-1 incremental revenue | - | Rs 92.8 lakh | Rs 307.9 lakh | Rs 851.0 lakh |
| Quote acceptance (needs assessed to quote accepted) | 43.6% | 45.4% | 49.1% | 55.5% |
| KYC completion after quote | 68.3% | 68.5% | 70.6% | 77.1% |
| Months to pay back build cost (*assumption* Rs 75 lakh) | - | 23 | 11 | 6 |

## Assumptions

- Adoption (share of leads using the digital journey): {'conservative': 0.4, 'expected': 0.6, 'ambitious': 0.8}.
- Recovered leads convert at {'conservative': 0.6, 'expected': 0.75, 'ambitious': 0.9} of the normal rate at every later step.
- Bundle of a lead recovered from a price objection: 65% of the segment average; mobile-only recoveries: 3 x Rs 349 postpaid lines.
- Acquisition spend held at the historic Rs 55.4 lakh per quarter; no savings assumed in the headline CAC.
- Platform: hosting Rs 3.0 lakh/quarter; Rs 2 per digital session; Rs 60 per KYC case; 35% of cases reviewed for 10 min at Rs 400/h.
- Field-effort sensitivity: {'conservative': 0.15, 'expected': 0.3, 'ambitious': 0.45} of micro and professional leads from field sales and partners start digital-first, saving their channel's spend per lead minus the website form's (Rs 274).
- Year-1 revenue: the extra monthly revenue arrives in monthly cohorts and decays with the historic 15.2% 6-month churn; payback uses a 35% contribution margin (*assumption*).
- Digital days to activate: 0.5 (advice + quote) + 1.0 (KYC) + 4.8 (observed KYC to activation).

| Loss reason | Conservative | Expected | Ambitious | Why |
|---|---:|---:|---:|---|
| Unreachable after 3 attempts | 5% | 10% | 20% | Owner can start from the WhatsApp / SMS link instead of waiting for a call |
| Wrong or invalid number | 10% | 20% | 30% | Mobile verified by OTP when the owner starts; affects future capture only |
| Not interested on first call | 0% | 0% | 0% | No lever |
| Owner had no time for a visit | 15% | 25% | 40% | Needs discovery happens in a 3-minute chat; no visit |
| Visit not scheduled by sales | 20% | 35% | 50% | No visit needed for standard bundles |
| Only wanted a mobile plan | 15% | 30% | 45% | Mobile-only checkout is allowed (small bundle) |
| Locked in with current provider | 0% | 0% | 0% | No lever (saved interest only) |
| Quote too complex to understand | 25% | 40% | 55% | Plain-language quote with reasons per product |
| Quote took too long to arrive | 30% | 50% | 65% | Quote is instant and server-priced in the session |
| Decided to wait | 10% | 15% | 25% | Saved quote held 15 days; reminder |
| Price too high | 3% | 7% | 12% | Right-sizing against current spend; lowest-cost option shown |
| Competitor offered cheaper plan | 0% | 5% | 10% | Transparent single price; Starter option |
| Missing GST or Udyam document | 25% | 40% | 55% | Checklist up front; registry verifies the number; non-GST path |
| Found paperwork too long | 25% | 40% | 55% | Phone upload, instant feedback; DigiLocker pull in production |
| Authorised signatory not available | 10% | 20% | 35% | Remote e-sign link (production integration) |
| Document details did not match | 20% | 35% | 50% | Mismatch explained at upload; human review instead of rejection |
| Installation delayed beyond 21 days | 10% | 20% | 30% | Dependency-aware schedule; stuck-order alerts |
| Customer cancelled before install | 5% | 10% | 20% | Tracker visibility |
| Site not feasible for fibre | 40% | 60% | 75% | 5G AirFiber fallback offered automatically |
| First payment failed | 40% | 60% | 75% | Retry with another method; order kept |

Recovery rates apply only to the adopted share. Reasons with no lever stay at 0%.
Not modelled (upside, unproven): lower churn from fewer status calls (historically 1 call: 5.9% churn, 5 calls: 27.9%; correlation, not causation) and cross-sell after activation.
