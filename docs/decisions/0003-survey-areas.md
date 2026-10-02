# 0003: Survey areas

- **Status:** Accepted (2026-10-02): Rittenhouse, East Passyunk, Roxborough
- **Date:** 2026-10-02
- **Evidence:** `scripts/week1_area_density.py`, `week1_mapillary_coverage.py`, `week1_frontage_coverage.py`

## Decision

| Profile | Area | Rough box (lng_min, lat_min, lng_max, lat_max) |
|---|---|---|
| Dense commercial core | **Rittenhouse** | (-75.1745, 39.9475, -75.1685, 39.9520) |
| Mixed rowhouse corridor | **East Passyunk** | (-75.1710, 39.9235, -75.1630, 39.9295) |
| Low-density residential | **Roxborough** (Ridge Ave area) | (-75.2195, 40.0345, -75.2115, 40.0405) |

Boxes are rough and get refined to street-aligned polygons after OSM ingest, when building counts replace parcel counts (target: at most ~2,000 buildings each).

## Evidence

Share of commercial or mixed-use parcels, and of active food-licence sites, with a Mapillary image within 50 m (30 m shown for reference; OPA points are parcel centroids, so 50 m is the fairer radius):

| Area | Parcels | Active food licences | Images | Commercial/mixed within 30 m / 50 m | Food licences within 30 m / 50 m | Typical image year |
|---|---|---|---|---|---|---|
| Rittenhouse | 2,536 | 103 | ~1,730 | 76% / 99% | 76% / 97% | 2019 |
| East Passyunk | 2,532 | 71 | ~1,780 | 54% / 79% | 49% / 73% | 2019–2020 |
| Roxborough | 781 | 16 | 89 | 48% / 82% | 19% / 94% | 2020 |
| Chestnut Hill | 399 | 21 | 148 | 28% / 63% | 10% / 62% | 2018 |
| Mayfair (NE) | 1,167 | 13 | 404 | 7% / 54% | 0% / 54% | 2019 |
| Mt Airy | 713 | 9 | 855 | 27% / 27% | 22% / 22% | 2018 |
| Holmesburg | 1,014 | 18 | 0 | 0% / 0% | 0% / 0% | none |

## Reasoning

- **Rittenhouse and East Passyunk** have the best coverage and the most commercial activity, and they match the dense-core and hard-mixed profiles in the roadmap.
- **Roxborough** is the best low-density option: mostly single-family (about 85% of parcels), 22 commercial and 18 mixed-use parcels, and the highest imagery coverage of the low-density candidates. Chestnut Hill was the roadmap's first choice but has a single 2018 pass and only 399 parcels. Mayfair, Mt Airy and Holmesburg are too thinly covered for the imagery tier to work.
- All three areas are inside city limits, so one parcel schema applies.

## Risks and notes

- **Imagery is 6–8 years old** (mostly 2018–2020) while licences and OSM are 2026. Escalation can confirm building form and long-lived signage, but a storefront may have changed hands. D5 (does the caption describe the target frontage?) won't catch that. Treat imagery-derived labels as lower confidence, and measure how often imagery disagrees with a current licence.
- **Roxborough has only 89 images**, from a single 2020 pass. Bearing-based image selection may fail for many buildings. That is acceptable: the cascade must fall through to the LLM and review-queue tiers when no usable image exists, and that fallback is worth measuring in its own right.
- **Image counts shift between API runs** (East Passyunk returned 1,611 and 1,782 in two runs), so coverage figures are approximate. Cache image IDs and capture dates at ingest, and report from the cached snapshot.
- Parcel counts overstate buildings in dense areas (condo towers). The 500–2,000 target is checked against OSM buildings.
- East Passyunk's box may exceed 2,000 buildings; shrink it at ingest if so.
