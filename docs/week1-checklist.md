# Week 1 (Oct 5–11): area selection + data checks

Yelp is not used this week (see decisions 0001 and 0002).

## Blocking checks
- [x] **Mapillary coverage**: 7 candidates measured (`week1_mapillary_coverage.py`, `week1_frontage_coverage.py`). See decision 0003.
- [x] **Parcel land use**: OPA `category_code_description` plus PCPC Land Use polygons (updated Dec 2025). See `docs/data-sources.md`.
- [x] **Business / food licenses**: updated daily, food types identifiable, point geometry on every row. See `docs/data-sources.md`.
- [x] Density check of candidate boxes: `python3 scripts/week1_area_density.py`
- [ ] Lock the three areas: proposed Rittenhouse, East Passyunk, Roxborough in `docs/decisions/0003-survey-areas.md`, awaiting confirmation.

## Setup
- [x] Repo, `.gitignore`, `pyproject.toml`, decision log
- [x] Docker Compose with Postgres 16 + PostGIS 3.6 + pgvector 0.8 (running, native arm64)
- [x] `colima start`, `.env`, `docker compose up -d db`, extensions verified
- [ ] Install `uv`, `uv sync`

## Ingest
- [ ] OSM streets, buildings, POIs for the three areas
- [ ] Parcel land use and business licenses
- [ ] `docs/data-sources.md` with source, date pulled and license for each

## Exit
All non-Yelp raw data loaded, areas confirmed, decision log current.
