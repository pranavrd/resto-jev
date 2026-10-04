# StreetWalker

A deterministic street survey of three Philadelphia areas. Each building is classified (residential, commercial, restaurant, cafe, and so on) with Jev decisions over OSM tags and geometry, escalating to street imagery and a local vision model only when confidence is low. Its restaurant universe feeds TableMap, a ranking and review-chat layer.

Status: the survey, census, search API, map UI and escalation cascade are built (decisions 0002 to 0018). The Yelp half has not started. Tier 0 (Jev plus a calibrated stacker) labels 88% of buildings correctly, a confidence gate picks which to escalate, and a human queue handles the rest; the imagery and local-LLM tiers were measured and do not help (decision 0018).

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

## Escalation cascade

Tier 0 answers every building; a gate escalates the ones it is unsure of; a human queue resolves them. At the threshold chosen on train for a 95% accurate kept set (tau 0.77), on the frozen test split: 18% of buildings escalated [12, 30], kept accuracy 94.3%, final D1 accuracy 0.953 (0.884 before), commercial-any F1 0.75 to 0.92. The two intermediate tiers made things worse on the buildings the gate escalates: street-image captions by -0.12 accuracy, a local LLM by -0.11. The cascade works in the rowhouse areas and not in the dense core (Rittenhouse: 75% escalated, Tier 0 not calibrated there). The human tier is an oracle until the review labels exist. See [decision 0018](docs/decisions/0018-escalation-cascade.md).

![Escalation curve](docs/img/cascade-curve.png)

```bash
.venv/bin/python -m streetwalker.cascade --figure docs/img/cascade-curve.png   # gates, thresholds, tier tables (train + dev; --final adds the logged test read)
.venv/bin/python -m streetwalker.review seed                                    # build the review queues, cache their photos
STREETWALKER_REVIEW=1 .venv/bin/uvicorn streetwalker.api:app --port 8000        # then cd web && npm run dev, open #/review
.venv/bin/python -m streetwalker.review report                                  # agreement with the parcel labels, seconds per label
```

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
cd web && npm run dev                                         # map UI at http://localhost:5173 (proxies /api to the API)
curl 'localhost:8000/places?lat=39.9496&lng=-75.1715&radius_m=300&kind=bar&max_rail_m=400&sort=distance'
```

![Places map](docs/img/places-rittenhouse.jpg)

The map UI is described in [web/README.md](web/README.md).

## Attribution

Map data © OpenStreetMap contributors (ODbL). Business licenses and land use: City of Philadelphia via OpenDataPhilly. Transit: SEPTA GTFS. Neighborhood boundaries: OpenDataPhilly, CC BY 4.0, Robert Cheetham / Azavea. Street imagery: Mapillary, CC BY-SA 4.0.
