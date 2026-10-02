# Week 1 (Oct 5–11): area selection + data checks

Yelp is not used this week (see decisions 0001 and 0002).

## Blocking checks
- [x] **Mapillary coverage**: 7 candidates measured (`week1_mapillary_coverage.py`, `week1_frontage_coverage.py`). See decision 0003.
- [x] **Parcel land use**: OPA `category_code_description` plus PCPC Land Use polygons (updated Dec 2025). See `docs/data-sources.md`.
- [x] **Business / food licenses**: updated daily, food types identifiable, point geometry on every row. See `docs/data-sources.md`.
- [x] Density check of candidate boxes: `python3 scripts/week1_area_density.py`
- [x] Areas locked: Rittenhouse, East Passyunk, Roxborough (`docs/decisions/0003-survey-areas.md`).

## Setup
- [x] Repo, `.gitignore`, `pyproject.toml`, decision log
- [x] Docker Compose with Postgres 16 + PostGIS 3.6 + pgvector 0.8 (running, native arm64)
- [x] `colima start`, `.env`, `docker compose up -d db`, extensions verified
- [x] Python env: `.venv` with `pip install -e .` (uv not needed)

## Ingest
- [x] OSM streets, buildings, POIs for the three areas
- [x] Parcels, land use, business licenses, Mapillary image metadata
- [x] `docs/data-sources.md` with source, date pulled and license for each

## Exit
Met 2026-10-02: all non-Yelp raw data loaded, areas confirmed, decision log current.

## Carried into Week 2
- Box tuning is optional: Rittenhouse has 445 buildings (under the ~500 target but 46% commercial), East Passyunk 2,548 (over ~2,000; it is a soft limit and cost is negligible).
- Next: Eulerian walk, frontage assignment, evidence bundles (roadmap Week 2).
