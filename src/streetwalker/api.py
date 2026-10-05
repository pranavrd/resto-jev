"""Place search API (decision 0017).   Run: .venv/bin/uvicorn streetwalker.api:app --reload --port 8000

Serves the restaurant census (`place`) with neighborhood and SEPTA context. The default app reads only non-Yelp tables:
ratings, reviews and anything else derived from Yelp are absent. The TableMap router (decision 0023) adds them, local only,
and is mounted only when STREETWALKER_TABLEMAP=1.
"""

import os
from typing import Annotated, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from streetwalker.api_common import ATTRIBUTION, Filters, to_place
from streetwalker.deps import Conn
from streetwalker.search import BadQuery, PlaceQuery, build

app = FastAPI(title="StreetWalker places", version="0.1.0", description="Restaurant census of three Philadelphia areas with transit context.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET"])


if os.environ.get("STREETWALKER_REVIEW") == "1":  # the review page writes labels, so it is opt-in
    from streetwalker.label_api import router as label_router
    from streetwalker.review_api import router as review_router

    app.include_router(review_router)
    app.include_router(label_router)

if os.environ.get("STREETWALKER_TABLEMAP") == "1":  # Yelp-derived content: opt-in, never in the default app
    from streetwalker.tablemap_api import router as tablemap_router

    app.include_router(tablemap_router)


def run(conn: psycopg.Connection, pq: PlaceQuery) -> tuple[list[dict], int]:
    try:
        sql, params = build(pq)
    except BadQuery as e:
        raise HTTPException(422, str(e)) from e
    rows = conn.execute(sql, params).fetchall()
    return [to_place(r) for r in rows], (rows[0]["total"] if rows else 0)


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
