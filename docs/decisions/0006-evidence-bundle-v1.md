# 0006: Tier-0 evidence bundle (v1)

- **Status:** Accepted
- **Date:** 2026-10-03

## What a bundle contains

One row per building in `evidence` (tier 0, `payload` jsonb + `text`). `text` is exactly what Jev is shown (about 120 tokens), rendered deterministically from the payload by `render_text`.

| Section | Contents | Source |
|---|---|---|
| `osm` | `building` value, levels, height, name, housenumber, has-unit flag, use tags (`amenity`, `shop`, `office`, ...), material, roof | OSM building tags. Address street is omitted (it is the fronted street). |
| `pois` | Business POIs linked to the building: tags (name, cuisine, brand, ...), whether contained or nearby, distance. Contact details become flags. | OSM POIs |
| `geometry` | Footprint area, perimeter, compactness, frontage width and depth in a street-aligned frame, aspect, setback, number of party walls and share of walls shared | Footprint + street |
| `street` | Street name, road class, side walked, assignment method, corner flag | Frontage (0005) |
| `context` | Up to 2 neighbours before and after on the same side (area, attached, POIs, use tags, `event_seq`) and block totals (buildings, business POIs, share attached) | Walk order (0005) |

## Rules

- **No ground truth.** Parcels, land use and licences are the answer key. `evidence.py` and `evidence_area.py` never read them, and a test fails if either mentions those tables.
- **No classifier outputs yet.** Neighbours carry facts, not decided classes, plus `event_seq` so the cascade can later inject only the decisions already made in walk order.
- **Business POIs only.** Street furniture (benches, bike parking, waste baskets, post boxes, ...) and public space (`tourism=artwork`, parks, playgrounds) are dropped. POIs that are themselves a building (same OSM id) are covered by that building's own tags.
- **POI linking:** the smallest footprint containing the POI, else the nearest within 10 m, else unlinked.
- **Party walls:** two footprints are attached when they share at least 2 m of boundary, measured with a 0.25 m tolerance (party walls are often drawn with a gap). Verified on the data: East Passyunk is 82% two-plus walls, Roxborough 51% one wall (semi-detached).
- Imagery fields (`image_id`, `caption`) exist for tier 1 and are empty here.

## How much signal is there?

Audit against ground truth (`scripts/audit_evidence.sql`, reporting only). "Any signal" means a linked business POI, an OSM use tag, or a name.

| Area | Ground-truth class (land use) | Buildings | Any signal |
|---|---|---|---|
| Rittenhouse | commercial | 129 | 41% |
| | mixed residential/commercial | 74 | 23% |
| | residential | 195 | 16% |
| East Passyunk | commercial | 57 | 33% |
| | mixed residential/commercial | 259 | 18% |
| | residential | 2,173 | 0% |
| Roxborough | commercial | 27 | 81% |
| | mixed residential/commercial | 18 | 72% |
| | residential | 742 | 0% |

Food: of active food-preparing licences that fall in a building, the building carries food evidence for **30%** (East Passyunk, 18 of 60), **46%** (Rittenhouse, 43 of 93) and **69%** (Roxborough, 9 of 13). Licence points can sit on a neighbouring footprint, so treat these as a lower bound.

## What this means for the cascade

- **Residential is nearly free:** silent buildings are overwhelmingly residential (East Passyunk 2,171 of 2,470; Roxborough 741 of 764). Geometry and context should separate them well.
- **Commercial in rowhouse areas is mostly invisible to OSM.** In East Passyunk 251 commercial or mixed buildings (79%) carry no signal. Sample: a land-use "mixed" rowhouse is textually identical to a residential one except for a pub next door. Tier 0 will have low confidence there, and imagery escalation is needed. Expect a **high escalation rate** in East Passyunk and Rittenhouse, much lower in Roxborough.
- Rittenhouse has a surprising 16% of residential-coded buildings with signal (shops at the ground floor of residential-coded parcels, or ground-truth noise). The mixed class is expected to be noisy (see the roadmap's measurement caveats).

## Week 3 notes
- Evaluate classifiers with **street- or block-grouped splits**: street name and block context are strong features, and random splits would leak them.
- The geometry-only gradient-boosted baseline can use `geometry`, `street` and `context` numerics straight from the jsonb payload.
