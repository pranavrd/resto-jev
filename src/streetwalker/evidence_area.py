"""Build tier-0 evidence bundles for every building.

Usage: python -m streetwalker.evidence_area [--area SLUG]   (run walk_area and frontage_area first)
Reads only OSM tables, the building/frontage tables and the walk. Never parcels, land use or licences.
"""

import argparse
import json
from collections import defaultdict

import psycopg
from shapely import wkt
from shapely.ops import transform

from streetwalker import db
from streetwalker.evidence import (
    BUILDING_USE_KEYS,
    BUNDLE_VERSION,
    building_osm,
    geometry_features,
    is_business_poi,
    link_pois,
    poi_summary,
    render_text,
    shared_walls,
)
from streetwalker.frontage_area import TO_UTM

NEIGHBOR_REACH = 2  # buildings on each side of this one, same side of the street


def _first_name(raw: str | None) -> str | None:
    if not raw:
        return None
    return json.loads(raw)[0] if raw.startswith("[") else raw


def _highway(raw: str) -> str:
    return "/".join(json.loads(raw)) if raw.startswith("[") else raw


def _poi_kind(tags: dict) -> str:
    return next((f"{k}={tags[k]}" for k in ("amenity", "shop", "office", "craft", "tourism", "healthcare", "leisure")
                 if k in tags), "poi")


def build_area(conn: psycopg.Connection, area_id: int) -> dict:
    brows = conn.execute(
        "SELECT b.id, b.osm_type, b.osm_id, ST_AsText(b.geom), b.edge_u, b.edge_v, b.edge_k, b.side, b.dist_m, "
        "b.along_m, b.assign_method, b.margin_m, ob.tags FROM building b "
        "JOIN osm_building ob ON ob.area_id = b.area_id AND ob.osm_type = b.osm_type AND ob.osm_id = b.osm_id "
        "WHERE b.area_id = %s ORDER BY b.id",
        (area_id,),
    ).fetchall()
    ids = [r[0] for r in brows]
    geoms = [transform(TO_UTM, wkt.loads(r[3])) for r in brows]
    tags = [r[12] for r in brows]

    own = {(r[1], r[2]) for r in brows}  # POIs that are the building itself are covered by its own tags
    prow = [
        r for r in conn.execute(
            "SELECT osm_type, osm_id, ST_AsText(geom), tags FROM osm_poi WHERE area_id = %s ORDER BY osm_type, osm_id",
            (area_id,),
        ).fetchall()
        if (r[0], r[1]) not in own and is_business_poi(r[3])
    ]
    links = link_pois(geoms, [transform(TO_UTM, wkt.loads(r[2])) for r in prow])
    pois_of = defaultdict(list)
    for ln in links:
        t = prow[ln.poi_idx][3]
        pois_of[ln.building_idx].append({"match": ln.match, "dist_m": round(ln.dist_m, 1), "tags": poi_summary(t)})
    for lst in pois_of.values():
        lst.sort(key=lambda p: (p["match"] != "contained", p["dist_m"]))

    conn.execute("DELETE FROM poi_link WHERE area_id = %s", (area_id,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO poi_link (area_id, osm_type, osm_id, building_id, match, dist_m) VALUES (%s,%s,%s,%s,%s,%s)",
            [(area_id, prow[ln.poi_idx][0], prow[ln.poi_idx][1], ids[ln.building_idx], ln.match, ln.dist_m)
             for ln in links],
        )

    walls = shared_walls(geoms)
    streets = {
        (u, v, k): (transform(TO_UTM, wkt.loads(g)), _first_name(name), _highway(hw), length_m)
        for u, v, k, g, name, hw, length_m in conn.execute(
            "SELECT u, v, k, ST_AsText(geom), name, highway, length_m FROM osm_street WHERE area_id = %s", (area_id,)
        )
    }

    events = conn.execute(
        "SELECT e.building_id, e.event_seq, e.step_seq, e.side_walk FROM walk_event e "
        "JOIN walk_run r ON r.id = e.run_id WHERE r.area_id = %s ORDER BY e.event_seq",
        (area_id,),
    ).fetchall()
    index_of = {bid: i for i, bid in enumerate(ids)}
    lanes: dict[tuple[int, int], list[int]] = defaultdict(list)  # (step, side) -> building indices in walk order
    per_step: dict[int, list[int]] = defaultdict(list)
    event_seq_of = {}
    for bid, event_seq, step_seq, side_walk in events:
        i = index_of[bid]
        lanes[(step_seq, side_walk)].append(i)
        per_step[step_seq].append(i)
        event_seq_of[i] = (event_seq, step_seq, side_walk)

    def kinds(i: int) -> list[str]:
        return [_poi_kind(p["tags"]) for p in pois_of.get(i, [])]

    def use_tags(i: int) -> dict:
        return {k: tags[i][k] for k in BUILDING_USE_KEYS if k in tags[i]}

    out_rows = []
    for i, r in enumerate(brows):
        bid, _, _, _, eu, ev, ek, _side, dist_m, along_m, method, margin, _t = r
        line, name, highway, length_m = streets[(eu, ev, ek)]
        geo = geometry_features(geoms[i], line, along_m / length_m * line.length, dist_m)
        n_party, ratio = walls[i]
        geo.update({"n_party_walls": n_party, "shared_wall_ratio": round(ratio, 2)})

        _, step_seq, side_walk = event_seq_of[i]
        lane = lanes[(step_seq, side_walk)]
        pos = lane.index(i)
        neighbors = []
        for rel in range(-NEIGHBOR_REACH, NEIGHBOR_REACH + 1):
            if rel == 0 or not 0 <= pos + rel < len(lane):
                continue
            j = lane[pos + rel]
            neighbors.append({
                "rel": rel, "event_seq": event_seq_of[j][0], "area_m2": round(geoms[j].area, 1),
                "attached": walls[j][0] > 0, "poi_kinds": kinds(j), "use_tags": use_tags(j),
            })
        block = per_step[step_seq]
        context = {
            "neighbors": neighbors,
            "segment": {
                "n_buildings": len(block),
                "n_business_pois": sum(len(pois_of.get(j, [])) for j in block),
                "frac_attached": round(sum(walls[j][0] > 0 for j in block) / len(block), 2),
            },
        }
        payload = {
            "osm": building_osm(tags[i]),
            "pois": pois_of.get(i, []),
            "geometry": geo,
            "street": {"name": name, "highway": highway, "side_walk": side_walk, "assign_method": method,
                       "is_corner": margin is not None and margin < 3},
            "context": context,
        }
        out_rows.append((bid, 0, BUNDLE_VERSION, json.dumps(payload), render_text(payload)))

    conn.execute("DELETE FROM evidence WHERE tier = 0 AND building_id = ANY(%s)", (ids,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO evidence (building_id, tier, version, payload, text) VALUES (%s, %s, %s, %s::jsonb, %s)",
            out_rows,
        )
    return {"buildings": len(out_rows), "pois_linked": len(links), "pois_total": len(prow)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", help="limit to one area slug")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        for area_id, slug in conn.execute("SELECT id, slug FROM area ORDER BY id").fetchall():
            if args.area and slug != args.area:
                continue
            s = build_area(conn, area_id)
            conn.commit()
            print(f"{slug:14s} bundles={s['buildings']:5d} business POIs linked {s['pois_linked']}/{s['pois_total']}")


if __name__ == "__main__":
    main()
