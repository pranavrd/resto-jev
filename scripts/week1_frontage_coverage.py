"""Week 1 check: how many parcels and food-license sites have a Mapillary image nearby?

Better than the grid-cell proxy in week1_mapillary_coverage.py: the question for the escalation
path is whether a commercial building has a frontage photo within walking distance.
Run: python3 scripts/week1_frontage_coverage.py   (needs MAPILLARY_TOKEN, see that script)
"""

import math
from datetime import UTC, datetime

from week1_area_density import CANDIDATES, FOOD_TYPES, sql
from week1_mapillary_coverage import fetch, load_token

COMMERCIAL = ("COMMERCIAL", "MIXED USE", "OFFICES", "RETAIL")
RADII_M = (30, 50)


def meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dy = (lat2 - lat1) * 111_320
    dx = (lng2 - lng1) * 111_320 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def nearest(pt: tuple[float, float], images: list[tuple[float, float, int]]) -> tuple[float, int]:
    best, year = float("inf"), 0
    for lat, lng, y in images:
        d = meters(pt[0], pt[1], lat, lng)
        if d < best:
            best, year = d, y
    return best, year


def report(label: str, pts: list[tuple[float, float]], images: list[tuple[float, float, int]]) -> None:
    if not pts:
        print(f"  {label}: none")
        return
    res = [nearest(p, images) for p in pts]
    shares = ", ".join(f"<={r}m {sum(d <= r for d, _ in res) / len(res):.0%}" for r in RADII_M)
    near_years = [y for d, y in res if d <= RADII_M[-1]]
    median_year = sorted(near_years)[len(near_years) // 2] if near_years else "-"
    print(f"  {label} (n={len(pts)}): {shares}; median image year within {RADII_M[-1]}m: {median_year}")


def main() -> None:
    token = load_token()
    food_list = ", ".join(f"'{t}'" for t in FOOD_TYPES)
    for name, bbox in CANDIDATES.items():
        x1, y1, x2, y2 = bbox
        env = f"ST_MakeEnvelope({x1},{y1},{x2},{y2},4326)"
        images = [
            (
                i["geometry"]["coordinates"][1],
                i["geometry"]["coordinates"][0],
                datetime.fromtimestamp(i["captured_at"] / 1000, UTC).year,
            )
            for i in fetch(bbox, token)
            if i.get("captured_at")
        ]
        parcels = sql(
            "SELECT category_code_description AS c, ST_Y(the_geom) AS lat, ST_X(the_geom) AS lng "
            f"FROM opa_properties_public WHERE ST_Intersects(the_geom, {env})"
        )
        food = sql(
            "SELECT ST_Y(the_geom) AS lat, ST_X(the_geom) AS lng FROM business_licenses "
            f"WHERE licensestatus = 'Active' AND licensetype IN ({food_list}) "
            f"AND ST_Intersects(the_geom, {env})"
        )
        print(f"\n=== {name}: {len(images)} images")
        report("commercial/mixed parcels", [(p["lat"], p["lng"]) for p in parcels if p["c"] in COMMERCIAL], images)
        report("active food licenses", [(f["lat"], f["lng"]) for f in food], images)


if __name__ == "__main__":
    main()
