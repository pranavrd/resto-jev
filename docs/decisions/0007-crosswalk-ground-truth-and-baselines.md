# 0007: Crosswalk, ground truth, splits and rule baselines

- **Status:** Accepted
- **Date:** 2026-10-03
- **Code:** `groundtruth.py`, `groundtruth_area.py`, `baseline_rules.py`, `evaluate.py`, `metrics.py`

## D1 classes and the crosswalk

D1 has seven scored classes: residential, commercial, mixed-use, industrial, civic-institutional, vacant, other. Jev may also answer `unknown` (an abstention, counted separately) and `parking` (folded into `other`: Land Use has no parking class).

Primary truth is the City's PCPC Land Use polygon containing the building (smallest polygon, see 0006 and the `building_land_use` view). OPA is only a cross-check: its parcel points are centroids and fall inside the footprint for just 83% of buildings, and it codes tax-exempt churches and schools as COMMERCIAL.

| Land use (c_dig2) | Class | Notes |
|---|---|---|
| 11, 12, 13 (low, medium, high density residential) | residential | Garages and sheds on residential parcels inherit this |
| 21 commercial consumer, 22 business/professional | commercial | |
| 23 commercial mixed residential | mixed-use | Includes 232, rowhouse store or office with residential |
| 31 industrial | industrial | |
| 41 civic/institution, 61 culture/amusement, 62 active recreation | civic-institutional | 61 and 62 are a judgement call (about 13 buildings) |
| 91 vacant | vacant | |
| 51 transportation, 52, 71 park, 72 cemetery, 81 water, 92 other/unknown | other | |

| OPA category | Class |
|---|---|
| Single family, multi family, apartments > 4 units | residential |
| Mixed use | mixed-use |
| Commercial, offices, retail, hotel | commercial |
| Industrial | industrial |
| Special purpose | civic-institutional |
| Vacant land (3 variants) | vacant |
| Garage (residential or commercial) | other |

**Label quality** (3,795 buildings): 80% `agree` (OPA says the same), 17% `land_use_only` (no OPA point in the footprint), 3% `disputed` (107). 57 footprints (1.5%) straddle two land-use classes and are flagged `split_footprint`. Class counts: residential 3,110, mixed-use 351, commercial 213, civic-institutional 58, other 39, industrial 22, vacant 2.

**D3 truth** is an active "Food Preparing and Serving" licence within 15 m of the building (146 buildings). The two ways of linking a licence agreed on all 158 licences that have an OPA account, and all 166 licences in our areas sit within 15 m of a building. Active retail-food licences (22 buildings) are stored separately and not counted as D3. Licences only cover what the City licenses, not every bar or cafe.

**Known ambiguity:** commercial versus mixed-use is a fuzzy boundary (apartment towers with ground-floor retail land in residential, commercial or civic in Land Use). We therefore also report **commercial-any** (commercial or mixed-use), the metric that matters for finding restaurants.

## Splits (frozen)

Train, dev and test are 60/20/20, grouped by street so a street's buildings never straddle splits. Streets holding more than 10% of an area's weight (non-residential buildings count 5, residential 1) are divided into blocks, otherwise one street decides a whole split (Roxborough's Ridge Avenue holds 35 of its 45 commercial buildings). Assignment is greedy per area and stored once in `split_assignment`, so rebuilding upstream tables never moves a street.

| | Buildings | Commercial | Mixed-use | Civic | Food-licensed |
|---|---|---|---|---|---|
| train | 2,312 | 127 | 221 | 27 | 90 |
| dev | 757 | 37 | 77 | 13 | 35 |
| test | 726 | 49 | 53 | 18 | 21 |

Roxborough has 45 commercial or mixed buildings in total, so its dev and test sets hold 11 and 1.

**Policy.** Rules and models are developed on train and checked on dev. The test split is touched through `evaluate --split test --final`, which logs each access to `docs/test-set-log.md`. Large streets split into blocks mean neighbouring blocks of one street can sit in different splits, so street-name features must stay out of learned baselines.

## Rule baselines (the first rungs of the evidence ablation)

| Set | Adds | Notes |
|---|---|---|
| rules-v1 | Tags only: OSM tags and POIs | Frozen exactly as first written, before any results |
| rules-v2 | Footprint geometry | Mixed-use versus commercial by rowhouse-like shape (attached, ≤ 300 m², ≤ 10 m wide). Train showed `addr:unit` and apartment tags mark large multi-tenant buildings, not residential ones |
| rules-v3 | Street context | Silent, attached, untagged building on a primary or tertiary street whose block has at least one business POI is mixed-use (rowhouse-like) or commercial |

D3 uses the same food-tag rule in all three.

## Results

| Split | Baseline | D1 accuracy | Macro-F1 | Commercial-any P / R / F1 | D3 food P / R / F1 |
|---|---|---|---|---|---|
| train (2,312) | v1 tags | 0.855 | 0.281 | 0.85 / 0.30 / 0.45 | 0.75 / 0.40 / 0.52 |
| | v2 + geometry | 0.855 | 0.279 | 0.85 / 0.30 / 0.45 | same |
| | v3 + context | 0.876 | 0.323 | 0.83 / 0.58 / 0.68 | same |
| dev (757) | v1 | 0.855 | 0.384 | 0.83 / 0.42 / 0.56 | 0.52 / 0.37 / 0.43 |
| | v2 | 0.863 | 0.401 | 0.83 / 0.42 / 0.56 | same |
| | v3 | 0.873 | 0.419 | 0.80 / 0.82 / 0.81 | same |
| **test (726, final)** | v1 | 0.840 | 0.352 | 0.85 / 0.32 / 0.47 | 0.67 / 0.48 / 0.56 |
| | v2 | 0.833 | 0.329 | 0.85 / 0.32 / 0.47 | same |
| | v3 | **0.857** | **0.389** | **0.89 / 0.53 / 0.66** | same |

Always predicting residential scores 0.800 accuracy on test.

Reading it honestly:
- **Tags alone barely beat "always residential".** Precision is fine; recall is not. Most commercial buildings carry no OSM signal (0006), and no rule can find what the evidence doesn't contain.
- **v2 did not help overall accuracy**: +0.8 points on dev, −0.7 on test, within noise. It makes commercial-versus-mixed decisions slightly more principled but does not move commercial-any.
- **v3 context is the real gain**: commercial-any recall 0.32 to 0.53 on test at precision 0.89. **Dev overstated it** (F1 0.81 against 0.66 on test and 0.68 on train). I also saw dev results from a first v3 attempt, whose road-class-only rule collapsed dev precision to 0.49, before changing it to require a known-business block, a change motivated by the train analysis. Dev is therefore not pristine for v3; test is.
- Per area (test, v3): East Passyunk commercial-any F1 0.66, Rittenhouse 0.66, Roxborough 1.00 on a single positive building (not meaningful).
- **D3 food** precision 0.67, recall 0.48 on 21 licensed buildings. OSM mapping misses licensed restaurants, and some mapped restaurants have no active licence.
- Rare classes are unsolved by tags: industrial (15 test buildings, all missed), other and vacant. They are untagged in OSM.

## What this sets up
The bar for Jev is test commercial-any F1 **0.66** (P 0.89, R 0.53) and D1 accuracy **0.857**, from tags, geometry and street context. Jev has to improve recall on silent commercial buildings; imagery escalation is how it gets there. Next: a gradient-boosted model on geometry and context features (train on train, tune on dev; no street names), then Jev D1 to D3.
