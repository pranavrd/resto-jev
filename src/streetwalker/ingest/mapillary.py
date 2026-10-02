"""Mapillary image metadata ingest (IDs, capture time, heading, position). Images are not downloaded."""

import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime

import psycopg
from dotenv import load_dotenv

from streetwalker.areas import Area
from streetwalker.db import ROOT

GRAPH = "https://graph.mapillary.com/images"
LIMIT = 2000  # API cap per request; a full page may be truncated, so split the box and retry


def _token() -> str:
    load_dotenv(ROOT / ".env")
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        raise SystemExit("MAPILLARY_TOKEN is not set in .env")
    return token


def _fetch(bbox: tuple[float, float, float, float], token: str) -> list[dict]:
    x1, y1, x2, y2 = bbox
    params = {
        "fields": "id,captured_at,compass_angle,is_pano,geometry",
        "bbox": f"{x1},{y1},{x2},{y2}",
        "limit": LIMIT,
    }
    req = urllib.request.Request(
        f"{GRAPH}?{urllib.parse.urlencode(params)}", headers={"Authorization": f"OAuth {token}"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)["data"]
    if len(data) < LIMIT:
        return data
    xm, ym = (x1 + x2) / 2, (y1 + y2) / 2
    seen: dict[str, dict] = {}
    for q in [(x1, y1, xm, ym), (xm, y1, x2, ym), (x1, ym, xm, y2), (xm, ym, x2, y2)]:
        for img in _fetch(q, token):
            seen[img["id"]] = img
    return list(seen.values())


def ingest_images(conn: psycopg.Connection, area: Area, area_id: int) -> int:
    images = _fetch(area.bbox, _token())
    conn.execute("DELETE FROM mapillary_image WHERE area_id = %s", (area_id,))
    rows = [
        (
            i["id"], area_id,
            datetime.fromtimestamp(i["captured_at"] / 1000, UTC) if i.get("captured_at") else None,
            i.get("compass_angle"), i.get("is_pano"),
            i["geometry"]["coordinates"][0], i["geometry"]["coordinates"][1],
        )
        for i in images
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO mapillary_image (id, area_id, captured_at, compass_angle, is_pano, geom) "
            "VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) ON CONFLICT (id) DO NOTHING",
            rows,
        )
    return len(rows)
