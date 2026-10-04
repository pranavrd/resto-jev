"""Build the place table and print the restaurant census.   Usage: python -m streetwalker.census_area

Sources (no Yelp): OSM food and drink places and active City "Food Preparing and Serving" licences, matched in
census.py. Run after groundtruth_area and baselines (the report compares them with the survey classifier).
"""

from collections import Counter
from datetime import UTC, datetime

import psycopg

from streetwalker import db
from streetwalker.census import Licence, OsmPlace, chapman, match_places, name_variants, osm_kind

FOOD_WHERE = (
    "(t.tags->>'amenity' IN ('restaurant','fast_food','food_court','cafe','bar','pub','biergarten','ice_cream') "
    "OR t.tags->>'shop' IN ('bakery','coffee','pastry','deli','ice_cream','chocolate','tea','confectionery'))"
)
MARGIN_DEG = 0.0004  # about 40 m: match across the box edge, count only places inside it
LICENCE_LINK_M = 15.0


def load_osm(conn: psycopg.Connection, area_id: int) -> tuple[list[OsmPlace], list[bool]]:
    sql = f"""
        SELECT t.osm_type, t.osm_id, t.tags, ST_X(pt), ST_Y(pt), t.building_id, ST_Intersects(t.g, a.geom)
        FROM (
          SELECT p.osm_type, p.osm_id, p.tags, ST_PointOnSurface(p.geom) AS g, pl.building_id
          FROM osm_poi p LEFT JOIN poi_link pl ON pl.area_id = p.area_id AND pl.osm_type = p.osm_type AND pl.osm_id = p.osm_id
          WHERE p.area_id = %(a)s AND NOT EXISTS (SELECT 1 FROM osm_building b WHERE b.area_id = p.area_id
                AND b.osm_type = p.osm_type AND b.osm_id = p.osm_id)
          UNION ALL
          SELECT b.osm_type, b.osm_id, ob.tags, ST_PointOnSurface(ob.geom), b.id
          FROM building b JOIN osm_building ob ON ob.area_id = b.area_id AND ob.osm_type = b.osm_type AND ob.osm_id = b.osm_id
          WHERE b.area_id = %(a)s
        ) t JOIN area a ON a.id = %(a)s
        CROSS JOIN LATERAL (SELECT ST_Transform(t.g, 32618) AS pt) q
        WHERE {FOOD_WHERE}
        ORDER BY t.osm_type, t.osm_id
    """
    places, inside = [], []
    for osm_type, osm_id, tags, x, y, bid, ins in conn.execute(sql, {"a": area_id}).fetchall():
        places.append(OsmPlace(osm_type, osm_id, tags.get("name"), osm_kind(tags), x, y, bid, tags.get("addr:housenumber"),
                               tags.get("addr:street"), tags.get("check_date"), "opening_hours" in tags))
        inside.append(ins)
    return places, inside


def load_licences(conn: psycopg.Connection, area_id: int) -> tuple[list[Licence], list[bool], list[dict]]:
    sql = """
        SELECT l.cartodb_id, l.business_name, l.legalname, l.address, ST_X(q.pt), ST_Y(q.pt), l.licensetype, l.geom,
               ST_Intersects(l.geom, a.geom), nb.id
        FROM business_license l JOIN area a ON a.id = %(a)s AND ST_DWithin(l.geom, a.geom, %(m)s)
        CROSS JOIN LATERAL (SELECT ST_Transform(l.geom, 32618) AS pt) q
        LEFT JOIN LATERAL (SELECT id FROM building WHERE area_id = a.id
                           AND ST_DWithin(ST_Transform(geom, 32618), q.pt, %(link)s) ORDER BY geom <-> l.geom LIMIT 1) nb ON true
        WHERE l.licensestatus = 'Active' AND l.licensetype LIKE 'Food Preparing%%' ORDER BY l.cartodb_id
    """
    lics, inside, raw = [], [], []
    for lid, bname, lname, addr, x, y, ltype, _g, ins, bid in conn.execute(sql, {"a": area_id, "m": MARGIN_DEG, "link": LICENCE_LINK_M}).fetchall():
        lics.append(Licence(lid, name_variants(bname, lname), addr, x, y, bid, ltype))
        inside.append(ins)
        raw.append({"business_name": bname, "legalname": lname})
    return lics, inside, raw


def confidence(has_osm: bool, has_lic: bool, basis: str | None, check_date: str | None, has_hours: bool) -> str:
    if has_osm and has_lic:
        return "high" if basis and ("name" in basis or "address" in basis) else "medium"
    if has_lic:
        return "medium"  # licensed, but nobody mapped it
    recent = bool(check_date) and int(check_date[:4]) >= datetime.now(UTC).year - 2
    return "medium" if (recent or has_hours) else "low"


