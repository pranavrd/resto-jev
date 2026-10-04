# 0018: The escalation cascade, assembled and measured

- **Status:** Accepted
- **Date:** 2026-10-04
- **Code:** `cascade.py` (gates, thresholds, accounting, report; 9 tests), `tier1.py`, `tier2.py`, `review.py` + `review_api.py` + `deps.py` (human queue; 10 tests), `web/src/review/` (the page; 5 tests on its geometry helpers); migrations 015 and 016; figure `docs/img/cascade-curve.png`
- **Reproduce:** `.venv/bin/python -m streetwalker.cascade [--final] [--figure PATH]`
- **Headline result #1 of the roadmap (the escalation curve).** The short version: Tier 0 plus a confidence gate plus a human queue is the whole useful cascade. The imagery tier and the local-LLM tier, built as the roadmap describes them and measured on the buildings the gate escalates, make the answers worse, on development data and again on the frozen test split.

## What the cascade is

| Tier | What it does | Run on | Output |
|---|---|---|---|
| 0 | `stack-gbm`: boosted trees over the evidence features plus Jev's answers (decision 0011) | every building | calibrated D1 probabilities |
| gate | escalate when the Tier 0 confidence (top class probability) is below tau | every building | keep or escalate |
| 1 | caption a street image with the local VLM, ask Jev again with the caption (decisions 0012 to 0015) | escalated buildings that have an image | new D1 probabilities |
| 2 | local LLM (Qwen2.5-VL-3B, text only) reads the same evidence text Jev reads | escalated buildings | one D1 answer |
| 3 | human review queue (`#/review`) | whatever is left | a label |

**Protocol.** The gate and every threshold were chosen on train out-of-fold predictions only (2,312 buildings). Dev (757) validated them. The frozen test split (726) was read through `cascade --final`, which is logged in `docs/test-set-log.md` (see "Test-split reads" below). All train and dev predictions are out-of-fold; test predictions come from the final model. The human tier is an **oracle**: it returns the parcel label. Section "What the oracle hides" says why that matters.

## 1. The gate

How well does each score rank Tier 0's own errors first? AUROC, and the share of Tier 0's errors that fall inside an escalation budget:

| Gate | AUROC train / dev / **test** | Errors caught at 10% / 20% / 30% escalated (test) |
|---|---|---|
| **stack-gbm confidence** | 0.908 / 0.867 / **0.855** | 45% / 62% / 76% |
| stack-gbm margin (top minus second) | 0.907 / 0.854 / 0.852 | 46% / 62% / 75% |
| Jev and stack-gbm disagree, then confidence | 0.901 / 0.877 / 0.850 | 38% / 62% / 76% |
| stack-lr confidence | 0.790 / 0.869 / 0.762 | 31% / 50% / 68% |
| Jev confidence | 0.802 / 0.816 / 0.698 | 29% / 56% / 74% |
| random order | 0.500 | 10% / 20% / 30% |

The choice (stack-gbm confidence) was made on train and holds on test. It is also the simplest, and the stacker is calibrated (decision 0011), so the number means something: escalate what the model says it is unsure about. Jev's own confidence is the worst gate on test, as expected from its overconfidence (ECE 0.096).

## 2. Operating points

tau is the smallest threshold whose kept buildings reach a target accuracy on train out-of-fold predictions. Escalation intervals are street-grouped bootstrap, 95%.

| Target accuracy of kept buildings | tau | Test: escalated | Test: kept accuracy | Test: D1 accuracy, Tier 0 to final | Commercial-any F1 | Food F1 |
|---|---|---|---|---|---|---|
| 90% | 0.49 | 4.8% [1.9, 11.7] | 90.9% [85.3, 94.2] | 0.884 to 0.913 | 0.75 to 0.81 | 0.47 to 0.61 |
| **95%** | **0.77** | **18.0% [11.8, 29.9]** | **94.3% [90.1, 96.9]** | **0.884 to 0.953** | **0.75 to 0.92** | **0.47 to 0.85** |
| 97% | 0.87 | 27.4% [17.7, 42.1] | 95.3% [90.6, 97.8] | 0.884 to 0.966 | 0.75 to 0.94 | 0.47 to 0.95 |

