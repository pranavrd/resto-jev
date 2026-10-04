"""Tier 3: the human review queue (decision 0018). Seeding, the page's data, label rules and the agreement report.

  seed    .venv/bin/python -m streetwalker.review seed [--n 50] [--gate-limit 200]
  report  .venv/bin/python -m streetwalker.review report

The `verify` set is random buildings that have a street photo, per area; labelled blind, it measures how well the
parcel ground truth agrees with what a person sees. The `gate` set is the buildings the cascade escalates, most
uncertain first. The web page (#/review, served by review_api.py) never shows ground truth or a prediction.
"""

import argparse
import random
import statistics
from collections import Counter, defaultdict

from psycopg.rows import tuple_row

from streetwalker import db
from streetwalker.cascade import COMM, load_rows
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.images_cache import fetch
from streetwalker.metrics import accuracy, cohens_kappa

CANT_TELL = "cant_tell"
LABELS = (*D1_CLASSES, CANT_TELL)
SETS = ("verify", "gate")
NEIGHBOUR_RADIUS_M = 60.0
SEED = 20261004


def sample_verify(candidates: list[tuple[int, str]], per_area: int, seed: int = SEED) -> list[int]:
    """Up to `per_area` random buildings per area, ordered round-robin so any prefix is balanced across areas."""
    by_area: dict[str, list[int]] = defaultdict(list)
    for bid, area in sorted(candidates):
        by_area[area].append(bid)
    rng = random.Random(seed)
    picked = {}
    for area in sorted(by_area):
        ids = by_area[area]
        rng.shuffle(ids)
        picked[area] = ids[:per_area]
    order = []
    for i in range(per_area):
        for area in sorted(picked):
            if i < len(picked[area]):
                order.append(picked[area][i])
    return order


def valid_label(label: str) -> bool:
    return label in LABELS


def latest_labels(conn, set_name: str | None = None) -> dict[int, tuple[str, float | None, bool]]:
    """The current label per building: the newest one that was not undone."""
    sql = "SELECT DISTINCT ON (building_id) building_id, label, seconds, evidence_shown FROM human_label WHERE NOT undone"
    args: list = []
    if set_name:
        sql += " AND set_name = %s"
        args.append(set_name)
    cur = conn.cursor(row_factory=tuple_row)  # callers pass plain or dict-row connections
    return {r[0]: (r[1], r[2], r[3]) for r in cur.execute(sql + " ORDER BY building_id, id DESC", args).fetchall()}


def seed(conn, per_area: int, gate_limit: int, tau: float) -> None:
    cands = conn.execute(
        "SELECT ip.building_id, a.slug FROM image_pick ip JOIN building b ON b.id = ip.building_id JOIN area a ON a.id = b.area_id "
        "JOIN ground_truth g ON g.building_id = b.id"
    ).fetchall()
    verify = sample_verify([(b, a) for b, a in cands], per_area)
    rows = load_rows(conn, ("train", "dev", "test"))
    gate = [r.building_id for r in sorted((r for r in rows if r.conf < tau), key=lambda r: (r.conf, r.building_id))][:gate_limit]
    for name, ids in (("verify", verify), ("gate", gate)):
        conn.execute("DELETE FROM review_item WHERE set_name = %s", (name,))
        for rank, bid in enumerate(ids, 1):
            conn.execute("INSERT INTO review_item (set_name, building_id, rank) VALUES (%s, %s, %s)", (name, bid, rank))
    conn.commit()
    need = conn.execute(
        "SELECT DISTINCT ip.image_id FROM review_item ri JOIN image_pick ip ON ip.building_id = ri.building_id"
    ).fetchall()
    print(f"queue: verify {len(verify)}, gate {len(gate)}; fetching {len(need)} images into the local cache", flush=True)
    for (image_id,) in need:
        fetch(image_id, 1024)  # cached files are skipped
    print("done")


