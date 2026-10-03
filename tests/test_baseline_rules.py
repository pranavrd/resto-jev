import pytest

from streetwalker.baseline_rules import (
    RULESETS,
    commercial_type,
    is_food,
    predict,
    predict_v2,
    predict_v3,
)


def payload(building="yes", use_tags=None, pois=None, area=60.0, width=5.0, walls=2, has_unit=False):
    osm = {"building": building}
    if use_tags:
        osm["use_tags"] = use_tags
    if has_unit:
        osm["has_unit"] = True
    return {
        "osm": osm,
        "pois": [{"match": "contained", "dist_m": 0, "tags": t} for t in (pois or [])],
        "geometry": {"area_m2": area, "frontage_width_m": width, "n_party_walls": walls},
    }


def check(p, d1, rule):
    got = predict(p)
    assert (got.d1, got.rule) == (d1, rule)
    return got


def test_silent_rowhouse_is_residential():
    check(payload(), "residential", "default_residential")


def test_residential_tag_without_business():
    check(payload("semidetached_house", walls=1), "residential", "residential_tag")


def test_accessory_buildings_inherit_residential():
    check(payload("garage", walls=0, area=20), "residential", "accessory_tag")


def test_civic_by_building_amenity_and_religion():
    check(payload("church"), "civic-institutional", "civic_tag")
    check(payload(use_tags={"amenity": "school"}), "civic-institutional", "civic_tag")
    check(payload(use_tags={"religion": "christian", "amenity": "place_of_worship"}), "civic-institutional", "civic_tag")
    check(payload(pois=[{"amenity": "library"}]), "civic-institutional", "civic_tag")


def test_industrial_and_parking():
    check(payload("warehouse", area=2000, walls=0, width=40), "industrial", "industrial_tag")
    check(payload("parking", area=2500, walls=0, width=50), "other", "parking_tag")


def test_business_in_rowhouse_footprint_is_mixed_use():
    got = check(payload(pois=[{"amenity": "restaurant", "name": "X"}]), "mixed-use", "business_in_rowhouse_footprint")
    assert got.d2 == "restaurant" and got.d3_food


def test_business_in_big_free_standing_building_is_commercial():
    check(payload(pois=[{"shop": "clothes"}], area=900, width=30, walls=0), "commercial", "business_in_other_footprint")


def test_business_in_apartments_or_unit_building_is_mixed_use():
    check(payload("apartments", pois=[{"shop": "clothes"}], area=800, width=25), "mixed-use", "business_in_residential_building")
    check(payload(pois=[{"shop": "clothes"}], area=800, width=25, has_unit=True), "mixed-use", "business_in_residential_building")


def test_commercial_tag_without_poi():
    got = check(payload("retail", area=400, width=15), "commercial", "commercial_tag")
    assert got.d2 == "retail"


def test_street_furniture_and_public_space_are_not_evidence_upstream_but_parking_amenity_is_other():
    check(payload(use_tags={"amenity": "parking"}), "other", "parking_tag")


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ([{"amenity": "restaurant"}], "restaurant"),
        ([{"amenity": "fast_food"}], "restaurant"),
        ([{"amenity": "cafe"}], "cafe"),
        ([{"shop": "coffee"}], "cafe"),
        ([{"amenity": "pub"}], "bar"),
        ([{"shop": "convenience"}], "grocery"),
        ([{"shop": "clothes"}], "retail"),
        ([{"shop": "hairdresser"}], "personal services"),
        ([{"amenity": "bank"}], "personal services"),
        ([{"healthcare": "optometrist"}], "personal services"),
        ([{"office": "lawyer"}], "office"),
        ([{"amenity": "restaurant"}, {"shop": "clothes"}], "restaurant"),  # food beats retail
    ],
)
def test_commercial_type(tags, expected):
    assert commercial_type(tags) == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [([{"amenity": "cafe"}], True), ([{"shop": "bakery"}], True), ([{"shop": "clothes"}], False),
     ([{"shop": "butcher"}], False), ([], False), ([{"amenity": "bank"}], False)],
)
def test_is_food(tags, expected):
    assert is_food(tags) is expected


def test_metrics_per_class_and_binary():
    from streetwalker.metrics import accuracy, binary, macro_f1, per_class

    truth = ["a", "a", "a", "b", "b", "c"]
    pred = ["a", "a", "b", "b", "b", "a"]
    stats = {s.label: s for s in per_class(truth, pred, ["a", "b", "c"])}
    assert stats["a"].precision == pytest.approx(2 / 3) and stats["a"].recall == pytest.approx(2 / 3)
    assert stats["b"].precision == pytest.approx(2 / 3) and stats["b"].recall == 1.0
    assert stats["c"].f1 == 0.0 and stats["c"].support == 1
    assert accuracy(truth, pred) == pytest.approx(4 / 6)
    assert macro_f1(list(stats.values())) == pytest.approx((stats["a"].f1 + stats["b"].f1 + 0.0) / 3)
    assert binary([True, True, False, False], [True, False, True, False]).f1 == pytest.approx(0.5)


