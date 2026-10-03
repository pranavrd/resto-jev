"""Build ground-truth labels for every building.  Usage: python -m streetwalker.groundtruth_area

Run after frontage_area (it needs the `building` table). Reads land use, OPA and licences, which the
evidence builder is forbidden to touch; this module is the only place they meet buildings.
"""

import json
import re

import psycopg

from streetwalker import db
from streetwalker.groundtruth import (
    CROSSWALK_VERSION,
    assign_splits,
    label_status,
    land_use_class,
    opa_class,
)

LICENSE_LINK_M = 15.0  # a licence belongs to the nearest building if one is this close
BIG_STREET_SHARE = 0.1  # streets above this share of an area's weight are split into blocks
BIG_POLYGON_DEG = 0.004  # land-use background polygons (whole neighbourhoods) are not parcels


def _street_group(slug: str, name: str | None, edge: tuple[int, int, int]) -> str:
    if name:
        label = json.loads(name)[0] if name.startswith("[") else name
        return f"{slug}|{re.sub(r'\s+', ' ', label.strip().lower())}"
    return f"{slug}|edge:{edge[0]}-{edge[1]}-{edge[2]}"


def build_area(conn: psycopg.Connection, area_id: int, slug: str) -> int:
    rows = conn.execute(
        """
        SELECT b.id, b.edge_u, b.edge_v, b.edge_k, lu.c_dig1, lu.c_dig2, s.name,
               (SELECT cat FROM (SELECT p.category_code_description AS cat, count(*) AS n FROM opa_parcel p
                                 WHERE ST_Intersects(b.geom, p.geom) AND p.category_code_description IS NOT NULL
                                 GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1) t) AS opa_cat
        FROM building b
        LEFT JOIN building_land_use lu ON lu.osm_type = b.osm_type AND lu.osm_id = b.osm_id AND lu.area_id = b.area_id
        LEFT JOIN osm_street s ON s.area_id = b.area_id AND s.u = b.edge_u AND s.v = b.edge_v AND s.k = b.edge_k
        WHERE b.area_id = %s ORDER BY b.id
        """,
        (area_id,),
    ).fetchall()

    split_ids = {
        r[0]
        for r in conn.execute(
            """
            WITH small_lu AS (SELECT c_dig1, geom FROM land_use
                              WHERE ST_XMax(geom) - ST_XMin(geom) < %(big)s AND ST_YMax(geom) - ST_YMin(geom) < %(big)s),
            parts AS (SELECT b.id, lu.c_dig1, sum(ST_Area(ST_Intersection(lu.geom, b.geom)::geography)) AS a
                      FROM building b JOIN small_lu lu ON ST_Intersects(lu.geom, b.geom)
                      WHERE b.area_id = %(area)s GROUP BY 1, 2),
            tot AS (SELECT id, sum(a) AS t FROM parts GROUP BY 1)
            SELECT p.id FROM parts p JOIN tot USING (id) GROUP BY p.id HAVING count(*) FILTER (WHERE p.a / tot.t >= 0.25) >= 2
            """,
            {"big": BIG_POLYGON_DEG, "area": area_id},
        )
    }

    licences: dict[int, list[int]] = {}
    for bid, kind in conn.execute(
        """
        SELECT nb.id, CASE WHEN l.licensetype LIKE 'Food Preparing%%' THEN 'serving' ELSE 'retail' END
        FROM business_license l
        JOIN area a ON a.id = %s AND ST_Intersects(l.geom, a.geom)
        CROSS JOIN LATERAL (SELECT id, ST_Distance(ST_Transform(geom, 32618), ST_Transform(l.geom, 32618)) AS d
                            FROM building WHERE area_id = a.id ORDER BY geom <-> l.geom LIMIT 1) nb
        WHERE l.licensestatus = 'Active'
          AND (l.licensetype LIKE 'Food Preparing%%' OR l.licensetype LIKE 'Food Establishment, Retail%%')
          AND nb.d <= %s
        """,
        (area_id, LICENSE_LINK_M),
    ):
        licences.setdefault(bid, [0, 0])[0 if kind == "serving" else 1] += 1

    labelled = []
    for bid, eu, ev, ek, c1, c2, street_name, opa_cat in rows:
        lu = land_use_class(c1, c2)
        labelled.append((bid, _street_group(slug, street_name, (eu, ev, ek)), (eu, ev, ek), c1, c2, lu, opa_cat))

    # Split assignment: balance weight per area, weighting non-residential buildings so commercial
    # examples spread across splits. A street holding more than BIG_STREET_SHARE of an area's weight
    # is divided into blocks (segments); otherwise one street would decide a whole split.
    street_weight: dict[str, float] = {}
    for _bid, key, _edge, _c1, _c2, lu, _cat in labelled:
        street_weight[key] = street_weight.get(key, 0.0) + (1.0 if lu == "residential" else 5.0)
    area_weight = sum(street_weight.values())
    groups: dict[str, tuple[str, float]] = {}
    group_of: dict[int, str] = {}
    for bid, key, edge, _c1, _c2, lu, _cat in labelled:
        gkey = f"{key}#{edge[0]}-{edge[1]}-{edge[2]}" if street_weight[key] > BIG_STREET_SHARE * area_weight else key
        group_of[bid] = gkey
        groups[gkey] = (slug, groups.get(gkey, (slug, 0.0))[1] + (1.0 if lu == "residential" else 5.0))
    fixed = dict(conn.execute("SELECT group_key, split FROM split_assignment").fetchall())
    assignment = assign_splits(groups, fixed)
    new_groups = [(k, v) for k, v in assignment.items() if k not in fixed]
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO split_assignment (group_key, split) VALUES (%s, %s)", new_groups)

    out = []
    for bid, _key, _edge, c1, c2, lu, opa_cat in labelled:
        opa = opa_class(opa_cat)
        serving, retail = licences.get(bid, [0, 0])
        out.append((
            bid, CROSSWALK_VERSION, c1, c2, lu, opa_cat, opa, label_status(lu, opa), bid in split_ids,
            serving, retail, serving > 0, assignment[group_of[bid]],
        ))
    conn.execute("DELETE FROM ground_truth WHERE building_id IN (SELECT id FROM building WHERE area_id = %s)", (area_id,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO ground_truth (building_id, crosswalk_version, land_use_c1, land_use_c2, d1_class, opa_category, "
            "opa_class, label_status, split_footprint, food_serving_licenses, food_retail_licenses, d3_food, split) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            out,
        )
    return len(out)


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        for area_id, slug in conn.execute("SELECT id, slug FROM area ORDER BY id").fetchall():
            n = build_area(conn, area_id, slug)
            conn.commit()
            print(f"{slug:14s} labelled buildings={n}")


if __name__ == "__main__":
    main()
