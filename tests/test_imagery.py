import pytest

from streetwalker.imagery import Image, angle_diff, bearing_deg, distance_m, pick_image

LAT, LNG = 39.95, -75.17
M = 1 / 111_320  # degrees of latitude per metre


def at(dy_m=0.0, dx_m=0.0):
    """A point dy_m north and dx_m east of the origin."""
    import math

    return LNG + dx_m * M / math.cos(math.radians(LAT)), LAT + dy_m * M


def img(i, dy, dx, compass, pano=False, year=2019):
    lng, lat = at(dy, dx)
    return Image(i, lng, lat, compass, pano, year)


def test_bearing_cardinal_directions():
    assert bearing_deg(LAT, LNG, LAT + 0.001, LNG) == pytest.approx(0, abs=0.01)
    assert bearing_deg(LAT, LNG, LAT, LNG + 0.001) == pytest.approx(90, abs=0.01)
    assert bearing_deg(LAT, LNG, LAT - 0.001, LNG) == pytest.approx(180, abs=0.01)
    assert bearing_deg(LAT, LNG, LAT, LNG - 0.001) == pytest.approx(270, abs=0.01)


def test_angle_diff_wraps_around_north():
    assert angle_diff(350, 10) == 20
    assert angle_diff(10, 350) == 20
    assert angle_diff(0, 180) == 180
    assert angle_diff(90, 90) == 0


def test_distance_m():
    assert distance_m(LAT, LNG, LAT + 10 * M, LNG) == pytest.approx(10, abs=0.01)


def test_picks_the_camera_that_faces_the_building():
    fx, fy = at(15, 0)  # frontage 15 m north of the origin
    facing = img("facing", 0, 0, 0)  # at origin, looking north, straight at it
    away = img("away", 0, 0, 180)  # same spot, looking south
    side = img("side", 0, 0, 90)  # looking east
    pick = pick_image(fx, fy, [away, side, facing])
    assert pick.image.id == "facing" and pick.angle_deg == pytest.approx(0, abs=0.1)
    assert pick.dist_m == pytest.approx(15, abs=0.1)


def test_rejects_too_close_too_far_off_axis_pano_and_missing_heading():
    fx, fy = at(15, 0)
    assert pick_image(fx, fy, [img("close", 12, 0, 0)]) is None  # 3 m away
    assert pick_image(fx, fy, [img("far", -30, 0, 0)]) is None  # 45 m away
    assert pick_image(fx, fy, [img("offaxis", 0, 0, 60)]) is None  # building 60 degrees off centre
    assert pick_image(fx, fy, [img("pano", 0, 0, 0, pano=True)]) is None
    assert pick_image(fx, fy, [Image("nohead", *at(0, 0), None, False, 2019)]) is None
    assert pick_image(fx, fy, []) is None


def test_prefers_better_aligned_then_newer():
    fx, fy = at(15, 0)
    aligned = img("aligned", 0, 0, 0)
    a_bit_off = img("off", 0, 0, 25)
    assert pick_image(fx, fy, [a_bit_off, aligned]).image.id == "aligned"
    old, new = img("old", 0, 0, 0, year=2015), img("new", 0, 0, 0, year=2023)
    assert pick_image(fx, fy, [old, new]).image.id == "new"


def test_heading_across_north_still_matches():
    fx, fy = at(15, 0)
    assert pick_image(fx, fy, [img("wrap", 0, 0, 355)]).angle_deg == pytest.approx(5, abs=0.1)
