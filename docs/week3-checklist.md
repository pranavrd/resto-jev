# Week 3 (Oct 19–25, started early): Tier 0 classification and ground truth

- [x] Crosswalk from land use and OPA codes to D1 classes, with label quality flags (decision 0007)
- [x] D3 ground truth from active food licences
- [x] Frozen street-grouped train/dev/test split with a logged test gate
- [x] Rule baselines v1 (tags), v2 (+ geometry), v3 (+ context) with evaluation
- [ ] Gradient-boosted baseline on geometry and context features (no street names)
- [ ] Jev D1 to D3 over all buildings (needs `JEV_API_KEY` in `.env`)
- [ ] Calibration analysis (reliability diagram, ECE)
- [ ] Tier 0 accuracy and calibration per area, compared with the baselines
