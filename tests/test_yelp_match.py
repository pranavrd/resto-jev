"""Pure matching tests. Every business and place here is invented: Yelp data never enters the repository."""

import pytest

from streetwalker.yelp_match import (
    YBiz,
    YPlace,
    address_hit,
    confidence,
    distinct_name,
    find_aliases,
    is_dining,
    match,
    name_sim,
    place_addresses,
    yelp_address,
)


def place(i, own, x=0.0, y=0.0, b=1, addresses=None, names=None):
    return YPlace(i, names or [own], x, y, b, addresses if addresses is not None else [(100, 100, "Oak St")], own)


def biz(i, name, address="100 Oak St", x=0.0, y=0.0, b=1, count=1):
    return YBiz(i, name, address, x, y, b, True, 10, count)


def test_yelp_address_drops_the_suite_and_reads_ranges():
    assert yelp_address("1616 Chapala St, Ste 2") == (1616, 1616, "Chapala St")
    assert yelp_address("209 S 20th St") == (209, 209, "S 20th St")
    assert yelp_address(None) is None and yelp_address("Rittenhouse Sq") is None


def test_address_hit_needs_the_number_in_range_on_the_same_street():
    known = place_addresses("259-61 S 20TH ST", "261", "South 20th Street")
    assert address_hit(known, "261 S 20th St") and address_hit(known, "260 South 20th Street")
    assert not address_hit(known, "263 S 20th St")  # outside the licence range
    assert not address_hit(known, "260 S 21st St")  # right number, wrong street
    assert not address_hit([], "261 S 20th St")


def test_distinctive_names_ignore_venue_words_and_read_number_words():
    assert distinct_name("20 Elm") == distinct_name("Twenty Elm")
    assert name_sim("Blue Heron Taproom", ["Blue Heron Cafe"]) >= 0.9  # same name, different kind of venue
    assert name_sim("Yoshi Sushi Bar", ["Kobe sushi bar"]) < 0.6  # only the venue words are shared
    assert name_sim("q.kitchen", ["Q KITCHEN + BAR"]) >= 0.8  # nothing distinctive left: compare the whole name
    assert name_sim("Blue Heron Cafe", ["BLUE HERON HOLDINGS LLC (Blue Heron)"]) >= 0.8


def test_same_name_address_and_building_is_a_high_confidence_match():
    (m,) = match([place(1, "Lucky Noodle")], [biz("y1", "Lucky Noodle")])
    assert (m.confidence, m.basis) == ("high", "name+address+building")


def test_same_address_but_different_names_is_never_high():
    # the storefront changed hands between the snapshot and now: address and building agree, the business does not
    (m,) = match([place(1, "Lucky Noodle")], [biz("y1", "Golden Dragon")])
    assert m.confidence == "low" and "name" not in m.basis


def test_matching_is_one_to_one_and_prefers_the_better_pair():
    places = [place(1, "Lucky Noodle", x=0, addresses=[(100, 100, "Oak St")]), place(2, "Blue Heron Cafe", x=20, b=2, addresses=[(102, 102, "Oak St")])]
    businesses = [biz("y2", "Blue Heron Cafe", "102 Oak St", x=20, b=2), biz("y1", "Lucky Noodle", "100 Oak St", x=0, b=1)]
    got = {(places[m.place_idx].own_name, businesses[m.biz_idx].id) for m in match(places, businesses)}
    assert got == {("Lucky Noodle", "y1"), ("Blue Heron Cafe", "y2")}


def test_a_place_does_not_take_a_business_that_is_not_near_and_shares_no_address():
    p = place(1, "Lucky Noodle", addresses=[])
    assert match([p], [biz("y1", "Golden Dragon", "9 Elm St", x=90, b=2)]) == []  # a different business down the street
    assert match([p], [biz("y2", "Lucky Noodle", "9 Elm St", x=90, b=2, count=3)]) == []  # a chain name, 90 m away


