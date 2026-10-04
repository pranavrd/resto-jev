"""Place search: turn filters into one parameterised SQL query (decision 0017). Pure, so it is testable without a database.

Every user-supplied value goes in as a bound parameter, never into the SQL text. Sort keys come from a fixed map.
Only the `place` table and its joins to `area` are used; no Yelp data is involved.
"""

from dataclasses import dataclass, field

CONFIDENCE_ORDER = ("low", "medium", "high")
SORTS = {
    "relevance": "score DESC NULLS LAST, p.name",
    "name": "lower(p.name) NULLS LAST, p.id",
    "distance": "distance_m NULLS LAST, p.id",
    "transit": "p.weekday_trips_400m DESC NULLS LAST, p.id",
}
SOURCE_FILTERS = {"both": ["osm", "licence"], "osm": ["osm"], "licence": ["licence"]}


class BadQuery(ValueError):
    pass


@dataclass
class PlaceQuery:
    q: str | None = None
    area: str | None = None
    kinds: list[str] = field(default_factory=list)
    neighborhood: str | None = None
    source: str | None = None  # osm | licence | both: which sources list the place
    min_confidence: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_m: float | None = None
    max_stop_m: float | None = None
    max_rail_m: float | None = None
    min_trips: int | None = None
    routes: list[str] = field(default_factory=list)
    sort: str | None = None
    limit: int = 50
    offset: int = 0
    place_id: int | None = None  # one place, for the detail endpoint


SELECT = """
    SELECT p.id, p.name, p.kind, p.kind_source, a.slug AS area, p.neighborhood, p.address, p.sources, p.confidence,
           p.building_id, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lng,
           p.nearest_stop_name, p.nearest_stop_m, p.nearest_rail_name, p.nearest_rail_m, p.stops_400m, p.routes_400m,
           p.modes_400m, p.weekday_trips_400m, p.licence_name, p.licence_type, p.match_basis, p.match_score, p.kind_jev,
           p.kind_jev_conf,
           {distance} AS distance_m, {score} AS score, count(*) OVER () AS total
    FROM place p JOIN area a ON a.id = p.area_id
"""


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def build(q: PlaceQuery) -> tuple[str, dict]:
    """Return (sql, params). Raises BadQuery for combinations that cannot be answered."""
    if (q.lat is None) != (q.lng is None):
        raise BadQuery("lat and lng go together")
    if q.radius_m is not None and q.lat is None:
        raise BadQuery("radius_m needs lat and lng")
    sort = q.sort or ("relevance" if q.q else "name")
    if sort not in SORTS:
        raise BadQuery(f"sort must be one of {', '.join(SORTS)}")
    if sort == "distance" and q.lat is None:
        raise BadQuery("sort=distance needs lat and lng")
    if sort == "relevance" and not q.q:
        raise BadQuery("sort=relevance needs q")
    if q.min_confidence is not None and q.min_confidence not in CONFIDENCE_ORDER:
        raise BadQuery(f"min_confidence must be one of {', '.join(CONFIDENCE_ORDER)}")
    if q.source is not None and q.source not in SOURCE_FILTERS:
        raise BadQuery(f"source must be one of {', '.join(SOURCE_FILTERS)}")

    params: dict = {"limit": q.limit, "offset": q.offset}
    where: list[str] = []
    if q.q:
        params.update(q=q.q.strip().lower(), like=_like(q.q.strip()))
        where.append(
            "(lower(coalesce(p.name, '')) LIKE lower(%(like)s) OR lower(coalesce(p.licence_name, '')) LIKE lower(%(like)s) "
            "OR lower(coalesce(p.address, '')) LIKE lower(%(like)s) "
            "OR similarity(lower(coalesce(p.name, '')), %(q)s) >= 0.3)"
        )
        score = (
            "greatest(similarity(lower(coalesce(p.name, '')), %(q)s), similarity(lower(coalesce(p.licence_name, '')), %(q)s), "
            "CASE WHEN lower(coalesce(p.name, '')) LIKE lower(%(like)s) THEN 0.6 ELSE 0 END)"
        )
    else:
        score = "NULL::float"
    if q.place_id is not None:
        where.append("p.id = %(place_id)s")
        params["place_id"] = q.place_id
    if q.area:
        where.append("a.slug = %(area)s")
        params["area"] = q.area
    if q.kinds:
        where.append("p.kind = ANY(%(kinds)s)")
        params["kinds"] = q.kinds
    if q.neighborhood:
        where.append("lower(p.neighborhood) = lower(%(hood)s)")
        params["hood"] = q.neighborhood
    if q.source:
        where.append("p.sources @> %(sources)s::text[] AND cardinality(p.sources) = %(n_sources)s")
        params.update(sources=SOURCE_FILTERS[q.source], n_sources=len(SOURCE_FILTERS[q.source]))
    if q.min_confidence:
        where.append("p.confidence = ANY(%(confs)s)")
        params["confs"] = list(CONFIDENCE_ORDER[CONFIDENCE_ORDER.index(q.min_confidence):])
    if q.max_stop_m is not None:
        where.append("p.nearest_stop_m <= %(max_stop_m)s")
        params["max_stop_m"] = q.max_stop_m
    if q.max_rail_m is not None:
        where.append("p.nearest_rail_m <= %(max_rail_m)s")
        params["max_rail_m"] = q.max_rail_m
    if q.min_trips is not None:
        where.append("p.weekday_trips_400m >= %(min_trips)s")
        params["min_trips"] = q.min_trips
    if q.routes:
        where.append("p.routes_400m && %(routes)s::text[]")  # any of the listed routes
        params["routes"] = q.routes

    if q.lat is not None:
        params.update(lat=q.lat, lng=q.lng)
        distance = "ST_Distance(p.geom::geography, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography)"
        if q.radius_m is not None:
            where.append(f"{distance} <= %(radius_m)s")
            params["radius_m"] = q.radius_m
    else:
        distance = "NULL::float"

    sql = SELECT.format(distance=distance, score=score)
    if where:
        sql += "    WHERE " + "\n      AND ".join(where) + "\n"
    sql += f"    ORDER BY {SORTS[sort]}\n    LIMIT %(limit)s OFFSET %(offset)s"
    return sql, params
