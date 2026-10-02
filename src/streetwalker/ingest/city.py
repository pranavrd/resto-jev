"""City of Philadelphia ingest: OPA parcels, PCPC land use, L&I business licenses (all public, no key)."""

import json
import urllib.parse
import urllib.request

import psycopg
from shapely.geometry import shape

from streetwalker.areas import Area

CARTO = "https://phl.carto.com/api/v2/sql"
LAND_USE = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/Land_Use/FeatureServer/0/query"


def _get_json(url: str, params: dict) -> dict:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=120) as resp:
        return json.load(resp)


def _carto(query: str) -> list[dict]:
    return _get_json(CARTO, {"q": query})["rows"]


def _envelope(area: Area) -> str:
    x1, y1, x2, y2 = area.bbox
    return f"ST_MakeEnvelope({x1},{y1},{x2},{y2},4326)"


def ingest_parcels(conn: psycopg.Connection, area: Area) -> int:
    rows = _carto(
        "SELECT parcel_number, category_code, category_code_description, building_code_description, "
        "zoning, number_stories, total_area, total_livable_area, year_built, location, "
        "ST_AsText(the_geom) AS wkt FROM opa_properties_public "
        f"WHERE ST_Intersects(the_geom, {_envelope(area)})"
    )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO opa_parcel (parcel_number, category_code, category_code_description, "
            "building_code_description, zoning, number_stories, total_area, total_livable_area, "
            "year_built, location, geom) VALUES (%(parcel_number)s, %(category_code)s, "
            "%(category_code_description)s, %(building_code_description)s, %(zoning)s, %(number_stories)s, "
            "%(total_area)s, %(total_livable_area)s, %(year_built)s, %(location)s, "
            "ST_SetSRID(ST_GeomFromText(%(wkt)s), 4326)) "
            "ON CONFLICT (parcel_number) DO UPDATE SET category_code = EXCLUDED.category_code, "
            "category_code_description = EXCLUDED.category_code_description, pulled_at = now()",
            rows,
        )
    return len(rows)


def ingest_licenses(conn: psycopg.Connection, area: Area) -> int:
    rows = _carto(
        "SELECT cartodb_id, licensenum, licensetype, licensestatus, address, business_name, legalname, "
        "initialissuedate, mostrecentissuedate, expirationdate, inactivedate, parcel_id_num, "
        "opa_account_num, ST_AsText(the_geom) AS wkt FROM business_licenses "
        f"WHERE ST_Intersects(the_geom, {_envelope(area)})"
    )
    for r in rows:  # the source uses a sentinel year 3200 for "no expiry"; timestamptz can't hold it sanely
        for k in ("mostrecentissuedate", "expirationdate", "inactivedate", "initialissuedate"):
            if r[k] and r[k].startswith("3200"):
                r[k] = None
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO business_license (cartodb_id, licensenum, licensetype, licensestatus, address, "
            "business_name, legalname, initialissuedate, mostrecentissuedate, expirationdate, inactivedate, "
            "parcel_id_num, opa_account_num, geom) VALUES (%(cartodb_id)s, %(licensenum)s, %(licensetype)s, "
            "%(licensestatus)s, %(address)s, %(business_name)s, %(legalname)s, %(initialissuedate)s, "
            "%(mostrecentissuedate)s, %(expirationdate)s, %(inactivedate)s, %(parcel_id_num)s, "
            "%(opa_account_num)s, ST_SetSRID(ST_GeomFromText(%(wkt)s), 4326)) "
            "ON CONFLICT (cartodb_id) DO UPDATE SET licensestatus = EXCLUDED.licensestatus, "
            "inactivedate = EXCLUDED.inactivedate, pulled_at = now()",
            rows,
        )
    return len(rows)


def ingest_land_use(conn: psycopg.Connection, area: Area) -> int:
    x1, y1, x2, y2 = area.bbox
    n, offset, page = 0, 0, 1000
    while True:
        data = _get_json(
            LAND_USE,
            {
                "where": "1=1", "geometry": f"{x1},{y1},{x2},{y2}", "geometryType": "esriGeometryEnvelope",
                "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
                "f": "geojson", "resultOffset": offset, "resultRecordCount": page,
            },
        )
        feats = data.get("features", [])
        with conn.cursor() as cur:
            for f in feats:
                p = f["properties"]
                cur.execute(
                    "INSERT INTO land_use (objectid, c_dig1, c_dig2, c_dig3, c_dig1desc, c_dig2desc, "
                    "c_dig3desc, year, vacbldg, geom) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "ST_SetSRID(ST_GeomFromText(%s), 4326)) "
                    "ON CONFLICT (objectid) DO UPDATE SET c_dig2 = EXCLUDED.c_dig2, c_dig3 = EXCLUDED.c_dig3, "
                    "year = EXCLUDED.year, pulled_at = now()",
                    (
                        p["objectid"], p.get("c_dig1"), p.get("c_dig2"), p.get("c_dig3"), p.get("c_dig1desc"),
                        p.get("c_dig2desc"), p.get("c_dig3desc"), p.get("year"), p.get("vacbldg"),
                        shape(f["geometry"]).wkt,
                    ),
                )
        n += len(feats)
        if len(feats) < page:
            return n
        offset += page
