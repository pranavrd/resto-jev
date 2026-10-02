# Week 1 (Oct 5–11): area selection + data checks

Yelp is not used this week (see decisions 0001 and 0002).

## Blocking checks
- [ ] **Mapillary coverage** for each candidate area (Rittenhouse / Washington Square West, East Passyunk, Chestnut Hill or a Northeast neighborhood). Record image counts and capture dates.
- [ ] **Parcel land use** on OpenDataPhilly: dataset name, fields, update date, license.
- [ ] **Business / food licenses** on OpenDataPhilly: fields, whether food establishments are identifiable, update date, license.
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
