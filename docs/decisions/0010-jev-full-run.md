# 0010: Jev over all buildings (prompt p1) and escalation gates

- **Status:** Accepted
- **Date:** 2026-10-03
- **Runs:** trial p1 = run 1, trial p2 = run 2, **full p1 = run 3** (all 3,795 buildings). Stored as baseline `jev-p1`.
- **Code:** `jev_run.py`, `scripts/analyze_gates.py`

## Operations

3,795 buildings answered, 0 errors, 3.90 million input tokens, **$0.164**, about 95 seconds with 6 workers (median latency 125 ms per request). Model pinned to `jev-1.13.0`. The key never left the client constructor.

## Accuracy at natural prevalence

Wording was tuned only on 100 train buildings (0009), so dev and test are untouched by it. The 100 trial buildings are inside the train+dev numbers (3%); the held-out numbers exclude them.

**Held-out (dev + test, 1,483 buildings; D1 acc, commercial-any F1 with 95% street-grouped CI; difference paired against Jev):**

| | D1 acc | Commercial-any F1 | vs Jev | D3 F1 | ECE |
|---|---|---|---|---|---|
| jev-p1 | 0.855 [0.79, 0.91] | 0.63 [0.48, 0.75] | n/a | 0.49 | 0.096 |
| rules-v1 (tags) | 0.848 | 0.52 [0.38, 0.65] | Jev +0.11 [+0.06, +0.16] | 0.48 | n/a |
| gbm-tags | 0.862 | 0.58 [0.46, 0.67] | Jev +0.04 [-0.04, +0.13] | 0.43 | 0.023 |
| gbm-full | 0.844 | 0.63 [0.43, 0.80] | 0.00 [-0.18, +0.20] | 0.49 | 0.028 |
| rules-v3 | 0.865 | 0.75 [0.60, 0.85] | rules ahead by 0.13 [0.00, +0.24] | 0.48 | n/a |

Train + dev pooled (3,069): Jev commercial-any P 0.85, R 0.47, F1 0.60 [0.51, 0.69]; D3 P 0.71, R 0.44, F1 0.54 (the best D3 precision of any baseline).

**Reading it:**
- Jev is **clearly better than tags-only rules** (+0.11) and **statistically tied with the learned model** and with the hand-written context rules (rules-v3's lead has an interval that just touches zero, and v3 is the optimistic baseline: written after studying train).
- **Jev is not a better classifier of silent buildings than a good baseline.** That was expected from the trial and holds at scale. Its value is elsewhere (below).
- **By area (held-out):** Rittenhouse F1 0.74 but accuracy 0.53 and ECE 0.32 (heavily commercial, confidently wrong on the commercial/mixed split); East Passyunk F1 0.50 (precision 0.89, recall 0.35), where rules-v3 reaches 0.75; Roxborough F1 0.74.

## Calibration

ECE 0.093 on train + dev, against 0.02 to 0.03 for the GBMs. Jev is **overconfident**: 2,624 of 3,069 answers have confidence of 0.9 or more, and they are right 92% of the time; answers at 0.6 to 0.9 are right only 36% to 51% of the time. Errors concentrate where the text has no signal. Calibration needs correcting before confidence is used as a gate.

## Which gate should trigger escalation? (`scripts/analyze_gates.py`)

Upper-bound analysis over all 3,795 buildings: escalated buildings are assumed to be resolved perfectly by imagery, the rest keep Jev's answer. 564 buildings are commercial or mixed; Jev alone finds 45% of them at precision 0.86. 94% of buildings are silent (no tag, POI or name), and 394 of the 564 are silent.

| Gate (higher score escalates first) | 5% | 10% | 15% | 20% | 30% |
|---|---|---|---|---|---|
| Jev low confidence | 0.54 | 0.67 | 0.74 | 0.83 | 0.89 |
| Jev risk: p(commercial) + p(mixed), non-commercial answers only | **0.67** | **0.80** | **0.84** | 0.88 | 0.90 |
| GBM risk, Jev non-commercial only | 0.63 | 0.74 | 0.83 | 0.90 | **0.98** |
| mean of Jev and GBM risk | 0.65 | 0.75 | 0.83 | **0.91** | 0.98 |

Cells are commercial-or-mixed recall at that escalation rate (precision stays 0.89 to 0.99).

**Findings**
- **Low escalation rates favour Jev's own risk score** (0.80 recall at 10%, about 380 buildings), **high rates favour the GBM** (0.98 at 30%). Their combination is near the best of both and is the natural first gate.
- **Confidence alone is the weakest gate** but not useless (0.67 at 10%).
- **This is an upper bound.** Real imagery is 2018 to 2020, covers 54% to 99% of commercial parcels within 50 m depending on area (0003), and a vision model will make errors. Real recall will be lower; the escalation sweep in Week 4 measures it.
- **Gate scores are not tuned**; no threshold was fitted on this data. The cascade should fit its gate on train and report on held-out.

## Next
1. Tier 1: Mapillary image selection by bearing, VLM caption, D5 relevance check, re-ask D1 to D3 with the caption.
2. A calibrated stacker (Jev probabilities plus evidence features, fit on train, scored held-out) as a better Tier 0 confidence and gate.
3. Tier 2 (local LLM) and the human review queue.
