# Week 3 (Oct 19–25, started early): Tier 0 classification and ground truth

- [x] Crosswalk from land use and OPA codes to D1 classes, with label quality flags (decision 0007)
- [x] D3 ground truth from active food licences
- [x] Frozen street-grouped train/dev/test split with a logged test gate
- [x] Rule baselines v1 (tags), v2 (+ geometry), v3 (+ context) with evaluation
- [x] Gradient-boosted baselines on geometry, tags and context (decision 0008): gbm-full ties rules-v3 within noise
- [x] Jev 100-building trial (decision 0009): matches baselines on tagged buildings, weaker and overconfident on silent ones
- [x] Jev D1 to D3 over all 3,795 buildings: $0.164, 0 errors (decision 0010)
- [x] Calibration analysis: Jev ECE 0.093 (overconfident), GBMs 0.02 to 0.03; reliability bins in `evaluate`
- [x] Tier 0 accuracy and calibration per area, compared with the baselines (0010)

Jev notes (from the SDK docs): package `typesafe-sdk`, key read from `TYPESAFE_API_KEY` (map from `JEV_API_KEY` in-process), pin `jev-1.13.0`, ask one thing per field, Jev reads literally and is weak at counting (we pass computed facts), tune each confidence bar separately. Evaluate Jev on all 3,795 buildings.

**Week 3 exit met 2026-10-03:** Tier 0 accuracy and calibration per area, compared with the baselines.

## Stackers (started Week 4 early)
- [x] stack-lr and stack-gbm over Jev's answers (decision 0011): calibrated (ECE 0.012 to 0.018), +0.13 commercial-any F1 over raw Jev held-out
- [x] Tier 1 groundwork (decision 0012): local MLX Qwen2.5-VL-3B (6.8 s per image), image selection for every building (32% coverage), 20-building pilot
- [x] East Passyunk panorama crops (decision 0013): Jev recall 0.29 to 0.67 on the 136 covered buildings; neighbour-sign false positives found
- [x] D5 check and tighter crops (decision 0014): strict own-sign attribution leaves imagery adding about 0.05 recall to Jev and almost nothing beyond the stacker; D5 on text alone does not work
- [x] OCR experiment (decision 0015): Apple Vision reads centre text on 17% of commercial/mixed crops (VLM 20%); 6 of 6 reviewed failures had no legible sign. Imagery tier is data-limited; stopping model changes there

## Restaurant census (Week 4 item, done early)
- [x] `place` table from OSM x licences, 195 places (184 public eating or drinking), matching validated by hand, Jev place kinds (decision 0016)
- [ ] Yelp comparison: blocked on the licence decision in 0001

## TableMap half, non-Yelp parts (Week 5 item, done early)
- [x] SEPTA GTFS stops and weekday service near the areas, City neighborhoods, per-place transit context (decision 0017); stop counts verified against raw GTFS
- [x] Place search API (`/places`, `/places.geojson`, `/places/{id}`, `/meta`), no Yelp fields, 16 new tests (decision 0017)
- [x] Map UI: places by kind, filters mapped one-to-one to API parameters, SEPTA stops and a 400 m ring for the selected place (web/README.md)

## Escalation cascade (Week 4 items, done early; decision 0018)
- [x] Gate analysis: stack-gbm confidence is the best gate (test AUROC 0.855); thresholds chosen on train, validated on dev, read once on test
- [x] Tier 1 imagery run for real on the 400 escalated buildings that have an image: worse than Tier 0 (test -0.123 [-0.284, 0.000])
- [x] Tier 2 local LLM run on all 754 escalated buildings: worse than Tier 0 (test -0.109 [-0.211, 0.000])
- [x] Headline escalation curve with the measured cascade, per-area and label-status breakdowns
- [x] Human review queue (blind labelling page, API, report), 145 ground-truth-check and 200 escalated buildings seeded
- [ ] **Label the 145 ground-truth-check buildings** (about 150 per the roadmap); gives the human agreement with parcel labels and the seconds per label
- [ ] Fill the human-time row of the cost table and re-state the curve with a real reviewer
- [ ] Optional: a stronger VLM for Tier 1 (7B, 5.5 GB download, needs approval); a Rittenhouse-aware Tier 0

## Yelp half, step 1: the match (decision 0019)
- [x] Agreement read in the download (two versions, 2021 and 2023); differences and the working rule recorded in 0001
- [x] Yelp business file extracted to `data/yelp/` (gitignored), Philadelphia loaded into the local DB
- [x] Places linked to Yelp businesses with confidence tiers; results kept in `docs/private/` (gitignored)
- [x] Reviews of the usable links loaded by streaming the file out of the zip (nothing written to disk), `user_id` dropped (decision 0020)
- [x] Jev aspect scoring (food, atmosphere, service, value) over every loaded review, plausibility-checked, not validated
- [x] Aspect labelling guidelines, a blind labelling page (`#/label`) and batch 1 (about 180 items, stratified, with repeats) (decision 0021)
- [x] Evaluation of Jev against labels, with a halo test (built and tested on planted data; not yet run on real labels)
- [x] Provisional place-level rating (Bayesian shrinkage, recency, frozen composite weights w1, credible intervals and rank intervals), status enforced `provisional`
- [x] **Owner decision 2026-10-04: no more manual labelling** (10 of 180 aspect items done; the 145 building labels were never started). Replaced by a constructed test set and hard cases (decision 0022); the rating stays provisional
- [x] Constructed probe set (176 invented reviews) and 20 hard cases run: mention and level handling good, no leakage, small halo (+0.23 of a level), implicit value and atmosphere mentions missed
- [ ] Optional, no labels needed: prompt-stability check, a lexicon baseline, a second AI annotator stored apart from human labels
- [ ] Dropped for lack of labels: baseline model vs Jev on human labels; the building ground-truth check and human review time
- [ ] Confirm which agreement version Yelp showed at the 2026-10-03 download (0001); the Data's term ends 2027-10-03


## TableMap search and chat (decision 0023)
- [x] Hybrid retrieval over `place`: census filters + aspect thresholds + full-text review search with passages, in one query (`tablemap.py`, router behind `STREETWALKER_TABLEMAP=1`, default app stays Yelp-free)
- [x] Retrieval eval on invented data, known synonym misses recorded as tests (15 new tests)
- [ ] Dense review embeddings (needs the owner's approval for an embedding-model download) and fusion with the lexical rank
- [ ] Chat over the provisional aspect data (open: which language model and key; review text to a hosted model rests on the owner's reading, decision 0001)
- [ ] Evals in CI (no CI exists yet; the retrieval eval is self-contained)
