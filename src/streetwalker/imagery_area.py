"""Choose an image for every building.   Usage: python -m streetwalker.imagery_area"""

import psycopg

from streetwalker import db
from streetwalker.imagery import Image, pick_image, pick_panorama


def pick_area(conn: psycopg.Connection, area_id: int) -> tuple[int, int]:
    images = [
        Image(r[0], r[1], r[2], r[3], bool(r[4]), r[5])
        for r in conn.execute(
            "SELECT id, ST_X(geom), ST_Y(geom), COALESCE(computed_compass, compass_angle), is_pano, EXTRACT(year FROM captured_at)::int "
            "FROM mapillary_image WHERE area_id = %s", (area_id,))
    ]
    buildings = conn.execute(
        "SELECT id, ST_X(frontage_pt), ST_Y(frontage_pt) FROM building WHERE area_id = %s ORDER BY id", (area_id,)
    ).fetchall()
    conn.execute("DELETE FROM image_pick WHERE building_id IN (SELECT id FROM building WHERE area_id = %s)", (area_id,))
    rows = []
    for bid, x, y in buildings:
        p = pick_image(x, y, images)
        if p:
            rows.append((bid, p.image.id, p.dist_m, p.angle_deg, p.score, p.image.year))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO image_pick (building_id, image_id, dist_m, angle_deg, score, year) VALUES (%s,%s,%s,%s,%s,%s)", rows)
    return len(buildings), len(rows)


def pick_panos_area(conn: psycopg.Connection, area_id: int) -> int:
    images = [
        Image(r[0], r[1], r[2], r[3], True, r[4])
        for r in conn.execute(
            # panoramas: the RAW compass_angle marks the centre column (matches travel direction for 100% of 63 East
            # Passyunk panoramas); computed_compass_angle is a consistent ~86 degrees off for them
            "SELECT id, ST_X(geom), ST_Y(geom), compass_angle, EXTRACT(year FROM captured_at)::int "
            "FROM mapillary_image WHERE area_id = %s AND is_pano", (area_id,))
    ]
    conn.execute("DELETE FROM pano_pick WHERE building_id IN (SELECT id FROM building WHERE area_id = %s)", (area_id,))
    rows = []
    for bid, x, y in conn.execute("SELECT id, ST_X(frontage_pt), ST_Y(frontage_pt) FROM building WHERE area_id = %s ORDER BY id", (area_id,)).fetchall():
        p = pick_panorama(x, y, images)
        if p:
            rows.append((bid, p.image.id, p.dist_m, p.bearing_deg, p.image.compass, p.image.year))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO pano_pick (building_id, image_id, dist_m, bearing_deg, heading_deg, year) VALUES (%s,%s,%s,%s,%s,%s)", rows)
    return len(rows)


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        for area_id, slug in conn.execute("SELECT id, slug FROM area ORDER BY id").fetchall():
            n, k = pick_area(conn, area_id)
            kp = pick_panos_area(conn, area_id)
            conn.commit()
            print(f"{slug:14s} {k:5d} of {n:5d} buildings have a usable photo ({k / n:.0%}); {kp:5d} have a panorama to crop from")


if __name__ == "__main__":
    main()
