"""Week 1 check: parcel and food-license density for candidate survey areas.

Queries the City of Philadelphia public Carto SQL API (no key needed). Stdlib only.
Run: python3 scripts/week1_area_density.py
"""

import json
import urllib.parse
import urllib.request

CARTO = "https://phl.carto.com/api/v2/sql"

# name -> (lng_min, lat_min, lng_max, lat_max). Rough boxes, to be refined when areas are locked.
CANDIDATES = {
    "rittenhouse": (-75.1745, 39.9475, -75.1685, 39.9520),
    "east_passyunk": (-75.1710, 39.9235, -75.1630, 39.9295),
    "chestnut_hill": (-75.2115, 40.0735, -75.2055, 40.0790),
    "mayfair_ne": (-75.0575, 40.0355, -75.0495, 40.0415),
    # Round 2 (low-density alternatives, added after thin Mapillary coverage in round 1)
    "mt_airy": (-75.1960, 40.0510, -75.1880, 40.0570),
    "roxborough": (-75.2195, 40.0345, -75.2115, 40.0405),
    "holmesburg": (-75.0330, 40.0370, -75.0250, 40.0430),
}

FOOD_TYPES = (
    "Food Preparing and Serving",
    "Food Preparing and Serving (30+ SEATS)",
    "Food Establishment, Retail Permanent Location",
    "Food Establishment, Retail Perm Location (Large)",
)


def sql(query: str) -> list[dict]:
    url = f"{CARTO}?{urllib.parse.urlencode({'q': query})}"
    with urllib.request.urlopen(url, timeout=90) as resp:
        return json.load(resp)["rows"]


def main() -> None:
    food_list = ", ".join(f"'{t}'" for t in FOOD_TYPES)
    for name, (x1, y1, x2, y2) in CANDIDATES.items():
        env = f"ST_MakeEnvelope({x1},{y1},{x2},{y2},4326)"
        parcels = sql(
            "SELECT category_code_description AS c, count(*) AS n FROM opa_properties_public "
            f"WHERE ST_Intersects(the_geom, {env}) GROUP BY 1 ORDER BY 2 DESC"
        )
        food = sql(
            "SELECT licensetype AS t, count(*) AS n FROM business_licenses "
            f"WHERE licensestatus = 'Active' AND licensetype IN ({food_list}) "
            f"AND ST_Intersects(the_geom, {env}) GROUP BY 1 ORDER BY 2 DESC"
        )
        print(f"\n=== {name}  bbox=({x1}, {y1}, {x2}, {y2})")
        print("parcels:", sum(r["n"] for r in parcels))
        print("  top categories:", ", ".join(f"{r['c']}={r['n']}" for r in parcels[:7]))
        print("active food licenses:", sum(r["n"] for r in food))
        for r in food:
            print(f"  {r['t']}: {r['n']}")


if __name__ == "__main__":
    main()
