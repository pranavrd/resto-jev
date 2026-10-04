"""Philadelphia neighborhood boundaries (OpenDataPhilly, CC BY 4.0, attribute Robert Cheetham / Azavea)."""

import json
import urllib.request

import psycopg
from shapely.geometry import MultiPolygon, shape

from streetwalker import db

URL = "https://raw.githubusercontent.com/opendataphilly/odp-data-storage/master/philadelphia-neighborhoods/philadelphia-neighborhoods.geojson"
PATH = db.ROOT / "data" / "neighborhoods" / "philadelphia-neighborhoods.geojson"


def ingest_neighborhoods(conn: psycopg.Connection) -> int:
    if not PATH.exists():
        PATH.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=120) as resp:
            PATH.write_bytes(resp.read())
    features = json.loads(PATH.read_text())["features"]
    conn.execute("DELETE FROM neighborhood")
    for f in features:
        geom = shape(f["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        p = f["properties"]
        conn.execute(
            "INSERT INTO neighborhood (name, listname, geom) VALUES (%s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326))",
            (p["NAME"], p["LISTNAME"], geom.wkt),
        )
    return len(features)
