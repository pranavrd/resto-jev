# 0013: Panorama crops, heading semantics and a corrected image coverage

- **Status:** Accepted (pilot, East Passyunk only)
- **Date:** 2026-10-04
- **Code:** `pano.py` (projection, roll, levelling), `imagery.py` (`pick_panorama`), `imagery_area.py`, `vlm.py` (`parse_caption`), `scripts/pano_pilot.py`, `scripts/pano_pilot_report.py`, `scripts/analyze_gates.py` (Part 3); tables `pano_pick`, column `mapillary_image.computed_compass`

## What was done

East Passyunk has 70 panoramas from one 2026 ride (the only recent imagery there); Rittenhouse has 179 from 2023. I cut a perspective view toward each building out of the panoramas, levelled it, captioned it with the local vision model and asked Jev with the caption added. I downloaded the 52 East Passyunk panoramas actually used, 52 MB at full resolution (5376 x 2688); no Rittenhouse panoramas were downloaded.

## Findings

1. **For panoramas, the raw `compass_angle` is the centre of the picture.** It points along the direction of travel between consecutive captures for 63 of 63 East Passyunk panoramas (median error 1.4 degrees). `computed_compass_angle` is a consistent **86 degrees off** for them (spread 78 to 92). My first heading test, using licensed business names on four buildings, was misleading: a licence point can sit on a neighbouring building.
2. **For ordinary photos the two headings agree closely** (median 7 degrees, 85% within 15), but the raw one is just the travel direction by construction, so it cannot reveal a sideways-facing camera. The computed heading has fewer wild outliers (90th percentile 29 degrees against 40). Ordinary photos therefore **use the computed heading**, and panoramas use the raw one. Unverified for photos; revisit if captions look pointed at the wrong building.
3. **This lowers earlier coverage numbers.** Commercial-or-mixed buildings with a facing photo: **East Passyunk 47%** (was 52%), **Rittenhouse 68%** (was 88%, inflated by raw headings), Roxborough 78%. Overall 32% of buildings have a photo (was 32%, now 31% with computed headings).
4. **Panoramas add modest coverage:** commercial-or-mixed East Passyunk 47% to 55%, Rittenhouse 68% to 72% (metadata only). 136 East Passyunk buildings (41 with no ordinary photo, 95 with a 2019 to 2020 photo that a 2026 view would replace).
5. **Bike-mounted panoramas are rolled.** Crops came out visibly tilted. An auto-level step tries roll angles and keeps the one that makes edges most axis-aligned. **A vertical-edges-only score failed** on a facade with bold horizontal stripes (it rotated the stripes toward 45 degrees); the fourth-harmonic gradient score fixed it and has a test for exactly that case. Median chosen roll 9 degrees.

## Pilot: 136 East Passyunk buildings (107 commercial or mixed, 29 other), caption prompt v3

| | |
|---|---|
| Street level reported | commercial or mixed: "not visible" 41, unparsed 41, shop window or storefront 19. The model is cautious and often does not commit |
| Readable sign text | **38%** of commercial or mixed buildings, but also **28% of the other buildings (8 of 29)**: it sometimes reads a **neighbour's** sign ("BARCELONA", "CITY FITNESS") |
| Jev with the caption | Commercial-or-mixed **TP 31 to 72, FP 1 to 7, recall 0.29 to 0.67**, precision 0.97 to 0.91. 47 buildings flipped to commercial (41 correct), none flipped the wrong way |
| Ranking | AUROC 0.851 to 0.818 (not better): the caption mostly moves the operating point and also raises p(commercial) for some non-commercial buildings |
| Versus no imagery | stack-gbm alone on this subset: recall 0.83, F1 0.88, so Jev plus caption (0.77) does not beat the stacker here. The subset is 79% positive (panoramas follow the commercial corridor) |
| Beyond the stacker | `max(stack, Jev + caption)`: recall 0.83 to 0.89, 3 new false positives; the caption rescues **6 of the stacker's 18 misses** ("SALLY'S", "THE CURE", "Headhunters", "ROBERT BRAND LAW") |
| Food | p(food) on 20 licensed buildings 0.46 to 0.45: no help for D3 |

n = 136, one area, train+dev+test buildings mixed: direction and failure modes, not a rate.

## Realistic imagery ceiling (`analyze_gates.py`, Part 3, mean(Jev, stack-gbm) hidden-risk gate)

| | buildings with imagery | commercial-or-mixed with imagery | recall at 10% escalation, r = 1.0 | r = 0.45 |
|---|---|---|---|---|
| photos only | 1,181 (31%) | 321 of 564 | 0.72 | 0.57 |
| photos + panoramas | 1,241 (33%) | 355 of 564 | 0.74 | 0.58 |

For comparison, the stacker alone with no imagery reaches recall 0.69 at precision 0.72, and Jev alone 0.45 at 0.86.

## Conclusions
- **Panoramas give fresh, high-resolution imagery where it is scarce, and the caption adds real but small information beyond the stacker** (about a third of its misses on this corridor), at the cost of neighbour-sign false positives. Over the whole survey the effect is small (355 vs 321 reachable commercial buildings).
- **The imagery lever is capped by coverage, not by the model.** About a third of buildings, and 63% of commercial or mixed ones, have any imagery. The honest cascade headline: stacker first, imagery as a modest addition.
- **The vision model's neighbour-sign errors are the next precision problem.** A D5 check ("does the sign belong to the target building?"), a second view, or cropping tighter around the frontage point would address it.

## Next
1. **D5 relevance check** and a tighter crop (narrower field of view aimed at the frontage point) to cut neighbour-sign false positives.
2. Decide whether to caption the ordinary photos at scale (about 1,200 images, roughly 2.3 hours locally) so the stacker can use caption features and the gain is measured on held-out data instead of this pilot.
3. Optionally the 7B Apache-2.0 model on the same 136 crops to see whether "not visible" falls.
