import pytest

from streetwalker.census import (
    Licence,
    OsmPlace,
    address_match,
    chapman,
    clean_name,
    match_places,
    name_similarity,
    name_variants,
    osm_kind,
    parse_address_range,
)


def test_clean_name_drops_legal_and_generic_words():
    assert clean_name("CREME  BRULEE II RESTAURANT INC") == "cremebruleeii"
    assert clean_name("Ameri Thai Bistro LLC") == "amerithaibistro"


def test_name_variants_pull_out_trade_names_in_parentheses():
    v = name_variants("FEAR FOODS CO (Juana Tamale)", "FEAR FOODS CO")
    assert any("Juana Tamale" in x for x in v)
    assert name_similarity("Juana Tamale", v) >= 0.9


def test_name_similarity_handles_partial_and_unrelated():
    assert name_similarity("Creme Brulee", ["CREME  BRULEE II RESTAURANT INC"]) >= 0.8
    assert name_similarity("Pizzata Pizzeria & Birreria", ["Pizzata Pizzeria"]) >= 0.8
    assert name_similarity("Sally's", ["MoonNight LLC"]) < 0.4
    assert name_similarity(None, ["x"]) == 0.0


@pytest.mark.parametrize(
    ("addr", "expected"),
    [("1709-17 E PASSYUNK AVE", (1709, 1717, "E PASSYUNK AVE")), ("1244 SNYDER AVE", (1244, 1244, "SNYDER AVE")),
     ("1930-32 S BROAD ST", (1930, 1932, "S BROAD ST")), ("no number here", None), (None, None)],
)
def test_parse_address_range(addr, expected):
    assert parse_address_range(addr) == expected


def test_address_match_needs_same_street_and_a_number_in_range():
    assert address_match("1711", "East Passyunk Avenue", "1709-17 E PASSYUNK AVE")
    assert address_match("1244", "Snyder Avenue", "1244 SNYDER AVE")
    assert not address_match("1720", "East Passyunk Avenue", "1709-17 E PASSYUNK AVE")
    assert not address_match("1711", "Snyder Avenue", "1709-17 E PASSYUNK AVE")
    assert not address_match(None, "Snyder Avenue", "1244 SNYDER AVE")


def test_osm_kind():
    assert osm_kind({"amenity": "restaurant"}) == "restaurant"
    assert osm_kind({"amenity": "pub"}) == "bar"
    assert osm_kind({"shop": "bakery"}) == "bakery or deli"
    assert osm_kind({"amenity": "cafe"}) == "cafe"


def osm(i, name, x=0.0, y=0.0, b=None, **kw):
    return OsmPlace("node", i, name, "restaurant", x, y, b, **kw)


def lic(i, names, x=0.0, y=0.0, b=None, address=None):
    return Licence(i, names, address, x, y, b, "Food Preparing and Serving")


def test_matches_by_name_and_building():
    ms = match_places([osm(1, "Creme Brulee", b=10)], [lic(7, ["CREME BRULEE II RESTAURANT INC"], b=10)])
    assert len(ms) == 1 and "name" in ms[0].basis and ms[0].score > 0.6


def test_building_one_to_one_matches_even_when_names_differ_but_is_flagged():
    ms = match_places([osm(1, "Pistola del Sur", b=5)], [lic(2, ["DEMILIOS OLD WORLD ICE TREATS"], b=5)])
    assert len(ms) == 1 and ms[0].basis == "building 1:1 (names differ)"


def test_two_places_in_one_building_pair_by_name_not_by_bonus():
    ms = match_places(
        [osm(1, "Alpha Cafe", b=3), osm(2, "Zeta Pizza", b=3)],
        [lic(10, ["ZETA PIZZA LLC"], b=3), lic(11, ["ALPHA CAFE INC"], b=3)],
    )
    pairs = {(m.osm_idx, m.lic_idx) for m in ms}
    assert pairs == {(0, 1), (1, 0)}


def test_neighbouring_building_match_needs_a_name_or_address():
    far_name = match_places([osm(1, "Cantina Los Caballitos", x=0, y=0, b=1)], [lic(2, ["CANTINA LOS CABALLITOS INC"], x=15, y=0, b=2)])
    assert len(far_name) == 1  # licence point landed on the next building, names agree
    no_basis = match_places([osm(1, "Cantina Los Caballitos", x=0, y=0, b=1)], [lic(2, ["TOTALLY DIFFERENT LLC"], x=15, y=0, b=2)])
    assert no_basis == []  # close but nothing else in common
    by_address = match_places(
        [osm(1, "Ultimo", x=0, y=0, b=1, housenumber="1900", street="South 15th Street")],
        [lic(2, ["XYZ HOLDINGS LLC"], x=10, y=0, b=2, address="1900 S 15TH ST")])
    assert len(by_address) == 1 and "address" in by_address[0].basis


def test_too_far_apart_never_matches_and_matching_is_one_to_one():
    assert match_places([osm(1, "Same Name")], [lic(2, ["SAME NAME LLC"], x=100)]) == []
    ms = match_places([osm(1, "Joe's Pizza"), osm(2, "Joe's Pizza")], [lic(9, ["JOES PIZZA LLC"])])
    assert len(ms) == 1


def test_chapman_estimate():
    n, lo, hi = chapman(100, 80, 60)
    assert n == pytest.approx(101 * 81 / 61 - 1) and lo < n < hi
    n2, _, _ = chapman(50, 50, 50)
    assert n2 == pytest.approx(50)  # perfect overlap: nothing is missing


def test_place_kind_question_and_state():
    from streetwalker.census_kind import state
    from streetwalker.jev_questions import PLACE_KINDS, build_place_questions

    q = build_place_questions()["kind"]
    assert set(q.criteria) == set(PLACE_KINDS)
    text = state("Kura Sushi USA, INC (Kura Revolving Sushi Bar)", "1721-23 CHESTNUT ST", "Food Preparing and Serving (30+ SEATS)")
    assert "30 or more seats" in text and "Kura" in text
    assert "fewer than 30 seats" in state("X", None, "Food Preparing and Serving")
