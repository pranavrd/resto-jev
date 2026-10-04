"""Write neighborhood and transit context onto every place.   Usage: python -m streetwalker.enrich

Needs `python -m streetwalker.ingest septa neighborhoods` first. census_area calls this at the end of its run, because
rebuilding the place table clears these columns.
"""

import psycopg

from streetwalker import db
from streetwalker.transit import Stop, StopTable, place_context, utm


def load_table(conn: psycopg.Connection) -> StopTable:
    rows = conn.execute("SELECT stop_id, name, ST_X(geom), ST_Y(geom), modes, service FROM transit_stop").fetchall()
    stops = []
    for sid, name, lon, lat, modes, service in rows:
        x, y = utm(lon, lat)
        stops.append(Stop(sid, name, x, y, frozenset(modes), {(k.rsplit("|", 1)[0], int(k.rsplit("|", 1)[1])): v for k, v in service.items()}))
    return StopTable(stops)


def enrich_places(conn: psycopg.Connection) -> dict:
    """Returns counts for the report. Safe to re-run."""
    table = load_table(conn)
    conn.execute(
        """
        UPDATE place p SET neighborhood = (
            SELECT n.listname FROM neighborhood n WHERE ST_Intersects(n.geom, p.geom) ORDER BY ST_Area(n.geom) LIMIT 1)
        """
    )
    rows = conn.execute("SELECT id, ST_X(ST_Transform(geom, 32618)), ST_Y(ST_Transform(geom, 32618)) FROM place").fetchall()
    for pid, x, y in rows:
        c = place_context(table, x, y)
        conn.execute(
            """
            UPDATE place SET nearest_stop_name = %(nearest_stop_name)s, nearest_stop_m = %(nearest_stop_m)s,
                   nearest_rail_name = %(nearest_rail_name)s, nearest_rail_m = %(nearest_rail_m)s, stops_400m = %(stops_400m)s,
                   routes_400m = %(routes_400m)s, modes_400m = %(modes_400m)s, weekday_trips_400m = %(weekday_trips_400m)s
            WHERE id = %(id)s
            """,
            {**c, "id": pid},
        )
    return {"places": len(rows), "stops": len(table.stops)}


def report(conn: psycopg.Connection) -> None:
    print(f"{'area':14s} {'places':>6s} {'no hood':>8s} {'stop m':>7s} {'rail m':>7s} {'routes':>7s} {'trips':>7s} {'<=400m rail':>12s}   neighborhoods")
    sql = """
        SELECT a.slug, count(*), count(*) FILTER (WHERE p.neighborhood IS NULL),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY p.nearest_stop_m),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY p.nearest_rail_m),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY cardinality(p.routes_400m)),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY p.weekday_trips_400m),
               count(*) FILTER (WHERE p.nearest_rail_m <= 400),
               string_agg(DISTINCT p.neighborhood, ', ')
        FROM place p JOIN area a ON a.id = p.area_id GROUP BY a.slug ORDER BY a.slug
    """
    for slug, n, nohood, stop_m, rail_m, routes, trips, rail400, hoods in conn.execute(sql).fetchall():
        f = lambda v, w: f"{v:{w}.0f}" if v is not None else " " * (w - 1) + "-"
        print(f"{slug:14s} {n:6d} {nohood:8d} {f(stop_m, 7)} {f(rail_m, 7)} {f(routes, 7)} {f(trips, 7)} {rail400:12d}   {hoods}")


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        print(enrich_places(conn))
        conn.commit()
        report(conn)


if __name__ == "__main__":
    main()
