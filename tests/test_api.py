"""API tests against the local database. Skipped when it is not running or has not been through census_area + enrich."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from streetwalker import db


def _ready() -> bool:
    try:
        with db.connect() as conn:
            return bool(conn.execute("SELECT count(*) FROM place WHERE weekday_trips_400m IS NOT NULL").fetchone()[0])
    except (psycopg.Error, KeyError):  # no server, or no POSTGRES_PASSWORD in the environment
        return False


pytestmark = pytest.mark.skipif(not _ready(), reason="needs the local DB with place + transit context")


@pytest.fixture(scope="module")
def client():
    from streetwalker.api import app

    return TestClient(app)


def test_filters_are_honoured(client):
    r = client.get("/places", params={"area": "rittenhouse", "kind": ["bar", "cafe"], "limit": 200}).json()
    assert r["total"] == len(r["items"]) > 0
    assert all(p["area"] == "rittenhouse" and p["kind"] in ("bar", "cafe") for p in r["items"])


def test_radius_search_is_sorted_by_distance_and_within_radius(client):
    r = client.get("/places", params={"lat": 39.9496, "lng": -75.1715, "radius_m": 200, "sort": "distance"}).json()
    d = [p["distance_m"] for p in r["items"]]
    assert d and d == sorted(d) and max(d) <= 200


def test_transit_filters_hold_on_every_result(client):
    r = client.get("/places", params={"max_rail_m": 400, "min_trips": 500, "limit": 200}).json()
    assert r["items"]
    assert all(p["transit"]["nearest_rail_m"] <= 400 and p["transit"]["weekday_trips_400m"] >= 500 for p in r["items"])


def test_name_search_finds_a_known_place_first(client):
    r = client.get("/places", params={"q": "melograno"}).json()
    assert r["items"][0]["name"] == "Melograno" and r["items"][0]["transit"]["nearest_rail_name"]


def test_paging_does_not_overlap_and_reports_the_total(client):
    a = client.get("/places", params={"limit": 10, "offset": 0}).json()
    b = client.get("/places", params={"limit": 10, "offset": 10}).json()
    assert a["total"] == b["total"] > 20
    assert not {p["id"] for p in a["items"]} & {p["id"] for p in b["items"]}


def test_bad_requests_are_rejected_not_crashed(client):
    assert client.get("/places", params={"sort": "distance"}).status_code == 422  # needs a point
    assert client.get("/places", params={"area": "atlantis"}).status_code == 422
    assert client.get("/places", params={"limit": 5000}).status_code == 422
    assert client.get("/places/999999").status_code == 404


def test_detail_and_geojson_agree_and_carry_attribution(client):
    first = client.get("/places", params={"limit": 1}).json()["items"][0]
    detail = client.get(f"/places/{first['id']}").json()
    assert detail["name"] == first["name"] and "match_basis" in detail and detail["attribution"]
    g = client.get("/places.geojson", params={"limit": 1}).json()
    assert g["features"][0]["geometry"]["type"] == "Point" and g["attribution"]


def test_no_yelp_fields_are_exposed(client):
    first = client.get("/places", params={"limit": 1}).json()["items"][0]
    detail = client.get(f"/places/{first['id']}").json()
    assert not any("yelp" in k.lower() or "rating" in k.lower() or "review" in k.lower() for k in {*first, *detail})
