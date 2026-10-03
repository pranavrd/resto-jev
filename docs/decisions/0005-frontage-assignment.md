# 0005: Frontage assignment and encounter order

- **Status:** Accepted
- **Date:** 2026-10-03

## Rules (`src/streetwalker/frontage.py`)

1. Candidate segments are street segments (see 0004) within 40 m of the footprint; if none, the nearest segment overall (`nearest_far`).
2. If the building has `addr:street` and a candidate carries that street name (normalised for abbreviations and directional words), take the nearest such candidate (`address`).
3. Otherwise take the nearest candidate (`nearest`), unless it is a service road (alley, driveway, parking aisle) and a non-service road lies within 15 m of it (`nearest_nonservice`).
4. **Position and side use the footprint centroid** (representative point if the centroid is outside the footprint), projected onto the segment. The nearest footprint point is arbitrary when a facade runs parallel to the street, which would scramble encounter order. The stored `frontage_pt` is the footprint point nearest the projected foot.
5. Side is the sign of the cross product of the segment direction and the vector to the building: `+1` left of the stored direction, `-1` right. Encounter events flip it when the walker passes the segment in the reverse direction.
6. `margin_m` is the gap between the chosen segment and the nearest candidate on a different **non-service** street. Small values mean a corner or ambiguous frontage. Alleys are excluded: an unnamed alley a few metres behind a house is not a second frontage.

## Encounter log

`walk_event` has one row per building, created on the segment's single non-repeat pass (0004). Buildings on a segment are ordered by distance along the direction walked, both sides interleaved. `walked_m` is cumulative metres since the start of the area walk (including re-walks and excluding jumps) and `sim_seconds = walked_m / 1.4`.

## Verification (2026-10-03)

- Every building has exactly one encounter: 445, 2,548 and 802.
- Side agrees with an independent PostGIS azimuth calculation for all 3,795 buildings.
- `walked_m` never decreases along `event_seq`.

## Evaluation: assignment without an address

About 18–20% of Rittenhouse and Roxborough buildings carry no `addr:street`. To measure the fallback, addresses were hidden on address-resolved buildings and the street recovered. The address-resolved street is the label (a good but imperfect proxy).

| Area | Labelled buildings | Plain nearest segment | Shipped fallback |
|---|---|---|---|
| Rittenhouse | 366 | 48.6% | 72.4% |
| East Passyunk | 2,533 | 89.1% | 90.4% |
| Roxborough | 639 | 62.3% | 91.9% |

Reproduce with `.venv/bin/python scripts/eval_frontage_fallback.py`.

Reading it:
- Plain nearest is unreliable wherever alleys, driveways or interior-block buildings exist. The non-service preference closes most of that gap in Roxborough.
- **Rittenhouse is the weak case (72%)**: large buildings with frontage on several streets and many alleys. About 22 of its 79 address-less buildings are probably assigned to the wrong street. This affects encounter order and neighbour context, but not the footprint-level evidence for classification.

## Known limits and follow-ups
- Accessory buildings (garages, sheds) far from any street still get a segment. Roxborough has 27 `nearest_far` buildings (more than 40 m from a street); treat them as accessory candidates in evidence assembly.
- A possible fallback improvement for address-less buildings is to take the street most common among neighbours along the block. Not done; revisit if neighbour-context ablations show street assignment errors matter.
- Buildings with several frontages (corner towers, through-block buildings) are assigned one segment. `margin_m` flags them.
