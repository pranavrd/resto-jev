# 0012: Vision model, image selection and the tier-1 pilot

- **Status:** Accepted (pilot findings, not a final measurement)
- **Date:** 2026-10-04
- **Code:** `imagery.py`, `imagery_area.py`, `images_cache.py`, `vlm.py`, `scripts/vlm_pilot.py`, `scripts/analyze_gates.py` (Part 3); table `image_pick`

## Hardware and model

Apple M2, 16 GB, no discrete GPU. A local **MLX** vision model is feasible, so Kaggle is **not needed for throughput**.

| | |
|---|---|
| Model | `mlx-community/Qwen2.5-VL-3B-Instruct-4bit`, 3.09 GB on disk |
| Speed | 6.8 s per image steady state (about 530 images per hour), 7 to 10 s on the first image |
| Memory | 3.9 GB peak |
| License | **Qwen Research License (non-commercial)**, acceptable for this portfolio project. The 7B variant is Apache-2.0 (about 5.5 GB at 4-bit, still feasible on 16 GB) and is the swap if the project ever becomes a hosted or commercial product |

Kaggle (free batch GPU) stays the fallback if a larger model is wanted for a few thousand images. Images are cached under `data/images` (gitignored), never committed or redistributed (CC BY-SA 4.0, attribution if shown). The database keeps image ids, picks and captions only.

For the later **chat layer**, an open-weight model behind a hosted API is acceptable if a local model is too slow, as long as the Yelp restrictions in 0001 are respected (no review text sent to third parties without consent).

## Image selection (`imagery.py`, 7 tests)

Pick the photo whose camera heading points at the building's frontage point: 4 to 35 m away, within 40 degrees of the frame centre, ideal distance 12 m, small preference for newer. Panoramas are skipped because their heading is not a viewing direction.

Coverage over all 3,795 buildings: **1,231 buildings (32%) have a usable photo.** Commercial 75%, mixed-use 63%, residential 26%. Commercial-or-mixed buildings with a photo, by area: **Rittenhouse 88%, Roxborough 80%, East Passyunk 52%**. Picks are 2015 to 2020 (mostly 2019 and 2020, mean age 6.8 years), median 20 m away and 15 degrees off centre. East Passyunk has newer 2026 imagery, but only as panoramas; **cropping a view out of those panoramas is the most promising way to get fresh East Passyunk imagery** and is not yet done.

## Pilot: 20 buildings (14 commercial or mixed, 6 residential), caption then ask Jev D1 to D3

Photos are often distant windshield shots with the camera tilted up, so ground floors sit at the bottom edge.

| Caption prompt | Result |
|---|---|
| v1 "storefront or house?" | Reads real signs ("NAILS", "Bread", "RINO BROS") but answers "storefront" for nearly everything, including homes, and reports traffic and street-name signs as shop signs |
| v2 neutral, with an explicit refusal phrase | Answers "ground floor not visible" for **all 20**; Jev's answers did not change |
| **v3 structured** (street level from a list that includes "not visible", plus the building's own sign text or "none") | **Commercial-any correct 9 of 20 to 12 of 20.** Mean p(commercial) on commercial or mixed 0.42 to 0.55; on residential 0.42 to 0.43 (**no new false positives**). Biggest flips: "GIFT STORE" 0.02 to 0.88, "Interior Concepts" 0.10 to 0.92 |
| v3 on the lower 55% of each photo | Also 12 of 20, finds more sign text ("Professional Nails", "PLENTY CAFE") but one caption echoed the prompt text; keep as an option |

Captions help only when readable signage exists (6 of 14 commercial or mixed buildings), and the model reports street level as "not visible" for most photos. n = 20: this shows direction and failure modes, not a rate.

## What imagery can realistically add (`analyze_gates.py`, Part 3)

Only buildings with a usable photo can be escalated, and imagery resolves only a fraction r of the commercial ones it is shown (pilot: about 0.45). Commercial-or-mixed recall at precision about 0.9, escalating the top x% of all buildings:

| Gate | 10% | 20% | 30% |
|---|---|---|---|
| Jev hidden risk, r = 1.0 (oracle) | 0.72 | 0.75 | 0.79 |
| mean(Jev, stack-gbm) hidden risk, r = 1.0 | 0.76 | 0.80 | 0.80 |
| mean(Jev, stack-gbm) hidden risk, **r = 0.45** | **0.59** | **0.61** | **0.61** |
| Jev alone, no imagery | 0.45 | | |
| stack-gbm alone, no imagery (0011) | 0.69 (precision 0.72) | | |

**Findings**
1. **The imagery ceiling is far below the earlier oracle numbers** (0.98 in 0010): only 380 of 564 commercial or mixed buildings have a usable photo, so even a perfect vision model plateaus near 0.80 recall.
2. **At a realistic resolution rate, imagery lifts Jev from 0.45 to about 0.60 recall**, about +0.15, at precision near 0.89. That is a real gain over raw Jev but **no better than the stacker alone with no imagery** (0.69 at precision 0.72). The cascade's headline curve will be modest, and the write-up should say so: the stacker is the main lever, imagery is an addition.
3. Imagery's value is concentrated in Rittenhouse and Roxborough (80 to 88% coverage); East Passyunk, the hardest area, is the worst covered.

## Next experiments (ordered by expected value per hour)
1. **East Passyunk panoramas:** crop a perspective view toward the building out of the 2026 panoramas. Fresh imagery for the area that needs it most.
2. **More than one photo per building** (top 2 or 3 picks) so a building whose first photo shows "not visible" gets another chance.
3. **Larger VLM** (Qwen2.5-VL-7B, Apache-2.0) on a few hundred images, locally or on Kaggle, to see whether "not visible" falls.
4. The D5 relevance check (does the caption describe the target building?) once captions are used at scale; and parsing the structured caption so echoed prompt text counts as "none".

## Not done
- No caption has been scored against ground truth beyond the 20-building pilot, and the pilot buildings are train-split trial buildings.
- Caption prompt v3 and the lower-crop option are candidates, not a frozen choice.
