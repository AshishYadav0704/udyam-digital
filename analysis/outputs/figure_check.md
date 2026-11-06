# Independent figure check

Every headline figure on the deck, in the README and in the business case, recomputed from `data/raw` with plain pandas (no project code imported). Scenario rows redo the business-case arithmetic from the assumptions declared in `business_case.json`; they check the arithmetic, not the assumptions. Produced by `analysis/06_figure_check.py`.

**62 of 62 figures match** what the documents show.

| Figure | Shown | Recomputed | Where | Match |
|---|---:|---:|---|---|
| Leads in the data | 5,000 | 5,000 | deck 2, README | yes |
| Activated customers | 368 | 368 | deck 2, README | yes |
| Lead-to-activation rate | 7.36% | 7.36% | deck 2 & 8, README | yes |
| Every step loses more than 30% (largest step pass rate) | < 70% | 68.3% | deck 2 | yes |
| Lost between needs assessment and quote acceptance | 1,113 | 1,113 | deck 2, README | yes |
| ... of which price (too high + cheaper competitor) | 621 | 621 | deck 2, README | yes |
| ... of which slow or complex quote | 385 | 385 | deck 2, README | yes |
| Lost because the needs visit never happened | 827 | 827 | deck 2 | yes |
| Accepted a quote, then dropped at paperwork | 273 | 273 | deck 2 | yes |
| Lost after KYC | 220 | 220 | deck 2 | yes |
| Activated bundles breaking a catalogue eligibility rule | 56 | 56 | deck 2 | yes |
| CAC via field sales | ₹24,335 | ₹24,335 | deck 2 | yes |
| Lowest CAC among web, WhatsApp, referral, inbound | ₹4,026 | ₹4,026 | deck 2 | yes |
| Highest CAC among web, WhatsApp, referral, inbound | 6,352 | 6,352 | deck 2 | yes |
| 6-month churn, activated customers with 4-5 status calls | 23.0% | 23.0% | deck 2 | yes |
| 6-month churn, activated customers with 1-2 status calls | 11.9% | 11.9% | deck 2 | yes |
| Blended CAC (spend / activations) | ₹15,053 | ₹15,053 | deck 8, README | yes |
| Days lead to activation (mean) | 17.6 | 17.6 | deck 8 | yes |
| Status calls per activated customer | 3.0 | 3.0 | deck 8, README | yes |
| Quote acceptance today (quote accepted / needs assessed) | 43.6% | 43.6% | deck 8 | yes |
| NPS index of activated customers | -25 | -25 | README | yes |
| Micro: leads | 2,709 | 2,709 | deck 3 | yes |
| Micro: activation | 4.1% | 4.1% | deck 3 | yes |
| Micro: CAC | ₹20,007 | ₹20,007 | deck 3 | yes |
| Micro: share of new MRR | 6% | 6% | deck 3 | yes |
| Micro: median bundle | ₹2,470 | ₹2,470 | deck 3 | yes |
| Micro: median contract | 12 months | 12 months | deck 3 | yes |
| Professional: leads | 1,247 | 1,247 | deck 3 | yes |
| Professional: activation | 11.1% | 11.1% | deck 3 | yes |
| Professional: CAC | ₹10,695 | ₹10,695 | deck 3 | yes |
| Professional: share of new MRR | 21% | 21% | deck 3 | yes |
| Professional: months of bundle revenue to recover CAC | 1.6-month | 1.6-month | deck 3 | yes |
| Professional: median bundle | ₹6,575 | ₹6,575 | deck 3 | yes |
| Professional: median contract | 12 months | 12 months | deck 3 | yes |
| Multi-site: leads | 755 | 755 | deck 3 | yes |
| Multi-site: activation | 11.0% | 11.0% | deck 3 | yes |
| Multi-site: CAC | ₹15,614 | ₹15,614 | deck 3 | yes |
| Multi-site: share of new MRR | 57% | 57% | deck 3 | yes |
| Multi-site: median bundle | ₹28,080 | ₹28,080 | deck 3 | yes |
| Multi-site: median contract | 12 months | 12 months | deck 3 | yes |
| Manufacturers: leads | 289 | 289 | deck 3 | yes |
| Manufacturers: activation | 12.8% | 12.8% | deck 3 | yes |
| Manufacturers: CAC | ₹15,324 | ₹15,324 | deck 3 | yes |
| Manufacturers: share of new MRR | 16% | 16% | deck 3 | yes |
| Manufacturers: median bundle | ₹15,910 | ₹15,910 | deck 3 | yes |
| Manufacturers: median contract | 24 months | 24 months | deck 3 | yes |
| Manufacturers: bundles with a leased line | 73% | 73% | deck 3 | yes |
| Multi-site + manufacturing share of new MRR | 73% | 73% | deck 3 | yes |
| Catalogue-midpoint price vs historic revenue | 100.2% | 100.2% | deck 3, README | yes |
| K11 address proof age on 15 Jul 2026 | 257 days | 257 days | deck 7 | yes |
| K06 certificate GSTIN fails its checksum | fails | fails | deck 7 | yes |
| Expected: activation rate | 10.0% | 10.0% | deck 8 | yes |
| Expected: CAC | ₹11,761 | ₹11,761 | deck 8 | yes |
| Expected: days to activate | 10.8 | 10.8 | deck 8 | yes |
| Expected: quote acceptance | 49.1% | 49.1% | deck 8 | yes |
| Conservative: activations per quarter | 405 | 405 | BUSINESS_CASE | yes |
| Expected: activations per quarter | 500 | 500 | BUSINESS_CASE | yes |
| Ambitious: activations per quarter | 763 | 763 | BUSINESS_CASE | yes |
| Conservative: CAC | ₹14,484 | ₹14,484 | BUSINESS_CASE | yes |
| Conservative: days to activate | 13.1 | 13.1 | BUSINESS_CASE | yes |
| Ambitious: CAC | ₹7,751 | ₹7,751 | BUSINESS_CASE | yes |
| Ambitious: days to activate | 8.6 | 8.6 | BUSINESS_CASE | yes |

Step pass rates (lead to activation): 68.1%, 58.0%, 43.6%, 68.3%, 62.6%.
Specimen GSTINs failing the checksum (ground truth, 11 checked): K06.
