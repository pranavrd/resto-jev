# Week 1 (Oct 5–11): area selection + data checks

Yelp is not used this week (see decisions 0001 and 0002).

## Blocking checks
- [ ] **Mapillary coverage** for each candidate area (Rittenhouse, East Passyunk, Chestnut Hill, Mayfair). Needs a free `MAPILLARY_TOKEN` in `.env`, then `python3 scripts/week1_mapillary_coverage.py` (written, not yet run).
- [x] **Parcel land use**: OPA `category_code_description` plus PCPC Land Use polygons (updated Dec 2025). See `docs/data-sources.md`.
- [x] **Business / food licenses**: updated daily, food types identifiable, point geometry on every row. See `docs/data-sources.md`.
- [x] Density check of candidate boxes: `python3 scripts/week1_area_density.py`
- [ ] Lock the three areas and record the decision in `docs/decisions/0003-survey-areas.md`.

## Setup
- [x] Repo, `.gitignore`, `pyproject.toml`, decision log
- [x] Docker Compose with Postgres 16 + PostGIS + pgvector (written, not yet run)
- [ ] `colima start`, copy `.env.example` to `.env`, `docker compose up -d db`, confirm extensions load
- [ ] Install `uv`, `uv sync`

## Ingest
- [ ] OSM streets, buildings, POIs for the three areas
- [ ] Parcel land use and business licenses
- [ ] `docs/data-sources.md` with source, date pulled and license for each

## Exit
All non-Yelp raw data loaded, areas confirmed, decision log current.
