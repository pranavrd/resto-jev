# 0016: Restaurant census (OSM x City licences, no Yelp)

- **Status:** Accepted
- **Date:** 2026-10-04
- **Code:** `census.py` (matching, 17 tests), `census_area.py` (builds the `place` table and prints the census), `census_kind.py` (Jev place kinds); tables `place`, columns `kind_jev`, `kind_source`

## What was built

A `place` is a business at a location, the unit the census counts and, later, the unit matched to Yelp. Two sources, resolved into one list:

- **OSM:** 99 food and drink places (restaurant, fast food, cafe, bar, pub, ice cream, bakery or deli) inside the three areas, including buildings that carry the tags themselves.
- **City licences:** 166 active "Food Preparing and Serving" licences (84 small, 82 with 30 or more seats). Retail-food licences (groceries, delis) are excluded.

Matching (`match_places`) scores each pair on name similarity (after dropping legal words such as LLC and INC, and reading trade names out of parentheses), shared building, distance up to 30 m, and an address match (same street, OSM house number inside the licence's range). It assigns one-to-one and accepts a pair only when something beyond closeness agrees. A building holding exactly one OSM place and one licence gets a bonus, flagged "building 1:1 (names differ)" when the names disagree.

## The census

| Area | Licensed | OSM | Matched | **Union** | OSM only | Licence only | OSM finds | Licences find | Estimated total (Chapman, 95%) |
|---|---|---|---|---|---|---|---|---|---|
| Rittenhouse | 93 | 58 | 40 | **111** | 18 | 53 | 43% | 69% | 134 [117, 151] |
| East Passyunk | 60 | 31 | 21 | **70** | 10 | 39 | 35% | 68% | 88 [72, 104] |
| Roxborough | 13 | 10 | 9 | **14** | 1 | 4 | 69% | 90% | 14 [14, 16] |
| **All** | 166 | 99 | 70 | **195** | 29 | 96 | **42%** | **71%** | **234 [212, 256]** |

- **195 places in 165 buildings** (150 buildings hold one place, 8 hold two, 7 hold three or more); after dropping the 11 that Jev classes as a hotel, institution or other non-public place, **184 public eating and drinking places**: Rittenhouse 105, East Passyunk 66, Roxborough 13.
- **Density:** Rittenhouse 434 places per km2, East Passyunk 154, Roxborough 31.
- **Match quality:** 63 of 70 matches are carried by name or address (name+address+building 30, address+building 16, name+building 11, name+address 4, address 2, name 1). Five are "building 1:1, names differ"; read by hand, four are plausibly the same business (La Colombe Coffee Roasters against LA COLOMBE TORREFACTION INC, Van Leeuwen against the restaurant partnership holding its licence), one is doubtful. Confidence tiers: **high 69** (matched on name or address), **medium 115** (licence-only 96, OSM-only with a recent check date or opening hours 18, weak match 1), **low 11** (OSM-only, nothing recent).

## What the census shows

1. **OSM finds only 42% of licensed food businesses** in these areas, and the licence list is the stronger discovery source. The licence-only places are real, named businesses: Barclay Prime, Kura Sushi, Kfar, Alaska Cafe, The Black Sheep Pub, Tavern 17, and restaurants inside the Sofitel and Kimpton hotels.
2. **OSM adds 29 places the licences do not list** (bars without a food licence, newer places, or places that closed), so neither source alone is the universe. The union is **83% of the capture-recapture estimate** (195 of 234).
3. **Licences give no kind.** Jev classifies a licensed place from its name and licence size (`census_kind.py`). Against the 70 places where OSM supplies a kind it agrees 60% strictly and 69% with fast food merged into restaurant; among its confident answers (0.9 or more) 79%. The disagreements are mostly genuine ambiguity (Village Whiskey: Jev says bar, which is right; Eurest at Capital One: Jev says institution; Vibrant Coffee Roasters and Bakery: cafe or bakery), so these are lower bounds. For the 96 licence-only places Jev finds 59 restaurants, 8 bars, 8 hotels or institutions, 7 bakeries or delis, 5 cafes, 4 fast food, 3 other and 2 ice cream.
4. **The survey classifier against the census** (building level, D3 predictions): against the **union** its precision is 89% for Jev and 74% for stack-gbm, but only 71% and 60% against licences alone. Many "false positives" against the licences are real OSM-mapped places without a food licence. Recall of the union is 47% to 56% across models (stack-gbm 56%, Jev 49%). The classifier finds about half the census buildings; the City's licence list is a far better restaurant finder than the survey is. The survey's value lies elsewhere (the land-use context, places no source lists, and any city without an open licence feed).

## Caveats
- **Capture-recapture assumes independent sources.** OSM and licences are not independent (chains and busy places appear in both), which makes the estimate too low, so read 234 as a floor-ish figure, not a measurement.
- **"Active" licences include places that may have closed**, and OSM may be stale (only a minority carry a `check_date`). The census is a registry of claims; confirming operation needs a third source such as Yelp recency.
- No independent ground truth for the 29 OSM-only and 96 licence-only places exists in this project yet; the confidence tiers are heuristics, not verified.
- Kind labels for licensed places are model output (Jev from name and licence size) and are not verified against signage.

## Deferred: the Yelp comparison
The roadmap's census also compares against Yelp. **Yelp has not been touched.** Before the first Yelp download, join or query, the licence question in decision 0001 must be settled: the terms allow academic use only, the project is not tied to an institution, and the consent email is the gating step. Matching `place` to Yelp is the first thing that would need it.
