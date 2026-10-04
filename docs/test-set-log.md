# Test-set log

The test split is frozen (decision 0007). Every evaluation that touches it is appended here by
`python -m streetwalker.evaluate --split test --final`. Tuning happens on dev only.

| When | Baseline | Split | Area | Labels |
|---|---|---|---|---|
| 2026-10-03 22:09 UTC | rules-v1, rules-v2, rules-v3 | test | all areas | all |
| 2026-10-03 22:09 UTC | rules-v3 | test | all areas | all |
| 2026-10-03 22:26 UTC | rules-v1, rules-v2, rules-v3, gbm-geometry, gbm-tags, gbm-full | test | all areas | all |
| 2026-10-03 22:27 UTC | rules-v3, rules-v1, gbm-tags, gbm-full | test | all areas | all |
| 2026-10-03 23:07 UTC | jev-p1, rules-v3, gbm-full, gbm-tags, rules-v1 | heldout | all areas | all |
| 2026-10-03 23:07 UTC | jev-p1, rules-v3, gbm-full | heldout | rittenhouse | all |
| 2026-10-03 23:07 UTC | jev-p1, rules-v3, gbm-full | heldout | east_passyunk | all |
| 2026-10-03 23:07 UTC | jev-p1, rules-v3, gbm-full | heldout | roxborough | all |
| 2026-10-04 02:27 UTC | jev-p1, stack-lr, stack-gbm, gbm-full, rules-v3 | heldout | all areas | all |
| 2026-10-04 09:27 UTC | cascade: gate, thresholds chosen on train; Tier 1, Tier 2 and full cascade at tau 0.77 | test | all areas | all |
| 2026-10-04, between the 09:27 and 09:30 runs | AD HOC, not via --final: per-area and label-status breakdown of the cascade at tau 0.77, pooled over all splits, run in a scratch query before the same tables were added to `cascade --final` (the 09:30 run); also a train+dev per-area threshold check (no test rows) | test (pooled with train, dev) | all areas | all |
| 2026-10-04 09:30 UTC | cascade: gate, thresholds chosen on train; Tier 1, Tier 2 and full cascade at tau 0.77 | test | all areas | all |
