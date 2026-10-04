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
- [ ] Tier 1 at scale: East Passyunk panorama crops, multiple photos per building, 7B comparison, D5 relevance, re-ask on all picked buildings
