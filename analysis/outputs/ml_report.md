# Lead propensity model - evaluation report

**Question:** which newly created leads are most likely to activate, so a human (inside sales, partner or field
sales) can be assigned to them first? The score prioritises help; it never blocks or rejects a customer.

## Data and split
- 5,000 leads; target = activated (7.36% overall). Creation-time features only (46 columns, see
  `backend/app/ml/features.py`); excluded for leakage: outcome, drop_reason, stage_reached, contacted_date, needs_assessed_date, quote_accepted_date, kyc_complete_date, activated_date, days_lead_to_activation, customer_follow_up_calls, bundle_products, monthly_bundle_value_inr, one_time_setup_inr, contract_months, churned_within_6_months, nps_score, acquisition_cost_inr.
- Chronological hold-out: train = leads created 1 Apr-31 May 2026 (3,296, 7.31% positive),
  test = 1-30 Jun 2026 (1,704, 7.45% positive). Model selection used 4 expanding-window folds inside
  the training period only.

## Feature-set selection (logistic regression, CV PR-AUC, training period only)
| feature_set      |   0.03 |    0.1 |    0.3 |    1.0 |
|:-----------------|-------:|-------:|-------:|-------:|
| full             | 0.1174 | 0.1149 | 0.1114 | 0.1105 |
| lean             | 0.1346 | 0.141  | 0.1409 | 0.1441 |
| no_product_flags | 0.1209 | 0.1168 | 0.1131 | 0.1109 |

Selected **lean** (5 categorical + 12 numeric inputs); C = 0.03 by the one-standard-error rule.
Dropping the 25 product-interest flags and the high-cardinality business type / state / language one-hots removes noise
that the larger models were fitting.

## Leaderboard on the selected feature set (sorted by CV PR-AUC)
| Model | CV PR-AUC | Test PR-AUC | Test ROC-AUC | Precision@10% | Lift@10% | Precision@20% | Recall@20% | Lift@20% | Brier |
|---|---|---|---|---|---|---|---|---|---|
| Extra trees | 0.151 ± 0.012 | 0.133 | 0.700 | 15.3% | 2.05x | 12.6% | 33.9% | 1.69x | 0.185 |
| Logistic regression **(shipped)** | 0.135 ± 0.018 | 0.155 | 0.731 | 15.9% | 2.13x | 17.0% | 45.7% | 2.28x | 0.209 |
| Random forest | 0.128 ± 0.005 | 0.134 | 0.693 | 14.7% | 1.97x | 14.4% | 38.6% | 1.93x | 0.153 |
| HistGradientBoosting | 0.119 ± 0.016 | 0.133 | 0.684 | 13.5% | 1.82x | 14.4% | 38.6% | 1.93x | 0.174 |
| CatBoost | 0.119 ± 0.018 | 0.120 | 0.653 | 10.0% | 1.34x | 11.7% | 31.5% | 1.57x | 0.146 |
| XGBoost | 0.116 ± 0.014 | 0.140 | 0.681 | 14.7% | 1.97x | 12.3% | 33.1% | 1.65x | 0.158 |
| LightGBM | 0.110 ± 0.013 | 0.131 | 0.669 | 13.5% | 1.82x | 10.9% | 29.1% | 1.46x | 0.135 |
| Segment x GSTIN rate (baseline) | 0.110 ± 0.016 | 0.106 | 0.657 | 12.9% | 1.74x | 11.7% | 31.5% | 1.57x | 0.068 |

Random ranking would score PR-AUC ≈ 0.075 and lift 1.0x.

**Decision:** Best CV PR-AUC: Extra trees (0.151). Margin over logistic regression +0.016 vs fold noise 0.018 -> shipped model: Logistic regression. Gain over the segment x GSTIN baseline: +0.024 PR-AUC (CV).

## Operating point (calibrated score ≥ top-20% training cut-off 0.114)
- Precision 16.6%, recall 40.9%, F1 0.236, 18.4% of June leads flagged.
- Confusion matrix [[TN, FP], [FN, TP]]: [[1316, 261], [75, 52]]
- Brier score 0.2086 raw -> 0.0661 after Platt recalibration (fitted on
  out-of-fold training predictions).

## Subgroup checks (June hold-out)
| Dimension | Group | n | Observed rate | Mean predicted | ROC-AUC | Flagged | Precision if flagged | Recall |
|---|---|---|---|---|---|---|---|---|
| segment | Micro retail & services | 918 | 4.2% | 4.2% | 0.755 | 2.0% | 11.1% | 5.1% |
| segment | Professional offices | 432 | 10.4% | 10.6% | 0.664 | 38.0% | 16.5% | 60.0% |
| segment | Small manufacturers | 98 | 15.3% | 11.7% | 0.667 | 38.8% | 23.7% | 60.0% |
| segment | Small multi-site businesses | 256 | 10.9% | 10.7% | 0.623 | 36.3% | 15.1% | 50.0% |
| has_gstin | N | 518 | 2.1% | 2.4% | 0.795 | 0.0% | - | 0.0% |
| has_gstin | Y | 1186 | 9.8% | 9.4% | 0.659 | 26.4% | 16.6% | 44.8% |
| city_tier | 1 | 865 | 9.1% | 8.2% | 0.696 | 25.9% | 16.1% | 45.6% |
| city_tier | 2 | 839 | 5.7% | 6.3% | 0.760 | 10.6% | 18.0% | 33.3% |

GSTIN status and segment are legitimate drivers of activation in this data (9.6% vs 2.0% with/without GSTIN), so the
model ranks non-GST leads lower. Because the score is only used to order human follow-up, the routing layer adds a
rule that keeps a share of follow-up capacity for non-GST micro businesses (assisted KYC path) so they are not
systematically ignored.

## What drives the score
Permutation importance (drop in test PR-AUC when a feature is shuffled):
- lead_source: 0.0265
- segment: 0.0109
- current_provider: 0.0086
- city_tier: 0.0082
- has_gstin: 0.0068
- turnover_ord: 0.0037
- num_sites: 0.0023
- n_interest: 0.0015
- log_price_to_spend: 0.0013
- log_spend: 0.0009

Logistic-regression coefficients (standardised; positive = more likely to activate):
- cat__lead_source_Referral: +0.691
- num__has_gstin: +0.373
- cat__segment_Professional offices: +0.297
- cat__gstin_status_Active: +0.278
- cat__current_internet_Mixed per site: +0.216
- cat__current_provider_Accel (mobile only): +0.197
- cat__lead_source_Inbound call: +0.187
- cat__current_provider_Accel: +0.174
- cat__lead_source_WhatsApp campaign: -0.473
- cat__lead_source_Website form: -0.370
- cat__segment_Micro retail & services: -0.368
- cat__current_provider_Local ISP: -0.294
- cat__current_internet_Business broadband: -0.197
- num__city_tier: -0.177

## Limitations
- One quarter of synthetic data; 245 training positives. Expect wide confidence intervals.
- No interaction history (opens, clicks, advisor engagement) - in production the digital journey itself will add
  much stronger signals (e.g. completed advisor, quote viewed) and the model should be retrained monthly.
- Calibration is checked on 1,704 June leads only; re-check after every retrain.
