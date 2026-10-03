import pytest
from shapely.geometry import LineString, box

from streetwalker.frontage import BuildingInfo, EdgeInfo, assign_all, name_keys, norm_street


def edge(coords, name=None, service=False):
    return EdgeInfo(LineString(coords), name_keys(name), service)


def bldg(x0, y0, x1, y1, addr=None):
    return BuildingInfo(box(x0, y0, x1, y1), addr)


# East-west street along y=0 running west to east, plus a north-south street along x=0.
EW = edge([(-100, 0), (100, 0)], "Walnut Street")
NS = edge([(0, -100), (0, 100)], "20th Street")


def test_side_is_left_of_direction_of_travel():
    north = bldg(20, 5, 30, 15)  # north of an eastbound street: left
    south = bldg(20, -15, 30, -5)  # south: right
    a, b = assign_all([north, south], [EW])
    assert (a.side, b.side) == (1, -1)


def test_reversed_edge_flips_side():
    rev = edge([(100, 0), (-100, 0)], "Walnut Street")
    (a,) = assign_all([bldg(20, 5, 30, 15)], [rev])
    assert a.side == -1


def test_along_distance_and_fraction():
    (f,) = assign_all([bldg(50, 5, 60, 15)], [EW])
    assert f.along_m == pytest.approx(155, abs=0.5)  # centroid x=55 -> 155 m from the west end
    assert f.frac == pytest.approx(0.775, abs=0.005)
    assert f.dist_m == pytest.approx(5)
    assert f.frontage_xy == pytest.approx((55, 5))  # middle of the facade facing the street


def test_corner_building_uses_address_over_nearest():
    corner = bldg(3, 2, 13, 12, addr="Walnut Street")  # 2 m from Walnut, 3 m from 20th: both agree
    (f,) = assign_all([corner], [EW, NS])
    assert f.method == "address" and f.edge_idx == 0
    corner2 = bldg(2, 3, 12, 13, addr="20th Street")  # 2 m from 20th, 3 m from Walnut: both agree
    (g,) = assign_all([corner2], [EW, NS])
    assert g.method == "address" and g.edge_idx == 1


def test_nearest_used_without_address_and_margin_flags_corner():
    corner = bldg(3, 2, 13, 12)
    (f,) = assign_all([corner], [EW, NS])
    assert f.method == "nearest" and f.edge_idx == 0  # 2 m beats 3 m
    assert f.margin_m == pytest.approx(1)  # a close call
    (far,) = assign_all([bldg(40, 20, 50, 30)], [EW, NS])
    assert far.margin_m > 10


def test_address_mismatch_marks_nearest_baseline_wrong():
    corner = bldg(2, 3, 12, 13, addr="Walnut Street")  # nearest is NS (2 m) but address says Walnut
    (f,) = assign_all([corner], [EW, NS])
    assert f.edge_idx == 0 and f.nearest_same is False


def test_service_road_is_deprioritised_when_no_address():
    alley = edge([(-100, 4), (100, 4)], None, service=True)
    house = bldg(20, 6, 30, 16)  # 2 m from the alley at y=4, 6 m from the street
    (f,) = assign_all([house], [alley, EW])
    assert f.method == "nearest_nonservice" and f.edge_idx == 1


def test_far_building_still_gets_a_segment():
    (f,) = assign_all([bldg(500, 500, 510, 510)], [EW])
    assert f.method == "nearest_far" and f.n_candidates == 1


def test_address_with_abbreviation_and_direction_variants():
    e = edge([(-100, 0), (100, 0)], "South 13th Street")
    (f,) = assign_all([bldg(20, 5, 30, 15, addr="13th St")], [e])
    assert f.method == "address"
    assert norm_street("E Passyunk Ave") == "east passyunk avenue"
    assert "passyunk avenue" in name_keys("East Passyunk Avenue")
    assert name_keys('["Main Street", "Route 1"]') >= {"main street"}


def test_rear_alley_does_not_make_a_corner():
    alley = edge([(-100, 12), (100, 12)], None, service=True)  # unnamed alley 2 m behind the house
    house = bldg(20, 3, 30, 10)  # 3 m from the street, 2 m from the alley
    (f,) = assign_all([house], [EW, alley])
    assert f.edge_idx == 0 and f.margin_m is None
