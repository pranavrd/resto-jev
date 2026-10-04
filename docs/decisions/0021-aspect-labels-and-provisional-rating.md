# 0021: Aspect labels (batch 1) and a provisional rating

- **Status:** Accepted. **Everything about ratings and aspect quality is provisional until batch 1 has been labelled and read.**
- **Date:** 2026-10-04
- **Code:** `aspect_labels.py` (sampler, 6 tests), `label_api.py` and `web/src/label/` (the page, 7 key-logic tests), `aspect_label_report.py` (the evaluation, 9 tests with a planted halo), `rating.py` (13 tests); migrations 020 (`aspect_label_item`, `aspect_label`) and 021 (`rating_run`, `restaurant_aspect`, `restaurant_rating`); guidelines in `docs/aspect-labeling-guidelines.md`
- **Results are private.** Figures derived from the Yelp Data are in `docs/private/` (gitignored; decision 0001). This record has method, rules and caveats.

## The rules this follows

1. **The rating is built now and marked provisional everywhere it appears.** Every table row has `status = 'provisional'`, enforced by a CHECK constraint (lifting it takes a migration that says why, not a quiet UPDATE). Every printout opens and closes with the same banner. The API and the map UI do not show it.
2. **Nothing is presented as a result until the first batch has spoken.** No ranking, no aspect claim, no "Jev is good at food" appears in a README, a doc or a demo before `aspect_label_report` has been run on a labelled batch 1 and read with its sample sizes.
3. **The composite weights are not tuned on the labels that judge them.** The weights were fixed in code before any label existed (version `w1`, see below). `rating.py` never reads the label tables, and a test fails if it ever mentions them. Batch 1 is the judging set; if weights or the prior are ever tuned, use batches 2 and up.
4. **Labels cannot be lost by relinking.** The label tables have no cascade from `yelp_review`: relinking places deletes reviews that stop being usable, and that must not delete a person's labels.

## The labelling batch

About 180 items (165 distinct reviews plus 15 repeats), built to answer the two open questions first.

| Part | Size | How picked | What it tells you |
|---|---|---|---|
| random | 120 | 24 at each star rating, spread across places (at most 4 reviews per place in the batch) | an **unbiased** read on how well Jev agrees with a person |
| value probe | 25 | reviews Jev says mention value, 5 per star rating | value is mentioned in about a quarter of reviews, so a random draw would leave too few to judge it |
| divergence probe | 20 | reviews where Jev's aspect score contradicts the star rating (4-5 stars with a negative aspect, 1-2 stars with a positive one) | where a **halo** would show |
| repeat | 15 | a second showing of random items, at least 40 items later | how consistent the labeller is with themself: the ceiling on any agreement |

The two probes are picked using Jev's own output. They say how Jev does on those reviews, **not** how it does overall, and the report keeps all parts apart and never pools them. Place spread is bounded by where the reviews are: the batch is mostly Rittenhouse because most reviews are, and Roxborough has almost none.

**The page is blind.** An item is the review text and nothing else: no star rating, no place, no stratum, no Jev answer. A person who sees "5 stars" will rate the service higher, which would manufacture the very halo the batch is meant to detect. The levels they choose from carry the same descriptions Jev is given. Time per item is recorded.

## The halo and value questions

- **Halo.** Among reviews where the person says an aspect is mentioned, regress Jev's score on the person's level and the star rating. If Jev reads the text, the stars' coefficient is about zero; if overall tone leaks into each aspect, it is positive. Intervals resample whole places. (Tested by planting a halo in invented data: the coefficient finds it, and stays near zero when there is none. A related diagnostic, correlation of Jev's errors across aspects, detects only a shared per-review error and not this halo, which the test also demonstrates.)
- **Value.** Mention precision and recall on the random part and the value probe, level agreement, and whether Jev's confidence predicts its error (the unlabelled checks suggested it does not for value).

## The provisional rating

Per place and aspect: each review that mentions the aspect contributes its score (0 to 4, divided by 4) with weight *mention probability × recency weight* (halving every 3 years before the snapshot's last review). The weighted scores become a Beta posterior around a prior built from all places, with the prior's strength estimated from how much places genuinely differ (empirical Bayes, no labels), so a place with few mentions is pulled toward the average. The Kish effective sample size scales the pseudo-counts, so recency weighting does not make a place look better known than it is. The four aspects are combined by drawing from each posterior, which gives a credible interval for the composite **and an interval for the rank**.

**The frozen weights (`w1`):** food 0.40, service 0.25, atmosphere 0.20, value 0.15. They were chosen as judgement before any label existed: food is why a restaurant exists; service and atmosphere shape the visit; value is the most personal and the aspect Jev is least sure about. Sensitivity to these choices is reported (equal weights, food-heavy, value-heavy, other half-lives, a prior half or twice as strong), not optimised.

## What the first look showed (provisional; the figures are in `docs/private/rating-provisional.md`)

Reported here only as things to check, not findings:

- The ranking is **insensitive to the composite weights**: equal, food-heavy and value-heavy weights, other half-lives and other prior strengths all give nearly the same order. The choice of weights matters little here, whatever they are.
- The composite ranks places **almost exactly like shrunk review stars alone**. If that holds up against labels, the aspect machinery adds explanation (which aspect, with what uncertainty) more than a different order.
- **Rank intervals are wide**: a place's plausible rank spans a large share of the list. A ranking of these places says less than its numbers suggest.

## What this does not show

- Nothing about whether Jev's aspect scores match a person's: that is what batch 1 is for.
- The aspects as a set are not shown to be better than the stars. That needs the labels and a downstream comparison.
- The data is mostly Rittenhouse and ends in January 2022 (decision 0020).

## Next, and what it needs

1. **Label batch 1** (about 180 items; at roughly 45 seconds each, an estimate, about two to two and a half hours; the page records the real time). Run `.venv/bin/python -m streetwalker.aspect_label_report` and read each part with its sample size.
2. Only then decide whether to extend toward 500 (batches 2 and up), and whether any setting is worth tuning on those later batches.
3. A baseline model for the cascade comparison also waits for labels.
