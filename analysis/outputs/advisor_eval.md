# Advisor extraction evaluation

Held-out set: 40 first-message utterances (English, Hinglish, Hindi), `backend/tests/advisor_eval_set.json`. Field = one expected value; case = every expected value right.

## offline

- Field accuracy: **98.5%** (133 fields)
- Case accuracy (all fields right): **95.0%** (40 cases)
- Unasked fills (a value set that the owner did not state): 3
- Latency: 39.41 ms per utterance

| Field | Correct | Total | Accuracy |
|---|---:|---:|---:|
| business_type | 39 | 39 | 100% |
| city | 38 | 38 | 100% |
| employees | 25 | 25 | 100% |
| gstin_status | 2 | 2 | 100% |
| has_gstin | 8 | 8 | 100% |
| needs | 11 | 12 | 92% |
| sites | 8 | 9 | 89% |

| Language | Cases fully right |
|---|---:|
| en | 24/25 |
| hinglish | 5/5 |
| hi | 9/10 |

Misses:

- `en19`: sites expected 3, got None
- `hi09`: needs expected ['cloud_email', 'backup_storage'], got ['cloud_email']

The advisor never relies on extraction alone: every slot it could not fill is asked as a question with tap-able answers, and the owner can correct the profile in a form before seeing prices.
