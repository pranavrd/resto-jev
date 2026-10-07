"""The census-against-Yelp analysis (decision 0033): the pure rules on invented businesses. No database, and no Yelp data: the real results are in
docs/private (gitignored), and a test checks that is where the report goes."""

from collections import Counter
from pathlib import Path

from streetwalker import census_vs_yelp as cy
from streetwalker.census_vs_yelp import Gap, bounds, explain, render, two_source_estimate

BIZ = "Blue Heron Cafe"


def gap(name=BIZ, categories="Restaurants, Cafes", places=(), licences=(), area="zz", reviews=10) -> Gap:
    return Gap("b1", name, area, reviews, categories, list(places), list(licences))


def test_a_listing_that_is_not_somewhere_to_eat_is_not_dining():
    assert explain(gap(categories="Grocery, Food")) == "not dining"
    assert explain(gap(categories="Hotels, Restaurants")) == "not dining"  # a hotel's reviews are about rooms (decision 0020)


def test_an_active_licence_of_the_census_type_with_no_place_is_a_census_miss_and_one_a_place_holds_is_only_a_missed_link():
    lic = (["Blue Heron Cafe LLC"], "Active", False, True)
    assert explain(gap(licences=[(*lic, False)])) == "census miss"
    assert explain(gap(licences=[(*lic, True)])) == "link missed"
    assert explain(gap(licences=[(["Blue Heron Cafe LLC"], "Active", False, False, False)])) == "other licence"  # retail food: outside the census's scope


def test_a_licence_that_has_ended_explains_a_business_that_is_gone():
    for status in ("Closed", "Inactive", "Expired", "Revoked"):
        assert explain(gap(licences=[(["Blue Heron Cafe LLC"], status, False, True, False)])) == "licence ended"
    assert explain(gap(licences=[(["Blue Heron Cafe LLC"], "Active", True, True, False)])) == "licence ended"  # an inactive date ends it whatever the status says
    assert explain(gap(licences=[(["Some Other Name Inc"], "Closed", False, True, False)])) == "unexplained"  # a licence under another name explains nothing


def test_a_similar_name_nearby_is_a_missed_link_only_as_far_as_its_similarity_allows():
    assert explain(gap(places=[("Blue Heron", 30.0, False)])) == "link missed"
    assert explain(gap(places=[("Blue Heron", 180.0, False)])) == "link missed"  # the same name, far: Yelp points can sit at the street edge
    assert explain(gap(places=[("Red Fox Tavern", 180.0, True)])) == "unexplained"  # a different name that far away says nothing


def test_turnover_needs_a_different_name_close_by_and_a_business_licensed_after_the_snapshot():
    assert explain(gap(places=[("Red Fox Tavern", 15.0, True)])) == "turnover"
    assert explain(gap(places=[("Red Fox Tavern", 15.0, False)])) == "unexplained"  # a neighbour that was already there is not a replacement
    assert explain(gap(places=[("Red Fox Tavern", 40.0, True)])) == "unexplained"


def test_the_order_of_explanations_puts_the_census_first():
    both = gap(licences=[(["Blue Heron Cafe LLC"], "Active", False, True, False), (["Blue Heron Cafe LLC"], "Closed", False, True, False)], places=[("Red Fox", 10.0, True)])
    assert explain(both) == "census miss"


def test_bounds_run_from_pessimistic_to_generous_and_never_the_wrong_way_round():
    gaps = Counter({"census miss": 1, "other licence": 2, "licence ended": 10, "link missed": 5, "turnover": 5, "unexplained": 10})
    b = bounds(40, gaps)
    assert b["yelp_open_dining"] == 73 and b["linked"] == 40 and b["held"] == 45
    assert round(b["low"], 3) == round(40 / 73, 3)
    assert round(b["mid"], 3) == round(45 / 58, 3)  # 15 explained gaps out of the denominator
    assert round(b["high"], 3) == round(45 / 48, 3)
    assert b["low"] <= b["mid"] <= b["high"] <= 1.0
    assert bounds(0, Counter())["low"] == 0.0  # nothing to divide by


def test_the_two_source_estimate_is_at_least_what_either_list_holds():
    n, lo, hi = two_source_estimate(100, 90, 80)
    assert n >= 100 and lo <= n <= hi
    assert two_source_estimate(100, 90, 90)[0] < two_source_estimate(100, 90, 60)[0]  # the fewer in both, the more both lists miss


def test_the_report_goes_under_docs_private_which_git_ignores_and_names_no_one_but_what_it_is_given():
    root = Path(cy.__file__).resolve().parents[2]
    assert cy.REPORT == root / "docs" / "private" / "census-vs-yelp.md"
    assert "docs/private/" in (root / ".gitignore").read_text().splitlines()
    text = render([gap(places=[("Red Fox Tavern", 10.0, False)], reviews=40), gap(name="Old Mill Bakery", categories="Grocery")], 7, {"before": [5, 3], "after": [4, 1], "unknown": [2, 1]})
    assert "Blue Heron Cafe" in text and "unexplained" in text and "7" in text and text.startswith("# The census against Yelp (PRIVATE")
    assert "Old Mill Bakery" not in text  # a listing that is not dining is counted, not listed
