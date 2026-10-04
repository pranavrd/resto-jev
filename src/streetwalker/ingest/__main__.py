"""Usage: python -m streetwalker.ingest [osm|streets|city|mapillary|septa|neighborhoods|all] [--area SLUG]"""

import argparse
from functools import partial

from streetwalker import db
from streetwalker.areas import AREAS
from streetwalker.ingest import city, mapillary, neighborhoods, osm, septa


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", default="all", choices=["osm", "streets", "city", "mapillary", "septa", "neighborhoods", "all"])
    ap.add_argument("--area", help="limit to one area slug")
    args = ap.parse_args()

    with db.connect() as conn:
        db.migrate(conn)
        for area in AREAS:
            if args.area and area.slug != args.area:
                continue
            area_id = conn.execute(
                "INSERT INTO area (slug, name, profile, geom) "
                "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326)) "
                "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, profile = EXCLUDED.profile, "
                "geom = EXCLUDED.geom RETURNING id",
                (area.slug, area.name, area.profile, area.polygon.wkt),
            ).fetchone()[0]
            conn.commit()

            steps = []
            if args.source in ("osm", "all"):
                steps += [
                    ("osm buildings", partial(osm.ingest_buildings, conn, area, area_id)),
                    ("osm pois", partial(osm.ingest_pois, conn, area, area_id)),
                ]
            if args.source in ("osm", "streets", "all"):
                steps.append(("osm streets", partial(osm.ingest_streets, conn, area, area_id)))
            if args.source in ("city", "all"):
                steps += [
                    ("opa parcels", partial(city.ingest_parcels, conn, area)),
                    ("land use", partial(city.ingest_land_use, conn, area)),
                    ("business licenses", partial(city.ingest_licenses, conn, area)),
                ]
            if args.source in ("mapillary", "all"):
                steps.append(("mapillary images", partial(mapillary.ingest_images, conn, area, area_id)))

            for label, step in steps:
                n = step()
                conn.commit()
                print(f"{area.slug:14s} {label:18s} {n:>6d} rows")

        for source, label, step in (
            ("septa", "septa stops", partial(septa.ingest_septa, conn)),
            ("neighborhoods", "neighborhoods", partial(neighborhoods.ingest_neighborhoods, conn)),
        ):
            if args.source in (source, "all"):  # citywide sources, loaded once
                n = step()
                conn.commit()
                print(f"{'citywide':14s} {label:18s} {n:>6d} rows")


if __name__ == "__main__":
    main()
