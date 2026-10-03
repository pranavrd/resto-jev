"""Plan and store the street walk for each area.  Usage: python -m streetwalker.walk_area [--area SLUG]"""

import argparse
import json

import psycopg
from shapely import wkt
from shapely.geometry import LineString

from streetwalker import db
from streetwalker.walk import StreetEdge, WalkPlan, is_street, plan_walk


def load_street_edges(conn: psycopg.Connection, area_id: int) -> tuple[list[StreetEdge], list[LineString], dict]:
    rows = conn.execute(
        "SELECT u, v, k, length_m, highway, ST_AsText(geom) FROM osm_street WHERE area_id = %s "
        "ORDER BY u, v, k",
        (area_id,),
    ).fetchall()
    edges, geoms = [], []
    for u, v, k, length_m, highway, geom_wkt in rows:
        if is_street(highway):
            edges.append(StreetEdge(u, v, k, length_m))
            geoms.append(wkt.loads(geom_wkt))
    nodes = {
        nid: (x, y)
        for nid, x, y in conn.execute(
            "SELECT id, ST_X(geom), ST_Y(geom) FROM osm_node WHERE area_id = %s", (area_id,)
        )
    }
    return edges, geoms, nodes


def save_walk(conn: psycopg.Connection, area_id: int, plan: WalkPlan, edges, geoms) -> int:
    conn.execute("DELETE FROM walk_run WHERE area_id = %s", (area_id,))  # cascades to walk_step
    run_id = conn.execute(
        "INSERT INTO walk_run (area_id, params, n_components, n_street_edges, street_km, walked_km, "
        "repeat_km, overhead_pct, naive_walked_km, n_jumps, jump_km) "
        "VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            area_id,
            json.dumps({"network": "street edges only", "eulerize": "length-weighted matching"}),
            plan.n_components, len(edges), plan.street_m / 1000, plan.walked_m / 1000,
            plan.repeat_m / 1000, plan.overhead_pct, plan.naive_walked_m / 1000, plan.n_jumps,
            plan.jump_m / 1000,
        ),
    ).fetchone()[0]
    rows = []
    for s in plan.steps:
        e, g = edges[s.edge_idx], geoms[s.edge_idx]
        forward = (s.u, s.v) == (e.u, e.v)
        line = g if forward else LineString(list(g.coords)[::-1])
        rows.append(
            (run_id, area_id, s.seq, s.component, s.u, s.v, e.u, e.v, e.k, s.is_repeat, s.is_jump,
             s.length_m, line.wkt)
        )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO walk_step (run_id, area_id, seq, component, u, v, edge_u, edge_v, edge_k, is_repeat, "
            "is_jump, length_m, geom) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "ST_SetSRID(ST_GeomFromText(%s), 4326))",
            rows,
        )
    return run_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", help="limit to one area slug")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        print(f"{'area':14s} {'edges':>6s} {'comps':>5s} {'street km':>10s} {'walked km':>10s} "
              f"{'overhead':>9s} {'naive ovh':>10s} {'jumps':>5s}")
        for area_id, slug in conn.execute("SELECT id, slug FROM area ORDER BY id").fetchall():
            if args.area and slug != args.area:
                continue
            edges, geoms, nodes = load_street_edges(conn, area_id)
            plan = plan_walk(edges, nodes)
            save_walk(conn, area_id, plan, edges, geoms)
            conn.commit()
            naive_pct = 100 * (plan.naive_walked_m - plan.street_m) / plan.street_m
            print(f"{slug:14s} {len(edges):6d} {plan.n_components:5d} {plan.street_m / 1000:10.2f} "
                  f"{plan.walked_m / 1000:10.2f} {plan.overhead_pct:8.1f}% {naive_pct:9.1f}% {plan.n_jumps:5d}")


if __name__ == "__main__":
    main()
