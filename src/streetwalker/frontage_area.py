"""Assign frontages for every building and generate the walk's encounter log.

Usage: python -m streetwalker.frontage_area [--area SLUG]   (run walk_area first)
"""

import argparse
from collections import defaultdict

import psycopg
from pyproj import Transformer
from shapely import wkt
from shapely.ops import transform

from streetwalker import db
from streetwalker.frontage import BuildingInfo, EdgeInfo, assign_all, name_keys
from streetwalker.walk import is_service, is_street

WALK_SPEED_MS = 1.4
TO_UTM = Transformer.from_crs(4326, 32618, always_xy=True).transform
TO_WGS = Transformer.from_crs(32618, 4326, always_xy=True).transform


def _levels(tags: dict) -> int | None:
    try:
        return int(float(tags["building:levels"]))
    except (KeyError, ValueError):
        return None


def load_inputs(conn: psycopg.Connection, area_id: int):
    """Street segments and buildings of an area, in projected metres, in a stable order."""
    edge_rows = [
        r
        for r in conn.execute(
            "SELECT u, v, k, length_m, highway, name, ST_AsText(geom) FROM osm_street WHERE area_id = %s "
            "ORDER BY u, v, k",
            (area_id,),
        ).fetchall()
        if is_street(r[4])
    ]
    edges = [
        EdgeInfo(transform(TO_UTM, wkt.loads(r[6])), name_keys(r[5]), is_service(r[4])) for r in edge_rows
    ]
    brows = conn.execute(
        "SELECT osm_type, osm_id, ST_AsText(geom), tags FROM osm_building WHERE area_id = %s "
        "ORDER BY osm_type, osm_id",
        (area_id,),
    ).fetchall()
    buildings = [BuildingInfo(transform(TO_UTM, wkt.loads(r[2])), r[3].get("addr:street")) for r in brows]
    return edge_rows, edges, brows, buildings


def assign_area(conn: psycopg.Connection, area_id: int) -> dict:
    edge_rows, edges, brows, buildings = load_inputs(conn, area_id)
    fronts = assign_all(buildings, edges)

    conn.execute("DELETE FROM building WHERE area_id = %s", (area_id,))  # cascades to walk_event
    rows = []
    for (osm_type, osm_id, geom_wkt, tags), b, f in zip(brows, buildings, fronts, strict=True):
        u, v, k, length_m = edge_rows[f.edge_idx][:4]
        scaled_along = f.frac * length_m
        pt = transform(TO_WGS, wkt.loads(f"POINT ({f.frontage_xy[0]} {f.frontage_xy[1]})"))
        rows.append(
            (area_id, osm_type, osm_id, geom_wkt, pt.wkt, u, v, k, f.side, f.dist_m, scaled_along, f.method,
             f.n_candidates, f.margin_m, f.nearest_same, b.geom.area, _levels(tags))
        )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO building (area_id, osm_type, osm_id, geom, frontage_pt, edge_u, edge_v, edge_k, side, "
            "dist_m, along_m, assign_method, n_candidates, margin_m, nearest_same, area_m2, levels) "
            "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326), ST_SetSRID(ST_GeomFromText(%s), 4326), "
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    return {"buildings": len(rows)}


def build_events(conn: psycopg.Connection, area_id: int) -> int:
    run = conn.execute("SELECT id FROM walk_run WHERE area_id = %s", (area_id,)).fetchone()
    if run is None:
        raise SystemExit("No walk for this area. Run: python -m streetwalker.walk_area")
    run_id = run[0]
    by_edge = defaultdict(list)
    for bid, u, v, k, side, along in conn.execute(
        "SELECT id, edge_u, edge_v, edge_k, side, along_m FROM building WHERE area_id = %s", (area_id,)
    ):
        by_edge[(u, v, k)].append((bid, side, along))

    conn.execute("DELETE FROM walk_event WHERE run_id = %s", (run_id,))
    events, cum_before, event_seq = [], 0.0, 0
    steps = conn.execute(
        "SELECT seq, u, v, edge_u, edge_v, edge_k, is_repeat, length_m FROM walk_step "
        "WHERE run_id = %s ORDER BY seq",
        (run_id,),
    ).fetchall()
    for seq, u, v, eu, ev, ek, is_repeat, length_m in steps:
        if not is_repeat:  # each segment's first pass is where its buildings are encountered
            forward = (u, v) == (eu, ev)
            encountered = []
            for bid, side, along in by_edge.get((eu, ev, ek), []):
                a = along if forward else length_m - along
                encountered.append((a, bid, side if forward else -side))
            for a, bid, side_walk in sorted(encountered):
                walked = cum_before + a
                events.append((run_id, event_seq, area_id, seq, bid, side_walk, a, walked, walked / WALK_SPEED_MS))
                event_seq += 1
        cum_before += length_m
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO walk_event (run_id, event_seq, area_id, step_seq, building_id, side_walk, along_m, "
            "walked_m, sim_seconds) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            events,
        )
    return len(events)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", help="limit to one area slug")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        for area_id, slug in conn.execute("SELECT id, slug FROM area ORDER BY id").fetchall():
            if args.area and slug != args.area:
                continue
            n = assign_area(conn, area_id)["buildings"]
            ev = build_events(conn, area_id)
            conn.commit()
            print(f"{slug:14s} buildings={n:5d} encounters={ev:5d}")


if __name__ == "__main__":
    main()
