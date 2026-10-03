# Week 3 (Oct 19–25, started early): Tier 0 classification and ground truth

- [x] Crosswalk from land use and OPA codes to D1 classes, with label quality flags (decision 0007)
- [x] D3 ground truth from active food licences
- [x] Frozen street-grouped train/dev/test split with a logged test gate
- [x] Rule baselines v1 (tags), v2 (+ geometry), v3 (+ context) with evaluation
- [x] Gradient-boosted baselines on geometry, tags and context (decision 0008): gbm-full ties rules-v3 within noise
- [ ] Jev D1 to D3 over all buildings (needs `JEV_API_KEY` in `.env`)
- [ ] Calibration analysis (reliability diagram, ECE)
- [ ] Tier 0 accuracy and calibration per area, compared with the baselines

Jev notes (from the SDK docs): package `typesafe-sdk`, key read from `TYPESAFE_API_KEY` (map from `JEV_API_KEY` in-process), pin `jev-1.13.0`, ask one thing per field, Jev reads literally and is weak at counting (we pass computed facts), tune each confidence bar separately. Evaluate Jev on all 3,795 buildings.
