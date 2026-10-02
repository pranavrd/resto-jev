# Data sources

Checked 2026-10-02. Re-check update dates when data is pulled.

## City of Philadelphia (OpenDataPhilly)

Terms: City of Philadelphia license (as-is, user bears responsibility, City reserves rights in the database; browsing and use constitutes acceptance). Attribute the City. Details: metadata.phila.gov terms of use.

> OpenDataPhilly moved to a new site; the old CKAN API (`/api/3/action/...`) no longer exists. Dataset pages are at `opendataphilly.org/datasets/<slug>/`, and data is served from Carto and ArcGIS endpoints below.

### Business licenses (`business_licenses`)
- Endpoint: `https://phl.carto.com/api/v2/sql` (public, no key). Updated daily; newest record initial-issued 2026-10-01.
- ~436k rows, all with point geometry. Key fields: `licensetype`, `licensestatus`, `address`, `business_name`, `legalname`, `initialissuedate`, `mostrecentissuedate`, `expirationdate`, `inactivedate`, `parcel_id_num`, `opa_account_num`, `the_geom`.
- Food types identifiable by `licensetype`: *Food Preparing and Serving* (4,299 active), *Food Preparing and Serving (30+ SEATS)* (2,662 active), *Food Establishment, Retail Permanent Location* (1,052), *Food Establishment, Retail Perm Location (Large)* (388), plus non-permanent, caterer and manufacturer types. `Sidewalk Cafe` is a separate type (292 active).
- **Use:** restaurant ground truth. Active `Food Preparing and Serving*` licenses approximate restaurants and cafes. It does not say restaurant versus cafe versus bar; D2 sub-types need another source (OSM tags, imagery, labels).
- **Caveats:** `mostrecentissuedate` contains a sentinel year 3200; ignore it. Status values: Active, Inactive, Closed, Expired, Revoked, Suspended. A license is for a legal entity at an address, not a building.

### Property assessments (`opa_properties_public`)
- Endpoint: same Carto SQL API. ~584k parcels, point geometry. Updated through at least 2026-09 (latest sale date 2026-09-23).
- Land-use field: `category_code_description`: SINGLE FAMILY, MULTI FAMILY, MIXED USE, COMMERCIAL, INDUSTRIAL, VACANT LAND, OFFICES, RETAIL, HOTEL, APARTMENTS > 4 UNITS, GARAGE, SPECIAL PURPOSE. Also `building_code_description`, `zoning`, `number_stories`, `total_area`, `year_built`.
- **Caveat:** one record per tax account, so condo towers have many records. Parcel counts overstate building counts in dense areas.

### Land Use (PCPC)
- Page: `opendataphilly.org/datasets/land-use/`. Service: `services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/Land_Use/FeatureServer/0` (polygons, 559k rows). Last edited 2025-12-30 / 2026-01-05. Record `year` is 2023 (515k) or 2025 (44k).
- Fields: `c_dig1/c_dig1desc` (9 major classes), `c_dig2/c_dig2desc`, `c_dig3/c_dig3desc` (sub-class where available), `vacbldg`.
- Commercial detail: 21x Consumer (211 Store, 212 Food Service and Drinking, 213 Auto), 22x Business/Professional, 23x Mixed Residential (231 Store/Office with Residential, **232 Rowhouse Store/Office with Residential**, 233 Detached/Semi-detached).
- **Use:** primary ground truth for D1 (residential / commercial / mixed-use / industrial / civic / vacant). Per-parcel polygons join to OSM building footprints spatially.
- **Join gotcha:** the layer contains huge background polygons (for example a ~19 km2 class-5 polygon from 2025) beneath the real parcel polygons, so a naive point-in-polygon join returns the wrong class. Use the `building_land_use` view (migration 002), which takes the smallest containing polygon.
- **Code map:** c_dig1 1 Residential, 2 Commercial, 3 Industrial, 4 Civic/Institution, 5 Transportation, 6 Culture/Recreation, 7 Park/Open Space, 8 Water, 9 Vacant. Proposed D1 mapping: mixed-use = c_dig2 23; commercial = c_dig2 21 or 22. Finalize in the Week 3 crosswalk.
- **Caveat:** 3-digit sub-classes are populated for only a small fraction of commercial parcels (212 Food Service: ~83), so it can't validate restaurant versus retail. Licenses carry that eval.

## Not yet checked
- **OSM:** pulled via OSMnx at ingest; attribution (ODbL) required.
- **Building footprints:** OSM buildings are the plan. The City also publishes footprints; check at ingest whether they are cleaner and which has better address attributes.

## Mapillary (checked 2026-10-02)
- Graph API v4, images endpoint with a bbox query; requires a free developer client token (`MAPILLARY_TOKEN` in `.env`).
- Coverage is concentrated on main commercial streets and is mostly 2018–2020, so imagery is 6–8 years older than the licence and OSM data. Per-area results are in `docs/decisions/0003-survey-areas.md`.
- Image counts vary slightly between API runs; snapshot IDs and capture dates at ingest.
- Images are CC BY-SA 4.0. Cache IDs and captions only, and attribute if images are shown.

## Ingest snapshot (2026-10-02)

Loaded by `python -m streetwalker.ingest all`. Re-runs replace each area's rows.

| Area | OSM buildings | OSM POIs | Street edges | OPA parcels | Land use polygons | Licences (all types) | Mapillary images |
|---|---|---|---|---|---|---|---|
| Rittenhouse | 445 | 329 | 990 | 2,536 | 482 | 1,875 | 1,760 |
| East Passyunk | 2,548 | 125 | 1,026 | 2,532 | 2,662 | 1,747 | 1,899 |
| Roxborough | 802 | 113 | 702 | 781 | 738 | 355 | 89 |

Ground-truth land use per building (via `building_land_use`):

| Area | Residential | Commercial (incl. mixed) | of which mixed res/comm | Other |
|---|---|---|---|---|
| Rittenhouse | 195 | 203 | 74 | 47 |
| East Passyunk | 2,173 | 316 | 259 | 59 |
| Roxborough | 742 | 45 | 18 | 15 |

Observations that shape Week 2–4:
- **OSM tags are thin outside the core.** East Passyunk: 2,540 of 2,548 buildings are bare `building=yes`, 31 are named, 28 carry a shop/amenity/office tag. Rittenhouse: 18 of 445 carry a use tag. Addresses are present on nearly all East Passyunk buildings (a City import), so addresses and geometry are the main Tier 0 evidence there.
- **OSM food POIs vs active food-prep licences:** Rittenhouse 62 vs 93, East Passyunk 36 vs 60, Roxborough 11 vs 13. OSM alone finds roughly 60–85% of licensed food businesses, which is the baseline for the restaurant census.
- Imagery is mostly 2018–2020 (see decision 0003).
