# 0011: Tier 0 stackers (Jev answers as features)

- **Status:** Accepted
- **Date:** 2026-10-04
- **Code:** `stacker.py`, `features.py` (Jev features), `gbm.py` (shared protocol), `scripts/analyze_gates.py`
- **Baselines stored:** `stack-lr`, `stack-gbm`

## What was built

Same protocol as 0008: street-grouped 5-fold CV over train + dev picks the settings, every train and dev prediction is out-of-fold, test comes from a final model. Jev needs no training, so only the stacker is fitted.

| Model | Inputs | Size |
|---|---|---|
| **stack-lr** | Jev's log-probabilities for the 7 D1 classes, its food-probability logit, a silent-building flag (no tag, POI or name) and silent x log p(commercial); standardised logistic regression, C = 0.1 | 10 features |
| **stack-gbm** | All 35 evidence features plus Jev's D1 distribution, confidence, commercial-any probability, food probability and D2 type; 60 boosting rounds, 4 leaves | 46 features |

CV log-loss: stack-gbm **0.378**, gbm-full 0.407, stack-lr 0.429. The food threshold is tuned on out-of-fold F1 (0.18 for stack-lr, 0.28 for stack-gbm).

## Results

**Held-out (dev + test, 1,483 buildings; paired differences against Jev, 95% street-grouped CI):**

| | D1 acc | Commercial-any F1 | vs Jev | D3 F1 | ECE |
|---|---|---|---|---|---|
| jev-p1 | 0.855 | 0.63 [0.48, 0.75] | n/a | 0.49 | 0.096 |
| stack-lr | 0.877 | 0.75 [0.62, 0.84] | **+0.13 [+0.03, +0.24]** | 0.54 | **0.012** |
| stack-gbm | **0.886** [0.84, 0.92] | **0.76** [0.63, 0.85] | **+0.13 [+0.01, +0.25]** | 0.54 | 0.018 |
| gbm-full | 0.844 | 0.63 [0.43, 0.80] | 0.00 [-0.20, +0.18] | 0.49 | 0.028 |
| rules-v3 | 0.865 | 0.75 [0.60, 0.85] | +0.13 [-0.00, +0.24] | 0.48 | n/a |

Train + dev pooled (3,069, out-of-fold): stack-gbm F1 0.70 [0.58, 0.80], stack-lr 0.68, Jev 0.60. The gains over Jev there are +0.10 [-0.02, +0.20] and +0.08 [-0.02, +0.17], so the pooled evidence is suggestive; the held-out intervals exclude zero.

The held-out comparison was logged as a test-split access.

## Findings

1. **Jev's overconfidence is fixable.** ECE falls from 0.096 to 0.012 to 0.018. A ten-feature logistic recalibration does it with no other evidence.
2. **Most of stack-lr's F1 gain is a better operating point, not better ranking.** AUROC 0.890 to 0.897 and average precision 0.715 to 0.731. Raw Jev is conservative (precision 0.84, recall 0.50); the recalibrated model trades some precision for recall (0.81 / 0.70).
3. **Jev adds real information to the evidence features.** stack-gbm ranks better than either alone: AUROC 0.946 and AP 0.762, against gbm-full 0.935 and 0.730, and Jev 0.890 and 0.715. Permutation importance puts footprint area, Jev's p(residential) and p(commercial or mixed) at the top.
4. **A stacker is a better standalone Tier 0 than raw Jev,** with no imagery cost: stack-gbm recall 0.69 at precision 0.72 (Jev alone: 0.45 at 0.86), D1 accuracy 0.886.
5. **The stackers do not make better escalation gates at low budgets.** With Jev answering and a stacker ranking who to escalate (oracle imagery), recall is 0.77 to 0.79 at 10% escalation, slightly below Jev's own risk score (0.80). At 20% to 30% GBM-informed ranking pulls ahead (0.91 and 0.97 against 0.88 and 0.90), at precision 0.92 to 0.93.

## Gate candidates for the cascade (oracle imagery, recall / precision, all 3,795 buildings)

| Gate | 5% | 10% | 15% | 20% | 30% |
|---|---|---|---|---|---|
| Jev answers, Jev hidden risk | 0.67/0.90 | 0.80/0.92 | 0.84/0.95 | 0.88/0.98 | 0.90/0.99 |
| Jev answers, mean(Jev, stack-gbm) risk | 0.66/0.90 | 0.78/0.91 | 0.85/0.92 | 0.91/0.92 | 0.97/0.93 |
| stack-gbm answers, stack-gbm hidden risk | 0.80/0.75 | 0.87/0.77 | 0.93/0.78 | 0.96/0.78 | 0.98/0.79 |

The choice depends on what the cascade optimises: the first two keep precision above 0.9; the third reaches high recall sooner but with more false positives accepted at Tier 0. Both are upper bounds because real imagery resolves fewer buildings than the oracle.

## Decisions
- **Tier 0 predictor for the cascade: stack-gbm** (calibrated probabilities, best accuracy). Jev's raw answers remain the reference baseline.
- **First gate to try: mean(Jev, stack-gbm) hidden risk**, thresholded on train and reported on held-out. Re-evaluate with real imagery results.
- Stackers use only Jev p1 answers. If a new Jev prompt or model version is ever used, re-run the stacker (the pin is recorded in `jev_run`).
