# 0008: Gradient-boosted baselines and evaluation protocol

- **Status:** Accepted
- **Date:** 2026-10-03
- **Code:** `features.py`, `gbm.py`, `calibration.py`, `bootstrap.py`, `evaluate.py`

## Protocol

- **Model:** scikit-learn `HistGradientBoostingClassifier` (7-class D1, binary D3).
- **Tuning:** 24-configuration grid (learning rate, iterations, leaves, minimum leaf size), chosen by **street-grouped 5-fold cross-validation over train + dev combined**, scored by multiclass log-loss. Dev alone is too small (13 civic, 2 industrial, 1 vacant buildings) to tune on.
- **Out-of-fold everywhere:** every train and dev prediction is out-of-fold, so no reported number is in-sample. Test rows come from a final model fit on all of train + dev. Test was accessed through the logged gate.
- **D3:** the decision threshold is tuned on out-of-fold F1; D1 uses the arg-max class.
- **Three feature sets mirror the evidence ablation:** geometry (11 features), + tags (24), + street and context (35).
- **Excluded by design:** street names, area, encounter order. The split keeps blocks, not whole streets, together, so a street-name feature would leak.
- **Confidence intervals:** street-grouped bootstrap (resample whole street groups, 1,000 draws). Buildings on a street are not independent, so a building-level bootstrap would be too narrow.

## Things that went wrong first (kept because they shaped the result)

1. **Log-loss was computed with the wrong class order** (sklearn assumes sorted labels, ours were not), giving 9.3 instead of 0.43. Replaced with `metrics.multiclass_log_loss` and a test that pins the behaviour.
2. **A segment-fingerprint feature.** `seg_n_buildings` is constant within a street segment and nearly unique to it, so trees memorised each segment's class mix. In East Passyunk dev, gbm-full fired on 125 buildings and 41 were right. Replaced with the ratio `seg_poi_density` and the grid was widened toward more regularised models. Grouped CV exposed it: before the fix the full model's CV log-loss (0.441) was no better than the tags model's (0.430); after it, 0.407 against 0.423.

## Cross-validated results (train + dev pooled, 3,069 buildings, all out-of-fold)

| Model | CV log-loss | D1 acc | Commercial-any P / R / F1 | D3 P / R / F1 | ECE |
|---|---|---|---|---|---|
| gbm-geometry | 0.477 | 0.831 | 0.56 / 0.35 / 0.43 | 0.18 / 0.66 / 0.29 | 0.028 |
| gbm-tags | 0.423 | 0.857 | 0.70 / 0.45 / 0.55 | 0.64 / 0.34 / 0.44 | 0.017 |
| gbm-full | 0.407 | 0.856 | 0.67 / 0.59 / 0.63 | 0.51 / 0.43 / 0.47 | 0.027 |
| rules-v3 (for reference) | n/a | 0.876 | 0.82 / 0.64 / 0.72 | 0.67 / 0.39 / 0.49 | n/a |

The ladder holds for the GBM: geometry, then tags, then context each help. Permutation importance for gbm-full (increase in held-out log-loss): footprint area +0.044, block POI density +0.043, road class +0.040, building tag category +0.014, height +0.014, `addr:unit` +0.011.

**rules-v3's pooled numbers are optimistic**: I wrote its context rule after studying train. The GBM numbers are honest out-of-fold estimates.

## Frozen test split (726 buildings; 102 commercial or mixed)

| Baseline | D1 acc | Commercial-any F1 [95% CI] | F1 difference vs rules-v3 [95% CI] | D3 F1 | ECE |
|---|---|---|---|---|---|
| rules-v1 (tags) | 0.840 | 0.47 [0.26, 0.67] | -0.19 [-0.41, -0.03] | 0.56 | n/a |
| rules-v3 (+ geometry + context) | 0.857 [0.76, 0.91] | 0.66 [0.36, 0.85] | n/a | 0.56 | n/a |
| gbm-geometry | 0.835 | 0.55 | n/a | 0.20 | 0.024 |
| gbm-tags | 0.855 | 0.58 [0.41, 0.75] | -0.08 [-0.29, +0.18] | 0.49 | 0.027 |
| gbm-full | 0.877 [0.80, 0.92] | 0.72 [0.46, 0.88] | +0.05 [-0.05, +0.20] | 0.54 | 0.034 |

## What this means

- **gbm-full and rules-v3 are statistically tied.** On test the GBM is ahead (+0.05), on pooled train + dev the rules are ahead (+0.09); both differences are inside the noise. Neither tells us the learned model beats a good hand-written rule at this data size.
- **Tags alone is clearly weaker** than adding geometry and context (rules-v1 vs rules-v3: -0.19, interval excludes zero). That is the evidence-ablation result for the first three rungs.
- **The bar for Jev** is about **0.66 to 0.72 commercial-any F1 and 0.86 to 0.88 D1 accuracy** from tags, geometry and context. The GBM's calibration is good (ECE 0.03), which sets the reference for Jev's.
- **Test is too small to detect modest gains** (intervals are about ±0.2). Jev needs no training data, so it is evaluated on **all 3,795 buildings**, and compared against the baselines' out-of-fold and test predictions on the same buildings. Intervals shrink to roughly ±0.07. rules-v3 stays slightly optimistic on that set; note it when comparing.
- Rare classes (industrial, other, vacant) stay unsolved by every non-imagery baseline.

## Reproduce
```bash
.venv/bin/python -m streetwalker.gbm                      # about 15 minutes, stores gbm-geometry, gbm-tags, gbm-full
.venv/bin/python -m streetwalker.evaluate --split trainval --compare rules-v3 gbm-full --bootstrap 1000
```
