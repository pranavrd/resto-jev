# 0014: Tighter crops, a position-aware caption and the D5 check

- **Status:** Accepted. The pilot answers the question it was run to answer: strict own-sign attribution removes most of imagery's apparent gain.
- **Date:** 2026-10-04
- **Code:** `imagery.fov_for_frontage`, `vlm.CAPTION_PROMPT_V4` and `parse_caption_v4`, `jev_questions.build_tier1_questions` (D5), `scripts/pano_pilot.py`, `scripts/pano_variants_report.py`

## What was tried

The 136 East Passyunk buildings with a panorama (0013), three variants:

| Variant | Field of view | Caption |
|---|---|---|
| wide-v3 | fixed 80 degrees | "street level" and one sign field |
| tight-v3 | from the building's frontage width and distance (35 to 75 degrees, the building fills about 60% of the frame) | same |
| tight-v4 | same tight view | separate fields for the sign on the **centre** building and for signs on **neighbouring** buildings |

Each Jev call also asked **D5**: does the description report a sign, awning, shop window or entrance on the target building itself?

## Results (107 commercial or mixed buildings, 29 other)

| | wide-v3 | tight-v3 | tight-v4 |
|---|---|---|---|
| Sign attributed to the target, commercial or mixed | 36% | 25% | **20%** |
| Sign attributed to the target, **other buildings (false)** | 28% | 10% | **7%** |
| Precision of a reported sign | 83% | 90% | **91%** |
| Jev + caption: TP / FP / FN | 72 / 7 / 35 | 62 / 5 / 45 | **42 / 1 / 65** |
| Recall / precision | 0.67 / 0.91 | 0.58 / 0.93 | **0.39 / 0.98** |
| AUROC / AP | 0.818 / 0.938 | 0.846 / 0.940 | **0.862 / 0.949** |
| Misses of the stacker that the caption rescues (of 18) | 6 (3 new FP) | 0 | **1 (0 new FP)** |

Reference on the same buildings: Jev tier 0 TP 31, FP 1, recall 0.29, AUROC 0.851, AP 0.948; stack-gbm TP 89, FP 7, recall 0.83.

## Findings

1. **Much of the wide-view gain was neighbours' signs.** Signs next door correlate with "this is a commercial corridor", which the stacker already knows from block POIs. Tightening the view and separating signs removed that shortcut: false signs fell from 28% to 7% and the caption's contribution beyond the stacker fell from 6 rescued buildings to 1. The honest value of imagery is the tight-v4 row.
2. **tight-v4 is clean but small.** It is the only variant that does not hurt Jev's ranking, with one false positive in 136, but it reads a sign on only 20% of commercial or mixed buildings, so recall rises from 0.29 to 0.39.
3. **D5 on text alone does not work.** It mostly tracks whether a sign was reported (AUROC 0.91 for that on tight-v3) and ranks commercial buildings only moderately (AUROC 0.71 to 0.74). Gating the caption by D5 at any threshold leaves the false positives unchanged and drops true positives (tight-v4: 42 to 39 TP, 1 FP either way; tight-v3 at 0.5 collapses to tier 0). Jev has no pixels or positions, so it cannot check where a sign is. **Spatial attribution has to come from the vision model's output, as in v4, and from geometry.** D5 is kept in `build_tier1_questions` but is not used as a gate.
4. **Parser fix:** the literal answer "not visible" had been recorded as a sign. Fixed in both parsers with tests; reports re-parse signs from the raw captions.

## Realistic imagery ceiling, updated (`analyze_gates.py`, Part 3)

Resolution rate r for buildings Jev missed, by pilot: 0.45 (20 photos), 0.54 (wide crops, neighbour signs included), **0.14 (tight-v4: 11 of 76)**. Commercial-or-mixed recall with the mean(Jev, stack-gbm) hidden-risk gate, photos plus panoramas, at 10% escalation: r = 1.0 gives 0.74; r = 0.45 gives 0.58; **r = 0.14 gives 0.49**. Jev alone is 0.45 and **stack-gbm alone, with no imagery, is 0.69 at precision 0.72**.

## Conclusion and recommendation

With a 3B vision model and strict attribution, **imagery adds about 0.05 recall to raw Jev and almost nothing beyond the stacker**. The stacker (0011) is the classifier that matters for commercial-or-mixed detection. Imagery stays in the system as a documented, low-yield tier with a clean, well-measured negative-to-marginal result, which is itself a portfolio finding: the lever is coverage and sign legibility, not question wording.

Options for the imagery tier, in rough order of expected value:
1. **A dedicated OCR model on the crops** (reads text without describing a scene; the 3B model reads signs on only 20% of commercial buildings). Cost: a few hundred MB of models, a short experiment on the same 136 crops.
2. **Scan the full frontage with several narrow overlapping crops** instead of one view per building.
3. **The 7B Apache-2.0 vision model** (about 5.5 GB download) to see whether it reads more signs.
4. **Stop investing here** and spend the time on the downstream product (ratings, search and the review chat), keeping the tier-1 code as is.

## Caveats
n = 136, one area, corridor-heavy (79% positive), train, dev and test buildings mixed; variants were compared on the same buildings, but the caption prompts were iterated on this set, so absolute numbers are optimistic. Not a measurement on held-out data.
