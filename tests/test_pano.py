import numpy as np
import pytest

from streetwalker.imagery import Image, pick_panorama
from streetwalker.pano import alignment, level_roll, perspective_view

W, H = 720, 360


def synthetic_pano():
    """Red encodes the column (so the longitude), green encodes the row (so the latitude)."""
    xs = np.linspace(0, 255, W)[None, :].repeat(H, 0)
    ys = np.linspace(0, 255, H)[:, None].repeat(W, 1)
    return np.stack([xs, ys, np.zeros_like(xs)], axis=-1).astype(np.uint8)


def centre(view):
    h, w = view.shape[:2]
    return view[h // 2, w // 2].astype(int)


def test_looking_along_the_panorama_heading_shows_its_centre_column():
    view = perspective_view(synthetic_pano(), pano_heading=40, bearing=40, out_w=200, out_h=150)
    r, g, _ = centre(view)
    assert r == pytest.approx(127.5, abs=3) and g == pytest.approx(127.5, abs=3)


def test_turning_right_samples_columns_to_the_right():
    # 90 degrees right of the centre is three quarters of the way across the panorama
    r, _, _ = centre(perspective_view(synthetic_pano(), pano_heading=0, bearing=90, out_w=200, out_h=150))
    assert r == pytest.approx(255 * 0.75, abs=3)
    r, _, _ = centre(perspective_view(synthetic_pano(), pano_heading=0, bearing=270, out_w=200, out_h=150))
    assert r == pytest.approx(255 * 0.25, abs=3)


def test_relative_bearing_is_what_matters_and_wraps_around_north():
    a = perspective_view(synthetic_pano(), pano_heading=350, bearing=10, out_w=100, out_h=80)
    b = perspective_view(synthetic_pano(), pano_heading=0, bearing=20, out_w=100, out_h=80)
    assert np.abs(a.astype(int) - b.astype(int)).max() <= 3


def test_positive_pitch_looks_up():
    up = centre(perspective_view(synthetic_pano(), 0, 0, pitch_deg=30, out_w=100, out_h=80))[1]
    level = centre(perspective_view(synthetic_pano(), 0, 0, pitch_deg=0, out_w=100, out_h=80))[1]
    down = centre(perspective_view(synthetic_pano(), 0, 0, pitch_deg=-30, out_w=100, out_h=80))[1]
    assert up < level < down  # green grows with the row, and the top of the panorama is row 0


def test_output_shape_and_dtype():
    v = perspective_view(synthetic_pano(), 0, 0, out_w=64, out_h=48)
    assert v.shape == (48, 64, 3) and v.dtype == np.uint8


def im(i, dy, pano=True, year=2026):
    return Image(i, -75.17, 39.95 + dy / 111_320, 0.0, pano, year)


def test_pick_panorama_distance_window_and_prefers_ideal_then_newer():
    fx, fy = -75.17, 39.95
    assert pick_panorama(fx, fy, [im("close", 2), im("far", 50), im("photo", 12, pano=False)]) is None
    best = pick_panorama(fx, fy, [im("a", 25), im("b", 12), im("c", 8)])
    assert best.image.id == "b" and best.bearing_deg == pytest.approx(180, abs=0.1)  # camera is north of the building
    assert pick_panorama(fx, fy, [im("old", 12, year=2018), im("new", 12, year=2026)]).image.id == "new"


def stripes_pano():
    """Vertical world lines every 10 degrees of longitude, plus a plain background."""
    arr = np.full((H, W, 3), 200, dtype=np.uint8)
    for lon in range(0, 360, 10):
        col = int(lon / 360 * W)
        arr[:, col : col + 2] = 20
    return arr


def test_roll_tilts_vertical_lines_and_the_levelling_search_prefers_upright():
    pano = stripes_pano()
    upright = alignment(perspective_view(pano, 0, 0, out_w=240, out_h=180))
    tilted = alignment(perspective_view(pano, 0, 0, out_w=240, out_h=180, roll_deg=20))
    assert upright > tilted + 0.1
    assert abs(level_roll(pano, 0, 0)) <= 3.0  # an already-upright scene needs no correction


def test_level_roll_returns_a_float_within_the_search_range():
    r = level_roll(stripes_pano(), 90, 100, search_deg=15, step_deg=5)
    assert isinstance(r, float) and -15 <= r <= 15


def bands_pano():
    """Bold horizontal bands (like a striped facade) every 10 degrees of latitude."""
    arr = np.full((H, W, 3), 200, dtype=np.uint8)
    for lat in range(0, 180, 10):
        row = int(lat / 180 * H)
        arr[row : row + 3, :] = 20
    return arr


def test_levelling_is_not_fooled_by_bold_horizontal_features():
    """A vertical-edges-only score rotates strong horizontals toward 45 degrees; the axis-alignment score must not."""
    pano = bands_pano()
    assert alignment(perspective_view(pano, 0, 0, out_w=240, out_h=180)) > alignment(
        perspective_view(pano, 0, 0, out_w=240, out_h=180, roll_deg=30)
    )
    assert abs(level_roll(pano, 0, 0)) <= 3.0


def test_parse_caption_variants():
    from streetwalker.vlm import parse_caption

    a = parse_caption("Street level: shop window or storefront.\nAwning or sign on that building: GIFT STORE")
    assert (a.street_level, a.sign) == ("shop window or storefront", "GIFT STORE")
    b = parse_caption("Street level: not visible\nAwning or sign on that building: none")
    assert (b.street_level, b.sign) == ("not visible", None)
    echoed = parse_caption("Street level: not visible\nAwning or sign on that building: the exact text on that building's own sign or awning, or none")
    assert echoed.sign is None  # the model repeated the instruction
    assert parse_caption("something unstructured").street_level == "unknown"
    assert parse_caption("Street level: entrance door with steps\nAwning or sign on that building: 'Nati's'").sign == "Nati's"
