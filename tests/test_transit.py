from datetime import date

import pandas as pd
import pytest

from streetwalker.transit import Stop, StopTable, active_services, place_context, typical_weekday


def stop(sid, x, y, service, modes=("bus",), name=None):
    return Stop(sid, name or sid, x, y, frozenset(modes), service)


def test_typical_weekday_is_a_wednesday_inside_every_feed():
    # Saturday 3 Oct 2026; one feed ends Saturday 17 Oct, the other much later
    assert typical_weekday([date(2026, 9, 27)] * 2, [date(2027, 2, 20), date(2026, 10, 17)], date(2026, 10, 3)) == date(2026, 10, 7)
    # today is past the shared window: fall back to the last Wednesday inside it
    assert typical_weekday([date(2026, 9, 27)], [date(2026, 10, 17)], date(2026, 12, 1)) == date(2026, 10, 14)
    # a feed that has not started yet pushes the day to its first Wednesday
    assert typical_weekday([date(2026, 11, 2)], [date(2026, 12, 31)], date(2026, 10, 3)) == date(2026, 11, 4)
    with pytest.raises(ValueError):
        typical_weekday([date(2026, 10, 8)], [date(2026, 10, 12)], date(2026, 10, 9))  # Thu to Mon: no Wednesday


def test_active_services_applies_weekday_dates_and_exceptions():
    cal = pd.DataFrame({
        "service_id": ["wk", "sat", "old"], "monday": ["1", "0", "1"], "tuesday": ["1", "0", "1"], "wednesday": ["1", "0", "1"],
        "thursday": ["1", "0", "1"], "friday": ["1", "0", "1"], "saturday": ["0", "1", "0"], "sunday": ["0", "0", "0"],
        "start_date": ["20260927", "20260927", "20250101"], "end_date": ["20261219", "20261219", "20260101"],
    })
    wed = date(2026, 10, 7)
    assert active_services(cal, None, wed) == {"wk"}  # "old" has expired, "sat" is a Saturday service
    exc = pd.DataFrame({"service_id": ["wk", "special"], "date": ["20261007", "20261007"], "exception_type": ["2", "1"]})
    assert active_services(cal, exc, wed) == {"special"}  # removed, then added
    assert active_services(cal, exc, date(2026, 10, 14)) == {"wk"}  # the exception is for one date only


def test_context_counts_each_route_direction_once_using_the_busiest_stop():
    table = StopTable([
        stop("a", 0, 0, {("R1", 0): 100, ("R2", 0): 50}),
        stop("b", 100, 0, {("R1", 0): 60}),  # same route and direction, a block further on: not added again
        stop("c", 0, 50, {("R1", 1): 90}),  # opposite direction, other side of the street: counted
        stop("far", 1000, 0, {("R9", 0): 500}),
    ])
    c = place_context(table, 0, 0)
    assert c["stops_400m"] == 3
    assert c["routes_400m"] == ["R1", "R2"]
    assert c["weekday_trips_400m"] == 100 + 50 + 90
    assert (c["nearest_stop_name"], c["nearest_stop_m"]) == ("a", 0.0)


def test_nearest_rail_ignores_buses_and_has_a_distance_cap():
    table = StopTable([
        stop("bus", 10, 0, {("B", 0): 10}),
        stop("subway", 900, 0, {("L", 0): 200}, modes=("subway",), name="Snyder"),
    ])
    c = place_context(table, 0, 0)
    assert (c["nearest_rail_name"], c["nearest_rail_m"]) == ("Snyder", 900.0)
    assert c["modes_400m"] == ["bus"] and c["stops_400m"] == 1  # the subway stop is outside the walk radius
    assert place_context(StopTable([stop("subway", 2500, 0, {("L", 0): 1}, modes=("subway",))]), 0, 0)["nearest_rail_name"] is None


def test_empty_table_returns_nulls_not_errors():
    c = place_context(StopTable([]), 0, 0)
    assert c["nearest_stop_name"] is None and c["stops_400m"] == 0 and c["routes_400m"] == []