def test_far_matches_need_the_address_or_a_unique_name_and_are_capped():
    p = place(1, "Lucky Noodle")
    far_addr = biz("y1", "Lucky Noodle", "100 Oak St", x=120, b=2)  # Yelp's point sits down the street, the address agrees
    (m,) = match([p], [far_addr])
    assert m.confidence in ("high", "medium") and "address" in m.basis
    unique = biz("y2", "Lucky Noodle", "7 Pine St", x=110, b=2, count=1)
    (m,) = match([p], [unique])
    assert m.confidence == "medium" and "unique" in m.basis  # capped: a name alone
    chain = biz("y3", "Lucky Noodle", "7 Pine St", x=110, b=2, count=5)
    assert match([p], [chain]) == []  # a chain name 110 m away says nothing
    assert match([p], [biz("y4", "Lucky Noodle", "100 Oak St", x=250, b=2)]) == []  # beyond any limit


def test_a_match_that_rests_only_on_a_licence_name_is_capped_at_medium():
    # the venue's own name is Pizza Palace; the operator's licence also names "Old Mill Tap"
    p = place(1, "Pizza Palace", names=["Pizza Palace", "Old Mill Tap"])
    (m,) = match([p], [biz("y1", "Old Mill Tap")])
    assert m.confidence == "medium" and "licence name only" in m.basis


def test_confidence_tiers():
    assert confidence(1.0, True, True, 5) == "high"
    assert confidence(0.95, False, False, 30) == "high"  # a strong name that is close
    assert confidence(0.7, False, False, 20) == "medium"
    assert confidence(0.2, True, True, 2) == "low"


def test_duplicate_listings_of_a_linked_business_become_aliases():
    businesses = [biz("y1", "Lucky Noodle", count=2), biz("y2", "Lucky Noodle", count=2), biz("y3", "Golden Dragon", "100 Oak St", count=1)]
    matches = match([place(1, "Lucky Noodle")], businesses)
    aliases = find_aliases(matches, businesses)
    assert len(matches) == 1 and len(aliases) == 1
    assert {businesses[matches[0].biz_idx].id, businesses[aliases[0][1]].id} == {"y1", "y2"}  # one linked, the other its alias
    # a low confidence link gets no aliases
    low = match([place(1, "Lucky Noodle")], [biz("y1", "Golden Dragon", count=2), biz("y2", "Golden Dragon", count=2)])
    assert find_aliases(low, [biz("y1", "Golden Dragon", count=2), biz("y2", "Golden Dragon", count=2)]) == []


@pytest.mark.parametrize("n", [1, 2])
def test_the_matcher_is_deterministic(n):
    places = [place(i, f"Place {i}", x=i * 5.0, b=i, addresses=[(100 + i, 100 + i, "Oak St")]) for i in range(1, 6)]
    businesses = [biz(f"y{i}", f"Place {i}", f"{100 + i} Oak St", x=i * 5.0, b=i) for i in range(5, 0, -1)]
    one = [(m.place_idx, m.biz_idx) for m in match(places, businesses)]
    assert one == [(m.place_idx, m.biz_idx) for m in match(places, businesses)] and len(one) == 5


def test_only_dining_listings_can_be_usable():
    assert is_dining("Restaurants, Italian") and is_dining("Coffee & Tea, Bakeries, Food") and is_dining("Bars, Nightlife")
    assert not is_dining("Fruits & Veggies, Specialty Food, Food, Grocery")  # "Food" alone is a market
    assert not is_dining("Hotels & Travel, Restaurants, Hotels")  # a hotel's reviews are about rooms, even with a restaurant inside
    assert not is_dining(None)
    hotel = YBiz("y1", "Lucky Noodle", "100 Oak St", 0.0, 0.0, 1, True, 10, 1, False)
    (m,) = match([place(1, "Lucky Noodle")], [hotel])
    assert m.confidence == "low" and "not a dining listing" in m.basis  # a perfect name and address, still not usable
