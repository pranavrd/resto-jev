"""Place search API (decision 0017).   Run: .venv/bin/uvicorn streetwalker.api:app --reload --port 8000

Serves the restaurant census (`place`) with neighborhood and SEPTA context. It reads only non-Yelp tables. Ratings,
reviews and anything else derived from Yelp are deliberately absent until decision 0001 is resolved.
"""

import os
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from streetwalker.deps import Conn
from streetwalker.search import BadQuery, PlaceQuery, build

ATTRIBUTION = [
    "Map data © OpenStreetMap contributors (ODbL)",
    "City of Philadelphia business licenses and land use (OpenDataPhilly)",
    "Transit data: SEPTA GTFS",
    "Neighborhood boundaries: OpenDataPhilly, CC BY 4.0, Robert Cheetham / Azavea",
]
TRANSIT_KEYS = ("nearest_stop_name", "nearest_stop_m", "nearest_rail_name", "nearest_rail_m", "stops_400m", "routes_400m", "modes_400m", "weekday_trips_400m")

app = FastAPI(title="StreetWalker places", version="0.1.0", description="Restaurant census of three Philadelphia areas with transit context.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET"])


if os.environ.get("STREETWALKER_REVIEW") == "1":  # the review page writes labels, so it is opt-in
    from streetwalker.label_api import router as label_router
    from streetwalker.review_api import router as review_router

    app.include_router(review_router)
    app.include_router(label_router)


def to_place(row: dict) -> dict:
    return {
        "id": row["id"], "name": row["name"], "kind": row["kind"], "kind_source": row["kind_source"], "area": row["area"],
        "neighborhood": row["neighborhood"], "address": row["address"], "sources": row["sources"], "confidence": row["confidence"],
        "building_id": row["building_id"], "lat": row["lat"], "lng": row["lng"],
        "distance_m": None if row.get("distance_m") is None else round(row["distance_m"], 1),
        "score": None if row.get("score") is None else round(row["score"], 3),
        "transit": {k: row[k] for k in TRANSIT_KEYS},
    }


def _query(
    q: str | None, area: str | None, kind: list[str], neighborhood: str | None, source: str | None, min_confidence: str | None,
    lat: float | None, lng: float | None, radius_m: float | None, max_stop_m: float | None, max_rail_m: float | None,
    min_trips: int | None, route: list[str], sort: str | None, limit: int, offset: int,
) -> PlaceQuery:
    return PlaceQuery(q, area, kind, neighborhood, source, min_confidence, lat, lng, radius_m, max_stop_m, max_rail_m, min_trips, route, sort, limit, offset)


def run(conn: psycopg.Connection, pq: PlaceQuery) -> tuple[list[dict], int]:
    try:
        sql, params = build(pq)
    except BadQuery as e:
        raise HTTPException(422, str(e)) from e
    rows = conn.execute(sql, params).fetchall()
    return [to_place(r) for r in rows], (rows[0]["total"] if rows else 0)