"Final" assumes the escalated buildings get the parcel label. The guarantee **holds on dev and slightly misses on test**: the 95% target kept 96.4% on dev and 94.3% on test, and the 97% target kept 98.0% on dev but 95.3% on test. The test intervals contain the targets, so this is not proof of miscalibration, but the guarantee should be read as "about 94 to 96%", not "at least 95%". The **escalation volume is the less predictable number**: at tau 0.77 it was 18.6% on train, 26.0% on dev and 18.0% on test, and whole streets move it, so budget for a range.

Pooled over all 3,795 buildings (gate = stack-gbm confidence, escalating the top k, oracle human tier), the human reviews needed to reach a final D1 accuracy:

| Final D1 accuracy | 0.90 | 0.92 | 0.94 | 0.96 | 0.98 | 1.00 |
|---|---|---|---|---|---|---|
| Share of buildings reviewed by a person | 3.6% | 7.4% | 12.1% | 19.7% | 28.9% | 79.9% |

The last column is the long tail: the final fifth of the errors are confident ones, hidden among buildings the model is sure about, and finding them means reviewing most of the survey.

![Escalation curve](../img/cascade-curve.png)

*Left: final accuracy against the share of buildings reviewed by a person; the dots are the measured cascade at the three thresholds. Right: how quickly each gate finds Tier 0's errors.*

## 3. Tier 1 (imagery): measured, and it hurts

Roadmap: caption an image, ask Jev again. Run for real on every escalated building that has an image (tau 0.77; 400 of the 754 escalated buildings, 80 minutes of local compute): a panorama crop aimed at the building where a panorama pick exists (134 buildings; best-known setup, decision 0014), otherwise the lower 55% of the picked photo (266 buildings; decision 0012). It involves no fitting, so all splits were run; the test split is only read in the final step.

| D1 accuracy on the escalated buildings that have a Tier 1 result | Tier 0 | Tier 1 alone | Tier 1 minus Tier 0 (95% interval) |
|---|---|---|---|
| train + dev, n = 327 | 0.581 | 0.434 | **-0.147 [-0.266, -0.041]** |
| **test, n = 73** | 0.671 | 0.548 | **-0.123 [-0.284, 0.000]** |

An untuned average of the two probability sets is also worse (-0.101 and -0.055). Used as a resolver (answer on its own when its confidence is high, otherwise send to a human), Tier 1 trades accuracy for fewer reviews at a poor rate:

| Measured cascade at tau 0.77 | Test: D1 accuracy | Test: share reviewed by a person | Train + dev: accuracy | Train + dev: human share |
|---|---|---|---|---|
| no imagery | **0.953** | 17.8% | 0.963 | 20.4% |
| Tier 1 accepted at confidence 0.95 | 0.934 | 12.0% | 0.947 | 16.3% |
| Tier 1 accepted at confidence 0.90 | 0.930 | 11.0% | 0.943 | 15.6% |
| Tier 1 accepted at confidence 0.80 | 0.924 | 10.1% | 0.935 | 14.1% |

Each percentage point of human review that Tier 1 saves costs about a third to two-fifths of a point of accuracy (test: 6.8 points of review for 2.3 of accuracy; train + dev: 4.8 for 2.0), and the purple squares in the figure sit below the no-imagery curve: sending the same buildings to a person is the better use of them.

**Why.** Two reasons, found by looking at the captions rather than assumed:

1. **Most captions say nothing.** In 257 of the 327 train + dev cases (and 60 of the 73 test cases) the caption was uninformative: the 3B model reported the ground floor as "not visible", or its reply could not be parsed, and it read no sign. On those, Jev answers residential 56% of the time (Tier 0: 34%), which suggests it reads "no sign seen" as evidence against a business. That is my inference from the answer mix, not something I tested, but it fits: absence of a sign is not evidence of absence.
2. **The errors that need help are a different problem.** Mixed-use confusions with residential or commercial account for 262 of Tier 0's 467 errors overall (191 against residential, 71 against commercial). A photo of the ground floor cannot settle those, because it cannot show whether people live above.

