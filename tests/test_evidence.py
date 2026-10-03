from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, box

from streetwalker import evidence, evidence_area
from streetwalker.evidence import (
    building_osm,
    geometry_features,
    is_business_poi,
    link_pois,
    poi_summary,
    render_text,
    shared_walls,
)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"amenity": "restaurant"}, True),
        ({"shop": "clothes"}, True),
        ({"office": "lawyer"}, True),
        ({"amenity": "bench"}, False),
        ({"amenity": "waste_basket"}, False),
        ({"tourism": "artwork"}, False),
        ({"tourism": "hotel"}, True),
        ({"leisure": "park"}, False),
        ({"leisure": "fitness_centre"}, True),
        ({"amenity": "bench", "shop": "kiosk"}, True),  # furniture amenity but also a shop
        ({"name": "Something"}, False),
    ],
)
def test_is_business_poi(tags, expected):
    assert is_business_poi(tags) is expected


def test_building_osm_keeps_signal_and_drops_street_and_noise():
    out = building_osm({
        "building": "yes", "building:levels": "3", "height": "12.4 m", "addr:housenumber": "1801",
        "addr:street": "Spruce Street", "addr:unit": "2", "source": "city", "amenity": "cafe", "cuisine": "coffee",
    })
    assert out["levels"] == 3 and out["height_m"] == 12.4 and out["housenumber"] == "1801"
    assert out["has_unit"] is True
    assert out["use_tags"] == {"amenity": "cafe", "cuisine": "coffee"}
    assert "addr:street" not in out and "source" not in out


def test_poi_summary_flags_instead_of_copying_contact_details():
    s = poi_summary({"name": "Cafe", "amenity": "cafe", "phone": "+1 555", "website": "x", "opening_hours": "Mo-Su"})
    assert s["has_phone"] and s["has_website"] and s["has_opening_hours"]
    assert "phone" not in s and "website" not in s


def test_link_pois_prefers_containing_smallest_then_nearby_then_none():
    big, small = box(0, 0, 40, 40), box(10, 10, 20, 20)
    far_house = box(100, 0, 110, 10)
    pois = [Point(15, 15), Point(25, 25), Point(115, 5), Point(500, 500)]
    links = {ln.poi_idx: ln for ln in link_pois([big, small, far_house], pois)}
    assert links[0].building_idx == 1 and links[0].match == "contained"  # smallest containing footprint
    assert links[1].building_idx == 0 and links[1].match == "contained"
    assert links[2].building_idx == 2 and links[2].match == "nearby" and links[2].dist_m == pytest.approx(5)
    assert 3 not in links  # nothing within 10 m


def test_shared_walls_counts_real_party_walls_only():
    a, b = box(0, 0, 10, 10), box(10, 0, 20, 10)  # 10 m shared wall
    c = box(40, 0, 50, 10)  # free-standing
    d, e = box(60, 0, 70, 10), box(70, 9, 80, 19)  # touch along only 1 m: not a party wall
    walls = shared_walls([a, b, c, d, e])
    assert walls[0][0] == 1 and walls[0][1] == pytest.approx(0.25, abs=0.02) and walls[1][0] == 1  # tolerance adds ~0.5 m
    assert walls[2] == (0, 0.0)
    assert walls[3][0] == 0 and walls[4][0] == 0


def test_geometry_features_are_street_aligned():
    street = LineString([(-50, 0), (50, 0)])
    row = box(0, 6, 5, 21)  # 5 m along the street, 15 m deep, 6 m back
    g = geometry_features(row, street, along_m=52.5, dist_m=6)
    assert g["frontage_width_m"] == pytest.approx(5, abs=0.1) and g["depth_m"] == pytest.approx(15, abs=0.1)
    assert g["aspect"] == pytest.approx(3, abs=0.05) and g["setback_m"] == 6
    rotated = LineString([(0, -50), (0, 50)])  # street runs north-south; same building turned 90 degrees
    g2 = geometry_features(box(6, 0, 21, 5), rotated, along_m=52.5, dist_m=6)
    assert g2["frontage_width_m"] == pytest.approx(5, abs=0.1) and g2["depth_m"] == pytest.approx(15, abs=0.1)


def _payload(**over):
    p = {
        "osm": {"building": "yes", "housenumber": "1801", "levels": 1},
        "pois": [{"match": "contained", "dist_m": 0.0,
                  "tags": {"amenity": "cafe", "name": "Joe", "brand": "Joe", "cuisine": "coffee"}}],
        "geometry": {"area_m2": 120.0, "frontage_width_m": 8.0, "depth_m": 15.0, "setback_m": 6.0,
                     "n_party_walls": 1, "shared_wall_ratio": 0.3},
        "street": {"name": "Spruce Street", "highway": "secondary", "is_corner": True},
        "context": {"neighbors": [{"rel": -1, "area_m2": 90.0, "attached": True, "poi_kinds": [], "use_tags": {}}],
                    "segment": {"n_buildings": 1, "n_business_pois": 1, "frac_attached": 1.0}},
    }
    p.update(over)
    return p


def test_render_text_is_deterministic_and_complete():
    text = render_text(_payload())
    assert text == render_text(_payload())
    assert "Building at 1801 Spruce Street (corner of two streets)" in text
    assert "1 level" in text and "1 levels" not in text
    assert 'POI: amenity=cafe, cuisine=coffee "Joe", inside the footprint' in text  # brand dropped: same as name
    assert "Attached to 1 neighbour (" in text
    assert "1 business POI," in text
    assert "Neighbour 1 before on this side" in text


def test_render_text_without_pois_or_neighbours():
    text = render_text(_payload(pois=[], geometry={**_payload()["geometry"], "n_party_walls": 0}))
    assert "POIs: none within the footprint or 10 m" in text
    assert "free-standing" in text


GROUND_TRUTH_TERMS = ("land_use", "opa_parcel", "business_license", "building_land_use", "category_code")


@pytest.mark.parametrize("module", [evidence, evidence_area])
def test_evidence_never_touches_ground_truth(module):
    """Evidence must come from OSM and geometry only; parcels, land use and licences are the answer key."""
    source = Path(module.__file__).read_text().lower()
    for term in GROUND_TRUTH_TERMS:
        assert term not in source, f"{module.__name__} references ground truth: {term}"
    assert "licen" not in render_text(_payload()).lower()