# Filters shared by /places and /places.geojson. Declared once so the two endpoints cannot drift apart.
def filters(
    q: Annotated[str | None, Query(max_length=100, description="Name, licensed name or address contains this; fuzzy on names")] = None,
    area: Annotated[Literal["rittenhouse", "east_passyunk", "roxborough"] | None, Query()] = None,
    kind: Annotated[list[str], Query(description="Repeat for several: restaurant, bar, cafe, ...")] = [],  # noqa: B006
    neighborhood: Annotated[str | None, Query(max_length=80)] = None,
    source: Annotated[Literal["osm", "licence", "both"] | None, Query(description="Exactly which sources list the place")] = None,
    min_confidence: Annotated[Literal["low", "medium", "high"] | None, Query()] = None,
    lat: Annotated[float | None, Query(ge=39.8, le=40.2)] = None,
    lng: Annotated[float | None, Query(ge=-75.4, le=-74.9)] = None,
    radius_m: Annotated[float | None, Query(gt=0, le=5000)] = None,
    max_stop_m: Annotated[float | None, Query(gt=0, le=2000, description="Nearest SEPTA stop within this many metres")] = None,
    max_rail_m: Annotated[float | None, Query(gt=0, le=2000, description="Nearest subway, trolley or regional rail stop within this distance")] = None,
    min_trips: Annotated[int | None, Query(ge=0, description="Weekday departures within 400 m, each route and direction counted once")] = None,
    route: Annotated[list[str], Query(description="Any of these SEPTA routes within 400 m")] = [],  # noqa: B006
    sort: Annotated[Literal["relevance", "name", "distance", "transit"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlaceQuery:
    return _query(q, area, kind, neighborhood, source, min_confidence, lat, lng, radius_m, max_stop_m, max_rail_m, min_trips, route, sort, limit, offset)


Filters = Annotated[PlaceQuery, Depends(filters)]


@app.get("/health")
def health(conn: Conn) -> dict:
    return {"status": "ok", "places": conn.execute("SELECT count(*) AS n FROM place").fetchone()["n"]}


@app.get("/meta")
def meta(conn: Conn) -> dict:
    one = lambda sql: conn.execute(sql).fetchall()
    return {
        "areas": one("SELECT a.slug, a.name, a.profile, count(p.id) AS places FROM area a LEFT JOIN place p ON p.area_id = a.id GROUP BY a.id ORDER BY a.id"),
        "kinds": one("SELECT kind, count(*) AS places FROM place GROUP BY kind ORDER BY count(*) DESC"),
        "neighborhoods": one("SELECT neighborhood AS name, count(*) AS places FROM place WHERE neighborhood IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"),
        "transit": one("SELECT max(service_date) AS service_date, max(feed_version) AS feed_version, count(*) AS stops FROM transit_stop")[0],
        "attribution": ATTRIBUTION,
    }


@app.get("/transit/stops")
def transit_stops(
    conn: Conn,
    area: Annotated[Literal["rittenhouse", "east_passyunk", "roxborough"] | None, Query()] = None,
    margin_m: Annotated[float, Query(ge=0, le=2000, description="With area: include stops this far outside it")] = 600,
) -> dict:
    """SEPTA stops as GeoJSON, with the routes calling there and weekday stop-times."""
    sql = "SELECT s.feed, s.stop_id, s.name, ST_X(s.geom) AS lng, ST_Y(s.geom) AS lat, s.modes, s.weekday_trips, s.service FROM transit_stop s"
    params: dict = {}
    if area:
        sql += " JOIN area a ON a.slug = %(area)s AND ST_DWithin(s.geom::geography, a.geom::geography, %(m)s)"
        params = {"area": area, "m": margin_m}
    features = [
        {"type": "Feature", "id": f"{r['feed']}:{r['stop_id']}", "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
         "properties": {"name": r["name"], "modes": r["modes"], "weekday_trips": r["weekday_trips"],
                        "routes": sorted({k.rsplit("|", 1)[0] for k in r["service"]})}}
        for r in conn.execute(sql + " ORDER BY s.feed, s.stop_id", params).fetchall()
    ]
    return {"type": "FeatureCollection", "features": features, "attribution": ATTRIBUTION}


@app.get("/places")
def places(conn: Conn, pq: Filters) -> dict:
    items, total = run(conn, pq)
    return {"total": total, "limit": pq.limit, "offset": pq.offset, "items": items, "attribution": ATTRIBUTION}


@app.get("/places.geojson")
def places_geojson(conn: Conn, pq: Filters) -> dict:
    """The same search as /places as a GeoJSON FeatureCollection, for map layers."""
    items, total = run(conn, pq)
    features = [
        {"type": "Feature", "id": p["id"], "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
         "properties": {k: v for k, v in p.items() if k not in ("lat", "lng")}}
        for p in items
    ]
    return {"type": "FeatureCollection", "features": features, "total": total, "attribution": ATTRIBUTION}


@app.get("/places/{place_id}")
def place(place_id: int, conn: Conn) -> dict:
    sql, params = build(PlaceQuery(place_id=place_id))
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise HTTPException(404, "no such place")
    detail = {k: row[k] for k in ("licence_name", "licence_type", "match_basis", "match_score", "kind_jev", "kind_jev_conf")}
    return {**to_place(row), **detail, "attribution": ATTRIBUTION}