def building_view(conn, building_id: int) -> dict:
    """What the page draws: target footprint, neighbours and streets in metres around the target, the camera positions."""
    row = conn.cursor(row_factory=tuple_row).execute(
        """
        WITH t AS (SELECT b.id, b.area_id, ST_Transform(ob.geom, 32618) AS g FROM building b
                   JOIN osm_building ob ON ob.area_id = b.area_id AND ob.osm_type = b.osm_type AND ob.osm_id = b.osm_id WHERE b.id = %(b)s),
             c AS (SELECT ST_X(ST_Centroid(g)) AS cx, ST_Y(ST_Centroid(g)) AS cy FROM t)
        SELECT (SELECT text FROM evidence WHERE building_id = %(b)s AND tier = 0),
               ST_AsGeoJSON(ST_Translate(t.g, -c.cx, -c.cy), 1)::json,
               (SELECT coalesce(json_agg(ST_AsGeoJSON(ST_Translate(ST_Transform(n.geom, 32618), -c.cx, -c.cy), 1)::json), '[]')
                  FROM osm_building n WHERE n.area_id = t.area_id AND ST_DWithin(ST_Transform(n.geom, 32618), t.g, %(r)s)
                   AND NOT (n.osm_type, n.osm_id) = (SELECT osm_type, osm_id FROM building WHERE id = %(b)s)),
               (SELECT coalesce(json_agg(ST_AsGeoJSON(ST_Translate(ST_CollectionExtract(ST_Intersection(ST_Transform(s.geom, 32618), ST_Buffer(t.g, %(r)s)), 2), -c.cx, -c.cy), 1)::json), '[]')
                  FROM osm_street s WHERE s.area_id = t.area_id AND ST_DWithin(ST_Transform(s.geom, 32618), t.g, %(r)s)),
               (SELECT coalesce(json_agg(json_build_object('x', ST_X(p) - c.cx, 'y', ST_Y(p) - c.cy, 'year', ip.year, 'dist_m', ip.dist_m, 'kind', 'photo')), '[]')
                  FROM image_pick ip JOIN mapillary_image mi ON mi.id = ip.image_id
                  CROSS JOIN LATERAL (SELECT ST_Transform(mi.geom, 32618) AS p) q WHERE ip.building_id = %(b)s)
        FROM t, c
        """,
        {"b": building_id, "r": NEIGHBOUR_RADIUS_M},
    ).fetchone()
    return {"text": row[0], "target": row[1], "neighbours": row[2], "streets": row[3], "cameras": row[4]}


def report(conn) -> None:
    labels = latest_labels(conn)
    if not labels:
        print("no human labels yet")
        return
    rows = conn.execute(
        """
        SELECT g.building_id, a.slug, g.d1_class, g.label_status, g.d3_food, s.d1_class, s.confidence
        FROM ground_truth g JOIN building b ON b.id = g.building_id JOIN area a ON a.id = b.area_id
        JOIN baseline_prediction s ON s.building_id = g.building_id AND s.baseline = 'stack-gbm'
        WHERE g.building_id = ANY(%s)
        """,
        (list(labels),),
    ).fetchall()
    secs = [labels[r[0]][1] for r in rows if labels[r[0]][1] is not None]
    n_cant = sum(labels[r[0]][0] == CANT_TELL for r in rows)
    scored = [r for r in rows if labels[r[0]][0] != CANT_TELL]
    human = [labels[r[0]][0] for r in scored]
    truth = [r[2] for r in scored]
    tier0 = [r[5] for r in scored]
    print(f"{len(rows)} labelled buildings; {n_cant} marked can't tell ({n_cant / len(rows):.0%}); {len(scored)} scored")
    if secs:
        print(f"seconds per label: median {statistics.median(secs):.1f}, mean {statistics.fmean(secs):.1f}, "
              f"90th percentile {sorted(secs)[int(0.9 * (len(secs) - 1))]:.1f}")
    print(f"evidence text opened on {sum(labels[r[0]][2] for r in rows) / len(rows):.0%} of labels")
    print(f"\nhuman vs parcel ground truth (7 classes): agreement {accuracy(truth, human):.3f}, Cohen's kappa {cohens_kappa(truth, human):.3f}")
    hc, tc = [h in COMM for h in human], [t in COMM for t in truth]
    print(f"commercial-any (commercial or mixed-use): agreement {sum(a == b for a, b in zip(hc, tc, strict=True)) / len(hc):.3f}")
    print(f"same buildings, Tier 0 (stack-gbm) vs ground truth: {accuracy(truth, tier0):.3f}; vs the human: {accuracy(human, tier0):.3f}")
    print("\nagreement by ground-truth label status (how sure the crosswalk was)")
    by_status = defaultdict(list)
    for r, h in zip(scored, human, strict=True):
        by_status[r[3]].append(h == r[2])
    for k, v in sorted(by_status.items()):
        print(f"  {k:16s} n={len(v):4d}  agreement {sum(v) / len(v):.2f}")
    print("\nby area")
    by_area = defaultdict(list)
    for r, h in zip(scored, human, strict=True):
        by_area[r[1]].append(h == r[2])
    for k, v in sorted(by_area.items()):
        print(f"  {k:14s} n={len(v):4d}  agreement {sum(v) / len(v):.2f}")
    print("\nwhere they differ (truth -> human)")
    for (t, h), c in Counter((r[2], x) for r, x in zip(scored, human, strict=True) if r[2] != x).most_common(10):
        print(f"  {t:20s} -> {h:20s} {c:3d}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--n", type=int, default=50, help="verify buildings per area")
    s.add_argument("--gate-limit", type=int, default=200)
    s.add_argument("--tau", type=float, default=0.77)
    sub.add_parser("report")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        if args.cmd == "seed":
            seed(conn, args.n, args.gate_limit, args.tau)
        else:
            report(conn)


if __name__ == "__main__":
    main()
