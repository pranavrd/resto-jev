"""Export per-area replay data for the web viewer.  Usage: python -m streetwalker.export_replay

Writes web/public/data/<slug>.json and index.json (gitignored: generated from the database).
Contains OSM and City of Philadelphia derived data only, no Yelp data.
"""

import json
import math
from itertools import pairwise

import psycopg

from streetwalker import db
from streetwalker.walk import is_street

OUT = db.ROOT / "web" / "public" / "data"
WALK_SPEED_MS = 1.4
SIMPLIFY_DEG = 0.000003  # ~0.3 m


def _lu_label(c1: int | None, c2: int | None) -> str:
    if c2 == 23:
        return "mixed"
    if c2 in (21, 22):
        return "commercial"
    return {1: "residential", 3: "industrial", 4: "civic", 9: "vacant"}.get(c1, "other")


def _vertex_times(path: list[list[float]], t0: float, t1: float) -> list[float]:
    """Timestamps for each vertex, proportional to distance along the path."""
    lat = math.radians(path[0][1])
    seg = [math.hypot((b[0] - a[0]) * math.cos(lat), b[1] - a[1]) for a, b in pairwise(path)]
    total = sum(seg) or 1.0
    out, acc = [t0], 0.0
    for s in seg:
        acc += s
        out.append(round(t0 + (t1 - t0) * acc / total, 1))
    return out


def _signal(payload: dict) -> int:
    """0 = no OSM use signal, 1 = use tag or name, 2 = linked business POI."""
    if payload["pois"]:
        return 2
    osm = payload["osm"]
    return 1 if "use_tags" in osm or "name" in osm else 0


def _kinds(payload: dict) -> str:
    bits = [p["tags"].get("amenity") or p["tags"].get("shop") or p["tags"].get("office") or "poi"
            for p in payload["pois"]]
    bits += [str(v) for k, v in payload["osm"].get("use_tags", {}).items() if k in ("amenity", "shop", "office")]
    return ", ".join(dict.fromkeys(bits))


def export_area(conn: psycopg.Connection, area_id: int, slug: str, name: str, profile: str) -> dict:
    xmin, ymin, xmax, ymax = conn.execute(
        "SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM area WHERE id = %s", (area_id,)
    ).fetchone()

    streets = [
        json.loads(g)["coordinates"]
        for g, hw in conn.execute(
            "SELECT ST_AsGeoJSON(geom, 6), highway FROM osm_street WHERE area_id = %s", (area_id,)
        )
        if is_street(hw)
    ]

    steps, cum = [], 0.0
    for seq, length_m, rep, jump, g in conn.execute(
        "SELECT s.seq, s.length_m, s.is_repeat, s.is_jump, ST_AsGeoJSON(s.geom, 6) FROM walk_step s "
        "JOIN walk_run r ON r.id = s.run_id WHERE r.area_id = %s ORDER BY s.seq", (area_id,)
    ):
        path = json.loads(g)["coordinates"]
        t0, t1 = cum / WALK_SPEED_MS, (cum + length_m) / WALK_SPEED_MS  # same clock as walk_event.sim_seconds
        steps.append({"t0": round(t0, 1), "t1": round(t1, 1), "r": int(rep), "j": int(jump),
                      "p": path, "t": _vertex_times(path, t0, t1)})
        cum += length_m

    buildings, polys = [], []
    rows = conn.execute(
        "SELECT b.id, e.event_seq, e.sim_seconds, ev.payload, ev.text, lu.c_dig1, lu.c_dig2, "
        "ST_AsGeoJSON(ST_SimplifyPreserveTopology(b.geom, %s), 6) "
        "FROM building b JOIN walk_event e ON e.building_id = b.id "
        "JOIN evidence ev ON ev.building_id = b.id AND ev.tier = 0 "
        "LEFT JOIN building_land_use lu ON lu.osm_type = b.osm_type AND lu.osm_id = b.osm_id AND lu.area_id = b.area_id "
        "WHERE b.area_id = %s ORDER BY e.event_seq", (SIMPLIFY_DEG, area_id),
    ).fetchall()
    for _bid, seq, t, payload, text, c1, c2, geojson in rows:
        osm, street = payload["osm"], payload["street"]
        addr = " ".join(x for x in (osm.get("housenumber"), street.get("name")) if x) or "unnamed street"
        idx = len(buildings)
        buildings.append({"seq": seq, "t": round(t, 1), "addr": addr, "sig": _signal(payload),
                          "kinds": _kinds(payload), "lu": _lu_label(c1, c2), "text": text})
        geom = json.loads(geojson)
        for rings in [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]:
            polys.append({"b": idx, "g": rings})

    duration = steps[-1]["t1"] if steps else 0
    data = {
        "slug": slug, "name": name, "profile": profile, "bounds": [xmin, ymin, xmax, ymax],
        "duration_s": duration, "speed_ms": WALK_SPEED_MS, "streets": streets, "steps": steps,
        "buildings": buildings, "polys": polys,
        "attribution": "© OpenStreetMap contributors · City of Philadelphia",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{slug}.json").write_text(json.dumps(data, separators=(",", ":")))
    return {"slug": slug, "name": name, "profile": profile, "buildings": len(buildings),
            "duration_s": duration, "bytes": (OUT / f"{slug}.json").stat().st_size}


def main() -> None:
    index = []
    with db.connect() as conn:
        for area_id, slug, name, profile in conn.execute("SELECT id, slug, name, profile FROM area ORDER BY id").fetchall():
            s = export_area(conn, area_id, slug, name, profile)
            index.append(s)
            print(f"{slug:14s} buildings={s['buildings']:5d} duration={s['duration_s'] / 60:6.0f} min  {s['bytes'] / 1e6:.2f} MB")
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))


if __name__ == "__main__":
    main()
