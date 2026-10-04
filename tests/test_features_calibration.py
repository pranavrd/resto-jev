import math

import pytest

from streetwalker.calibration import ece, reliability_bins
from streetwalker.features import (
    CATEGORICAL,
    FEATURE_SETS,
    JEV,
    JEV_CLASSES,
    building_category,
    extract,
    jev_features,
)


def bundle(**over):
    p = {
        "osm": {"building": "yes", "levels": 3, "height_m": 11.0},
        "pois": [
            {"match": "contained", "dist_m": 0, "tags": {"amenity": "cafe", "name": "Joe"}},
            {"match": "nearby", "dist_m": 6, "tags": {"shop": "clothes"}},
        ],
        "geometry": {"area_m2": 90.0, "perimeter_m": 40.0, "compactness": 0.7, "frontage_width_m": 6.0,
                     "depth_m": 15.0, "aspect": 2.5, "setback_m": 5.0, "n_party_walls": 2, "shared_wall_ratio": 0.5},
        "street": {"name": "Spruce Street", "highway": "tertiary", "side_walk": 1, "assign_method": "address",
                   "is_corner": True},
        "context": {
            "neighbors": [
                {"rel": -1, "event_seq": 4, "area_m2": 80.0, "attached": True, "poi_kinds": ["amenity=bar"], "use_tags": {}},
                {"rel": 1, "event_seq": 6, "area_m2": 100.0, "attached": False, "poi_kinds": [], "use_tags": {"shop": "x"}},
            ],
            "segment": {"n_buildings": 20, "n_business_pois": 5, "frac_attached": 0.9},
        },
    }
    p.update(over)
    return p


def test_extract_covers_every_feature_set():
    f = extract(bundle())
    for name, cols in FEATURE_SETS.items():
        if name != "stack":  # the stack set also needs Jev's answers
            assert set(cols) <= set(f)
    assert f["n_pois"] == 2 and f["n_pois_contained"] == 1 and f["n_pois_nearby"] == 1
    assert f["has_food"] == 1 and f["has_retail"] == 1 and f["has_business"] == 1
    assert f["road_class"] == "tertiary" and f["is_corner"] == 1
    assert f["nb_n"] == 2 and f["nb_n_with_pois"] == 1 and f["nb_n_attached"] == 1 and f["nb_n_with_use_tags"] == 1
    assert f["nb_mean_area_m2"] == pytest.approx(90.0) and f["nb_nearest_poi_rel"] == 1
    assert f["seg_poi_density"] == pytest.approx(5 / 20) and "seg_n_buildings" not in f


def test_extract_handles_missing_and_empty_context():
    p = bundle(osm={"building": "yes"}, pois=[])
    p["context"] = {"neighbors": [], "segment": {"n_buildings": 1, "n_business_pois": 0, "frac_attached": 0.0}}
    f = extract(p)
    assert math.isnan(f["levels"]) and math.isnan(f["height_m"]) and math.isnan(f["nb_mean_area_m2"])
    assert f["nb_nearest_poi_rel"] == 3 and f["has_business"] == 0 and f["n_pois"] == 0


def test_no_street_name_area_or_order_features():
    banned = {"street_name", "name", "area", "area_slug", "event_seq", "walked_m", "side_walk", "assign_method"}
    for cols in FEATURE_SETS.values():
        assert not banned & set(cols)
    f = extract(bundle())
    assert "Spruce Street" not in f.values()
    assert {"building_cat", "road_class"} <= set(FEATURE_SETS["full"]) and "jev_d2" in CATEGORICAL


def test_building_category():
    assert building_category("semidetached_house") == "house"
    assert building_category("apartments") == "apartments"
    assert building_category("retail") == "commercial"
    assert building_category("church") == "civic"
    assert building_category("garage") == "accessory"
    assert building_category("yes") == "yes" and building_category("weird") == "other"


def test_ece_perfectly_calibrated_and_overconfident():
    conf = [0.8] * 10
    assert ece(conf, [True] * 8 + [False] * 2) == pytest.approx(0.0)
    assert ece([0.9] * 10, [True] * 5 + [False] * 5) == pytest.approx(0.4)
    assert ece([], []) == 0.0


def test_reliability_bins_edges():
    bins = reliability_bins([0.05, 0.95, 1.0], [False, True, True], n_bins=10)
    assert [b.n for b in bins] == [1, 2]  # 1.0 lands in the last bin
    assert bins[1].accuracy == 1.0 and bins[1].mean_confidence == pytest.approx(0.975)


def test_jev_features_and_stack_set():
    probs = dict.fromkeys(JEV_CLASSES, 0.0) | {"residential": 0.7, "commercial": 0.1, "mixed-use": 0.2}
    j = jev_features(probs, 0.7, 0.3, "retail")
    assert j["jev_p_comm_any"] == pytest.approx(0.3) and j["jev_conf"] == 0.7 and j["jev_d2"] == "retail"
    assert set(JEV) == set(j)
    assert set(FEATURE_SETS["stack"]) == set(FEATURE_SETS["full"]) | set(JEV)
    assert not set(JEV) & set(FEATURE_SETS["full"])  # the plain GBMs never see Jev's answers
