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
- [ ] Map UI over `/places.geojson`
