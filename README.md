# StreetWalker

A deterministic street survey of three Philadelphia areas. Each building is classified (residential, commercial, restaurant, cafe, and so on) with Jev decisions over OSM tags and geometry, escalating to street imagery and a local vision model only when confidence is low. Its restaurant universe feeds TableMap, a ranking and review-chat layer.

Status: Week 3 complete. Tier 0 (Jev over all 3,795 buildings, $0.16) ties the best baselines on commercial-any F1 (0.63 held-out); escalation to imagery is the next lever (Week 4).

## Data policy

Raw data lives in `data/` and is never committed. Yelp data, and anything derived from it, stays private until the Yelp license question in [decision 0001](docs/decisions/0001-yelp-license-and-showcase.md) is resolved.

## Local setup

```bash
cp .env.example .env        # set a local password; add MAPILLARY_TOKEN for the Mapillary step
docker compose up -d db     # Postgres + PostGIS + pgvector on localhost:5433
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m streetwalker.ingest all   # OSM, City of Philadelphia data, Mapillary metadata (~3 min)
```

## Replay viewer

```bash
.venv/bin/python -m streetwalker.export_replay
cd web && npm install && npm run dev
```

Evidence signal (what OSM tells the walker) next to the City's land use (ground truth), Rittenhouse after the full walk:

![Evidence signal view](docs/img/replay-rittenhouse-evidence.jpg)
![Land use view](docs/img/replay-rittenhouse-landuse.jpg)

See [web/README.md](web/README.md).

## Restaurant census

195 food and drink places in the three areas (184 public eating or drinking places), from OSM and City food licences matched into one list. OSM finds 42% of the licensed businesses; licences find 71% of OSM's places; capture-recapture suggests about 234 exist. See [decision 0016](docs/decisions/0016-restaurant-census.md).

```bash
.venv/bin/python -m streetwalker.census_area   # builds the place table, prints the census
.venv/bin/python -m streetwalker.census_kind   # Jev kinds for licensed places
```

## Place search API

Each place carries its neighborhood and SEPTA context (nearest stop and rail stop, routes and weekday departures within 400 m), and a read-only API searches them by name, kind, area, location and transit. No Yelp data is involved. See [decision 0017](docs/decisions/0017-transit-neighborhoods-and-search-api.md).

```bash
.venv/bin/python -m streetwalker.ingest septa neighborhoods   # SEPTA GTFS (22 MB) and neighborhood polygons
.venv/bin/python -m streetwalker.enrich                       # write context onto each place
.venv/bin/uvicorn streetwalker.api:app --port 8000            # interactive docs at http://localhost:8000/docs
curl 'localhost:8000/places?lat=39.9496&lng=-75.1715&radius_m=300&kind=bar&max_rail_m=400&sort=distance'
```

## Attribution

Map data © OpenStreetMap contributors (ODbL). Business licenses and land use: City of Philadelphia via OpenDataPhilly. Transit: SEPTA GTFS. Neighborhood boundaries: OpenDataPhilly, CC BY 4.0, Robert Cheetham / Azavea. Street imagery: Mapillary, CC BY-SA 4.0.
