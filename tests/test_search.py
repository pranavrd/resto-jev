import pytest

from streetwalker.search import BadQuery, PlaceQuery, build


def test_no_filters_sorts_by_name_with_no_where_clause():
    sql, params = build(PlaceQuery())
    assert "WHERE" not in sql and "ORDER BY lower(p.name)" in sql
    assert params == {"limit": 50, "offset": 0}


def test_user_text_is_only_ever_a_bound_parameter():
    evil = "x'; DROP TABLE place; --"
    sql, params = build(PlaceQuery(q=evil, neighborhood=evil, area=evil, kinds=[evil], routes=[evil]))
    assert "DROP TABLE" not in sql
    assert evil.lower() in params.values() or evil in params.values() or any(evil.lower() in str(v) for v in params.values())


def test_like_wildcards_in_the_query_are_escaped():
    _, params = build(PlaceQuery(q="50%_off"))
    assert params["like"] == "%50\\%\\_off%"


def test_text_search_sorts_by_relevance_and_scores():
    sql, params = build(PlaceQuery(q="  Pizza "))
    assert params["q"] == "pizza" and "similarity(" in sql and "ORDER BY score DESC" in sql


def test_distance_filter_and_sort_need_a_point():
    sql, params = build(PlaceQuery(lat=39.95, lng=-75.17, radius_m=300, sort="distance"))
    assert "<= %(radius_m)s" in sql and params["radius_m"] == 300 and "ORDER BY distance_m" in sql
    for bad in (PlaceQuery(lat=39.95), PlaceQuery(radius_m=100), PlaceQuery(sort="distance"), PlaceQuery(sort="relevance"), PlaceQuery(sort="nope")):
        with pytest.raises(BadQuery):
            build(bad)


def test_min_confidence_includes_the_levels_above_it():
    _, params = build(PlaceQuery(min_confidence="medium"))
    assert params["confs"] == ["medium", "high"]
    with pytest.raises(BadQuery):
        build(PlaceQuery(min_confidence="certain"))


def test_source_filter_is_exact():
    _, params = build(PlaceQuery(source="osm"))
    assert params["sources"] == ["osm"] and params["n_sources"] == 1
    _, params = build(PlaceQuery(source="both"))
    assert params["sources"] == ["osm", "licence"] and params["n_sources"] == 2
    with pytest.raises(BadQuery):
        build(PlaceQuery(source="yelp"))


def test_filters_combine_with_and():
    sql, _ = build(PlaceQuery(area="rittenhouse", kinds=["bar"], max_rail_m=400, min_trips=100, routes=["12"]))
    assert sql.count("\n      AND ") == 4