def build_area(conn: psycopg.Connection, area_id: int) -> dict:
    osm, osm_in = load_osm(conn, area_id)
    lics, lic_in, lic_raw = load_licences(conn, area_id)
    matches = match_places(osm, lics)
    by_osm = {m.osm_idx: m for m in matches}
    matched_lic = {m.lic_idx: m for m in matches}

    # A place belongs to the area its location is in: the licence point when it has one (it sits on the parcel), else
    # the OSM point. Every count below is taken over this one population.
    rows: list[tuple[str, int | None, int | None, float | None, str | None, str]] = []  # source, osm idx, lic idx, score, basis, confidence
    for m in matches:
        o = osm[m.osm_idx]
        if lic_in[m.lic_idx]:
            rows.append(("both", m.osm_idx, m.lic_idx, m.score, m.basis, confidence(True, True, m.basis, o.check_date, o.has_hours)))
    for i, o in enumerate(osm):
        if i not in by_osm and osm_in[i]:
            rows.append(("osm", i, None, None, None, confidence(True, False, None, o.check_date, o.has_hours)))
    for j in range(len(lics)):
        if j not in matched_lic and lic_in[j]:
            rows.append(("licence", None, j, None, None, confidence(False, True, None, None, False)))

    conn.execute("DELETE FROM place WHERE area_id = %s", (area_id,))
    for source, i, j, score, basis, conf in rows:
        o = osm[i] if i is not None else None
        lic = lics[j] if j is not None else None
        x, y = (lic.x, lic.y) if lic else (o.x, o.y)
        name = o.name if o and o.name else (lic_raw[j]["business_name"] if lic else None)
        conn.execute(
            """
            INSERT INTO place (area_id, building_id, name, kind, geom, sources, osm_type, osm_id, licence_id, licence_type,
                               licence_name, address, match_score, match_basis, confidence)
            VALUES (%s, %s, %s, %s, ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 32618), 4326), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (area_id, (lic.building_id if lic and lic.building_id else (o.building_id if o else None)), name,
             o.kind if o else "licensed food service", x, y,
             {"both": ["osm", "licence"], "osm": ["osm"], "licence": ["licence"]}[source],
             o.osm_type if o else None, o.osm_id if o else None, lic.id if lic else None, lic.licence_type if lic else None,
             lic_raw[j]["business_name"] if lic else None, lic.address if lic else None, score, basis, conf),
        )
    src = Counter(r[0] for r in rows)
    return {
        "licences": src["both"] + src["licence"], "osm": src["both"] + src["osm"], "matched": src["both"],
        "basis": Counter(r[4] for r in rows if r[0] == "both"), "confidence": Counter(r[5] for r in rows),
    }


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        totals = Counter()
        print(f"{'area':14s} {'licensed':>8s} {'OSM':>5s} {'matched':>8s} {'union':>6s} {'OSM only':>9s} {'lic only':>9s}   OSM finds  licence finds   Chapman estimate")
        for area_id, slug in conn.execute("SELECT id, slug FROM area ORDER BY id").fetchall():
            s = build_area(conn, area_id)
            conn.commit()
            union = s["licences"] + s["osm"] - s["matched"]
            n, lo, hi = chapman(s["osm"], s["licences"], s["matched"])
            print(f"{slug:14s} {s['licences']:8d} {s['osm']:5d} {s['matched']:8d} {union:6d} {s['osm'] - s['matched']:9d} {s['licences'] - s['matched']:9d}"
                  f"   {s['matched'] / s['licences']:8.0%} {s['matched'] / s['osm']:12.0%}   {n:5.0f} [{max(lo, union):.0f}, {hi:.0f}]")
            totals.update({"licences": s["licences"], "osm": s["osm"], "matched": s["matched"]})
        n, lo, hi = chapman(totals["osm"], totals["licences"], totals["matched"])
        u = totals["licences"] + totals["osm"] - totals["matched"]
        print(f"{'all areas':14s} {totals['licences']:8d} {totals['osm']:5d} {totals['matched']:8d} {u:6d} {totals['osm'] - totals['matched']:9d} "
              f"{totals['licences'] - totals['matched']:9d}   {totals['matched'] / totals['licences']:8.0%} {totals['matched'] / totals['osm']:12.0%}   {n:5.0f} [{max(lo, u):.0f}, {hi:.0f}]")


if __name__ == "__main__":
    main()
