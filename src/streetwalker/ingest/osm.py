"""OSM ingest: buildings, POIs and the walkable street graph for each area (via OSMnx / Overpass)."""

import json

import osmnx as ox
import pandas as pd
import psycopg

from streetwalker.areas import Area
from streetwalker.db import ROOT

ox.settings.use_cache = True
ox.settings.cache_folder = str(ROOT / "data" / "osm_cache")
ox.settings.log_console = False

POI_TAGS = {"amenity": True, "shop": True, "office": True, "craft": True, "tourism": True, "healthcare": True}
POI_BUFFER_DEG = 0.0003  # ~30 m: pick up POIs mapped just outside the box


def _tags(row: pd.Series) -> str:
    tags = {k: v for k, v in row.drop("geometry").items() if not _is_missing(v)}
    return json.dumps(tags, default=str)


def _is_missing(v: object) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


def _features(poly, tags: dict) -> pd.DataFrame:
    try:
        return ox.features_from_polygon(poly, tags)
    except ox._errors.InsufficientResponseError:
        return pd.DataFrame()


def ingest_buildings(conn: psycopg.Connection, area: Area, area_id: int) -> int:
    gdf = _features(area.polygon, {"building": True})
    conn.execute("DELETE FROM osm_building WHERE area_id = %s", (area_id,))
    rows = []
    for (osm_type, osm_id), row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        if not geom.representative_point().within(area.polygon):  # avoid boundary double counting
            continue
        rows.append((osm_type, int(osm_id), area_id, geom.wkt, _tags(row)))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO osm_building (osm_type, osm_id, area_id, geom, tags) "
            "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326), %s::jsonb) "
            "ON CONFLICT DO NOTHING",
            rows,
        )
    return len(rows)


def ingest_pois(conn: psycopg.Connection, area: Area, area_id: int) -> int:
    gdf = _features(area.polygon.buffer(POI_BUFFER_DEG), POI_TAGS)
    conn.execute("DELETE FROM osm_poi WHERE area_id = %s", (area_id,))
    rows = []
    for (osm_type, osm_id), row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        rows.append((osm_type, int(osm_id), area_id, geom.wkt, _tags(row)))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO osm_poi (osm_type, osm_id, area_id, geom, tags) "
            "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326), %s::jsonb) "
            "ON CONFLICT DO NOTHING",
            rows,
        )
    return len(rows)


def ingest_streets(conn: psycopg.Connection, area: Area, area_id: int) -> int:
    # network_type="all", not "walk": the walk filter silently drops many residential streets
    # (about 200 in Roxborough), which leaves houses with no street to front onto.
    # to_undirected stores one edge per physical segment instead of one per travel direction.
    graph = ox.convert.to_undirected(
        ox.graph_from_polygon(area.polygon, network_type="all", retain_all=True, truncate_by_edge=True)
    )
    nodes, edges = ox.graph_to_gdfs(graph)
    edges = edges.reset_index()
    xy = {int(n): (r.x, r.y) for n, r in nodes.iterrows()}
    conn.execute("DELETE FROM osm_street WHERE area_id = %s", (area_id,))
    conn.execute("DELETE FROM osm_node WHERE area_id = %s", (area_id,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO osm_node (area_id, id, geom) VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
            [(area_id, n, x, y) for n, (x, y) in xy.items()],
        )
    rows = []
    for e in edges.itertuples():
        geom = e.geometry
        ux, uy = xy[int(e.u)]
        if (geom.coords[0][0] - ux) ** 2 + (geom.coords[0][1] - uy) ** 2 > (
            geom.coords[-1][0] - ux
        ) ** 2 + (geom.coords[-1][1] - uy) ** 2:
            geom = geom.reverse()  # store every geometry oriented u -> v
        rows.append(
            (
                area_id, int(e.u), int(e.v), int(e.key),
                json.dumps(e.osmid) if isinstance(e.osmid, list) else str(e.osmid),
                json.dumps(e.highway) if isinstance(e.highway, list) else e.highway,
                json.dumps(e.name) if isinstance(e.name, list) else (None if _is_missing(e.name) else e.name),
                float(e.length),
                geom.wkt,
            )
        )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO osm_street (area_id, u, v, k, osm_way_id, highway, name, length_m, geom) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326)) "
            "ON CONFLICT DO NOTHING",
            rows,
        )
    return len(rows)