*Exploratory, defined after seeing the numbers above:* restricting to the 70 train + dev buildings whose caption says something (a sign was read, or a storefront, door, garage or wall was seen), Tier 1 is still not better (0.443 against Tier 0's 0.614; -0.171 [-0.393, +0.041]); on the 13 such test buildings it is 0.538 against 0.769. These subsets are small, so the claim is "not shown to help", and abstaining on uninformative captions removes the main way Tier 1 hurts rather than creating a gain.

Panorama crops did worst (train + dev: 0.358 against Tier 0's 0.566, n = 106). That differs from the first panorama pilot (decision 0013: Jev's commercial recall 0.29 to 0.67), which measured commercial-any recall on every covered building, not 7-class accuracy on the hard band; the corrected pilot (decision 0014) had already cut the gain to about 0.05 recall and nothing beyond the stacker. This result extends it: on the buildings that need help, imagery does not provide it.

## 4. Tier 2 (local LLM): measured, and it hurts

The same evidence text Jev reads, one fixed prompt (`t2-p1`, never tuned), run on all 754 escalated buildings (3.5 s each, no download).

| D1 accuracy on the escalated buildings | Tier 0 | Tier 2 | Jev alone | Tier 2 minus Tier 0 |
|---|---|---|---|---|
| train + dev, n = 625 | 0.571 | 0.485 | 0.518 | -0.086 [-0.269, +0.079] |
| **test, n = 129** | 0.612 | 0.504 | 0.527 | **-0.109 [-0.211, 0.000]** |

The 3B model names a class every time, but it is no better than Jev (the stronger reader of the same text) and worse than the stacker, so it cannot resolve what Tier 0 cannot. When Tier 2 and Tier 0 agree (50% of train + dev, 67% of test) the answer is right 65 to 66% of the time, far below any useful bar, and where they disagree Tier 0 is right more often (train + dev 154 against 100; test 22 against 8). It has no confidence of its own to gate on. A hosted LLM would be a stronger Tier 2, but Jev already is a hosted model reading this text at Tier 0, so that is the same tier again.

## 5. Where the cascade works and where it does not

**Per area, at the same tau 0.77** (all splits pooled):

| Area | n | Tier 0 accuracy | Escalated | Kept accuracy | Final accuracy |
|---|---|---|---|---|---|
| East Passyunk | 2,548 | 0.911 | 14.5% | 0.954 | 0.960 |
| Roxborough | 802 | 0.965 | 6.4% | 0.973 | 0.975 |
| **Rittenhouse** | 445 | **0.521** | **75.1%** | **0.748** | 0.937 |

The pooled 18% escalation is an average of two areas where the cascade works and one where it does not. In the dense core **Tier 0 is not usable on its own**: its confidence is not calibrated there (in the 0.9 to 1.0 band it claims 0.95 and is right 0.82 of the time) and no threshold keeps at least 30 buildings at 95% accuracy on train. A per-area threshold does not rescue it, whereas it works as expected in East Passyunk (tau 0.69: dev escalation 13.3%, kept accuracy 0.941) and Roxborough. The stacker is trained mostly on rowhouse areas (88% of the buildings are in East Passyunk or Roxborough) and has no area feature. In a Rittenhouse-like core the honest description is "a review-assist tool where nearly every building is checked", and the headline curve should be read as the curve for areas that look like the other two.

**Label noise is part of "error".** Where land use and OPA disagree (107 buildings), Tier 0's error rate is 64.5%; where only land use exists (636), 14.8%; where they agree (3,052), 10.0%. Those weaker labels hold 35% of all Tier 0 errors from 20% of the buildings. Rittenhouse has more of them (26% against 19% overall). The gate escalates disputed labels at 57%, so it partly works as a label-quality detector, but the oracle "human" would be returning labels that are themselves unreliable.

## 6. Cost and time per building (measured)

| Tier | Per building | Notes |
|---|---|---|
| 0 | $0.00004, Jev call 0.1 s | $0.164 for all 3,795; every building |
| 1 | 11.4 s caption (panorama crops 14.4 s, photos 9.9 s) + 0.2 s Jev | escalated buildings with an image only; the 400 took 80 minutes, partly while Tier 2 shared the GPU, so the per-caption time is an upper estimate |
| 2 | 3.5 s | escalated buildings |
| 3 | **not measured** | the review page records time per label; `streetwalker.review report` prints it |

At tau 0.77, 754 of 3,795 buildings (20%) are escalated, so the human queue is 754 reviews. At an assumed 10, 20 or 30 seconds each that is 2.1, 4.2 or 6.3 hours; those seconds are placeholders until the queue produces a measurement.

## 7. The human queue

Built because the cascade ends there, and because the parcel labels need checking. `#/review` shows a plan of the building and its surroundings (the target highlighted, the camera position), the street photo and, for panorama buildings, a close crop; one button per class with the same definitions Jev gets, "can't tell", undo, and keyboard shortcuts. It is **blind**: it never shows the parcel label or any model answer, and the OSM evidence text is behind a click (opening it is recorded).

- **Ground-truth check:** 145 random buildings that have a street photo (50 per area, Roxborough has 45), to measure how well the parcel labels agree with what a person sees.
- **Escalated by the cascade:** the 200 buildings the model was least sure about.
- `python -m streetwalker.review report` prints agreement with the parcel label overall, by class, by area and by label status, Cohen's kappa, "can't tell" rate, and seconds per label.

**No labels exist yet.** The agreement numbers, the human time per label and the check on the oracle assumption all wait for someone to label the 145 buildings (the roadmap's "about 150 human labels"). The labels write to Postgres only when the API runs with `STREETWALKER_REVIEW=1`.

## Decisions

1. **The cascade as shipped is Tier 0, the stack-gbm confidence gate at tau 0.77 (target 95% on train) and the human queue.** Tier 1 and Tier 2 stay in the code and the write-up as measured negative results; they are not in the default path.
2. **Report the guarantee as a range** (kept accuracy about 94 to 96% at tau 0.77) and the escalation as a range (test interval about 12 to 30%, dev 13 to 45%), from the street-grouped intervals above.
3. **Treat a Rittenhouse-like core as review-everything**, or retrain Tier 0 with area information, before claiming the cascade for it. Do not extend the headline to dense cores.
4. **Keep the oracle assumption visible.** The curve's final-accuracy numbers are upper bounds until the verification labels say how often a person agrees with the parcel label.

## What the oracle hides, and other caveats

- **The human tier is not a person yet.** Final accuracy assumes a reviewer who always returns the parcel label. A real reviewer will disagree with it more often on disputed and land-use-only labels, and may be wrong on mixed-use. The 145 verification labels bound this.
- **Tier 1 is one setup, not imagery in general.** A 3B local VLM, about 79% of whose captions said nothing (317 of 400), over mostly 2018 to 2020 photos with an unverified ordinary-photo heading. A 7B VLM (a 5.5 GB download) or a hosted vision model could do better; I have not tried it and do not claim imagery cannot help. What is shown is that this setup, on the buildings the gate escalates, does not.
- **Tier 1 and Tier 2 were evaluated only on the escalation band** (tau 0.77), where they are meant to act, and the band is hard by construction (Tier 0 accuracy 0.57 to 0.67 there).
- **The per-area and label-status tables were added after looking at pooled data.** They are descriptive, and the "informative captions only" block in section 3 was defined after seeing the main result. Neither feeds a decision threshold.
- **Intervals are wide.** Street-grouped bootstrap, a few dozen streets; several test intervals touch zero (Tier 1 -0.123 [-0.284, 0.000], Tier 2 -0.109 [-0.211, 0.000]). The direction is the same on train + dev and test and the train + dev intervals exclude zero for Tier 1, so the claim is "does not help", not a precise size.
- **The parcel label is the yardstick throughout**, including for the 7-class D1 task where mixed-use against commercial is partly a judgement call.

## Test-split reads

`cascade --final` was run twice on 2026-10-04 (09:27 and 09:30 UTC): the first with the gate, thresholds and tier tables, the second after the per-area and label-status tables were added. Between them I ran one scratch query pooling train, dev and test for the per-area and label-status breakdown (and a train + dev per-area threshold check); it is recorded in the log as ad hoc. Nothing was tuned on the test split: the gate, tau, the acceptance bars (0.80, 0.90, 0.95) and both tiers' settings were fixed before the final run, from train and dev.
