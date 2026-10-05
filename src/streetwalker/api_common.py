"""Pieces shared by the place API (api.py) and the TableMap router (tablemap_api.py)."""

from typing import Annotated, Literal

from fastapi import Depends, Query

from streetwalker.search import PlaceQuery

ATTRIBUTION = [
    "Map data © OpenStreetMap contributors (ODbL)",
    "City of Philadelphia business licenses and land use (OpenDataPhilly)",
    "Transit data: SEPTA GTFS",
    "Neighborhood boundaries: OpenDataPhilly, CC BY 4.0, Robert Cheetham / Azavea",
]
TRANSIT_KEYS = ("nearest_stop_name", "nearest_stop_m", "nearest_rail_name", "nearest_rail_m", "stops_400m", "routes_400m", "modes_400m", "weekday_trips_400m")


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