def street_payload(highway="residential", block_pois=3, **kw):
    p = payload(**kw)
    p["street"] = {"highway": highway}
    p["context"] = {"segment": {"n_business_pois": block_pois}}
    return p


def test_v1_is_unchanged_by_the_new_rule_sets():
    p = payload(pois=[{"shop": "clothes"}], area=800, width=25, has_unit=True)
    assert predict(p).rule == "business_in_residential_building"  # v1 keeps its original behaviour
    assert RULESETS["rules-v1"](p) == predict(p)


def test_v2_decides_mixed_vs_commercial_by_footprint_not_by_unit_or_apartment_tags():
    big_units = street_payload(pois=[{"shop": "clothes"}], area=800, width=25, has_unit=True)
    assert (predict_v2(big_units).d1, predict_v2(big_units).rule) == ("commercial", "business_in_larger_footprint")
    tower = street_payload("residential", building="apartments", pois=[{"shop": "clothes"}], area=900, width=30, walls=0)
    assert predict_v2(tower).d1 == "commercial"
    row = street_payload(pois=[{"shop": "clothes"}])
    assert predict_v2(row).d1 == "mixed-use"
    house = street_payload(building="detached", pois=[{"shop": "clothes"}], area=400, width=14, walls=0)
    assert predict_v2(house).rule == "business_in_house_tag" and predict_v2(house).d1 == "mixed-use"


def test_v2_retail_tag_in_a_rowhouse_footprint_is_mixed_use():
    assert predict_v2(street_payload(building="retail")).rule == "commercial_tag_rowhouse_footprint"
    assert predict_v2(street_payload(building="retail", area=500, width=20)).d1 == "commercial"


def test_v3_corridor_rule_only_fires_for_silent_attached_untagged_buildings_on_corridor_roads():
    assert predict_v2(street_payload("tertiary")).d1 == "residential"  # v2 has no context
    got = predict_v3(street_payload("tertiary"))
    assert (got.d1, got.rule) == ("mixed-use", "corridor_silent_rowhouse")
    assert predict_v3(street_payload("primary", area=900, width=30)).rule == "corridor_silent_building"
    assert predict_v3(street_payload("residential")).d1 == "residential"
    assert predict_v3(street_payload("secondary")).d1 == "residential"
    assert predict_v3(street_payload("tertiary", walls=0)).d1 == "residential"  # free-standing: not a corridor rowhouse
    assert predict_v3(street_payload("tertiary", building="semidetached_house")).d1 == "residential"
    assert predict_v3(street_payload("tertiary", block_pois=0)).d1 == "residential"  # no known businesses on the block


def test_multiclass_log_loss_respects_custom_class_order():
    from streetwalker.metrics import multiclass_log_loss

    classes = ("zebra", "apple")  # deliberately not alphabetical
    probs = [[0.9, 0.1], [0.2, 0.8]]
    good = multiclass_log_loss(["zebra", "apple"], probs, classes)
    assert good == pytest.approx(-(__import__("math").log(0.9) + __import__("math").log(0.8)) / 2)
    bad = multiclass_log_loss(["apple", "zebra"], probs, classes)  # confidently wrong
    assert bad > good * 5


def test_grouped_bootstrap_resamples_groups_and_is_deterministic():
    from streetwalker.bootstrap import grouped_bootstrap

    rows = [1.0] * 10 + [0.0] * 10
    groups = ["a"] * 10 + ["b"] * 10  # two groups: resampling whole groups yields means of 0, 0.5 or 1 only
    lo, hi = grouped_bootstrap(rows, groups, lambda r: sum(r) / len(r), n=400, seed=1)
    assert (lo, hi) == (0.0, 1.0)
    assert grouped_bootstrap(rows, groups, lambda r: sum(r) / len(r), n=400, seed=1) == (lo, hi)
    many = [1.0, 0.0] * 50  # one building per group: ordinary bootstrap, interval is narrow around 0.5
    lo2, hi2 = grouped_bootstrap(many, [str(i) for i in range(100)], lambda r: sum(r) / len(r), n=400, seed=1)
    assert 0.35 < lo2 < 0.5 < hi2 < 0.65
