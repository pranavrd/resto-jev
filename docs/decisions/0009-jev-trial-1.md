# 0009: Jev trial 1 (100 buildings)

- **Status:** Accepted; findings shape the Week 4 cascade design
- **Date:** 2026-10-03
- **Code:** `jev_questions.py`, `jev_client.py`, `jev_trial.py`; tables `jev_run`, `decision`, `eval_set`

## Setup

- Model `jev-1.13.0`, pinned. One request per building, three questions answered in parallel: **D1** main use (pick one of the 7 classes), **D2** commercial type (with a "none" option), **D3** food-or-drink service (yes/no probability). State is the tier-0 evidence text (0006).
- Sample: 100 buildings from the **train split only** (so wording can be iterated without touching dev or test), stratified toward hard cases: 15 food-licensed, 15 commercial, 20 mixed-use, 10 residential on primary or tertiary streets, 24 other residential, 8 civic, and a few industrial, other and vacant. **Not natural prevalence** (46% commercial-or-mixed against about 10% in the survey), so accuracy and ECE here are not comparable to the baselines' headline numbers. Comparisons are on the same 100 buildings.
- The API key stays in `.env`; the SDK reads `TYPESAFE_API_KEY`, the client is given `JEV_API_KEY` directly and the value is never printed or logged.

## Operations

| | |
|---|---|
| Requests | 100 per run, 0 errors |
| Latency | median 125 ms, p90 166 ms, max 326 ms |
| Input tokens | about 1,025 per request (the questions are about two thirds of that) |
| Cost | $0.0043 per 100 buildings, so about $0.17 for all 3,795 |

## Results (same 100 buildings)

| | D1 acc | Commercial-any P / R / F1 | AUROC of p(commercial)+p(mixed) |
|---|---|---|---|
| Jev p1 | 0.530 | 0.88 / 0.50 / 0.64 | 0.78 |
| Jev p2 | 0.540 | 0.85 / 0.50 / 0.63 | n/a |
| rules-v3 | 0.550 | 0.79 / 0.57 / 0.66 | n/a |
| gbm-full | 0.570 | 0.87 / 0.59 / 0.70 | 0.85 |

Split by whether the building carries any tag, POI or name:

| | Jev | rules-v3 | gbm-full |
|---|---|---|---|
| With signal (24): commercial-any F1 | 0.85 | 0.82 | 0.85 |
| Silent (76): commercial-any F1 | 0.46 | 0.53 | 0.59 |

D3 food: precision 0.83, recall 0.45 (F1 0.59) at any threshold from 0.3 to 0.5. D2 labelled 6 of 12 food-licensed buildings that Jev considered commercial as restaurants and answered "none" for 2.

## Findings

1. **When the evidence is there, Jev matches the baselines.** On buildings with a tag, POI or name, commercial-any F1 is 0.85 for Jev, rules-v3 and gbm-full alike. Jev is not better at reading tags than a rule table.
2. **Silent buildings are the whole problem, and Jev is slightly worse than the baselines there** (F1 0.46 against 0.53 and 0.59). When Jev calls a silent building commercial it is right (precision 1.00), but it misses 70%. Many misses are genuinely invisible: about half the mixed-use buildings Jev called residential got p(residential) of 0.9 or more.
3. **Jev's top-class confidence cannot flag them.** 74 of 100 answers have confidence of 0.8 or more and only 58% are right; 8 answers at 0.6 to 0.8 were all wrong. A confidence gate would accept exactly the buildings that most need imagery. (The sample over-represents hard cases, so ECE of 0.38 overstates the natural-prevalence problem, but the high-confidence misses are real.) Confidence is honest about the text, not about the building: with nothing in the text, the answer is "residential" with certainty.
4. **Wording is not the lever.** Prompt p2 told Jev how to weigh block context. Mixed-use recall rose from 0.14 to 0.25, commercial recall and corridor-residential accuracy fell, F1 stayed at 0.64 to 0.63, calibration did not change. This is consistent with TypeSafe's guidance that Jev is weak at counting and numeric judgement. p1 stays the default; no further wording iteration on this axis.

## Implications for the cascade (Week 4)

- **Do not gate escalation on Jev's argmax confidence alone.** Triage silent buildings with a separate risk score. The GBM already ranks commercial-any better than Jev (AUROC 0.85 against 0.78), so a candidate gate is: escalate when the building is silent and the GBM's p(commercial or mixed) is not near zero, or when Jev and the GBM disagree.
- **A calibrated stacker** over Jev's distribution plus the evidence features may beat either model alone and gives a confidence that means something. It needs Jev's answers on the train and dev buildings.
- **Jev's best use is interpretation of rich evidence** (names, tags, POIs: D2 and D3) and the imagery captions at tier 1, where the text finally contains the signal. Silent rowhouses need imagery, not a better prompt.
- Natural-prevalence numbers need a full run: **about $0.17 and 10 minutes for all 3,795 buildings**, which also gives the stacker its training data.

## Not done
- State format (JSON versus text) was not compared; the failure mode here is missing evidence, not parsing.
- D2 has no ground truth, so it is only inspected, not scored.
