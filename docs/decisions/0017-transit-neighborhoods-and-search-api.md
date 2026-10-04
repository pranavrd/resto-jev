# 0017: SEPTA and neighborhood context, and the place search API (no Yelp)

- **Status:** Accepted
- **Date:** 2026-10-03
- **Code:** `transit.py` (GTFS parsing and distance maths, 5 tests), `ingest/septa.py`, `ingest/neighborhoods.py`, `enrich.py`, `search.py` (query builder, 8 tests), `api.py` (FastAPI, 8 tests against the local DB); migration 014 (`transit_stop`, `neighborhood`, new `place` columns, `pg_trgm`)

## What was built

Every `place` in the census now carries a neighborhood and its SEPTA context, and a read-only HTTP API searches them.

- **SEPTA GTFS**, release `v202609270` (pinned in `ingest/septa.py`): the bus feed, which also holds the subway and trolley lines, and the rail feed. About 22 MB, downloaded once to `data/septa/`. 5,094 stops within roughly 3 km of the survey areas are stored with the service they get on one typical weekday: Wednesday 2026-10-07, chosen as the first Wednesday inside both feeds' validity.
- **Neighborhoods:** OpenDataPhilly's 159 neighborhood polygons (CC BY 4.0, attribute Robert Cheetham / Azavea; data last updated 2024). A place takes the smallest polygon that contains it.
- **Per-place transit context** (`enrich.py`), over stops within **400 m in a straight line**:
  - `nearest_stop` and `nearest_rail` (subway, trolley or regional rail, reported up to 2 km),
  - `stops_400m`, `routes_400m`, `modes_400m`,
  - `weekday_trips_400m`: weekday departures within walking distance, where **each route and direction is counted once, at its busiest stop in range**. Summing over stops would count a route that calls at three nearby stops three times, and taking one stop per route would drop the opposite direction on the other side of the street.
- `census_area` re-runs the enrichment when it finishes, because rebuilding `place` clears those columns.

## Results

| Area | Places | Median nearest stop | Median nearest rail | Median routes within 400 m | Median weekday departures within 400 m | Within 400 m of rail |
|---|---|---|---|---|---|---|
| Rittenhouse | 111 | 52 m | 336 m | 19 | 2,526 | 71 of 111 |
| East Passyunk | 70 | 59 m | 291 m | 7 | 846 | 62 of 70 |
| Roxborough | 14 | 68 m | 1,152 m | 9 | 319 | 0 of 14 |

The pattern matches what the places are: Rittenhouse sits by the 19th St trolley station and a dense bus grid; East Passyunk by the Snyder stop on the Broad Street Line; Roxborough is bus-only, with Manayunk regional rail about 1.15 km off. Every place got a neighborhood (East Passyunk spans three: East Passyunk, Lower Moyamensing and Newbold).

**Validation.** The stop service counts were checked against the raw GTFS files with a separate plain-`csv` implementation (calendar, calendar_dates, trips, stop_times) for four stops, including Walnut St & 20th St (310 weekday stop-times) and Snyder Av & Broad St (89 and 87). All four matched exactly. That checks the counting, not the choices below. The area patterns above are plausibility checks only.

## The API

```bash
.venv/bin/uvicorn streetwalker.api:app --port 8000     # docs at /docs
```

| Endpoint | What it returns |
|---|---|
| `GET /places` | filtered, ranked, paged places (`total`, `items`) |
| `GET /places.geojson` | the same search as a FeatureCollection, for map layers |
| `GET /places/{id}` | one place with its match basis and Jev kind details |
| `GET /meta` | areas, kinds, neighborhoods, transit snapshot date, attribution |
| `GET /health` | status and place count |

Filters on `/places`: `q` (substring on name, licensed name or address, plus trigram similarity on names), `area`, `kind` (repeatable), `neighborhood`, `source` (exactly osm, licence or both), `min_confidence`, `lat`/`lng`/`radius_m`, `max_stop_m`, `max_rail_m`, `min_trips`, `route` (repeatable), `sort` (relevance, name, distance, transit), `limit` (at most 200), `offset`.

Design points:

- **One builder, bound parameters.** `search.build` turns the filters into one SQL string and a parameter dict. User text never reaches the SQL text, and sort keys come from a fixed map. A test passes a SQL-injection string through every text filter.
- **Invalid combinations are 422s, not 500s:** `sort=distance` without a point, `radius_m` without a point, an unknown area or sort, a limit over 200.
- **No Yelp fields.** The API reads `place`, `area`, `transit_stop` and `neighborhood` only, and a test asserts no field name contains yelp, rating or review. Yelp-derived fields come only after decision 0001 is resolved, and then behind a flag so the public surface can stay Yelp-free.
- Every response carries the attribution lines (OSM, City of Philadelphia, SEPTA, neighborhoods).

## Caveats

- **One weekday snapshot.** Evenings, weekends and service changes are not captured, and the rail feed is valid only to 2026-10-17, so the snapshot ages quickly. Re-run `python -m streetwalker.ingest septa` and `python -m streetwalker.enrich` after bumping the release tag.
- **Straight-line, not walking distance.** 400 m as the crow flies overstates access across barriers (rail cuts, highways). A street-graph distance is possible, since the walk network is already loaded, but I haven't judged it worth it for a filter.
- **"Rail" means subway, trolley and regional rail together.** A trolley stop is not rapid transit, so use `modes_400m` when the distinction matters.
- **Neighborhood is weak as a filter here:** Rittenhouse and Roxborough each fall in a single neighborhood, so it only separates places within East Passyunk. It will matter when the survey areas grow.
- **The census counts licences, not businesses.** Eleven addresses hold more than one place. Most are different tenants of a multi-unit building (1709-17 Chestnut St). At least one is one business with two licences (AKA RS Liquor at 135 S 18th St, listed twice). That puts the census at 195 with perhaps 1 to 3 duplicates, under 2%. Not fixed here; fixing it means a same-legal-name rule that I'd want to check by hand.
- **Name search is lexical.** Substring plus trigram similarity finds "melograno" and typos, but not "cheap sushi". That is the job of the hybrid search and chat layer later.
- **Local dev service.** Unauthenticated, read-only, one database connection per request, CORS limited to the local Vite port. Deploying it publicly needs rate limits and a pooled connection. OSM-derived data falls under ODbL share-alike when publicly used, so check what that requires of the database before any public deployment.

## Next

The API is the surface the Yelp layer will attach to (`place` is the unit that gets matched). A map UI over `/places.geojson` is a small step on top of the existing viewer.
